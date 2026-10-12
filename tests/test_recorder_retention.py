"""Guard the audited Recorder boundaries without a database or production I/O.

The fixtures describe separate battery packs, canonical power streams, and
historical consumers. Runtime-only checks use HA's real filter/service schema
when this suite runs in the pinned HA image; the other checks also run in CI.
"""

from copy import deepcopy
from fnmatch import fnmatchcase
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
with patch.object(sys, "path", [str(ROOT / "tools"), *sys.path]):
    from ha_yaml import read, resolve

try:
    from homeassistant.helpers.entityfilter import INCLUDE_EXCLUDE_FILTER_SCHEMA
    from homeassistant.components.recorder.services import SERVICE_PURGE_ENTITIES_SCHEMA
except ImportError:
    INCLUDE_EXCLUDE_FILTER_SCHEMA = None
    SERVICE_PURGE_ENTITIES_SCHEMA = None


# Two independent MQTT device registrations, each containing four four-cell BMSs.
# The _2 registration must not be mistaken for duplicate history and discarded.
CELL_ENTITIES = {
    f"sensor.jbd_chain2_monitor_voltage_cell{cell}_bms{bms}{suffix}"
    for cell in range(1, 5)
    for bms in range(1, 5)
    for suffix in ("", "_2")
}
BATTERY_OVERRIDES = {
    f"sensor.jbd_battery_chain_{chain}_{metric}"
    for chain in (1, 2)
    for metric in (
        "minimum_cell_voltage", "maximum_cell_voltage", "low_voltage",
        "high_voltage", "low_cell_voltage", "high_cell_voltage",
    )
}
EMPORIA_CHANNELS = (
    "balance", "family_room", "fridge", "garage", "hallway_and_pressure_cooker",
    "home", "kitchen_fridge_side", "kitchen_stove_teapot_area",
    "living_and_dining_and_bath2", "microwave", "office_and_bedrooms",
    "solar_shed_bedrooms_on_1st_light_bedroom_2_3_tv_samsung_switch_ap_range_hood",
    "totalusage",
)
HEATER_DIAGNOSTICS = {
    f"sensor.heater_{heater}_energy_{metric}"
    for heater in ("one", "two")
    for metric in ("apparentpower", "current", "factor", "reactivepower")
}
TASMOTA_SOLAR_DEVICES = (120, 121)
HISTORICAL_INPUTS = {
    "binary_sensor.dishwasher_running",  # Today's history_stats runtime.
    "sensor.total_power_consuming", "sensor.ac_loads",  # AC + DC != AC alone.
    "sensor.ac_in_power", "sensor.ac_in_consumption",  # Power != integral kWh.
    "sensor.current_solar_production", "sensor.solar_total_power",
    "sensor.pv1_kwh", "sensor.battery_consumption", "sensor.battery_load",
    "sensor.sensor_total_battery_in_integral",
    "sensor.sensor_total_battery_out_integral",
    "sensor.corrected_battery_soc", "sensor.battery_percent", "sensor.battery_w",
    "sensor.water_level_2_water_level", "sensor.water_speed",
    "climate.thermostat_2",  # Existing five-day raw-history chart.
    # Meter totals used by Energy must survive even if instantaneous power
    # aliases or diagnostics are excluded.
    "sensor.home_123_1d", "sensor.home_balance_1d", "sensor.bath_1_12_1d",
    "sensor.kitchen_fridge_5_1d", "sensor.kitchen_tea_9_1d",
    "sensor.microwave_8_1d", "sensor.office_and_bedrooms_14_1d",
    *(f"sensor.home_{channel}_1d" for channel in (1, 2, 3, 6, 7, 10, 11, 13, 15, 16)),
    *(
        f"sensor.heater_{heater}_energy_{metric}"
        for heater in ("one", "two")
        for metric in ("power", "total", "today", "yesterday")
    ),
    *(
        f"sensor.jbd_battery_chain_{chain}_{metric}"
        for chain in (1, 2)
        for metric in (
            "charge", "cell_voltage_deviation", "temperature", "cell_imbalance",
            "internal_failure", "high_charge_current", "high_discharge_current",
        )
    ),
}


