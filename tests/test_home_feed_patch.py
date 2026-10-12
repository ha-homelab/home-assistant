"""Check language resolution against modern/legacy HA frontend inputs."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from patch_home_feed_card import LANGUAGE_EXPRESSION, MARKER, patch


class HomeFeedPatchTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js needed to execute browser expression")
    def test_language_selection(self):
        cases = [
            ({"locale": {"language": "ru"}, "language": "en"}, "ru"),
            ({"language": "de"}, "de"),
            ({"locale": None, "language": "fr", "resources": None}, "fr"),
            ({"resources": {"es": {}}}, "es"),
            ({"resources": None}, "en"),
            ({"resources": {}}, "en"),
            ({}, "en"),
        ]
        code = (
            "const fs=require('node:fs');"
            "const inputs=JSON.parse(fs.readFileSync(0,'utf8'));"
            "const result=inputs.map(e=>(" + LANGUAGE_EXPRESSION + "));"
            "process.stdout.write(JSON.stringify(result));"
        )
        actual = subprocess.check_output(
            ["node", "-e", code], input=json.dumps([case[0] for case in cases]), text=True
        )
        self.assertEqual(json.loads(actual), [case[1] for case in cases])

    def test_unknown_or_damaged_source_is_rejected(self):
        for source in ("", "this._language=Object.keys(e.resources)[0]", MARKER, MARKER + "changed"):
            with self.subTest(source=source), self.assertRaises(ValueError):
                patch(source)


if __name__ == "__main__":
    unittest.main()
