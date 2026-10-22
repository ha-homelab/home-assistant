"""Passive telemetry must preserve provenance and never invent usable maps."""
from copy import deepcopy
import importlib.util
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "config/custom_components/roomba_insights"
spec = importlib.util.spec_from_file_location("roomba_insights_telemetry", COMPONENT / "telemetry.py")
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)

P = {"point": {"x": 0, "y": -42}, "theta": 180}
COMMAND = {"command": "start", "pmap_id": "synthetic-map", "user_pmapv_id": "test-v1",
           "regions": [{"region_id": "1", "type": "rid", "region_name": "Test room"}]}


class TelemetryTest(unittest.TestCase):
    def setUp(self):
        self.value = model.Telemetry()
        self.reported = {"pose": deepcopy(P), "cap": {"pose": 1}, "cleanMissionStatus": {"phase": "run"}}

    def result(self, connected=True):
        return self.value.snapshot(connected=connected, entry_state="loaded")

    def test_invalid_coordinates_rejected_and_zero_kept(self):
        self.assertEqual(model.pose(P)["x"], 0)
        for value in [None, True, False, "12", float("nan"), float("inf"), -float("inf"), 10**1000]:
            for key in ["x", "y"]:
                candidate = deepcopy(P)
                candidate["point"][key] = value
                self.assertIsNone(model.pose(candidate), (key, value))
            candidate = deepcopy(P)
            candidate["theta"] = value
            self.assertIsNone(model.pose(candidate), value)
        self.assertIsNone(model.pose({"point": {"x": 1, "y": 2}}))
        self.assertIsNone(model.pose({"point": {"x": 1, "y": 2}, "theta": 361}))

    def test_initial_cache_does_not_claim_fresh_pose(self):
        self.value.update(self.reported, received_at="cache-time", initial=True)
        p = self.result()["position"]
        self.assertIsNone(p["observed_at"])
        self.assertIsNone(p["received_at"])
        self.assertEqual(p["timestamp_quality"], "not_provided")
        self.assertEqual(p["frame_quality"], "uncalibrated")
        self.assertFalse(self.result()["position_current"])

    def test_battery_message_never_refreshes_pose(self):
        self.value.update(self.reported, received_at="pose-time", delta={"pose": P})
        self.value.update(self.reported, received_at="battery-time", delta={"batPct": 80})
        self.assertEqual(self.result()["position"]["received_at"], "pose-time")
        self.assertIsNone(self.result()["position"]["observed_at"])

    def test_last_contact_is_only_actual_nonempty_message_receipt(self):
        self.value.update(self.reported, received_at="cache", initial=True)
        self.assertIsNone(self.result()["last_message_received_at"])
        self.value.update(self.reported, received_at="empty", delta={})
        self.assertIsNone(self.result()["last_message_received_at"])
        self.value.update(self.reported, received_at="battery", delta={"batPct": 70})
        self.assertEqual(self.result()["last_message_received_at"], "battery")
        self.assertIsNone(self.result()["position"]["received_at"])

    def test_partial_pose_does_not_mix_with_cache(self):
        self.value.update(self.reported, received_at="old", delta={"pose": P})
        self.reported["pose"]["point"]["x"] = 999
        self.value.update(self.reported, received_at="partial", delta={"pose": {"point": {"x": 999}}})
        self.assertFalse(self.result()["position_report_valid"])
        self.assertEqual(self.result()["position"]["x"], 0)
        self.assertEqual(self.result()["position"]["received_at"], "old")

    def test_disconnection_preserves_diagnostic_but_not_connected_receipt(self):
        self.value.update(self.reported, received_at="old", delta={"pose": P})
        self.assertFalse(self.result(False)["position_received_while_connected"])
        self.assertEqual(self.result(False)["position"]["received_at"], "old")

    def test_pose_capability_does_not_accept_boolean(self):
        self.reported["cap"]["pose"] = True
        self.value.update(self.reported, received_at="now", initial=True)
        self.assertFalse(self.result()["pose_supported"])

    def test_no_sensitive_fields_forwarded(self):
        self.reported.update(password="SECRET", blid="SECRET", mac="SECRET", netinfo={"addr": "SECRET"}, wlcfg={"ssid": "SECRET"})
        self.reported["cleanMissionStatus"]["password"] = "SECRET"
        self.reported["lastCommand"] = dict(COMMAND, password="SECRET")
        self.value.update(self.reported, received_at="now", initial=True)
        self.assertNotIn("SECRET", repr(self.result()))
        self.assertNotIn("map_id", self.result())
        self.assertFalse(self.result()["map_image_available"])

    def valid_command(self, command=None, maps=None, initial=False):
        command = deepcopy(COMMAND if command is None else command)
        self.reported["lastCommand"] = command
        self.reported["pmaps"] = maps if maps is not None else [{"synthetic-map": "test-v1"}]
        self.value.update(self.reported, received_at="now", initial=initial, delta={"lastCommand": command})
        return self.result()

    def test_only_actual_complete_command_can_be_learned(self):
        cached = self.valid_command(initial=True)
        self.assertFalse(cached["room_request_observed"])
        live = self.valid_command()
        self.assertTrue(live["room_request_observed"])
        self.assertTrue(live["room_request_matches_current_map"])
        self.assertEqual(live["position"]["frame_quality"], "uncalibrated")
        self.assertIsNone(live["position"]["received_at"])

    def test_generic_start_does_not_reuse_merged_room_fields(self):
        self.valid_command()
        self.value.update(self.reported, received_at="next", delta={"lastCommand": {"command": "start"}})
        self.assertFalse(self.result()["room_request_observed"])
        self.assertNotIn("regions", self.result()["last_command"])

    def test_malformed_partial_or_oversized_commands_never_ready(self):
        candidates = [dict(COMMAND, command="stop"), dict(COMMAND, regions=[]),
                      dict(COMMAND, regions=COMMAND["regions"] * 101),
                      dict(COMMAND, regions=COMMAND["regions"] * 2),
                      dict(COMMAND, regions=COMMAND["regions"] + [{"region_id": "2", "type": "invalid"}]),
                      dict(COMMAND, regions=[{"type": "rid"}]), dict(COMMAND, pmap_id=""), dict(COMMAND, pmap_id="   ")]
        for candidate in candidates:
            with self.subTest(candidate=candidate):
                self.assertFalse(self.valid_command(candidate)["room_request_matches_current_map"])

    def test_map_change_invalidates_request_without_calibrating_pose(self):
        self.valid_command()
        self.reported["pmaps"] = [{"synthetic-map": "test-v2"}]
        self.value.update(self.reported, received_at="new-map", delta={"pmaps": self.reported["pmaps"]})
        self.assertFalse(self.result()["room_request_matches_current_map"])
        self.assertFalse(self.result()["position_current"])

    def test_ambiguous_map_catalog_does_not_confirm_request(self):
        value = self.valid_command(maps=[{"synthetic-map": "test-v1"}, {"synthetic-map": "test-v2"}])
        self.assertTrue(value["room_request_observed"])
        self.assertFalse(value["room_request_matches_current_map"])

    def test_truncated_or_malformed_catalog_cannot_confirm_a_request(self):
        catalogs = [
            [{"synthetic-map": "test-v1"}] * 25 + [{"synthetic-map": "test-v2"}],
            [{"synthetic-map": "test-v1"}, None],
            [{"synthetic-map": "test-v1"}, {"bad": {"nested": "unknown"}}],
            [{"synthetic-map": "test-v1"}, {"pmap_id": "incomplete"}],
            {f"synthetic-map-{i}": "test-v1" for i in range(26)},
        ]
        for catalog in catalogs:
            result = self.valid_command(maps=catalog)
            self.assertFalse(result["map_catalog_complete"])
            self.assertFalse(result["room_request_matches_current_map"])

    def test_input_mutation_does_not_change_captured_values(self):
        self.valid_command()
        self.value.update(self.reported, received_at="pose", delta={"pose": P})
        snapshot = self.result()
        self.reported["lastCommand"]["regions"][0]["region_id"] = "CHANGED"
        snapshot["last_command"]["regions"][0]["region_id"] = "MUTATED"
        self.assertEqual(self.result()["last_command"]["regions"][0]["region_id"], "1")