def policy_decision(policy, entity_id):
    """Evaluate only the exclusion policy plus exact exceptions used here.

    The shape test forbids include domains/globs, which would select a different
    HA precedence rule. A separate optional test compares these boundaries with
    HA's actual filter, rather than claiming this small model tests HA itself.
    """
    if entity_id in policy.get("include", {}).get("entities", []):
        return True
    excluded = policy.get("exclude", {})
    return not (
        entity_id in excluded.get("entities", [])
        or entity_id.split(".", 1)[0] in excluded.get("domains", [])
        or any(fnmatchcase(entity_id, glob) for glob in excluded.get("entity_globs", []))
    )


def boundary_cases():
    kept = CELL_ENTITIES | BATTERY_OVERRIDES | HISTORICAL_INPUTS | {
        f"sensor.{channel}_power_1s_power" for channel in EMPORIA_CHANNELS
    } | {f"sensor.solar_tasmota_tasmota_{device}_power_total" for device in TASMOTA_SOLAR_DEVICES}
    excluded = HEATER_DIAGNOSTICS | {
        f"sensor.{channel}_power_1s_power_on_l1" for channel in EMPORIA_CHANNELS
    } | {f"sensor.solar_tasmota_tasmota_{device}_power_l1" for device in TASMOTA_SOLAR_DEVICES}
    return dict.fromkeys(kept, True) | dict.fromkeys(excluded, False) | {
        # Adding exact includes must not silently turn recording into an allowlist.
        "sensor.future_household_measurement": True,
        "sensor.jbd_chain2_monitor_voltage_cell5_bms5": True,
        # Existing exclusions must remain effective outside the exact exceptions.
        "sensor.unrelated_voltage": False,
        "sensor.weather_future": False,
        "camera.future_camera": False,
        "media_player.future_player": False,
        # Module catalogs/events are live diagnostics, not long-term history.
        **{f"sensor.ruview_node{node}_server_modules": False for node in (1, 3, 10, 255)},
        **{f"sensor.home_floorplan_ruview_node{node}_modules": False for node in (1, 3, 10, 255)},
        "sensor.ruview_assumed_zone_activity": False,
        "sensor.home_floorplan_assumed_zone_activity": False,
        # The exact diagnostic exclusions must not become a history-wide glob.
        "sensor.future_assumed_zone_activity": True,
        "sensor.home_floorplan_assumed_zone_activity_temperature": True,
        # Do not drop the existing room evidence or underlying sensors.
        "binary_sensor.ruview_node1_presence": True,
        "binary_sensor.ruview_node2_motion": True,
        "binary_sensor.ruview_node3_fall": True,
        "sensor.ruview_node1_classification": True,
        "sensor.home_floorplan_ruview_node1_activity": True,
        "sensor.home_floorplan_upper_k_activity": True,
        "sensor.unrelated_server_modules": True,
    }


class RecorderPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = read(ROOT / "config/integrations/recorder.yaml")

    def test_global_history_and_existing_purge_policy_are_preserved(self):
        self.assertEqual(self.policy["purge_keep_days"], 28)
        self.assertNotEqual(self.policy.get("auto_purge"), False)
        self.assertIs(self.policy["auto_repack"], False)
        self.assertNotIn("purge_interval", self.policy)

    def test_exceptions_are_exact_battery_extrema_and_faults(self):
        included = self.policy["include"]
        self.assertEqual(set(included), {"entities"})
        self.assertEqual(set(included["entities"]), BATTERY_OVERRIDES)
        self.assertEqual(len(included["entities"]), len(BATTERY_OVERRIDES))
        # These exclusions are what make exact exceptions safe to add without
        # changing the default for all other entities into an include-only list.
        self.assertTrue(self.policy["exclude"]["domains"])
        self.assertIn("sensor.*_voltage", self.policy["exclude"]["entity_globs"])

    def test_filter_preserves_canonical_energy_safety_and_live_cell_statistics(self):
        for entity_id, expected in boundary_cases().items():
            with self.subTest(entity=entity_id):
                self.assertEqual(policy_decision(self.policy, entity_id), expected)

    def test_diagnostic_and_alias_exclusions_do_not_use_broad_globs(self):
        reviewed_exclusions = HEATER_DIAGNOSTICS | {
            f"sensor.{channel}_power_1s_power_on_l1" for channel in EMPORIA_CHANNELS
        }
        exact = self.policy["exclude"]["entities"]
        self.assertTrue(reviewed_exclusions <= set(exact))
        self.assertFalse(CELL_ENTITIES & set(exact))
        for glob in self.policy["exclude"]["entity_globs"]:
            with self.subTest(glob=glob):
                self.assertFalse(any(fnmatchcase(e, glob) for e in CELL_ENTITIES))
                self.assertFalse(any(fnmatchcase(e, glob) for e in reviewed_exclusions))

    @unittest.skipUnless(INCLUDE_EXCLUDE_FILTER_SCHEMA, "Home Assistant runtime is not installed")
    def test_actual_home_assistant_filter_matches_protected_boundaries(self):
        actual = INCLUDE_EXCLUDE_FILTER_SCHEMA({
            name: deepcopy(self.policy[name]) for name in ("include", "exclude")
        })
        for entity_id, expected in boundary_cases().items():
            with self.subTest(entity=entity_id):
                self.assertEqual(actual(entity_id), expected)


class CellRetentionAutomationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = read(ROOT / "config/packages/recorder_retention.yaml")
        rules = cls.package["automation"]
        if len(rules) != 1:
            raise AssertionError("The retention package must contain one reviewed automation")
        cls.rule = rules[0]

    def test_package_is_loaded_without_replacing_the_automation_library(self):
        resolved = resolve(ROOT / "config/configuration.yaml", permit_missing_components=True)
        self.assertEqual(resolved["homeassistant"]["packages"]["recorder_retention"], self.package)
        self.assertEqual(resolved["recorder"]["purge_keep_days"], 28)
        self.assertEqual(set(self.package), {"automation"})

    def test_only_daily_time_trigger_and_stable_identity(self):
        self.assertEqual(self.rule["id"], "ha_homelab_recorder_jbd_cell_retention")
        self.assertEqual(self.rule["triggers"], [{"trigger": "time", "at": "07:30:00"}])
        self.assertEqual(self.rule["mode"], "single")
        self.assertNotIn("trigger", self.rule)  # No parallel legacy/startup trigger.

    def test_backup_gate_fails_closed_for_busy_or_unknown_state(self):
        # A positive state condition fails on missing/unknown/unavailable too;
        # an "is not busy" template would allow those states through.
        self.assertEqual(self.rule["conditions"], [{
            "condition": "state", "entity_id": "sensor.backup_backup_manager_state", "state": "idle",
        }])

    def test_purge_cannot_expand_to_domains_globs_repack_or_all_history(self):
        actions = self.rule["actions"]
        self.assertEqual(len(actions), 1)
        action = actions[0]
        self.assertEqual(set(action), {"action", "data"})
        self.assertEqual(action["action"], "recorder.purge_entities")
        data = action["data"]
        # In particular, keep_days must never disappear: this service defaults
        # to zero rather than the recorder's global history retention.
        self.assertEqual(set(data), {"entity_id", "keep_days"})
        self.assertEqual(data["keep_days"], 7)
        self.assertIsInstance(data["entity_id"], list)
        self.assertEqual(set(data["entity_id"]), CELL_ENTITIES)
        self.assertEqual(len(data["entity_id"]), 32)
        self.assertTrue(set(data["entity_id"]).isdisjoint(BATTERY_OVERRIDES | HISTORICAL_INPUTS))

    @unittest.skipUnless(SERVICE_PURGE_ENTITIES_SCHEMA, "Home Assistant runtime is not installed")
    def test_actual_home_assistant_purge_schema_accepts_only_reviewed_scope(self):
        data = SERVICE_PURGE_ENTITIES_SCHEMA(deepcopy(self.rule["actions"][0]["data"]))
        self.assertEqual(data["keep_days"], 7)
        self.assertEqual(set(data["entity_id"]), CELL_ENTITIES)
        self.assertFalse(data.get("domains"))
        self.assertFalse(data.get("entity_globs"))


if __name__ == "__main__":
    unittest.main()
