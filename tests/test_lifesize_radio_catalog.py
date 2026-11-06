import copy
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("radio_catalog", ROOT / "scripts/sync_lifesize_radio_catalog.py")
module = importlib.util.module_from_spec(spec)
with patch.object(sys, "path", [str(ROOT / "scripts"), *sys.path]):
    spec.loader.exec_module(module)


class RadioCatalogTests(unittest.TestCase):
    def package(self):
        return {"input_select": {"lifesize_222_station": {"options": ["Old · 701"]},
                                 "lifesize_222_destination": {"options": ["201", "701"]}},
                "script": {"lifesize_222_radio": {
                    "fields": {"source": {"selector": {"select": {"options": []}}}},
                    "sequence": [{"variables": {"stations": {}}},
                                 {"condition": "template", "value_template": "{{ source in stations }}"}]},
                           "unrelated": {"sequence": [{"delay": 1}]}}}

    def test_sources_agree_and_other_controls_are_preserved(self):
        package = self.package()
        original = copy.deepcopy(package)
        catalog = {"stations": {"one": {"name": "One", "extension": "701"},
                                "two": {"name": "Two", "extension": "711"}}}
        result = module.sync_catalog(package, catalog)
        self.assertEqual(package, original)
        self.assertEqual(result["script"]["unrelated"], original["script"]["unrelated"])
        radio = result["script"]["lifesize_222_radio"]
        self.assertEqual(radio["sequence"][1], original["script"]["lifesize_222_radio"]["sequence"][1])
        self.assertEqual(result["input_select"]["lifesize_222_station"]["options"],
                         radio["fields"]["source"]["selector"]["select"]["options"])
        self.assertEqual(result["input_select"]["lifesize_222_destination"]["options"], ["201", "701", "711"])
        self.assertEqual(module.sync_catalog(result, catalog), result)

    def test_duplicate_or_non_radio_numbers_are_rejected(self):
        for numbers in (("701", "701"), ("201", "711")):
            catalog = {"stations": {str(i): {"name": "Station", "extension": n}
                                    for i, n in enumerate(numbers)}}
            with self.assertRaises(ValueError):
                module.sync_catalog(self.package(), catalog)


if __name__ == "__main__":
    unittest.main()