try:
    from homeassistant.core import HomeAssistant
except ImportError:
    HA_AVAILABLE = False
else:
    HA_AVAILABLE = True
    sys.path.insert(0, str(ROOT / "config"))
    import custom_components
    from custom_components import roomba_insights as integration


if os.environ.get("REQUIRE_HA_RUNTIME") == "1" and not HA_AVAILABLE:
    raise RuntimeError("Home Assistant runtime is required for Roomba Insights tests")

@unittest.skipUnless(HA_AVAILABLE, "Requires Home Assistant runtime for lifecycle tests")
class LifecycleTest(unittest.TestCase):
    def setUp(self):
        self.jobs = []
        self.hass = SimpleNamespace(add_job=lambda *args: self.jobs.append(args))
        self.manager = integration.InsightsManager(self.hass)
        self.robot = SimpleNamespace(master_state={"state": {"reported": {"pose": deepcopy(P)}}},
                                     roomba_connected=True, on_message_callbacks=[object()], on_disconnect_callbacks=[object()])
        self.robot.register_on_message_callback = self.robot.on_message_callbacks.append
        self.robot.register_on_disconnect_callback = self.robot.on_disconnect_callbacks.append
        self.entry = SimpleNamespace(entry_id="test", state=integration.ConfigEntryState.LOADED,
                                     runtime_data=SimpleNamespace(roomba=self.robot))
        self.hass.config_entries = SimpleNamespace(async_get_entry=lambda _id: self.entry)
        self.binding = integration.NativeBinding(self.manager, self.entry, self.robot)
        self.manager.bindings["test"] = self.binding

    def test_callback_cleanup_leaves_native_callbacks_untouched(self):
        message_owner, disconnect_owner = self.robot.on_message_callbacks[0], self.robot.on_disconnect_callbacks[0]
        self.binding.close()
        self.binding.close()
        self.assertEqual(self.robot.on_message_callbacks, [message_owner])
        self.assertEqual(self.robot.on_disconnect_callbacks, [disconnect_owner])
        self.binding.on_message({"state": {"reported": {"pose": P}}})
        self.binding.on_disconnect("late")
        self.assertEqual(self.jobs, [])

    def test_unload_or_replacement_invalidates_connection_before_reconcile(self):
        self.assertTrue(self.manager.snapshot("test", "vacuum.test")["connected"])
        self.entry.state = integration.ConfigEntryState.SETUP_RETRY
        self.assertFalse(self.manager.snapshot("test", "vacuum.test")["connected"])
        self.entry.state = integration.ConfigEntryState.LOADED
        self.entry.runtime_data.roomba = object()
        self.assertFalse(self.manager.snapshot("test", "vacuum.test")["connected"])

    def test_queued_old_callback_does_not_update_replacement(self):
        sensor = SimpleNamespace(hass=True, entity_id="sensor.test", async_write_ha_state=lambda: self.jobs.append("write"))
        self.manager.entities["test"] = sensor
        self.manager.bindings["test"] = object()
        self.manager.async_notify("test", self.binding)
        self.assertEqual(self.jobs, [])

    def test_trail_receives_actual_delta_and_explicit_disconnect_boundary(self):
        events = []
        self.binding.trail = SimpleNamespace(
            update=lambda reported, delta, **kwargs: events.append(("update", delta)),
            break_path=lambda **kwargs: events.append(("break", kwargs["reason"])),
            snapshot=lambda: "frozen",
        )
        delta = {"pose": deepcopy(P)}
        self.binding.on_message({"state": {"reported": delta}})
        self.binding.on_disconnect("connection lost")
        self.assertEqual(events, [("update", delta), ("break", "disconnected")])

    def test_normal_disconnect_and_unavailable_entry_break_trail_on_inspection(self):
        events = []
        self.binding.trail = SimpleNamespace(
            break_path=lambda **kwargs: events.append(kwargs["reason"]),
            snapshot=lambda: "frozen",
        )
        self.robot.roomba_connected = False
        self.assertEqual(self.manager.snapshot_trail("test"), "frozen")
        self.robot.roomba_connected = True
        self.entry.state = integration.ConfigEntryState.SETUP_RETRY
        self.manager.snapshot_trail("test")
        self.assertEqual(events, ["disconnected", "disconnected"])

    def test_malformed_messages_do_not_crash_callback(self):
        for payload in [None, [], {"state": None}, {"state": {"reported": None}}]:
            self.binding.on_message(payload)
        self.assertEqual(len(self.jobs), 4)

