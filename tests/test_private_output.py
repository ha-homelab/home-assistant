import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("private_output_test", ROOT / "scripts/private_output.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def cli_inputs():
    station = {"name": "Radio", "extension": "711", "url": "https://example.org/radio.mp3"}
    entity = "media_player.example"
    package = {
        "input_select": {"lifesize_222_station": {"options": []},
                         "lifesize_222_destination": {"options": []}},
        "script": {"lifesize_222_radio": {
            "fields": {"source": {"selector": {"select": {"options": []}}}},
            "sequence": [{"variables": {"stations": {}}}]}}}
    return {
        "build_phones_dashboard": [{"url_path": "phones", "devices": []}],
        "build_radio_console": [{"stations": {"radio": station}}, []],
        "prepare_lovelace_layout": [
            {"views": [{"path": "media", "cards": [
                {"type": "grid", "cards": [{"type": "media-control", "entity": entity}]}]}]},
            {"views": [{"path": "home", "sections": []}, {"path": "gx", "cards": []}]},
            {"devices": [{"entity": entity, "name": "Example", "shortcuts": [
                {"name": "Radio", "id": station["url"], "type": "music"}]}]}],
        # JSON is also valid YAML for this CLI's package input.
        "sync_lifesize_radio_catalog": [package, {"stations": {"radio": station}}],
    }


class PrivateOutputTests(unittest.TestCase):
    def test_bytes_are_private_before_atomic_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            output.write_text("old")
            output.chmod(0o644)
            old_umask = os.umask(0)
            try:
                with module.private_output(output, ()) as stream:
                    self.assertEqual(stat.S_IMODE(os.fstat(stream.fileno()).st_mode), 0o600)
                    stream.write("new")
                    stream.flush()
                    self.assertEqual(output.read_text(), "old")
            finally:
                os.umask(old_umask)
            self.assertEqual(output.read_text(), "new")
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            self.assertEqual(list(Path(directory).iterdir()), [output])

    def test_partial_write_or_failed_replace_preserves_previous_file(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            output.write_text("old")
            with self.assertRaisesRegex(ValueError, "serialize"):
                with module.private_output(output, ()) as stream:
                    stream.write("partial")
                    raise ValueError("serialize")
            self.assertEqual(output.read_text(), "old")
            with patch.object(module.os, "replace", side_effect=OSError("replace")):
                with self.assertRaisesRegex(OSError, "replace"):
                    with module.private_output(output, ()) as stream:
                        stream.write("new")
            self.assertEqual(output.read_text(), "old")
            self.assertEqual(list(Path(directory).iterdir()), [output])

    def test_all_clis_protect_each_source_and_publish_private_output(self):
        for name, data in cli_inputs().items():
            with self.subTest(cli=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                sources = [root / f"source-{i}.json" for i in range(len(data))]
                for source, value in zip(sources, data):
                    source.write_text(json.dumps(value))
                original = [source.read_bytes() for source in sources]
                command = [sys.executable, str(ROOT / "scripts" / f"{name}.py"), *map(str, sources)]

                def run(output):
                    return subprocess.run([*command, str(output)], cwd=root, text=True,
                                          capture_output=True, timeout=15)

                for source in sources:
                    hardlink = root / "hardlink"
                    hardlink.hardlink_to(source)
                    symlink = root / "symlink"
                    symlink.symlink_to(source)
                    for output in (source, hardlink, symlink):
                        result = run(output)
                        self.assertEqual(result.returncode, 2, result.stderr)
                        self.assertIn("Output must not", result.stderr)
                        self.assertEqual([p.read_bytes() for p in sources], original)
                    hardlink.unlink()
                    symlink.unlink()

                unrelated = root / "unrelated"
                unrelated.write_text("unrelated")
                link = root / "link"
                for target in (unrelated, root / "missing"):
                    link.symlink_to(target)
                    self.assertEqual(run(link).returncode, 2)
                    self.assertEqual(unrelated.read_text(), "unrelated")
                    self.assertFalse((root / "missing").exists())
                    link.unlink()

                output = root / "output"
                output.write_text("previous")
                output.chmod(0o644)
                result = run(output)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotEqual(output.read_text(), "previous")
                self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
                self.assertEqual([p.read_bytes() for p in sources], original)
                self.assertFalse(list(root.glob(".output.*")))

    def test_module_entry_points_support_relative_imports(self):
        for name in cli_inputs():
            with self.subTest(cli=name):
                result = subprocess.run([sys.executable, "-m", f"scripts.{name}", "--help"],
                                        cwd=ROOT, text=True, capture_output=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("usage:", result.stdout)


if __name__ == "__main__":
    unittest.main()
