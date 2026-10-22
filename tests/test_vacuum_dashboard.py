"""Exercise private inventory projection and dynamic vacuum-map safety."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_vacuum_dashboard import build_view, validate_map


def fixture():
    return {
        "vacuum_entity": "vacuum.test_robot",
        "map_entity": "image.test_robot_custom",
        "room_ids": [18],
        "states": [
            {"entity_id": "vacuum.test_robot", "state": "docked", "attributes": {"supported_features": 30524}},
            {"entity_id": "image.test_robot_custom", "state": "2026-01-01T00:00:00+00:00", "attributes": {
                "access_token": "SECRET_IMAGE_TOKEN", "entity_picture": "/private?token=SECRET_IMAGE_TOKEN",
                "calibration_points": [
                    {"map": {"x": 0, "y": 0}, "vacuum": {"x": 1000, "y": 1000}},
                    {"map": {"x": 100, "y": 0}, "vacuum": {"x": 2000, "y": 1000}},
                    {"map": {"x": 0, "y": 100}, "vacuum": {"x": 1000, "y": 2000}},
                ],
                "rooms": {
                    "18": {"number": 18, "name": "Test room", "x0": 1000, "y0": 1000,
                           "x1": 2000, "y1": 2000, "pos_x": None, "pos_y": None,
                           "unexpected": "SECRET_UNRELATED_VALUE"},
                    "7": {"number": 7, "name": "Unknown", "outline": [[0, 0], [50, 0], [0, 50]]},
                },
            }},
            {"entity_id": "select.test_cleaning_mode", "state": "vac_and_mop", "attributes": {}},
            {"entity_id": "switch.test_dock_drying", "state": "off", "attributes": {}},
            {"entity_id": "sensor.test_filter_left", "state": "40", "attributes": {}},
            {"entity_id": "vacuum.other_robot", "state": "unavailable", "attributes": {}},
        ],
        "controls": {"cleaning": ["select.test_cleaning_mode"], "dock": ["switch.test_dock_drying"],
                     "maintenance": ["sensor.test_filter_left"]},
        "other_vacuums": ["vacuum.other_robot"],
    }


def image_entity(inventory):
    return next(row for row in inventory["states"] if row["entity_id"] == inventory["map_entity"])


def map_wrapper(view):
    return view["sections"][0]["cards"][1]


def project_in_node(wrapper, inventories):
    payload = {"card": wrapper,
               "source": str(Path(__file__).resolve().parents[1] / "config/www/roborock-map-card.js"),
               "inventories": inventories}
    source = """
const fs = require('node:fs');
const vm = require('node:vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const context = vm.createContext({HTMLElement: class {}, window: {},
  customElements: {get() {}, define() {}}});
