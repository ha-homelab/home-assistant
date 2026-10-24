"""Retirements must not hide accidental deletion or identity reuse."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from config_contract import fingerprint, read_manifest, seed_value, validate_inventory
from verify_runtime import expected_execution_mode


class InventoryTest(unittest.TestCase):
    def setUp(self):
        self.manifest = deepcopy(read_manifest())
        self.files = [entry['file'] for entry in self.manifest['automations']]

    def test_reviewed_retirements_keep_the_complete_original_inventory(self):
        validate_inventory(self.manifest, self.files)
        self.assertEqual(self.manifest['automation_count'], 97)
        retired = {entry['order'] for entry in self.manifest['retired_automations']}
        active = {entry['order'] for entry in self.manifest['automations']}
        self.assertTrue({69, 98, 106, 110, 111} <= retired)
        self.assertTrue({20, 21, 41, 42} <= active)

    def test_missing_rule_cannot_be_hidden_by_lowering_the_count(self):
        self.manifest['automations'].pop()
        self.manifest['automation_count'] -= 1
        self.files.pop()
        with self.assertRaisesRegex(AssertionError, 'Original automation inventory'):
            validate_inventory(self.manifest, self.files)

    def test_retirement_requires_a_reason(self):
        self.manifest['retired_automations'][0]['retirement']['reason'] = ''
        with self.assertRaisesRegex(AssertionError, 'Retirement needs'):
            validate_inventory(self.manifest, self.files)

    def test_retired_identity_cannot_be_reused(self):
        self.manifest['automations'][0]['id'] = self.manifest['retired_automations'][0]['id']
        with self.assertRaisesRegex(AssertionError, 'Duplicate original id'):
            validate_inventory(self.manifest, self.files)

    def test_identity_seed_keeps_reviewed_queue_and_legacy_alias(self):
        current = {'id': 'stable', 'alias': 'Readable name', 'mode': 'queued',
                   'max': 2, 'triggers': [], 'actions': []}
        entry = {'id': 'stable', 'previous_metadata': {'alias': 'Legacy name', 'mode': 'single'},
                 'previous_top_level_keys': ['alias', 'trigger', 'action'],
                 'behavior_change': 'Reviewed bounded connection bootstrap queue'}
        seeded = seed_value(current, entry)
        self.assertEqual(seeded['alias'], 'Legacy name')
        self.assertEqual(fingerprint(seeded), fingerprint(current))

    def test_identity_seed_does_not_accept_unreviewed_mode_change(self):
        current = {'id': 'stable', 'mode': 'queued', 'max': 2, 'actions': []}
        entry = {'id': 'stable', 'previous_metadata': {'alias': 'Legacy name'},
                 'previous_top_level_keys': ['alias', 'action']}
        self.assertNotEqual(fingerprint(seed_value(current, entry)), fingerprint(current))

    def test_runtime_mode_uses_reviewed_rule_only_after_migration(self):
        entry = next(e for e in self.manifest['automations'] if e['order'] == 118)
        self.assertEqual(expected_execution_mode(entry, 'before'), 'single')
        self.assertEqual(expected_execution_mode(entry, 'seed'), 'queued')
        self.assertEqual(expected_execution_mode(entry, 'final'), 'queued')
        del entry['behavior_change']
        self.assertEqual(expected_execution_mode(entry, 'final'), 'single')
