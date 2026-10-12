"""Exercise the actual promotion script against isolated files, never a HA instance."""

from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / 'tools/promote.py'
SPEC = importlib.util.spec_from_file_location('promote', MODULE_PATH)
PROMOTE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROMOTE)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def tree(path):
    if not path.exists():
        return None
    return {str(file.relative_to(path)): digest(file) for file in sorted(path.rglob('*')) if file.is_file()}


def write(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value)


class PromotionTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='ha-promotion-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.stage = self.root / '.ha-homelab-stage-test'
        self.stage.mkdir()
        self.original = {
            'automations/old.yaml': 'old automation\n',
            'automations/old.yaml.bak': 'original editor backup\n',
            'scripts/old.yaml': 'old script\n',
            'configuration.yaml': 'old configuration\n',
            'secrets.yaml': 'existing secret\n',
            'release.json': '{"identity_seed": true}\n',
            '.storage/keep': 'unrelated live registry\n',
            'www/keep.jpg': 'unrelated camera output\n',
            '.configuration.yaml.ha-homelab-new': 'unrelated preexisting temporary file\n',
        }
        self.proposed = {
            'automations/001_new.yaml': 'new automation\n',
            'scripts/001_new.yaml': 'new script\n',
            'configuration.yaml': 'new configuration\n',
            'integrations/new.yaml': 'new included configuration\n',
            'secrets.yaml': 'existing secret\n',
            'release.json': '{"identity_seed": false}\n',
        }
        for name, value in self.original.items():
            write(self.root, name, value)
        for name, value in self.proposed.items():
            write(self.stage, name, value)
        self.receipt = self.make_receipt()
        # Replace only the literal filesystem root. The script still runs unchanged otherwise.
        self.code = PROMOTE.REMOTE.replace("'/config'", repr(str(self.root)))

    def make_receipt(self):
        files = tree(self.stage)
        return {
            'remote_stage': str(self.stage), 'files': files,
            'live_files': {name: digest(self.root / name) for name in files},
            'live_directories': {name: tree(self.root / name) for name in ('automations', 'scripts')},
            'release': {'identity_seed': False},
        }

    def run_promotion(self, scope='overlay', *, returncode=0, report=None):
        report = {'config_dir': str(self.root), 'total_errors': 0} if report is None else report
        output = report if isinstance(report, str) else json.dumps(report)
        checker = subprocess.CompletedProcess(['mock-check-config'], returncode, stdout=output.encode())
        printed = io.StringIO()
        with patch('sys.argv', ['promote-test', json.dumps(self.receipt), scope]), \
             patch('subprocess.run', return_value=checker) as mocked_checker, \
             redirect_stdout(printed):
            exec(compile(self.code, '<isolated-promotion>', 'exec'), {'__name__': '__main__'})
        mocked_checker.assert_called_once()
        command = mocked_checker.call_args.args[0]
        self.assertIn('--json', command)
        self.assertNotIn('--output', command)
        self.assertEqual(command[command.index('--config') + 1], str(self.root))
        return json.loads(printed.getvalue())

    def assert_original_preserved(self):
        for name, value in self.original.items():
            self.assertEqual((self.root / name).read_text(), value, name)
        for directory in ('automations', 'scripts'):
            expected = {str(Path(name).relative_to(directory)): hashlib.sha256(value.encode()).hexdigest()
                        for name, value in self.original.items() if name.startswith(directory + '/')}
            self.assertEqual(tree(self.root / directory), expected)

    def test_success_keeps_unrelated_files_and_rollback_copy(self):
        result = self.run_promotion()
        for name, value in self.proposed.items():
            self.assertEqual((self.root / name).read_text(), value)
        for name in ('.storage/keep', 'www/keep.jpg', '.configuration.yaml.ha-homelab-new'):
            self.assertEqual((self.root / name).read_text(), self.original[name])
        backup = Path(result['backup'])
        self.assertEqual((backup / 'automations/old.yaml.bak').read_text(), self.original['automations/old.yaml.bak'])
        self.assertEqual((backup / 'configuration.yaml').read_text(), self.original['configuration.yaml'])
        self.assertFalse(result['reloaded'])

    def test_rejects_ordinary_file_lost_update_before_writing(self):
        write(self.root, 'configuration.yaml', 'edited after staging\n')
        with self.assertRaisesRegex(AssertionError, 'Live file changed'):
            self.run_promotion()
        self.assertEqual((self.root / 'configuration.yaml').read_text(), 'edited after staging\n')
        self.assertEqual(tree(self.root / 'automations'), self.receipt['live_directories']['automations'])
        self.assertFalse(list(self.root.glob('.ha-homelab-backup-*')))

    def test_rejects_directory_lost_update_including_backup_files(self):
        write(self.root, 'automations/edited.yaml.bak', 'new user backup\n')
        with self.assertRaisesRegex(AssertionError, 'Live directory changed'):
            self.run_promotion()
        self.assertEqual((self.root / 'automations/edited.yaml.bak').read_text(), 'new user backup\n')
        self.assertFalse(list(self.root.glob('.ha-homelab-backup-*')))

    def test_rejects_unvalidated_added_stage_file(self):
        write(self.stage, 'automations/unvalidated.yaml', 'unexpected enabled rule\n')
        with self.assertRaisesRegex(AssertionError, 'Staged directory differs'):
            self.run_promotion()
        self.assert_original_preserved()

    def test_rejects_symlink_added_to_staged_directory(self):
        (self.stage / 'automations/unvalidated').symlink_to(self.root / 'www', target_is_directory=True)
        with self.assertRaisesRegex(AssertionError, 'Symlink'):
            self.run_promotion()
        self.assert_original_preserved()

    def test_rolls_back_failed_installed_configuration_check(self):
        with self.assertRaisesRegex(RuntimeError, 'Installed HA configuration rejected'):
            self.run_promotion(returncode=1, report={'config_dir': str(self.root), 'total_errors': 1})
        self.assert_original_preserved()
        self.assertFalse((self.root / 'integrations/new.yaml').exists())
        self.assertEqual(len(list(self.root.glob('.ha-homelab-backup-*'))), 1)

    def test_rolls_back_partial_file_copy_failure_and_removes_temporary_file(self):
        original_copy = shutil.copy2

        def copy_with_failure(source, destination, *args, **kwargs):
            if Path(source) == self.stage / 'configuration.yaml':
                raise OSError('simulated partial file copy failure')
            return original_copy(source, destination, *args, **kwargs)

        with patch('shutil.copy2', side_effect=copy_with_failure):
            with self.assertRaisesRegex(OSError, 'simulated partial file copy failure'):
                self.run_promotion()
        self.assert_original_preserved()
        self.assertFalse((self.root / 'integrations/new.yaml').exists())
        self.assertFalse(list(self.root.glob('.configuration.yaml.ha-homelab-new-*')))

    def test_rolls_back_directory_copy_failure(self):
        original_copytree = shutil.copytree

        def copytree_with_failure(source, destination, *args, **kwargs):
            if Path(source) == self.stage / 'scripts':
                raise OSError('simulated directory copy failure')
            return original_copytree(source, destination, *args, **kwargs)

        with patch('shutil.copytree', side_effect=copytree_with_failure):
            with self.assertRaisesRegex(OSError, 'simulated directory copy failure'):
                self.run_promotion()
        self.assert_original_preserved()

    def test_rejects_unrelated_json_instead_of_checker_report(self):
        with self.assertRaisesRegex(RuntimeError, 'Installed HA configuration rejected'):
            self.run_promotion(report={'total_errors': 0})
        self.assert_original_preserved()

    def test_finds_matching_report_after_warning_and_unrelated_json(self):
        output = 'Warning {not json}\n{"unrelated": true}\n' + json.dumps({'config_dir': str(self.root), 'total_errors': 0})
        result = self.run_promotion(report=output)
        self.assertEqual(result['check_exit_code'], 0)

    def prepare_automation_only(self):
        # Seed overlay is already installed, including scripts and root configuration.
        shutil.rmtree(self.root / 'scripts')
        shutil.copytree(self.stage / 'scripts', self.root / 'scripts')
        for name, value in self.proposed.items():
            if not name.startswith('automations/') and name != 'release.json':
                write(self.root, name, value)
        self.receipt = self.make_receipt()

    def test_automation_only_updates_release_marker_and_preserves_other_files(self):
        self.prepare_automation_only()
        before_scripts = tree(self.root / 'scripts')
        result = self.run_promotion('automations')
        self.assertEqual(result['scope'], 'automations')
        self.assertEqual((self.root / 'release.json').read_text(), self.proposed['release.json'])
        self.assertEqual(tree(self.root / 'scripts'), before_scripts)
        self.assertEqual((self.root / 'configuration.yaml').read_text(), self.proposed['configuration.yaml'])

    def test_automation_only_rejects_mismatched_non_automation_content(self):
        with self.assertRaisesRegex(AssertionError, 'Non-automation content differs'):
            self.run_promotion('automations')
        self.assert_original_preserved()
        self.assertFalse(list(self.root.glob('.ha-homelab-backup-*')))

    def test_automation_only_checks_release_marker_for_lost_updates(self):
        self.prepare_automation_only()
        write(self.root, 'release.json', '{"user_changed":true}\n')
        with self.assertRaisesRegex(AssertionError, 'Live file changed'):
            self.run_promotion('automations')
        self.assertEqual((self.root / 'release.json').read_text(), '{"user_changed":true}\n')

    def test_automation_only_rejects_extra_live_script(self):
        self.prepare_automation_only()
        write(self.root, 'scripts/user_added.yaml', 'new live script\n')
        with self.assertRaisesRegex(AssertionError, 'Non-automation directory differs'):
            self.run_promotion('automations')
        self.assertEqual((self.root / 'scripts/user_added.yaml').read_text(), 'new live script\n')
        self.assertFalse(list(self.root.glob('.ha-homelab-backup-*')))

    def test_rejects_symlink_in_live_parent_path(self):
        outside = self.root / 'outside-managed-path'
        outside.mkdir()
        (self.root / 'integrations').symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(AssertionError, 'Symlink in managed path'):
            self.run_promotion()
        self.assertFalse((outside / 'new.yaml').exists())
        self.assertFalse(list(self.root.glob('.ha-homelab-backup-*')))


if __name__ == '__main__':
    unittest.main()
