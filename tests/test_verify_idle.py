"""Verify the offline idle gate through its command-line interface."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


TOOL = Path(__file__).resolve().parents[1] / 'tools/verify_idle.py'


class VerifyIdleTest(unittest.TestCase):
    def check_states(self, states):
        with tempfile.TemporaryDirectory(prefix='ha-idle-test-') as directory:
            export = Path(directory) / 'states.json'
            export.write_text(json.dumps(states))
            return subprocess.run([sys.executable, str(TOOL), str(export)], capture_output=True, text=True)

    def test_disabled_automation_and_idle_entities_pass_without_output(self):
        result = self.check_states([
            {'entity_id': 'automation.disabled', 'state': 'off', 'attributes': {'current': 0}},
            {'entity_id': 'automation.enabled', 'state': 'on', 'attributes': {'current': 0}},
            {'entity_id': 'script.idle', 'state': 'off', 'attributes': {}},
            {'entity_id': 'sensor.unrelated', 'state': 'on', 'attributes': {'current': 5}},
        ])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '')
        self.assertEqual(result.stderr, '')

    def test_running_script_without_current_is_detected(self):
        result = self.check_states([
            {'entity_id': 'script.running', 'state': 'on',
             'attributes': {'friendly_name': 'This label must not be printed'}},
        ])
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, 'script.running\n')
        self.assertEqual(result.stderr, '')

    def test_invalid_counts_never_report_an_idle_system(self):
        for current in [float('nan'), float('inf'), float('-inf'), -1, -0.5, True, False, '0', None]:
            with self.subTest(current=current):
                result = self.check_states([
                    {'entity_id': 'automation.invalid', 'state': 'on',
                     'attributes': {'current': current}},
                ])
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '')
                self.assertIn('invalid running-action count', result.stderr)

    def test_huge_positive_integer_still_reports_running(self):
        result = self.check_states([
            {'entity_id': 'automation.running', 'state': 'on',
             'attributes': {'current': 10 ** 400}},
        ])
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, 'automation.running\n')

    def test_running_queued_automation_is_detected(self):
        result = self.check_states([
            {'entity_id': 'automation.queued', 'state': 'on',
             'attributes': {'mode': 'queued', 'current': 2}},
        ])
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, 'automation.queued\n')
        self.assertEqual(result.stderr, '')


if __name__ == '__main__':
    unittest.main()
