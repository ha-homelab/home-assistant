"""Offline LG remote hold regression; optionally exercise the pinned full bundle."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from patch_lg_remote_control import AFTER, BEFORE, MARKER, REPLACEMENTS, patch


class LGRemotePatchTests(unittest.TestCase):
    def test_unknown_or_damaged_bundle_rejected(self):
        for source in ('', BEFORE, MARKER, MARKER + AFTER):
            with self.subTest(source=source[:30]), self.assertRaises(ValueError):
                patch(source)

    @unittest.skipUnless(shutil.which('node'), 'Node.js executes actual volume methods')
    def test_volume_methods_without_device_calls(self):
        # Exact code fragments used in the transformation, never a reimplemented
        # approximation of the old timer or the new click method.
        service_before = 'callServiceFromConfig(t,e,o){var i;let s=e,n=o;const r=null===(i=this.config.keys)||void 0===i?void 0:i[t],c="string"==typeof(null==r?void 0:r.service)?r.service.trim():"";c&&(s=c,n=r.data),this.hass.callService(s.split(".")[0],s.split(".")[1],n)}'
        original = BEFORE + 'updated(t){}' + service_before + '_getIcon(t,e){}' + 'id="plusButton" id="minusButton"'
        updated = original
        for before, after in REPLACEMENTS:
            updated = updated.replace(before, after)
        self.run_node(original, updated)

    def run_node(self, original, updated):
        script = Path(__file__).with_name('lg_remote_volume.cjs')
        result = subprocess.check_output(['node', str(script)], input=json.dumps({'original': original, 'patched': updated}), text=True)
        self.assertTrue(json.loads(result)['oldRunawayReproduced'])

    @unittest.skipUnless(os.environ.get('LG_REMOTE_CONTROL_SOURCE'), 'Set LG_REMOTE_CONTROL_SOURCE to reviewed 2.1.0 bundle')
    def test_pinned_full_bundle_and_idempotence(self):
        source = Path(os.environ['LG_REMOTE_CONTROL_SOURCE']).read_text()
        updated = patch(source)
        self.assertEqual(patch(updated), updated)
        with self.assertRaises(ValueError):
            patch(updated + '\n')
        if shutil.which('node'):
            self.run_node(source, updated)
            subprocess.run(['node', '--check'], input=updated, text=True, check=True, capture_output=True)


if __name__ == '__main__':
    unittest.main()
