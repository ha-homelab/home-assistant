import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / "scripts/build_phones_dashboard.py"
spec = importlib.util.spec_from_file_location("phones_dashboard", PATH)
module = importlib.util.module_from_spec(spec)
with patch.object(sys, "path", [str(PATH.parent), *sys.path]):
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

    def run_cli(self, manifest, output):
        with patch("sys.argv", [str(PATH), str(manifest), str(output)]):
            module.main()

    def test_output_is_private_before_writing_and_replaces_atomically(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, output = root / "manifest.json", root / "dashboard.json"
            manifest.write_text('{"url_path":"phones","devices":[]}')
            output.write_text("previous output")
            output.chmod(0o644)
            original_dump = json.dump

            def checked_dump(value, stream, **kwargs):
                self.assertEqual(stat.S_IMODE(os.fstat(stream.fileno()).st_mode), 0o600)
                self.assertEqual(output.read_text(), "previous output")
                return original_dump(value, stream, **kwargs)

            old_umask = os.umask(0)
            try:
                with patch.object(module.json, "dump", side_effect=checked_dump):
                    self.run_cli(manifest, output)
            finally:
                os.umask(old_umask)
            self.assertEqual(json.loads(output.read_text())["title"], "Phones")
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            self.assertEqual(sorted(p.name for p in root.iterdir()), ["dashboard.json", "manifest.json"])

    def test_source_aliases_and_output_symlinks_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "manifest.json"
            original = '{"url_path":"phones","devices":[]}'
            manifest.write_text(original)
            hardlink, symlink, unrelated = root / "hardlink", root / "symlink", root / "unrelated"
            hardlink.hardlink_to(manifest)
            symlink.symlink_to(manifest)
            unrelated.write_text("untouched")
            otherlink = root / "otherlink"
            otherlink.symlink_to(unrelated)
            for output in (manifest, hardlink, symlink, otherlink):
                with self.subTest(output=output.name), self.assertRaises(SystemExit), patch("sys.stderr"):
                    self.run_cli(manifest, output)
                self.assertEqual(manifest.read_text(), original)
                self.assertEqual(unrelated.read_text(), "untouched")

    def test_serialization_failure_keeps_previous_output_and_removes_temporary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, output = root / "manifest.json", root / "dashboard.json"
            manifest.write_text('{"url_path":"phones","devices":[]}')
            output.write_text("previous output")
            with patch.object(module.json, "dump", side_effect=ValueError("serialization failed")):
                with self.assertRaises(ValueError):
                    self.run_cli(manifest, output)
            self.assertEqual(output.read_text(), "previous output")
            self.assertEqual(sorted(p.name for p in root.iterdir()), ["dashboard.json", "manifest.json"])


if __name__ == "__main__":
    unittest.main()
