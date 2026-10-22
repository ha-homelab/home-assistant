"""Exercise native Roomba presentation and private dashboard merging offline."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_roomba_dashboard import build_view, patch_dashboard


def fixture():
    profile = {
        "entity": "vacuum.example", "name": "Example robot", "model": "960",
        "battery": "sensor.example_battery", "charging": "binary_sensor.example_charging",
        "bin_full": "binary_sensor.example_bin", "network": "binary_sensor.example_network",
        "dock_power": "switch.example_dock", "last_recovery": "input_datetime.example_recovery",
        "statistics": ["sensor.example_missions"],
        "capability_note": "Cleaning path only; no room selection.",
    }
    states = [{"entity_id": entity, "state": "on", "attributes": {}}
              for entity in [profile[key] for key in ("battery", "charging", "bin_full", "network",
                                                       "dock_power", "last_recovery")] + profile["statistics"]]
    states.append({"entity_id": "vacuum.example", "state": "docked", "attributes": {
        "supported_features": 13084, "position": [9999, 8888, 7777],
        "access_token": "SECRET_TOKEN", "entity_picture": "/private?token=SECRET_TOKEN",
        "password": "SECRET_PASSWORD", "rooms": {"SECRET_ROOM": 99}}})
    return {"profiles": [profile], "states": states}


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


class RoombaDashboardTests(unittest.TestCase):
    def test_native_view_is_deterministic_and_projects_no_private_attributes(self):
        inventory = fixture()
        original = copy.deepcopy(inventory)
        view = build_view(inventory)
        self.assertEqual(inventory, original)
        self.assertEqual(view, build_view(inventory))
        inventory["states"].reverse()
        self.assertEqual(view, build_view(inventory))
        self.assertEqual(view["path"], "roombas")
        self.assertEqual(view["title"], "Roombas")
        self.assertEqual(view["max_columns"], 3)
        encoded = json.dumps(view)
        for forbidden in ("SECRET_TOKEN", "SECRET_PASSWORD", "SECRET_ROOM", "9999", '"position":', "custom:"):
            self.assertNotIn(forbidden, encoded)
        commands = [row["commands"] for row in walk(view) if row.get("type") == "vacuum-commands"]
        self.assertEqual(commands, [["start_pause", "stop", "return_home", "locate"]])

    def test_unavailable_controls_are_conditional_and_more_info_is_safe(self):
        inventory = fixture()
        inventory["states"][-1]["state"] = "unavailable"
        cards = build_view(inventory)["sections"][0]["cards"]
        self.assertEqual(cards[0]["conditions"], [
            {"condition": "state", "entity": "vacuum.example", "state_not": "unknown"},
            {"condition": "state", "entity": "vacuum.example", "state_not": "unavailable"},
        ])
        self.assertEqual(cards[1]["conditions"][0]["condition"], "or")
        self.assertNotIn("features", cards[1]["card"])
        for row in walk(build_view(inventory)):
            if row.get("type") == "tile":
                self.assertEqual(row["tap_action"], {"action": "more-info"})
                self.assertEqual(row["icon_tap_action"], {"action": "more-info"})
        actions = [row["perform_action"] for row in walk(build_view(inventory)) if "perform_action" in row]
        self.assertEqual(actions, ["switch.turn_on"])
        self.assertNotIn("toggle", json.dumps(build_view(inventory)).replace("show_header_toggle", ""))

    def test_unknown_and_partial_capabilities_never_invent_controls(self):
        for feature in (None, True, "13084", -1, 0, 256):
            with self.subTest(feature=feature):
                inventory = fixture()
                inventory["states"][-1]["attributes"]["supported_features"] = feature
                self.assertFalse(any(row.get("type") == "vacuum-commands" for row in walk(build_view(inventory))))
        inventory = fixture()
        inventory["states"][-1]["attributes"]["supported_features"] = 16
        commands = [row["commands"] for row in walk(build_view(inventory)) if row.get("type") == "vacuum-commands"]
        self.assertEqual(commands, [["return_home"]])

    def test_dock_power_is_read_only_and_only_on_action_is_available(self):
        view = build_view(fixture())
        rows = [row for row in walk(view)
                if row.get("type") == "simple-entity" and row.get("entity") == "switch.example_dock"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Dock power")
        for action in ("tap_action", "hold_action", "double_tap_action"):
            self.assertEqual(rows[0][action], {"action": "none"})
        buttons = [row for row in walk(view) if row.get("type") == "conditional"
                   and row.get("card", {}).get("name") == "Power dock on"]
        self.assertEqual(buttons[0]["conditions"], [
            {"condition": "state", "entity": "switch.example_dock", "state": "off"}])
        self.assertEqual(buttons[0]["card"]["tap_action"]["perform_action"], "switch.turn_on")

    def test_telemetry_displays_native_state_and_only_actual_message_timestamp(self):
        inventory = fixture()
        inventory["profiles"][0]["telemetry"] = "sensor.example_telemetry"
        inventory["states"].append({"entity_id": "sensor.example_telemetry", "state": "connected",
                                    "attributes": {"last_message_received_at": "2026-01-01T00:00:00+00:00",
                                                   "private_value": "SECRET_TELEMETRY",
                                                   "position_received_at": "SECRET_SUBSTITUTE_TIMESTAMP"}})
        view = build_view(inventory)
        rows = [row for row in walk(view) if row.get("entity") == "sensor.example_telemetry"]
        self.assertEqual(rows, [{"entity": "sensor.example_telemetry", "name": "Local telemetry",
                                 "tap_action": {"action": "more-info"}}])
        timestamps = [row["content"] for row in walk(view)
                      if row.get("type") == "markdown" and "Last local message" in row.get("content", "")]
        self.assertEqual(len(timestamps), 1)
        template = timestamps[0]
        self.assertIn("state_attr('sensor.example_telemetry', 'last_message_received_at')", template)
        self.assertIn("{% if received is none %}\nNever received", template)
        self.assertIn("observed is not none and observed.tzinfo is not none", template)
        self.assertIn("Timestamp unavailable", template)
        self.assertIn("as_datetime(received, none)", template)
        for alternative in ("last_updated", "last_changed", "position_received_at", "relative_time", "now("):
            self.assertNotIn(alternative, template)
        for private in ("SECRET_TELEMETRY", "SECRET_SUBSTITUTE_TIMESTAMP", "2026-01-01T00:00:00+00:00"):
            self.assertNotIn(private, json.dumps(view))
        # Output remains dynamic for missing/invalid timestamps and disconnected
        # states: it must not bake an initial age or a fabricated receipt date.
        for value in (None, "unknown", "unavailable", "bad date", 0):
            inventory["states"][-1]["attributes"]["last_message_received_at"] = value
            inventory["states"][-1]["state"] = "disconnected"
            self.assertEqual(build_view(inventory), view)
        inventory["profiles"][0]["telemetry"] = "switch.example_dock"
        with self.assertRaises(ValueError):
            build_view(inventory)
        inventory["profiles"][0]["telemetry"] = "sensor.missing_telemetry"
        with self.assertRaises(ValueError):
            build_view(inventory)

    def test_network_failure_diagnostic_directs_coverage_check(self):
        view = build_view(fixture())
        diagnostics = [row for row in walk(view) if row.get("type") == "conditional"
                       and "No network response" in row.get("card", {}).get("content", "")]
        self.assertEqual(len(diagnostics), 1)
        self.assertIn({"condition": "state", "entity": "binary_sensor.example_network", "state": "off"},
                      diagnostics[0]["conditions"][0]["conditions"])
        self.assertIn("Wi-Fi coverage at the dock", diagnostics[0]["card"]["content"])

    def test_only_explicit_valid_entities_are_displayed(self):
        inventory = fixture()
        inventory["states"].append({"entity_id": "sensor.example_tank", "state": "unknown", "attributes": {}})
        self.assertNotIn("sensor.example_tank", json.dumps(build_view(inventory)))
        invalid = [
            lambda x: x["profiles"][0].update(battery="sensor.missing"),
            lambda x: x["profiles"][0].update(network="switch.example_dock"),
            lambda x: x["profiles"][0].update(statistics=["sensor.example_battery"]),
            lambda x: x["profiles"].append(copy.deepcopy(x["profiles"][0])),
            lambda x: x["states"].append(copy.deepcopy(x["states"][0])),
            lambda x: x["profiles"][0].update(name="{{ states('sensor.secret') }}"),
            lambda x: x["profiles"][0].update(password="SECRET_PASSWORD"),
        ]
        for mutate in invalid:
            with self.subTest(mutation=mutate):
                candidate = fixture()
                mutate(candidate)
                with self.assertRaises(ValueError):
                    build_view(candidate)

    def test_minimal_profile_does_not_require_diagnostics_or_map(self):
        inventory = {"profiles": [{"entity": "vacuum.example", "name": "Example"}],
                     "states": [{"entity_id": "vacuum.example", "state": "unavailable", "attributes": {}}]}
        view = build_view(inventory)
        self.assertEqual(len(view["sections"]), 1)
        self.assertFalse(any(row.get("type") in ("entities", "picture-entity", "vacuum-commands") for row in walk(view)))

    def test_recovery_is_one_read_only_card_and_statistics_stay_separate(self):
        inventory = fixture()
        for index in range(4):
            entity = f"vacuum.other_{index}"
            recovery = f"input_datetime.other_{index}_recovery"
            inventory["profiles"].append({"entity": entity, "name": f"Other {index}",
                                          "last_recovery": recovery})
            inventory["states"].extend([
                {"entity_id": entity, "state": "unavailable", "attributes": {}},
                {"entity_id": recovery, "state": "2026-01-01 12:00:00", "attributes": {}},
            ])
        view = build_view(inventory)
        self.assertEqual(len(view["sections"]), 6)  # Five robots, one diagnostics section.
        diagnostics = view["sections"][-1]["cards"]
        self.assertEqual(len(diagnostics), 2)
        self.assertEqual(diagnostics[0]["title"], "Example robot · Statistics")
        self.assertEqual(diagnostics[0]["entities"], ["sensor.example_missions"])
        recovery = diagnostics[1]
        self.assertEqual(recovery["title"], "Connection recovery")
        self.assertFalse(recovery["show_header_toggle"])
        self.assertEqual(len(recovery["entities"]), 5)
        for row in recovery["entities"]:
            self.assertEqual(row["type"], "simple-entity")
            for action in ("tap_action", "hold_action", "double_tap_action"):
                self.assertEqual(row[action], {"action": "none"})
        # An input_datetime must never slip back into its default editable row.
        helper_rows = [row for row in walk(view)
                       if str(row.get("entity", "")).startswith("input_datetime.")]
        self.assertEqual(helper_rows, recovery["entities"])

    def test_maps_require_verification_and_never_copy_image_tokens(self):
        inventory = fixture()
        inventory["states"].append({"entity_id": "image.example_map", "state": "2026-01-01T00:00:00Z",
                                     "attributes": {"entity_picture": "/private?token=SECRET_MAP_TOKEN"}})
        inventory["profiles"][0]["map"] = {"entity": "image.example_map", "verified": True}
        view = build_view(inventory)
        pictures = [row for row in walk(view) if row.get("type") == "picture-entity"]
        self.assertEqual(pictures[0]["entity"], "image.example_map")
        self.assertNotIn("SECRET_MAP_TOKEN", json.dumps(view))
        for mapping in ({"entity": "image.example_map"},
                        {"entity": "image.example_map", "verified": "true"},
                        {"entity": "image.example_map", "verified": True, "coordinates": [1, 2]},
                        {"entity": "image.example_map", "verified": True, "navigation_path": "/map"},
                        {"navigation_path": "https://example.test/map", "verified": True},
                        {"navigation_path": "//example.test/map", "verified": True}):
            with self.subTest(mapping=mapping):
                inventory["profiles"][0]["map"] = mapping
                with self.assertRaises(ValueError):
                    build_view(inventory)
        inventory["profiles"][0]["map"] = {"entity": "image.example_map", "verified": True}
        inventory["states"][-1]["state"] = "unavailable"
        with self.assertRaises(ValueError):
            build_view(inventory)

    def test_verified_local_navigation_is_not_a_vacuum_action(self):
        inventory = fixture()
        inventory["profiles"][0]["map"] = {"navigation_path": "/house-plan/roomba", "verified": True}
        view = build_view(inventory)
        maps = [row for row in walk(view) if row.get("name") == "Open map / cleaning path"]
        self.assertEqual(maps[0]["tap_action"], {"action": "navigate", "navigation_path": "/house-plan/roomba"})

    def test_relative_trail_accepts_waiting_image_without_weakening_map_verification(self):
        inventory = fixture()
        inventory["profiles"][0]["trail"] = "image.example_trail"
        inventory["states"].append({"entity_id": "image.example_trail", "state": "unavailable",
                                     "attributes": {"entity_picture": "/private?token=SECRET_TRAIL_TOKEN",
                                                    "coordinates": [12345, 67890]}})
        view = build_view(inventory)
        pictures = [row for row in walk(view) if row.get("type") == "conditional"
                    and row.get("card", {}).get("type") == "picture-entity"]
        self.assertEqual(len(pictures), 1)
        self.assertEqual(pictures[0]["card"]["entity"], "image.example_trail")
        self.assertEqual(pictures[0]["conditions"], [
            {"condition": "state", "entity": "image.example_trail", "state_not": "unknown"},
            {"condition": "state", "entity": "image.example_trail", "state_not": "unavailable"},
        ])
        waiting = [row for row in walk(view) if row.get("type") == "conditional"
                   and "valid cleaning mission identity" in row.get("card", {}).get("content", "")]
        self.assertEqual(len(waiting), 1)
        self.assertEqual(waiting[0]["conditions"][0]["condition"], "or")
        encoded = json.dumps(view)
        self.assertIn("uncalibrated odometry; not a house map", encoded)
        for private in ("SECRET_TRAIL_TOKEN", "12345", "67890", "coordinates"):
            self.assertNotIn(private, encoded)
        actions = [row["perform_action"] for row in walk(view) if "perform_action" in row]
        self.assertEqual(actions, ["switch.turn_on"])
        inventory["states"][-1]["state"] = "2026-01-01T00:00:00Z"
        self.assertEqual(build_view(inventory), view)
        for invalid in ("image.missing", "sensor.example_battery", "camera.example_trail"):
            inventory["profiles"][0]["trail"] = invalid
            with self.assertRaises(ValueError):
                build_view(inventory)

    def test_patch_preserves_unrelated_content_and_is_idempotent(self):
        inventory = fixture()
        view = build_view(inventory)
        roborock = {"type": "custom:vacuum-card", "entity": "vacuum.roborock_q_revo", "image": "default"}
        legacy = {"type": "custom:vacuum-card", "entity": "vacuum.example", "image": "default",
                  "visibility": [{"condition": "user", "users": ["private-user-id"]}],
                  "view_layout": {"grid-area": "vacuum"}, "grid_options": {"columns": 6}}
        arbitrary = {"type": "button", "entity": "vacuum.example", "tap_action": {"action": "more-info"}}
        dashboard = {"title": "House", "custom_metadata": {"preserve": [1, 2]}, "views": [
            {"path": "home", "cards": [{"type": "vertical-stack", "cards": [legacy, roborock, arbitrary]}]},
            {"path": "vacuum-map", "private_room_names": {"1": "Keep exactly"}},
        ]}
        original = copy.deepcopy(dashboard)
        patched = patch_dashboard(dashboard, view, inventory["profiles"])
        self.assertEqual(dashboard, original)
        self.assertEqual(patched, patch_dashboard(patched, view, inventory["profiles"]))
        cards = patched["views"][0]["cards"][0]["cards"]
        self.assertEqual(cards[1:], [roborock, arbitrary])
        self.assertEqual(patched["views"][1], original["views"][1])
        self.assertEqual(cards[0]["type"], "tile")
        self.assertEqual(cards[0]["tap_action"]["navigation_path"], "/lovelace/roombas")
        for key in ("visibility", "view_layout", "grid_options"):
            self.assertEqual(cards[0][key], legacy[key])
        self.assertEqual(patched["custom_metadata"], original["custom_metadata"])

    def test_merge_latest_preserves_concurrent_unrelated_edits_and_collapses_duplicate_view(self):
        inventory = fixture()
        view = build_view(inventory)
        first = patch_dashboard({"views": [{"path": "home", "cards": []}]}, view, inventory["profiles"])
        latest = copy.deepcopy(first)
        latest["views"][0]["cards"].append({"type": "markdown", "content": "Added by another editor"})
        latest["views"].extend([{"path": "new-view", "cards": []}, {"path": "roombas", "cards": []}])
        merged = patch_dashboard(latest, view, inventory["profiles"])
        self.assertEqual(merged["views"][0], latest["views"][0])
        self.assertEqual([v["path"] for v in merged["views"]], ["home", "roombas", "new-view"])

    def test_cli_and_duplicate_input_keys(self):
        script = Path(__file__).resolve().parents[1] / "scripts/build_roomba_dashboard.py"
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder) / "inventory.json", Path(folder) / "view.json"
            source.write_text(json.dumps(fixture()))
            result = subprocess.run([sys.executable, str(script), str(source), "--output", str(output)],
                                    capture_output=True, text=True, check=True)
            self.assertIn("no device commands", result.stdout)
            self.assertEqual(json.loads(output.read_text()), build_view(fixture()))
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            source.write_text('{"profiles": [], "profiles": []}')
            result = subprocess.run([sys.executable, str(script), str(source), "--output", str(output)],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Duplicate JSON key", result.stderr)


if __name__ == "__main__":
    unittest.main()
