"""Regression tests for migration guardrails, with no Home Assistant side effects."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from tools.validate import ValidationError, canonical_runtime, load_yaml, read_scripts, scan_secrets, validate

SOURCE = Path(__file__).resolve().parents[1]

class RepositoryValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for directory in ('config', 'contracts'):
            shutil.copytree(SOURCE / directory, self.root / directory)

    def tearDown(self):
        self.temp.cleanup()

    def test_current_configuration_preserves_50_active_identifiers(self):
        self.assertEqual(validate(self.root)['script_count'], 50)

    def test_retired_script_cannot_return_without_reversing_its_retirement(self):
        registry = json.loads((self.root / 'contracts/script-registry.json').read_text())['scripts']
        baseline = json.loads((self.root / 'contracts/source-baseline.json').read_text())['scripts']
        key = 'your_kodi_script'
        value = dict(baseline[key])
        value.update({field: registry[key][field] for field in ('alias', 'description', 'icon')})
        value.setdefault('mode', 'single')
        (self.root / registry[key]['file']).write_text(json.dumps({key: value}))
        with self.assertRaisesRegex(ValidationError, 'identifiers changed'):
            validate(self.root)

    def test_retirement_cannot_name_an_unknown_script(self):
        path = self.root / 'contracts/reviewed-runtime.json'
        config = json.loads(path.read_text())
        config['retired_scripts']['unknown'] = {'date': '2026-09-22', 'reason': 'test'}
        path.write_text(json.dumps(config))
        with self.assertRaisesRegex(ValidationError, 'unknown script IDs'):
            validate(self.root)

    def test_retirement_requires_an_explanation(self):
        path = self.root / 'contracts/reviewed-runtime.json'
        config = json.loads(path.read_text())
        config['retired_scripts']['your_kodi_script']['reason'] = ''
        path.write_text(json.dumps(config))
        with self.assertRaisesRegex(ValidationError, 'Retirement needs'):
            validate(self.root)

    def test_deleted_script_is_rejected(self):
        (self.root / 'config/notifications/backdoor_motion.yaml').unlink()
        with self.assertRaisesRegex(ValidationError, 'identifiers changed'):
            validate(self.root)

    def test_unreviewed_change_to_reviewed_script_is_rejected(self):
        path = self.root / 'config/notifications/mqtt_message.yaml'
        path.write_text(path.read_text().replace('living_room/notifications', 'different/topic'))
        with self.assertRaisesRegex(ValidationError, 'executable configuration differs'):
            validate(self.root)

    def test_reviewed_contract_cannot_add_identifiers(self):
        path = self.root / 'contracts/reviewed-runtime.json'
        config = json.loads(path.read_text())
        config['scripts']['unreviewed'] = {'sequence': []}
        path.write_text(json.dumps(config))
        with self.assertRaisesRegex(ValidationError, 'unknown script IDs'):
            validate(self.root)

    def test_delay_change_is_rejected(self):
        path = self.root / 'config/notifications/backdoor_motion.yaml'
        path.write_text(path.read_text().replace('00:00:10', '00:00:11'))
        with self.assertRaisesRegex(ValidationError, 'executable configuration differs'):
            validate(self.root)

    def test_duplicate_script_across_files_is_rejected(self):
        shutil.copy(self.root / 'config/notifications/backdoor_motion.yaml', self.root / 'config/duplicate.yaml')
        with self.assertRaisesRegex(ValidationError, 'Duplicate script key'):
            read_scripts(self.root)

    def test_duplicate_nested_yaml_key_is_rejected(self):
        path = self.root / 'duplicate.yaml'
        path.write_text('script:\n  sequence:\n    - data:\n        message: first\n        message: second\n')
        with self.assertRaisesRegex(ValidationError, 'Duplicate YAML key'):
            load_yaml(path)

    def test_unsupported_script_unique_id_is_rejected(self):
        path = self.root / 'config/notifications/backdoor_motion.yaml'
        path.write_text(path.read_text().replace('backdoormotion:\n', 'backdoormotion:\n  unique_id: backdoormotion\n'))
        with self.assertRaisesRegex(ValidationError, 'unsupported script options'):
            read_scripts(self.root)

    def test_yml_extension_is_rejected(self):
        (self.root / 'config/hidden.yml').write_text('hidden: {}\n')
        with self.assertRaisesRegex(ValidationError, 'ignore .yml'):
            read_scripts(self.root)

    def test_payload_alias_is_execution_data(self):
        original = {'sequence': [{'service': 'mqtt.publish', 'data': {'alias': 'a'}}]}
        changed = copy.deepcopy(original)
        changed['sequence'][0]['data']['alias'] = 'b'
        self.assertNotEqual(canonical_runtime(original), canonical_runtime(changed))

    def test_implicit_single_mode_matches_explicit_single(self):
        original = {'sequence': [{'delay': '00:00:01'}]}
        changed = {**original, 'mode': 'single', 'alias': 'Readable name'}
        self.assertEqual(canonical_runtime(original), canonical_runtime(changed))

    def test_scalar_types_are_not_conflated(self):
        self.assertNotEqual(canonical_runtime({'sequence': [{'data': {'value': True}}]}), canonical_runtime({'sequence': [{'data': {'value': 1}}]}))

    def test_secret_value_is_rejected_without_printing_it(self):
        value = 'synthetic-test-value'
        (self.root / 'credential.yaml').write_text('password: ' + value + '\n')
        with self.assertRaises(ValidationError) as error:
            scan_secrets(self.root)
        self.assertNotIn(value, str(error.exception))

    def test_secret_reference_remains_unresolved(self):
        (self.root / 'reference.yaml').write_text('password: !secret device_password\n')
        scan_secrets(self.root)
        self.assertEqual(load_yaml(self.root / 'reference.yaml')['password'], {'__ha_secret_reference__': 'device_password'})

    def test_credential_in_comment_is_rejected(self):
        (self.root / 'comment.md').write_text('# ' + 'ghp_' + 'x' * 36 + '\n')
        with self.assertRaisesRegex(ValidationError, 'possible credential'):
            scan_secrets(self.root)

if __name__ == '__main__':
    unittest.main()
