"""Configuration policy checks must survive Python's optimization flags."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parents[1] / "tools"
VALID_CONFIG = """\
input_number:
  nightime: {}
recorder:
  db_url: !secret recorder_db_url
  purge_keep_days: 28
homeassistant:
  time_zone: America/Los_Angeles
"""


class ValidationOptimizationTest(unittest.TestCase):
    def test_configuration_contracts_remain_enforced_with_optimization(self):
        with tempfile.TemporaryDirectory(prefix="validation-optimization-") as temporary:
            root = Path(temporary)
            (root / "tools").mkdir()
            (root / "config").mkdir()
            for name in ("validate.py", "ha_yaml.py"):
                shutil.copyfile(TOOLS / name, root / "tools" / name)
            config = root / "config/configuration.yaml"
            cases = [
                (VALID_CONFIG, None),
                (VALID_CONFIG.replace("nightime: {}", "unexpected: {}"), "shadowed helpers"),
                (VALID_CONFIG.replace("!secret recorder_db_url", "!secret wrong_database"), "recorder_db_url secret"),
                (VALID_CONFIG.replace("purge_keep_days: 28", "purge_keep_days: 999"), "28 days"),
                (VALID_CONFIG.replace("purge_keep_days: 28", "purge_keep_days: 28\n  purge_interval: 1"), "purge_interval"),
                (VALID_CONFIG.replace("America/Los_Angeles", "UTC"), "time zone"),
            ]
            for arguments, optimized in (([], None), (["-O"], None), (["-OO"], None), ([], "1")):
                environment = os.environ.copy()
                environment.pop("PYTHONOPTIMIZE", None)
                if optimized:
                    environment["PYTHONOPTIMIZE"] = optimized
                for source, error in cases:
                    with self.subTest(arguments=arguments, environment=optimized, error=error):
                        config.write_text(source)
                        result = subprocess.run(
                            [sys.executable, *arguments, str(root / "tools/validate.py")],
                            env=environment, capture_output=True, text=True, check=False,
                        )
                        if error:
                            self.assertNotEqual(result.returncode, 0, result.stdout)
                            self.assertIn(error, result.stderr)
                            self.assertNotIn("Validated", result.stdout)
                        else:
                            self.assertEqual(result.returncode, 0, result.stderr)
                            self.assertIn("Validated", result.stdout)


if __name__ == "__main__":
    unittest.main()
