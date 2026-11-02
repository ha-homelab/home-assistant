import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / "scripts/build_phones_dashboard.py"
spec = importlib.util.spec_from_file_location("phones_dashboard", PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PhonesDashboardTests(unittest.TestCase):
    def test_offline_devices_and_all_controls_remain_visible(self):
        devices = []
        for index in range(15):
            prefix = f"example_{index}"
            devices.append({"key": prefix, "title": prefix, "family": "Phones",
                            "status": "media_player." + prefix,
                            "player": "media_player." + prefix,
                            "online": False,
                            "entities": ["switch." + prefix, "sensor." + prefix]})
        result = module.build({"url_path": "phones", "devices": devices})
        self.assertEqual(len(result["views"]), 16)
        for device, view in zip(devices, result["views"][1:]):
            self.assertTrue(set(device["entities"]) <= module.entity_refs(view))
        self.assertNotIn("conditional", str(result))

    def test_same_entity_is_not_duplicated_in_generated_groups(self):
        device = {"key": "one", "title": "One", "family": "Phones",
                  "status": "sensor.one", "entities": ["switch.one"],
                  "cards": [{"type": "entities", "entities": ["switch.one"]}]}
        result = module.build({"url_path": "phones", "devices": [device]})
        self.assertEqual(len(result["views"][1]["cards"]), 1)

    def test_duplicate_view_is_rejected(self):
        with self.assertRaises(ValueError):
            module.build({"url_path": "phones", "devices": [],
                          "extra_views": [{"path": "home"}]})


if __name__ == "__main__":
    unittest.main()
