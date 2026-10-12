"""Verify the archived diff can recreate and reverse the deployed hotfix."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.patch_localtuya_cover import patch

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / 'patches/localtuya'


@unittest.skipUnless(os.getenv('LOCAL_TUYA_COVER_SOURCE'), 'Requires pinned LocalTuya source')
class LocalTuyaPatchArtifactTest(unittest.TestCase):
    def test_archived_diff_recreates_installed_file_and_reverses_cleanly(self):
        metadata = json.loads((KIT / 'baseline.json').read_text())
        original = Path(os.environ['LOCAL_TUYA_COVER_SOURCE']).read_bytes()
        self.assertEqual(hashlib.sha256(original).hexdigest(), metadata['source_sha256'],
                         'This historical artifact requires its own unmodified baseline')
        with tempfile.TemporaryDirectory(prefix='localtuya-patch-roundtrip-') as folder:
            subprocess.run(['git', 'init', '-q', folder], check=True)
            source = Path(folder) / metadata['source_path']
            source.parent.mkdir(parents=True)
            source.write_bytes(original)
            artifact = str(KIT / metadata['patch_file'])
            for args in (['--check'], []):
                subprocess.run(['git', 'apply', *args, artifact], cwd=folder, check=True)
            restored = source.read_bytes()
            self.assertEqual(hashlib.sha256(restored).hexdigest(), metadata['patched_sha256'])
            self.assertEqual(restored, patch(original.decode()).encode())
            subprocess.run(['git', 'apply', '--reverse', '--check', artifact], cwd=folder, check=True)
            subprocess.run(['git', 'apply', '--reverse', artifact], cwd=folder, check=True)
            self.assertEqual(source.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