@unittest.skipUnless(HA_AVAILABLE, "Requires Home Assistant runtime for setup tests")
class SetupTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import tempfile
        from homeassistant import loader
        from homeassistant.bootstrap import async_load_base_functionality
        from homeassistant.auth import auth_manager_from_config
        from homeassistant.config_entries import ConfigEntries, ConfigEntry
        from homeassistant.helpers import entity_registry as er
        self.original_component_path = custom_components.__path__
        custom_components.__path__ = [str(ROOT / "config/custom_components")]
        # The image platform depends on HTTP. Keep the real platform/view setup,
        # but never bind a second HTTP listener inside the production pod.
        self.http_bind_patch = patch("homeassistant.components.http.server.HomeAssistantHTTP.async_bind",
                                     new=AsyncMock(), create=True)
        self.http_bind_patch.start()
        self.temp = tempfile.TemporaryDirectory(prefix="roomba-insights-test-")
        (Path(self.temp.name) / "custom_components").symlink_to(ROOT / "config/custom_components", target_is_directory=True)
        self.hass = HomeAssistant(self.temp.name)
        loader.async_setup(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self.hass.config.skip_pip = True
        self.assertTrue(await async_load_base_functionality(self.hass))
        self.hass.auth = await auth_manager_from_config(self.hass, [], [])
        self.robot = SimpleNamespace(master_state={"state": {"reported": {"pose": deepcopy(P), "cap": {"pose": 1}}}},
                                     roomba_connected=True, on_message_callbacks=[], on_disconnect_callbacks=[])
        self.robot.register_on_message_callback = self.robot.on_message_callbacks.append
        self.robot.register_on_disconnect_callback = self.robot.on_disconnect_callbacks.append
        self.natives = []
        registry = er.async_get(self.hass)
        for i in range(5):
            entry = ConfigEntry(domain="roomba", title=f"Test robot {i}", data={}, options={}, source="user",
                                unique_id=f"synthetic-{i}", version=1, minor_version=1, discovery_keys={}, subentries_data=None,
                                state=integration.ConfigEntryState.LOADED if i == 0 else integration.ConfigEntryState.SETUP_RETRY)
            if i == 0:
                entry.runtime_data = SimpleNamespace(roomba=self.robot)
            self.hass.config_entries._entries[entry.entry_id] = entry
            registry.async_get_or_create("vacuum", "roomba", f"synthetic-{i}", suggested_object_id=f"test_robot_{i}", config_entry=entry)
            self.natives.append(entry)
        self.companion = ConfigEntry(domain="roomba_insights", title="Roomba Insights", data={}, options={}, source="user",
                                     unique_id="roomba_insights", version=1, minor_version=1, discovery_keys={}, subentries_data=None,
                                     state=integration.ConfigEntryState.LOADED)
        self.hass.config_entries._entries[self.companion.entry_id] = self.companion
        # No native integration setup: the five entries above are intentional
        # fixtures and the one local MQTT client is a plain fake object.
        self.hass.config.components.add("roomba")
        self.hass.config.components.add("roomba_insights")

    async def asyncTearDown(self):
        runtime = getattr(self.companion, "runtime_data", None)
        if runtime is not None:
            runtime.close()
        await self.hass.async_stop(force=True)
        self.http_bind_patch.stop()
        self.temp.cleanup()
        custom_components.__path__ = self.original_component_path

    async def test_setup_five_entries_with_only_one_connected_and_unload(self):
        self.assertTrue(await integration.async_setup_entry(self.hass, self.companion))
        await self.hass.async_block_till_done()
        manager = self.companion.runtime_data
        self.assertEqual(len(manager.entities), 5)
        self.assertEqual(len(manager.bindings), 1)
        self.assertEqual(len(manager.images), 1)
        self.assertEqual(len(self.hass.states.async_all("image")), 1)
        states = [s for s in self.hass.states.async_all("sensor") if "native_entry_state" in s.attributes]
        self.assertEqual(len(states), 5)
        self.assertEqual(sum(s.attributes["connected"] for s in states), 1)
        self.assertEqual(len(self.robot.on_message_callbacks), 1)
        self.assertTrue(await integration.async_unload_entry(self.hass, self.companion))
        self.assertEqual(self.robot.on_message_callbacks, [])
        self.assertEqual(self.robot.on_disconnect_callbacks, [])
        self.assertTrue(manager.closed)
        # HA intentionally restores registry entities as unavailable on unload.
        self.assertTrue(all(state.state == "unavailable" for state in self.hass.states.async_all("image")))
        self.assertTrue(all(image._removed for image in manager.images.values()))
        for image in manager.images.values():
            self.assertIsNone(await image.async_image())

    async def test_config_flow_aborts_existing_singleton(self):
        from custom_components.roomba_insights.config_flow import RoombaInsightsConfigFlow
        flow = RoombaInsightsConfigFlow()
        flow.hass = self.hass
        flow.context = {"source": "user"}
        flow.handler = "roomba_insights"
        from homeassistant.data_entry_flow import AbortFlow
        with self.assertRaises(AbortFlow) as caught:
            await flow.async_step_user({})
        self.assertEqual(caught.exception.reason, "already_configured")


if __name__ == "__main__":
    unittest.main()