vm.runInContext(fs.readFileSync(input.source, 'utf8'), context);
const results = input.inventories.map(inventory => {
  const states = Object.fromEntries(inventory.states.map(row => [row.entity_id, row]));
  const data = context.projectRoborockMap(states[input.card.map_entity], input.card.room_ids, input.card.room_names);
  const config = data.valid ? context.roborockInnerConfig(input.card, data) : {};
  return {data, type: data.valid ? config.type : 'markdown', modes: config.map_modes || []};
});
process.stdout.write(JSON.stringify(results));
"""
    return json.loads(subprocess.check_output([shutil.which("node"), "-e", source],
                                              input=json.dumps(payload), text=True))


class VacuumDashboardTests(unittest.TestCase):
    def test_projection_is_deterministic_private_and_does_not_mutate_input(self):
        inventory = fixture()
        original = copy.deepcopy(inventory)
        view = build_view(inventory)
        self.assertEqual(inventory, original)
        self.assertEqual(build_view(inventory), view)
        inventory["states"].reverse()
        self.assertEqual(build_view(inventory), view)
        rendered = json.dumps(view)
        for value in ("SECRET_IMAGE_TOKEN", "SECRET_UNRELATED_VALUE", "access_token", "Test room"):
            self.assertNotIn(value, rendered)
        self.assertEqual(view["path"], "vacuum-map")
        self.assertEqual(view["max_columns"], 3)
        self.assertEqual([section["column_span"] for section in view["sections"]], [2, 1])
        wrapper = map_wrapper(view)
        self.assertEqual(wrapper, {"type": "custom:homelab-roborock-map-card",
                                   "entity": inventory["vacuum_entity"], "map_entity": inventory["map_entity"],
                                   "room_ids": [18], "grid_options": {"columns": "full", "rows": "auto"}})
        self.assertNotIn("config-template-card", rendered)

    def test_only_supported_controls_and_explicit_other_vacuums_are_added(self):
        view = build_view(fixture())
        controls = view["sections"][1]["cards"]
        buttons = controls[0]["cards"]
        services = {row["tap_action"]["perform_action"]: row for row in buttons}
        self.assertEqual(set(services), {"vacuum.start", "vacuum.pause", "vacuum.stop", "vacuum.return_to_base"})
        self.assertIn("confirmation", services["vacuum.start"]["tap_action"])
        self.assertIn("confirmation", services["vacuum.return_to_base"]["tap_action"])
        self.assertEqual(controls[1]["features"], [{"type": "vacuum-fan-speed"}])
        self.assertEqual(controls[-1]["entities"], ["vacuum.other_robot"])
        inventory = fixture()
        inventory["states"][0]["attributes"]["supported_features"] = 256
        inventory.pop("controls")
        inventory.pop("other_vacuums")
        self.assertEqual(build_view(inventory)["sections"][1]["cards"], [])

    def test_bad_calibration_or_missing_map_data_is_rejected(self):
        mutations = [
            lambda a: a.pop("entity_picture"),
            lambda a: a.update(entity_picture=" "),
            lambda a: a.update(entity_picture=42),
            lambda a: a.pop("calibration_points"),
            lambda a: a["calibration_points"].pop(),
            lambda a: a["calibration_points"][0]["map"].update(x=float("nan")),
            lambda a: a["calibration_points"][0]["vacuum"].update(x=float("inf")),
            lambda a: a["calibration_points"][0]["map"].update(x=True),
            lambda a: a["calibration_points"][2].update(map={"x": 50, "y": 0}),
            lambda a: a.update(rooms={}),
            lambda a: a["rooms"]["18"].update(number=19),
            lambda a: a["rooms"]["18"].update(outline=[[0, 0], [1, 1], [2, 2]]),
            lambda a: a["rooms"]["18"].update(pos_x=15),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                inventory = fixture()
                mutate(image_entity(inventory)["attributes"])
                with self.assertRaises(ValueError):
                    build_view(inventory)
        inventory = fixture()
        image_entity(inventory)["state"] = "unavailable"
        with self.assertRaisesRegex(ValueError, "unavailable"):
            build_view(inventory)

    def test_invalid_or_ambiguous_entity_and_room_allowlists_are_rejected(self):
        mutations = [
            lambda i: i.update(vacuum_entity="vacuum.missing"),
            lambda i: i.update(map_entity="camera.test_robot_custom"),
            lambda i: i["states"].append(copy.deepcopy(i["states"][0])),
            lambda i: i["controls"].update(unreviewed=[]),
            lambda i: i["controls"].update(maintenance=["button.reset_filter"]),
            lambda i: i["other_vacuums"].append(i["vacuum_entity"]),
            lambda i: i.pop("room_ids"),
            lambda i: i.update(room_ids=[]),
            lambda i: i.update(room_ids=[18, 18]),
            lambda i: i.update(room_ids=[True]),
            lambda i: i.update(room_ids=["18"]),
            lambda i: i.update(room_ids=[999]),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                inventory = fixture()
                mutate(inventory)
                with self.assertRaises(ValueError):
                    build_view(inventory)

    @unittest.skipUnless(shutil.which("node"), "Node.js needed to execute browser projection")
    def test_runtime_rooms_follow_geometry_without_exposing_unapproved_segments(self):
        inventory = fixture()
        wrapper = map_wrapper(build_view(inventory))
        changed = copy.deepcopy(inventory)
        room = image_entity(changed)["attributes"]["rooms"]["18"]
        room.update(x0=5000, x1=6000, name="Updated name")
        initial, updated = project_in_node(wrapper, [inventory, changed])
        self.assertEqual(initial["data"]["rooms"], validate_map(image_entity(inventory), [18]))
        self.assertEqual(updated["data"]["rooms"], validate_map(image_entity(changed), [18]))
        self.assertEqual([room["id"] for room in initial["data"]["rooms"]], [18])
        self.assertEqual(updated["data"]["rooms"][0]["label"]["x"], 5500)
        self.assertEqual(updated["type"], "custom:xiaomi-vacuum-map-card")
        self.assertEqual([mode["template"] for mode in updated["modes"]],
                         ["vacuum_clean_segment", "vacuum_clean_zone", "vacuum_goto"])
        self.assertTrue(all(mode["run_immediately"] is False for mode in updated["modes"]))

    @unittest.skipUnless(shutil.which("node"), "Node.js needed to execute browser projection")
    def test_runtime_loss_or_corruption_replaces_map_instead_of_reusing_geometry(self):
        inventory = fixture()
        wrapper = map_wrapper(build_view(inventory))
        invalid = []
        for mutate in (
            lambda e: e.update(state="unavailable"),
            lambda e: e.update(state=None),
            lambda e: e["attributes"].pop("entity_picture"),
            lambda e: e["attributes"].update(entity_picture=" "),
            lambda e: e["attributes"].pop("rooms"),
            lambda e: e["attributes"]["rooms"].pop("18"),
            lambda e: e["attributes"]["calibration_points"][0].update(map={"x": None, "y": 10}),
            lambda e: e["attributes"]["rooms"]["18"].update(number=99),
        ):
            changed = copy.deepcopy(inventory)
            mutate(image_entity(changed))
            invalid.append(changed)
        for result in project_in_node(wrapper, invalid):
            self.assertEqual(result, {"data": {"valid": False, "rooms": []}, "type": "markdown", "modes": []})

    @unittest.skipUnless(shutil.which("node"), "Node.js needed to execute browser projection")
    def test_unknown_names_use_room_id_and_unrelated_attributes_are_ignored(self):
        inventory = fixture()
        inventory["room_ids"] = [7]
        wrapper = map_wrapper(build_view(inventory))
        result = project_in_node(wrapper, [inventory])[0]
        self.assertEqual(result["data"]["rooms"][0]["label"]["text"], "Room 7")
        self.assertNotIn("SECRET", json.dumps(result))

    def test_canonical_room_ids_are_required_even_when_parser_has_room_metadata(self):
        inventory = fixture()
        inventory.pop("room_ids")
        with self.assertRaisesRegex(ValueError, "verified current-map segment IDs"):
            build_view(inventory)

    def test_only_explicit_bounded_room_name_overrides_are_copied(self):
        inventory = fixture()
        inventory["room_names"] = {"18": "  Example alias  "}
        original = copy.deepcopy(inventory)
        wrapper = map_wrapper(build_view(inventory))
        self.assertEqual(wrapper["room_names"], {"18": "Example alias"})
        self.assertEqual(inventory, original)
        self.assertNotIn("Test room", json.dumps(wrapper))
        for names in (None, [], {"7": "Not selected"}, {"018": "Noncanonical"}, {18: "Not a string ID"},
                      {"18": " "}, {"18": "x" * 129}, {"18": 1}, {"18": {"html": "bad"}}):
            with self.subTest(names=names):
                inventory["room_names"] = names
                with self.assertRaisesRegex(ValueError, "Room names"):
                    build_view(inventory)

    @unittest.skipUnless(shutil.which("node"), "Node.js needed to execute browser projection")
    def test_room_override_survives_geometry_refresh_and_requires_valid_actual_room(self):
        inventory = fixture()
        inventory["room_names"] = {"18": "Example alias"}
        wrapper = map_wrapper(build_view(inventory))
        moved = copy.deepcopy(inventory)
        image_entity(moved)["attributes"]["rooms"]["18"].update(x1=3000, name="New device label")
        broken = copy.deepcopy(moved)
        image_entity(broken)["attributes"]["rooms"]["18"]["number"] = 19
        initial, changed, invalid = project_in_node(wrapper, [inventory, moved, broken])
        self.assertEqual(initial["data"]["rooms"][0]["label"]["text"], "Example alias")
        self.assertEqual(changed["data"]["rooms"][0]["label"]["text"], "Example alias")
        self.assertEqual(changed["data"]["rooms"][0]["outline"][1][0], 3000)
        self.assertFalse(invalid["data"]["valid"])

    def test_cli_invalid_input_does_not_replace_existing_output(self):
        script = Path(__file__).resolve().parents[1] / "scripts/build_vacuum_dashboard.py"
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "inventory.json"
            output = Path(directory) / "view.json"
            source.write_text('{"states": [], "states": ["SECRET"]}')
            output.write_text("existing content")
            result = subprocess.run([sys.executable, str(script), str(source), "--output", str(output)],
                                    text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(output.read_text(), "existing content")
            self.assertNotIn("SECRET", result.stderr)

    @unittest.skipUnless(shutil.which("node"), "Node.js needed to test custom card lifecycle")
    def test_custom_card_lifecycle(self):
        source = Path(__file__).with_name("test_roborock_map_card.js")
        result = subprocess.run([shutil.which("node"), "--test", str(source)], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
