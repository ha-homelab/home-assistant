"""Exercise the actual SHA-pinned card methods without HA or Mercedes requests."""

import json
import os
from pathlib import Path
import subprocess
import unittest

from tools import patch_vehicle_info_card as hotfix


@unittest.skipUnless(os.getenv("VEHICLE_INFO_CARD_SOURCE"), "Requires reviewed card bundle")
class VehicleInfoCardPatchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path(os.environ["VEHICLE_INFO_CARD_SOURCE"]).read_text()
        cls.patched = hotfix.patch(cls.source)

    def test_original_legacy_and_current_assets_produce_identical_patch(self):
        original = self.patched.removeprefix(hotfix.MARKER)
        for before, after in hotfix.REPLACEMENTS:
            original = original.replace(after, before, 1)
        legacy = hotfix.LEGACY_MARKER + original.replace(hotfix.BEFORE, hotfix.AFTER, 1)
        v2 = original
        for before, after in hotfix.V2_REPLACEMENTS:
            v2 = v2.replace(before, after, 1)
        v2 = hotfix.V2_MARKER + v2
        for source in (original, legacy, v2, self.patched):
            self.assertEqual(hotfix.patch(source), self.patched)
            with self.assertRaises(ValueError):
                hotfix.patch(source + "\n// changed upstream or corrupt local asset")
        self.assertIn(hotfix.BUNDLED_MAP, self.patched)
        self.assertEqual(self.patched.count(hotfix.AFTER), 1)

    def test_real_javascript_pressure_and_recovery_paths(self):
        result = subprocess.run(
            ["node", str(Path(__file__).with_name("vehicle_info_card_pressure.cjs"))],
            input=json.dumps({"original": self.source, "patched": self.patched}),
            text=True, capture_output=True, check=True, timeout=30,
        )
        self.assertEqual(json.loads(result.stdout)["result"], "passed")
