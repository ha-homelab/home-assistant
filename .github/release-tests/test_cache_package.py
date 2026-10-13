"""Exercise the real wheel/sdist boundary with frozen beta and RC metadata."""

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import package_cache
import stage_release_assets
import version_plan
import version_receipt


class CachePackageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="cache-package-contract-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name in (
            *package_cache.FILES,
            ".release-policy.json",
            ".github/requirements-build.txt",
        ):
            destination = self.root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, destination)
        shutil.copytree(ROOT / "scripts", self.root / "scripts")
        self.command("git", "init", "-q")
        self.command("git", "add", ".")
        self.command(
            "git",
            "-c",
            "user.name=Package fixture",
            "-c",
            "user.email=package@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            "Synthetic package fixture",
        )
        self.policy = json.loads((self.root / ".release-policy.json").read_text())

    def command(self, *args):
        return subprocess.check_output(
            args, cwd=self.root, text=True, stderr=subprocess.STDOUT
        )

    def freeze(self, channel):
        shutil.copyfile(ROOT / "pyproject.toml", self.root / "pyproject.toml")
        plan = version_plan.create_plan(
            "0.1.0",
            channel,
            7,
            self.command("git", "rev-parse", "HEAD").strip(),
            self.policy,
            build_number=7,
        )
        (self.root / ".release-plan.json").write_text(json.dumps(plan))
        self.command(
            sys.executable,
            "scripts/version_plan.py",
            "sync",
            "--plan",
            ".release-plan.json",
        )
        return plan

    def test_real_beta_rc_packages_install_and_receive_matching_receipts(self):
        for channel in ("beta", "rc"):
            with self.subTest(channel=channel):
                plan = self.freeze(channel)
                artifacts = package_cache.build(
                    self.root, "0.1.0", channel, self.root / channel
                )
                self.assertEqual(len(artifacts), 2)
                staged = stage_release_assets.stage(
                    self.root, channel, [channel + "/*"]
                )
                inventory = [
                    {
                        "name": p.name,
                        "size": p.stat().st_size,
                        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                    }
                    for p in sorted(staged.iterdir())
                ]
                version_receipt.verify_receipts(staged, plan, inventory, self.policy)
                self.assertEqual(
                    len(
                        version_receipt.verify_declared_artifacts(
                            staged, self.policy, plan
                        )
                    ),
                    2,
                )

    def test_snapshot_cannot_copy_unselected_household_files(self):
        (self.root / "config/household.yaml").write_text(
            "synthetic: outside-distribution\n"
        )
        destination = self.root / "snapshot"
        package_cache.snapshot(self.root, destination)
        selected = {
            str(path.relative_to(destination))
            for path in destination.rglob("*")
            if path.is_file()
        }
        self.assertEqual(selected, set(package_cache.FILES))

    def test_snapshot_rejects_linked_source(self):
        path = self.root / package_cache.FILES[2]
        path.unlink()
        path.symlink_to(self.root / "pyproject.toml")
        with self.assertRaisesRegex(ValueError, "regular tracked"):
            package_cache.snapshot(self.root, self.root / "snapshot")

    def test_wheel_rejects_unexpected_configuration(self):
        artifact = self.root / "unexpected.whl"
        with zipfile.ZipFile(artifact, "w") as archive:
            archive.writestr("notification_frame_cache.py", "pass")
            archive.writestr("config/household.yaml", "synthetic: outside-distribution")
        with self.assertRaisesRegex(ValueError, "unexpected"):
            package_cache.verify_inventory(artifact)


if __name__ == "__main__":
    unittest.main()
