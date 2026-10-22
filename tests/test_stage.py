"""Exercise the real remote staging code against isolated local directories."""
from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "stage", Path(__file__).resolve().parents[1] / "tools/stage.py")
STAGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STAGE)


def write(root, name, content):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class StageEnvironmentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ha-staging-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.stage = self.root / ".ha-homelab-stage-test"
        self.stage.mkdir()
        self.secrets = write(self.stage, "secrets.yaml", "private: local-value\n")
        self.secrets.chmod(0o644)

    def run_remote(self, source, *arguments):
        # Substitute only the root literal, retaining the exact production code.
        code = source.replace("'/config'", repr(str(self.root)))
        output = io.StringIO()
        with patch("sys.argv", ["stage-test", str(self.stage), *arguments]), redirect_stdout(output):
            exec(compile(code, "<isolated-stage>", "exec"), {"__name__": "__main__"})
        return output.getvalue()

    def prepare(self):
        return self.run_remote(STAGE.PREPARE_ENVIRONMENT)

    def test_bundled_component_wins_without_mixing_installed_files(self):
        bundled = write(self.stage, "custom_components/roomba_insights/__init__.py", "reviewed new code\n")
        installed = write(self.root, "custom_components/roomba_insights/__init__.py", "old installed code\n")
        write(self.root, "custom_components/roomba_insights/obsolete.py", "old implementation\n")
        other = write(self.root, "custom_components/other_integration/__init__.py", "installed dependency\n")
        before = {path: digest(path) for path in (bundled, installed, other)}

        self.prepare()

        components = self.stage / "custom_components"
        self.assertFalse(components.is_symlink())
        self.assertFalse((components / "roomba_insights").is_symlink())
        self.assertFalse((components / "roomba_insights/obsolete.py").exists())
        dependency = components / "other_integration"
        self.assertTrue(dependency.is_symlink())
        self.assertEqual(dependency.resolve(), other.parent.resolve())
        self.assertEqual((dependency / "__init__.py").read_text(), "installed dependency\n")
        self.assertEqual({path: digest(path) for path in before}, before)
        self.assertEqual(self.secrets.stat().st_mode & 0o777, 0o600)

    def test_bundle_without_components_gets_per_child_links_and_is_idempotent(self):
        write(self.root, "custom_components/example/__init__.py", "installed\n")
        write(self.root, "custom_components/__init__.py", "namespace setup\n")
        self.prepare()
        components = self.stage / "custom_components"
        self.assertTrue(components.is_dir())
        self.assertFalse(components.is_symlink())
        links = {entry.name: entry.readlink() for entry in components.iterdir()}
        self.assertEqual(set(links), {"example", "__init__.py"})
        self.prepare()
        self.assertEqual({entry.name: entry.readlink() for entry in components.iterdir()}, links)

    def test_no_installed_components_is_valid(self):
        self.prepare()
        components = self.stage / "custom_components"
        self.assertTrue(components.is_dir())
        self.assertEqual(list(components.iterdir()), [])

    def test_existing_file_and_broken_link_are_never_overwritten(self):
        existing = write(self.stage, "custom_components/existing", "bundled file\n")
        broken = self.stage / "custom_components/broken"
        broken.symlink_to(self.root / "missing")
        write(self.root, "custom_components/existing/__init__.py", "live\n")
        write(self.root, "custom_components/broken/__init__.py", "live\n")
        self.prepare()
        self.assertEqual(existing.read_text(), "bundled file\n")
        self.assertFalse(existing.is_symlink())
        self.assertTrue(broken.is_symlink())
        self.assertEqual(broken.readlink(), self.root / "missing")

    def test_rejects_staged_root_link_without_adding_live_links(self):
        live = self.root / "custom_components"
        live.mkdir()
        write(live, "example/__init__.py", "live\n")
        (self.stage / "custom_components").symlink_to(live, target_is_directory=True)
        with self.assertRaisesRegex(AssertionError, "must be a real directory"):
            self.prepare()
        self.assertEqual(sorted(path.name for path in live.iterdir()), ["example"])
        self.assertFalse((live / "example").is_symlink())

    def test_rejects_staging_directory_link(self):
        linked_stage = self.root / ".ha-homelab-stage-link"
        linked_stage.symlink_to(self.stage, target_is_directory=True)
        self.stage = linked_stage
        with self.assertRaisesRegex(AssertionError, "Invalid staging directory"):
            self.prepare()

    def test_transfer_and_live_fingerprints_remain_enforced_with_component_links(self):
        bundle_names = ("secrets.yaml", "custom_components/roomba_insights/__init__.py",
                        "automations/example.yaml", "scripts/example.yaml")
        for name in bundle_names[1:]:
            write(self.stage, name, "bundled " + name)
            write(self.root, name, "installed " + name)
        write(self.root, "secrets.yaml", "existing live secret\n")
        write(self.root, "custom_components/other/__init__.py", "other installed code\n")
        manifest = {name: digest(self.stage / name) for name in bundle_names}
        self.prepare()
        report = json.loads(self.run_remote(STAGE.FINGERPRINT, json.dumps(manifest)))
        self.assertEqual(report["live_files"], {name: digest(self.root / name) for name in bundle_names})
        self.assertEqual(report["live_directories"], {
            name: {"example.yaml": digest(self.root / name / "example.yaml")}
            for name in ("automations", "scripts")})
        self.assertNotIn("custom_components/other/__init__.py", report["live_files"])
        write(self.stage, "custom_components/roomba_insights/__init__.py", "changed after transfer\n")
        with self.assertRaisesRegex(AssertionError, "Staging transfer changed file"):
            self.run_remote(STAGE.FINGERPRINT, json.dumps(manifest))

    def test_managed_file_symlink_still_fails_fingerprint(self):
        target = write(self.root, "elsewhere.txt", "linked managed content\n")
        managed = self.stage / "configuration.yaml"
        managed.symlink_to(target)
        with self.assertRaises(AssertionError):
            self.run_remote(STAGE.FINGERPRINT, json.dumps({"configuration.yaml": digest(target)}))


if __name__ == "__main__":
    unittest.main()
