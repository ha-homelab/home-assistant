"""Run the actual browser card against isolated DOM and transport boundaries."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CoreUpdateCardTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node.js is required for browser behavior tests')
    def test_confirmation_capture_cancellation_concurrency_and_rendering(self):
        result = subprocess.run(
            ['node', str(ROOT / 'tests/core_update_card.cjs'),
             str(ROOT / 'config/www/core-update-card.js')],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout), {'result': 'passed', 'scenarios': 10})


if __name__ == '__main__':
    unittest.main()
