"""Build real temporary monorepos and verify the tracked-file boundary."""

from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


TOOLS = Path(__file__).resolve().parents[1] / 'tools'
SPEC = importlib.util.spec_from_file_location('build', TOOLS / 'build.py')
BUILD = importlib.util.module_from_spec(SPEC)
with patch.object(sys, 'path', [str(TOOLS), *sys.path]):
    SPEC.loader.exec_module(BUILD)


def git(repository, *arguments):
    return subprocess.check_output([
        'git', '-C', str(repository), '-c', 'user.name=Build Test',
        '-c', 'user.email=build-test@example.invalid', '-c', 'commit.gpgsign=false',
        *arguments,
    ], stderr=subprocess.STDOUT).decode().strip()


def write(root, name, content):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


class BuildTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='ha-build-test-')
        self.addCleanup(temporary.cleanup)
        # macOS may return a /var alias; the fixture uses its canonical directory.
        self.workspace = Path(temporary.name).resolve()
        self.root = self.workspace / 'root'
        self.root.mkdir()
        git(self.root, 'init', '--quiet')
        ignores = '**/secrets.yaml\n__pycache__/\nconfig/ignored.yaml\n'
        write(self.root, '.gitignore', ignores)
        write(self.root, 'config/configuration.yaml',
              'automation: !include_dir_merge_list automations/\nscript: !include_dir_merge_named scripts/\n')
        write(self.root, 'config/python_scripts/task.py', '# Tracked automation helper.\n')
        write(self.root, 'config/blueprints/automation/.gitkeep', '')
        self.children = {}
        for name in ('automations', 'scripts'):
            child = self.root / 'dependencies' / name
            child.mkdir(parents=True)
            write(child, '.gitignore', ignores)
            payload = [{'alias': f'Rule {i}'} for i in range(130)] if name == 'automations' else {
                f'script_{i}': {'sequence': []} for i in range(54)
            }
            write(child, 'config/rules.yaml', json.dumps(payload))
            if name == 'automations':
                write(child, 'migration/automations.json', json.dumps({'automation_count': len(payload)}))
            else:
                write(child, 'contracts/script-registry.json', json.dumps({'scripts': {key: {} for key in payload}}))
                write(child, 'contracts/reviewed-runtime.json', json.dumps({'retired_scripts': {}}))
            self.children[name] = child
        git(self.root, 'add', '.gitignore', 'config', 'dependencies')
        git(self.root, 'commit', '--quiet', '-m', 'Bundled source fixture')

    def add_ignored_artifacts(self):
        for repository in (self.root, *self.children.values()):
            write(repository, 'config/secrets.yaml', 'ignored credential fixture\n')
            write(repository, 'config/__pycache__/artifact.pyc', 'ignored bytecode fixture\n')
            write(repository, 'config/ignored.yaml', 'ignored configuration fixture\n')
        self.assertEqual(git(self.root, 'status', '--porcelain', '--ignore-submodules=none'), '')

    def run_build(self, *, secrets=None):
        output = self.workspace / 'bundle'
        arguments = ['build-test', str(output)]
        if secrets is not None:
            arguments += ['--secrets', str(secrets)]
        with patch.object(BUILD, 'ROOT', self.root), patch.object(sys, 'argv', arguments), redirect_stdout(io.StringIO()):
            BUILD.main()
        return output

    def test_build_copies_only_tracked_files_from_all_bundled_components(self):
        self.add_ignored_artifacts()
        output = self.run_build()
        self.assertEqual((output / 'python_scripts/task.py').read_text(), '# Tracked automation helper.\n')
        self.assertTrue((output / 'blueprints/automation/.gitkeep').is_file())
        self.assertTrue((output / 'automations/rules.yaml').is_file())
        self.assertTrue((output / 'scripts/rules.yaml').is_file())
        files = {str(path.relative_to(output)) for path in output.rglob('*') if path.is_file()}
        self.assertEqual(files, {
            'configuration.yaml', 'python_scripts/task.py', 'blueprints/automation/.gitkeep',
            'automations/rules.yaml', 'scripts/rules.yaml', 'release.json',
        })
        release = json.loads((output / 'release.json').read_text())
        self.assertEqual(release['root_revision'], git(self.root, 'rev-parse', 'HEAD'))
        self.assertEqual(release['component_revision_type'], 'git-tree')
        for name in self.children:
            self.assertEqual(release['components'][name], git(self.root, 'rev-parse', f'HEAD:dependencies/{name}'))
        # The helper also excludes ordinary untracked files; the CLI separately rejects dirty trees.
        write(self.root, 'config/untracked.yaml', 'unreviewed definition\n')
        copied = self.workspace / 'copied'
        BUILD.copy_tracked_config(self.root, copied)
        self.assertFalse((copied / 'untracked.yaml').exists())
        self.assertTrue((copied / 'configuration.yaml').is_file())

    def test_explicit_external_secrets_are_the_only_credentials_copied(self):
        self.add_ignored_artifacts()
        secrets = self.workspace / 'approved-secrets.yaml'
        secrets.write_text('explicit credential fixture\n')
        output = self.run_build(secrets=secrets)
        self.assertEqual((output / 'secrets.yaml').read_text(), 'explicit credential fixture\n')
        self.assertEqual(stat.S_IMODE((output / 'secrets.yaml').stat().st_mode), 0o600)
        self.assertEqual(list(output.rglob('secrets.yaml')), [output / 'secrets.yaml'])
        git(self.root, 'add', '--force', 'config/secrets.yaml')
        with self.assertRaisesRegex(ValueError, 'supplied explicitly'):
            BUILD.copy_tracked_config(self.root, self.workspace / 'rejected')

    def commit_child_change(self, name):
        git(self.root, 'add', 'dependencies/' + name)
        git(self.root, 'commit', '--quiet', '-m', 'Reviewed component change')

    def test_rejects_uncommitted_component_change(self):
        write(self.children['scripts'], 'config/rules.yaml', '{}')
        with self.assertRaises(SystemExit):
            self.run_build()

    def test_rejects_nested_repository_even_when_root_looks_clean(self):
        git(self.children['scripts'], 'init', '--quiet')
        with self.assertRaises(SystemExit):
            self.run_build()

    def test_build_uses_declared_active_script_inventory_after_retirement(self):
        child = self.children['scripts']
        payload = json.loads((child / 'config/rules.yaml').read_text())
        payload.pop('script_0')
        write(child, 'config/rules.yaml', json.dumps(payload))
        write(child, 'contracts/reviewed-runtime.json', json.dumps({'retired_scripts': {'script_0': {'reason': 'Retired'}}}))
        self.commit_child_change('scripts')
        self.assertEqual(len(json.loads((self.run_build() / 'scripts/rules.yaml').read_text())), 53)

    def test_same_script_count_cannot_hide_a_changed_identifier(self):
        child = self.children['scripts']
        payload = json.loads((child / 'config/rules.yaml').read_text())
        payload['unexpected'] = payload.pop('script_0')
        write(child, 'config/rules.yaml', json.dumps(payload))
        self.commit_child_change('scripts')
        with self.assertRaisesRegex(AssertionError, 'Unexpected folder script inventory'):
            self.run_build()

    def test_rejects_tracked_symlink_file(self):
        outside = self.workspace / 'outside.yaml'
        outside.write_text('outside the repository\n')
        (self.root / 'config/link.yaml').symlink_to(outside)
        git(self.root, 'add', 'config/link.yaml')
        with self.assertRaisesRegex(ValueError, 'Symlink'):
            BUILD.copy_tracked_config(self.root, self.workspace / 'rejected')

    def test_rejects_symlink_in_parent_directory(self):
        original = self.root / 'config/python_scripts'
        outside = self.workspace / 'outside-directory'
        shutil.move(original, outside)
        original.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'Symlink'):
            BUILD.copy_tracked_config(self.root, self.workspace / 'rejected')

if __name__ == '__main__':
    unittest.main()
