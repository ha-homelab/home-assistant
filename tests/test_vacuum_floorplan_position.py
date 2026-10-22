"""Exercise the read-only position feed in isolated HA; never contact a robot."""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import yaml

try:
    from homeassistant import loader
    from homeassistant.bootstrap import async_load_base_functionality
    from homeassistant.components.template.config import async_validate_config
    from homeassistant.components.sensor import SensorExtraStoredData
    from homeassistant.config_entries import ConfigEntries
    from homeassistant.core import HomeAssistant, State, SupportsResponse
    from homeassistant.exceptions import HomeAssistantError
    from homeassistant.helpers.template import Template
    from homeassistant.helpers.template.extensions.config_entries import ConfigEntryExtension
    from homeassistant.helpers.entity_component import DATA_INSTANCES
    from homeassistant.setup import async_setup_component
except ImportError:
    if os.environ.get("REQUIRE_HA_RUNTIME") == "1":
        raise
    HA_AVAILABLE = False
else:
    HA_AVAILABLE = True

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "config/packages/vacuum_floorplan_position.yaml"
ROBOT = "vacuum.roborock_q_revo"
SELECTOR = "select.roborock_q_revo_selected_map"
SENSOR = "sensor.roborock_q_revo_floorplan_position"


class PositionPackageStructureTest(unittest.TestCase):
    def test_only_read_services_and_explicit_frequency_are_configured(self):
        package = yaml.safe_load(PACKAGE.read_text())
        block = package["template"][0]
        calls = block["actions"][1]["then"]
        self.assertEqual([step["action"] for step in calls],
                         ["roborock.get_maps", "roborock.get_vacuum_current_position", "roborock.get_maps"])
        self.assertTrue(all(step["continue_on_error"] for step in calls))
        self.assertEqual(block["triggers"][1], {"trigger": "time_pattern", "seconds": "/15", "id": "tick"})
        sensor = block["sensor"][0]
        self.assertEqual(sensor["default_entity_id"], SENSOR)
        self.assertTrue(sensor["unique_id"])
        self.assertEqual(sensor["attributes"]["observed_at"], "{{ none }}")
        self.assertNotIn("get('observed_at')", json.dumps(package))


