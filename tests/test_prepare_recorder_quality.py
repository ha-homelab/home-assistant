"""Protect actual Energy identities and immutable coverage without HA access."""

from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


TOOLS = Path(__file__).resolve().parents[1] / "tools"
SPEC = importlib.util.spec_from_file_location("prepare_recorder_quality", TOOLS / "prepare_recorder_quality.py")
prepare_module = importlib.util.module_from_spec(SPEC)
with patch.object(sys, "path", [str(TOOLS), *sys.path]):
    SPEC.loader.exec_module(prepare_module)

CELL = "sensor.battery_cell"
WATER = "sensor.water_main_total"


def base_policy():
    return {
        "schema_version": 1,
        "entities": {
            CELL: {"runtime_kind": "numeric", "max_reported_age_seconds": 120,
                   "raw_required": True, "statistics": "measurement"},
        },
    }


def runtime_export():
    return {
        "energy": {
            "energy_sources": [{"type": "water", "stat_energy_from": WATER}],
            "device_consumption": [],
        },
        "states": [{"entity_id": WATER, "state": "12.5",
                    "attributes": {"state_class": "total_increasing"}}],
    }


class PrepareRecorderQualityTests(unittest.TestCase):
    def test_actual_energy_id_is_added_without_replacing_base_coverage(self):
        base, runtime = base_policy(), runtime_export()
        original_base, original_runtime = deepcopy(base), deepcopy(runtime)
        result = prepare_module.prepare(base, runtime)

        # The base cell is absent from runtime, but must remain a required check.
        self.assertEqual(set(result["entities"]), {CELL, WATER})
        self.assertEqual(result["entities"][CELL], original_base["entities"][CELL])
        self.assertEqual(result["entities"][WATER], {
            "runtime_kind": "numeric", "max_reported_age_seconds": None,
            "raw_required": True, "statistics": "total",
        })
        self.assertEqual(base, original_base)
        self.assertEqual(runtime, original_runtime)

    def test_prices_and_cost_statistics_are_not_counter_sources(self):
        runtime = runtime_export()
        runtime["energy"]["energy_sources"][0].update({
            "stat_cost": "external_provider:water_cost",
            "entity_energy_price": "sensor.water_price",
            "entity_energy_price_export": "sensor.export_price",
            "stat_compensation": "sensor.grid_compensation",
        })
        result = prepare_module.prepare(base_policy(), runtime)
        self.assertEqual(set(result["entities"]), {CELL, WATER})

    def test_device_and_battery_counters_are_required_too(self):
        runtime = runtime_export()
        runtime["energy"]["energy_sources"].append({
            "type": "battery", "stat_energy_from": "sensor.battery_out",
            "stat_energy_to": "sensor.battery_in",
        })
        runtime["energy"]["device_consumption"].append({"stat_consumption": "sensor.fridge_energy"})
        runtime["energy"]["device_consumption_water"] = [{"stat_consumption": "sensor.garden_water"}]
        additions = {"sensor.battery_out", "sensor.battery_in", "sensor.fridge_energy", "sensor.garden_water"}
        runtime["states"].extend({"entity_id": entity, "attributes": {"state_class": "total"}}
                                 for entity in additions)
        result = prepare_module.prepare(base_policy(), runtime)
        self.assertEqual(set(result["entities"]), {CELL, WATER, *additions})

    def test_missing_configured_energy_entity_is_not_silently_dropped(self):
        runtime = runtime_export()
        runtime["states"] = []
        with self.assertRaisesRegex(ValueError, "absent from runtime"):
            prepare_module.prepare(base_policy(), runtime)

    def test_missing_or_non_cumulative_state_class_fails(self):
        for attributes in ({}, {"state_class": None}, {"state_class": "measurement"}):
            with self.subTest(attributes=attributes):
                runtime = runtime_export()
                runtime["states"][0]["attributes"] = attributes
                with self.assertRaisesRegex(ValueError, "cumulative state class"):
                    prepare_module.prepare(base_policy(), runtime)

    def test_external_statistics_need_an_explicit_policy(self):
        runtime = runtime_export()
        runtime["energy"]["energy_sources"][0]["stat_energy_from"] = "utility_provider:water_total"
        with self.assertRaisesRegex(ValueError, "explicit policy"):
            prepare_module.prepare(base_policy(), runtime)

    def test_duplicate_runtime_ids_fail_even_when_values_match(self):
        runtime = runtime_export()
        runtime["states"].append(deepcopy(runtime["states"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate runtime entity"):
            prepare_module.prepare(base_policy(), runtime)

    def test_runtime_cannot_weaken_a_conflicting_base_rule(self):
        base = base_policy()
        base["entities"][WATER] = deepcopy(base["entities"][CELL])
        with self.assertRaisesRegex(ValueError, "immutable base policy"):
            prepare_module.prepare(base, runtime_export())

    def test_incomplete_or_empty_energy_preferences_fail(self):
        for energy in ({}, {"energy_sources": []},
                       {"energy_sources": [], "device_consumption": []}):
            with self.subTest(energy=energy):
                runtime = runtime_export()
                runtime["energy"] = energy
                with self.assertRaises(ValueError):
                    prepare_module.prepare(base_policy(), runtime)

    def test_exact_boundary_scope_and_epoch_are_preserved(self):
        cutoff = "2026-10-02T07:30:00-07:00"
        result = prepare_module.prepare(
            base_policy(), runtime_export(), retention_entities=[CELL], retention_cutoff=cutoff,
            exclusion_entities=["sensor.redundant_alias"], exclusion_cutoff=cutoff,
        )
        expected = datetime(2026, 10, 2, 14, 30, tzinfo=timezone.utc).timestamp()
        self.assertEqual(result["retention"], {"entity_ids": [CELL], "cutoff_ts": expected})
        self.assertEqual(result["exclusions"]["cutoff_ts"], expected)

    def test_duplicate_boundary_ids_fail(self):
        with self.assertRaisesRegex(ValueError, "boundary check scope"):
            prepare_module.prepare(base_policy(), runtime_export(),
                                   retention_entities=[CELL, CELL], retention_cutoff=1_790_950_000)


if __name__ == "__main__":
    unittest.main()
