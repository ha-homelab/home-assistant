"""Control requests must preserve stable IDs and reject incomplete target groups."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('kodi_ha', ROOT / 'tools/kodi_ha.py')
ha = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ha)
COMMANDS = json.loads((ROOT / 'tools/kodi_ha_commands.json').read_text())


class FakeClient(ha.Client):
    def __init__(self, states=None, entries=None):
        self.states, self.entries, self.calls = states or {}, entries or [], []

    def request(self, method, path, data=None):
        self.calls.append((method, path, data))
        if path.startswith('states/'):
            if path[7:] not in self.states:
                raise ha.ClientError('Missing entity')
            return self.states[path[7:]]
        if path.startswith('config/config_entries/entry?'):
            return self.entries
        return {}


class KodiHaTests(unittest.TestCase):
    def test_full_group_is_checked_before_control(self):
        client = FakeClient({'switch.audio_l': {'state': 'off'}})
        group = {'group': {'service': 'switch.toggle', 'entities': ['switch.audio_l', 'switch.example']}}
        with self.assertRaises(ha.ClientError):
            ha.run_alias(client, 'group', group)
        self.assertFalse(any(method == 'POST' for method, _, _ in client.calls))

    def test_unavailable_group_member_prevents_all_control(self):
        client = FakeClient({'switch.audio_l': {'state': 'off'}, 'switch.example': {'state': 'unavailable'}})
        group = {'group': {'service': 'switch.toggle', 'entities': ['switch.audio_l', 'switch.example']}}
        with self.assertRaises(ha.ClientError):
            ha.run_alias(client, 'group', group)
        self.assertFalse(any(method == 'POST' for method, _, _ in client.calls))

    def test_clean_name_does_not_change_entity_id(self):
        client = FakeClient({'light.porch_one': {'state': 'off', 'attributes': {'friendly_name': 'Porch Light'}}})
        result = ha.run_alias(client, 'po', COMMANDS)
        self.assertEqual(client.calls[-1], ('POST', 'services/light/toggle', {'entity_id': ['light.porch_one']}))
        self.assertEqual(result['targets'][0]['name'], 'Porch Light')

    def test_dry_run_has_no_post(self):
        client = FakeClient({'light.porch_one': {'state': 'off'}})
        result = ha.run_alias(client, 'po', COMMANDS, dry_run=True)
        self.assertTrue(result['dry_run'])
        self.assertFalse(any(method == 'POST' for method, _, _ in client.calls))

    def test_retired_commands_have_no_requests(self):
        for alias, command in COMMANDS.items():
            if 'retired' in command:
                client = FakeClient()
                with self.assertRaises(ha.ClientError):
                    ha.run_alias(client, alias, COMMANDS)
                self.assertEqual(client.calls, [])

    def test_reload_uses_current_enabled_registration(self):
        client = FakeClient(entries=[{'domain': 'localtuya', 'entry_id': 'old', 'disabled_by': 'user'},
                                     {'domain': 'localtuya', 'entry_id': 'current', 'disabled_by': None}])
        ha.run_alias(client, 'T', COMMANDS)
        self.assertEqual(client.calls[-1], ('POST', 'config/config_entries/entry/current/reload', {}))

    def test_ambiguous_reload_does_not_guess(self):
        client = FakeClient(entries=[{'domain': 'mqtt', 'entry_id': 'one'}, {'domain': 'mqtt', 'entry_id': 'two'}])
        with self.assertRaises(ha.ClientError):
            ha.run_alias(client, 'M', COMMANDS)
        self.assertFalse(any(method == 'POST' for method, _, _ in client.calls))

    def test_audio_shortcuts_only_control_audio(self):
        for alias, service in [('aa', 'toggle'), ('aaf', 'turn_off')]:
            client = FakeClient({'switch.audio_l': {'state': 'off'}})
            ha.run_alias(client, alias, COMMANDS)
            self.assertEqual(client.calls[-1], ('POST', 'services/switch/' + service,
                                                {'entity_id': ['switch.audio_l']}))

    def test_removed_lamp_shortcuts_make_no_requests(self):
        for alias in ('aaa', 'al-o-mbp', 'al-o-mbpf'):
            client = FakeClient()
            with self.assertRaises(ha.ClientError):
                ha.run_alias(client, alias, COMMANDS)
            self.assertEqual(client.calls, [])

    def test_restart_service_uses_rest_path(self):
        client = FakeClient()
        ha.run_alias(client, 'harestart', COMMANDS)
        self.assertEqual(client.calls, [('POST', 'services/homeassistant/restart', {})])

    def test_redirect_never_forwards_credentials(self):
        self.assertIsNone(ha.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.example/'))


if __name__ == '__main__':
    unittest.main()