@unittest.skipUnless(HA_AVAILABLE, "Home Assistant runtime is not installed")
class VacuumFloorplanPositionTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.entry_state = "loaded"
        self.patches = [
            patch.object(ConfigEntryExtension, "config_entry_id", lambda extension, entity: "test-entry"),
            patch.object(ConfigEntryExtension, "config_entry_attr", lambda extension, entry, attr:
                         {"domain": "roborock", "state": self.entry_state}.get(attr)),
        ]
        for patcher in self.patches:
            patcher.start()
        self.temp = tempfile.TemporaryDirectory(prefix="ha-position-test-")
        self.hass = HomeAssistant(self.temp.name)
        loader.async_setup(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self.hass.config.skip_pip = True
        self.assertTrue(await async_load_base_functionality(self.hass))
        self.package = yaml.safe_load(PACKAGE.read_text())
        await async_validate_config(self.hass, self.package)
        self.calls = []
        self.position = {ROBOT: {"x": 12000, "y": 23000}}
        self.maps = {ROBOT: {"maps": [{"flag": 4, "name": "Example map", "rooms": {}}]}}
        self.after_maps = None
        self.position_error = False
        self.position_hook = None
        self.map_error_at = None
        self.map_calls = 0
        self.position_gate = asyncio.Event()
        self.position_gate.set()
        self.position_entered = asyncio.Event()
        self.hass.states.async_set(ROBOT, "docked")
        self.hass.states.async_set(SELECTOR, "Example map")

        async def get_maps(call):
            self.calls.append("get_maps")
            self.map_calls += 1
            if self.map_error_at == self.map_calls:
                raise HomeAssistantError("Synthetic cached-map error")
            return deepcopy(self.after_maps if self.map_calls % 2 == 0 and self.after_maps is not None else self.maps)

        async def get_position(call):
            self.calls.append("get_vacuum_current_position")
            self.position_entered.set()
            await self.position_gate.wait()
            if self.position_hook:
                self.position_hook()
            if self.position_error:
                raise HomeAssistantError("Synthetic read-only RPC error")
            return deepcopy(self.position)

        self.hass.services.async_register("roborock", "get_maps", get_maps, supports_response=SupportsResponse.ONLY)
        self.hass.services.async_register("roborock", "get_vacuum_current_position", get_position,
                                          supports_response=SupportsResponse.ONLY)
        # The production schema above includes the real time/state triggers.
        # Drive the same actions/templates by an isolated event to avoid sleeps
        # and unrelated wall-clock ticks during failure/race scenarios.
        test_config = deepcopy(self.package)
        test_config["template"][0]["triggers"] = [
            {"trigger": "event", "event_type": "test_position_poll", "id": "test"}]
        self.assertTrue(await async_setup_component(self.hass, "template", test_config))
        await self.hass.async_start()
        await self.hass.async_block_till_done()

    async def asyncTearDown(self):
        self.position_gate.set()
        await self.hass.async_block_till_done()
        await self.hass.async_stop(force=True)
        for patcher in reversed(self.patches):
            patcher.stop()
        self.temp.cleanup()

    async def poll(self):
        self.hass.bus.async_fire("test_position_poll")
        await self.hass.async_block_till_done()
        result = self.hass.states.get(SENSOR)
        self.assertIsNotNone(result)
        return result

    async def test_success_has_verified_map_identity_but_no_invented_observation_time(self):
        result = await self.poll()
        self.assertEqual(result.state, "reported")
        self.assertEqual(result.attributes["x"], 12000)
        self.assertEqual(result.attributes["y"], 23000)
        self.assertEqual(result.attributes["map_id"], 4)
        self.assertEqual(result.attributes["selected_map"], "Example map")
        self.assertIsNone(result.attributes["observed_at"])
        self.assertEqual(result.attributes["timestamp_quality"], "not_provided")
        self.assertEqual(result.attributes["source_entity"], ROBOT)
        self.assertEqual(result.attributes["coordinate_system"], "roborock_map")
        self.assertEqual(result.attributes["units"], "mm")
        self.assertIsNotNone(datetime.fromisoformat(result.attributes["retrieved_at"]).tzinfo)
        first = result.attributes["retrieved_at"]
        later = datetime.now(timezone.utc) + timedelta(minutes=5)
        with patch("homeassistant.util.dt.utcnow", return_value=later):
            result = await self.poll()
        self.assertNotEqual(result.attributes["retrieved_at"], first)
        self.assertIsNone(result.attributes["observed_at"])

    async def test_rpc_failure_keeps_last_known_coordinates_and_association(self):
        before = await self.poll()
        self.position_error = True
        result = await self.poll()
        self.assertEqual(result.state, "unavailable")
        for key in ("x", "y", "map_id", "selected_map", "retrieved_at", "observed_at"):
            self.assertEqual(result.attributes[key], before.attributes[key])
        self.position_error = False
        self.position[ROBOT]["x"] = 13000
        self.assertEqual((await self.poll()).attributes["x"], 13000)

    async def test_unknown_source_or_unloaded_integration_avoids_rpc_and_keeps_last_known(self):
        before = await self.poll()
        for entity in (ROBOT, SELECTOR):
            prior = self.hass.states.get(entity).state
            self.hass.states.async_set(entity, "unavailable")
            self.calls.clear()
            result = await self.poll()
            self.assertEqual(result.state, "unavailable")
            self.assertEqual(result.attributes["retrieved_at"], before.attributes["retrieved_at"])
            self.assertEqual(self.calls, [])
            self.hass.states.async_set(entity, prior)
        self.hass.services.async_remove("roborock", "get_vacuum_current_position")
        self.entry_state = "not_loaded"
        self.calls.clear()
        self.assertEqual((await self.poll()).state, "unavailable")
        self.assertEqual(self.calls, [])

    async def test_malformed_position_never_overwrites_last_known(self):
        before = await self.poll()
        for response in ({}, [], {ROBOT: {}}, {ROBOT: {"x": "12000", "y": 23000}},
                         {ROBOT: {"x": True, "y": 23000}}, {ROBOT: {"x": float("nan"), "y": 23000}},
                         {ROBOT: {"x": float("inf"), "y": 23000}}, {ROBOT: {"x": 1e8, "y": 23000}},
                         {ROBOT: {"x": 12000, "y": 23000, "unexpected": True}},
                         {ROBOT: {"x": 12000, "y": 23000}, "vacuum.other": {"x": 1, "y": 2}}):
            with self.subTest(response=response):
                self.position = response
                result = await self.poll()
                self.assertEqual(result.state, "unavailable")
                self.assertEqual(result.attributes["x"], before.attributes["x"])
                self.assertEqual(result.attributes["retrieved_at"], before.attributes["retrieved_at"])

    async def test_missing_duplicate_or_ambiguous_map_identity_is_unavailable(self):
        before = await self.poll()
        for entries in ([], [{"flag": True, "name": "Example map"}],
                        [{"flag": 4, "name": "Other map"}],
                        [{"flag": 4, "name": "Example map"}, {"flag": 5, "name": "Example map"}],
                        [{"flag": 4, "name": "Example map"}, {"flag": 4, "name": "Other map"}],
                        [{"flag": "4", "name": "Example map"}], [{"flag": 4, "name": []}]):
            with self.subTest(entries=entries):
                self.maps = {ROBOT: {"maps": entries}}
                result = await self.poll()
                self.assertEqual(result.state, "unavailable")
                self.assertEqual(result.attributes["map_id"], before.attributes["map_id"])

    async def test_default_map_label_and_changed_catalog_are_checked(self):
        self.maps = {ROBOT: {"maps": [{"flag": 9, "name": "", "rooms": {}}]}}
        self.hass.states.async_set(SELECTOR, "Map 9")
        result = await self.poll()
        self.assertEqual(result.state, "reported")
        self.assertEqual(result.attributes["map_id"], 9)
        self.after_maps = {ROBOT: {"maps": [{"flag": 10, "name": "Map 9", "rooms": {}}]}}
        result = await self.poll()
        self.assertEqual(result.state, "unavailable")
        self.assertEqual(result.attributes["map_id"], 9)

    async def test_selector_switch_and_switch_back_during_rpc_are_rejected(self):
        before = await self.poll()
        def change_and_restore():
            self.hass.states.async_set(SELECTOR, "Other map")
            self.hass.states.async_set(SELECTOR, "Example map")
        self.position_hook = change_and_restore
        self.position[ROBOT]["x"] = 50000
        result = await self.poll()
        self.assertEqual(result.state, "unavailable")
        self.assertEqual(result.attributes["x"], before.attributes["x"])
        self.assertEqual(result.attributes["retrieved_at"], before.attributes["retrieved_at"])

    async def test_first_failure_has_no_fake_position_or_timestamp(self):
        self.position_error = True
        result = await self.poll()
        self.assertEqual(result.state, "unavailable")
        for key in ("x", "y", "map_id", "selected_map", "retrieved_at", "observed_at"):
            self.assertIsNone(result.attributes.get(key))

    async def test_zero_coordinates_are_valid_and_cached_catalog_failure_is_not(self):
        self.position = {ROBOT: {"x": 0, "y": 0}}
        before = await self.poll()
        self.assertEqual(before.state, "reported")
        self.assertEqual((before.attributes["x"], before.attributes["y"]), (0, 0))
        self.map_error_at = self.map_calls + 2
        result = await self.poll()
        self.assertEqual(result.state, "unavailable")
        self.assertEqual(result.attributes["retrieved_at"], before.attributes["retrieved_at"])

    async def test_restored_success_is_kept_when_first_poll_fails(self):
        entity = self.hass.data[DATA_INSTANCES]["sensor"].get_entity(SENSOR)
        attributes = {"x": 12000, "y": 23000, "map_id": 4, "selected_map": "Example map",
                      "retrieved_at": "2026-01-01T00:00:00+00:00", "observed_at": None}
        restored = State(SENSOR, "reported", attributes)
        extra = SensorExtraStoredData("reported", None)
        with patch.object(entity, "async_get_last_state", AsyncMock(return_value=restored)), \
             patch.object(entity, "async_get_last_extra_data", AsyncMock(return_value=extra)):
            await entity.async_restore_last_state()
        entity.async_write_ha_state()
        self.position_error = True
        result = await self.poll()
        self.assertEqual(result.state, "unavailable")
        for key, value in attributes.items():
            self.assertEqual(result.attributes[key], value)

    async def test_overlapping_poll_is_conservative_and_does_not_start_a_second_rpc(self):
        before = await self.poll()
        self.calls.clear()
        self.position_gate.clear()
        self.position_entered.clear()
        self.hass.bus.async_fire("test_position_poll")
        await asyncio.wait_for(self.position_entered.wait(), timeout=1)
        self.hass.bus.async_fire("test_position_poll")
        for _ in range(10):
            await asyncio.sleep(0)
            if self.hass.states.get(SENSOR).state == "unavailable":
                break
        intermediate = self.hass.states.get(SENSOR)
        self.assertEqual(intermediate.state, "unavailable")
        self.assertEqual(intermediate.attributes["retrieved_at"], before.attributes["retrieved_at"])
        self.assertEqual(self.calls.count("get_vacuum_current_position"), 1)
        self.position_gate.set()
        await self.hass.async_block_till_done()
        self.assertEqual(self.hass.states.get(SENSOR).state, "reported")

    async def test_poll_frequency_is_15_seconds_active_and_60_seconds_idle(self):
        condition = self.package["template"][0]["conditions"][0]["value_template"]
        template = Template(condition, self.hass)
        for state in ("cleaning", "returning", "docked", "idle", "unavailable"):
            self.hass.states.async_set(ROBOT, state)
            for second in (0, 15, 30, 45):
                trigger = {"id": "tick", "now": datetime(2026, 1, 1, 0, 0, second, tzinfo=timezone.utc)}
                self.assertEqual(template.async_render({"trigger": trigger}),
                                 state in ("cleaning", "returning") or second == 0)
        self.assertTrue(template.async_render({"trigger": {"id": "source_change"}}))


if __name__ == "__main__":
    unittest.main()
