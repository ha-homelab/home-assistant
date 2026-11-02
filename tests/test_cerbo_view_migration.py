import copy
import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / "scripts/reorganize_media_cerbo.py"
spec = importlib.util.spec_from_file_location("cerbo_migration", PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixtures():
    main = {"title": "Home", "custom_header": {"compact_mode": True}, "views": [
        {"title": "Media", "path": "media", "cards": [{"type": "media-control", "entity": "media_player.example"}]},
        {"title": "Energy", "path": "energy", "cards": [{"type": "button", "tap_action": {
            "action": "navigate", "navigation_path": "/cerbo-gx/gx"}}]},
    ]}
    controller_entities = ["sensor.gx_device_dynamic_ess_target_soc", "sensor.gx_device_available_version",
                           "update.gx_device_firmware", "number.gx_device_ess_max_charge_current",
                           "switch.gx_device_ess_batterylife_schedule_charge_0_enabled",
                           "time.gx_device_ess_batterylife_schedule_charge_0_start",
                           "select.gx_device_ess_batterylife_schedule_charge_0_days",
                           "number.gx_device_ess_batterylife_schedule_charge_0_duration",
                           "number.gx_device_ess_batterylife_schedule_charge_0_soc"]
    cerbo = {"title": "Cerbo GX", "views": [
        {"title": "Cerbo GX", "path": "home", "sections": [{"type": "grid", "cards": [
            {"type": "tile", "entity": "update.gx_device_firmware", "tap_action": {"action": "more-info"}},
            {"type": "button", "name": "All GX settings and statuses", "tap_action": {
                "action": "navigate", "navigation_path": "/cerbo-gx/gx"}},
            {"type": "tile", "entity": "sensor.battery_charge", "tap_action": {
                "action": "navigate", "navigation_path": "/cerbo-gx/device-1"}},
        ]}]},
        {"title": "GX Device", "path": "gx", "subview": True, "cards": [
            {"type": "entities", "title": "Wrong phone grouping", "entities": controller_entities + [
                {"entity": "switch.gx_device_dvcc", "name": "Charge coordination", "icon": "mdi:power"}]}]},
        {"title": "Battery", "path": "device-1", "subview": True, "back_path": "/cerbo-gx/home", "cards": [
            {"type": "entities", "entities": ["sensor.battery_charge", "number.battery_limit"]}]},
    ]}
    return main, cerbo


class CerboViewMigrationTests(unittest.TestCase):
    def test_controller_is_inline_and_device_navigation_stays_inside_lovelace(self):
        main, cerbo = fixtures()
        original = copy.deepcopy((main, cerbo))
        result = module.migrate_cerbo_view(main, cerbo)
        self.assertEqual((main, cerbo), original, "Inputs must not be mutated")
        self.assertEqual(result["custom_header"], main["custom_header"])
        self.assertEqual(result["views"][0], main["views"][0])
        by_path = {v["path"]: v for v in result["views"]}
        home = by_path["cerbo-gx"]
        self.assertFalse(home["subview"])
        self.assertNotIn("gx", by_path)
        self.assertTrue(module._entity_refs(cerbo["views"][1]) <= module._entity_refs(home))
        self.assertTrue(module._entity_refs(cerbo) <= module._entity_refs(result))
        self.assertTrue(by_path["cerbo-device-1"]["subview"])
        self.assertEqual(by_path["cerbo-device-1"]["back_path"], "/lovelace/cerbo-gx")
        self.assertNotIn("/cerbo-gx/", str(result))
        self.assertIn("/lovelace/cerbo-device-1", str(home))
        self.assertNotIn("All GX settings and statuses", str(home))
        self.assertIn("Charge coordination", str(home))
        self.assertEqual(home["sections"][0]["cards"][0]["tap_action"], {"action": "more-info"})

    def test_energy_groups_and_schedule_rows_are_meaningful(self):
        main, cerbo = fixtures()
        result = module.migrate_cerbo_view(main, cerbo)
        sections = next(v for v in result["views"] if v["path"] == "cerbo-gx")["sections"]
        grouped = {s["cards"][0]["heading"]: s for s in sections if s["cards"][0].get("type") == "heading"}
        self.assertIn("Dynamic ESS", grouped)
        self.assertIn("Firmware and system health", grouped)
        self.assertNotIn("Voice assistant", grouped)
        self.assertNotIn("Bluetooth", grouped)
        rows = grouped["Charging schedule 1"]["cards"][1]["entities"]
        self.assertEqual([r.rsplit("_", 1)[-1] for r in rows], ["enabled", "days", "start", "duration", "soc"])
        for section in sections:
            for card in section["cards"]:
                self.assertEqual(card["grid_options"]["columns"], 12)

    def test_rerunning_is_idempotent_and_unrelated_paths_are_protected(self):
        main, cerbo = fixtures()
        result = module.migrate_cerbo_view(main, cerbo)
        self.assertEqual(module.migrate_cerbo_view(result, cerbo), result)
        main["views"].append({"title": "My unrelated view", "path": "cerbo-device-1", "cards": []})
        with self.assertRaisesRegex(ValueError, "conflicts"):
            module.migrate_cerbo_view(main, cerbo)

    def test_later_user_edits_to_generated_views_are_not_overwritten(self):
        main, cerbo = fixtures()
        for path in ("cerbo-gx", "cerbo-device-1"):
            with self.subTest(path=path):
                result = module.migrate_cerbo_view(main, cerbo)
                view = next(v for v in result["views"] if v["path"] == path)
                view["icon"] = "mdi:star"
                edited = copy.deepcopy(result)
                with self.assertRaisesRegex(ValueError, "conflicts"):
                    module.migrate_cerbo_view(result, cerbo)
                self.assertEqual(result, edited)


if __name__ == "__main__":
    unittest.main()
