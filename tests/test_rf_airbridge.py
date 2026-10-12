"""Verify the RF package in isolated Home Assistant; never contact real radio.

The transmit service is mocked. Receive matching uses the actual HA template
engine with representative malformed and nonmatching MQTT payloads.
"""
import json
import os
from copy import deepcopy
from pathlib import Path
import re
import tempfile
import unittest

import yaml

try:
    from homeassistant import loader
    from homeassistant.bootstrap import async_load_base_functionality
    from homeassistant.config import async_hass_config_yaml, merge_packages_config
    from homeassistant.config_entries import ConfigEntries
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.selector import validate_selector
    from homeassistant.helpers.template import Template
    from homeassistant.setup import async_setup_component
    import voluptuous as vol
except ImportError:
    if os.environ.get('REQUIRE_HA_RUNTIME') == '1':
        raise
    HA_AVAILABLE = False
else:
    HA_AVAILABLE = True

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(HA_AVAILABLE, 'Requires the deployed Home Assistant runtime')
class RFAirbridgeTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='rf-airbridge-test-')
        self.hass = HomeAssistant(self.temp.name)
        loader.async_setup(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self.hass.config.skip_pip = True
        self.assertTrue(await async_load_base_functionality(self.hass))
        source = (ROOT / 'config/packages/rf_airbridge.yaml').read_text()
        self.package = yaml.safe_load(source)
        # Use HA's actual YAML include and recursive package merge. Directly
        # loading the package into script setup misses empty-selector removal.
        package_dir = Path(self.temp.name) / 'packages'
        package_dir.mkdir()
        (package_dir / 'rf_airbridge.yaml').write_text(source)
        (Path(self.temp.name) / 'configuration.yaml').write_text(
            'homeassistant:\n  packages: !include_dir_named packages\n'
            'script: {}\n'
        )
        self.config = await async_hass_config_yaml(self.hass)
        condition = self.config['automation'][0]['conditions'][0]['value_template']
        self.receive = Template(condition, self.hass)
        self.reject_transmit = Template(
            self.config['script']['rf_send_code']['sequence'][0]['if'][0]['value_template'],
            self.hass,
        )
        # Keep the private RF identity in the package rather than duplicating it.
        self.packet = {
            'source': 'rf', 'origin': 'radio', 'format': 'rc_switch',
            'protocol': int(re.search(r"packet.get\('protocol'\) == (\d+)", condition)[1]),
            'bits': int(re.search(r"packet.get\('bits'\) == (\d+)", condition)[1]),
            'code': re.search(r"packet.get\('code'\) == '([01]+)'", condition)[1],
        }
        self.calls = []
        self.hass.services.async_register('esphome', 'rf_send_rf_code', self.transmit)
        self.assertTrue(await async_setup_component(self.hass, 'script', self.config))
        await self.hass.async_start()
        self.assertTrue(self.hass.services.has_service('script', 'rf_send_code'))

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.temp.cleanup()

    async def transmit(self, call):
        self.calls.append(dict(call.data))

    def matches(self, payload):
        return self.receive.async_render({'trigger': {'payload': payload}})

    async def send(self, **fields):
        await self.hass.services.async_call('script', 'rf_send_code', fields, blocking=True)

    async def test_exact_matching_payload_and_observation_metadata(self):
        self.assertTrue(self.matches(json.dumps(self.packet)))
        self.assertTrue(self.matches(json.dumps(dict(self.packet, event_id='test', sequence=19, uptime_ms=1000))))
        self.assertEqual(len(self.packet['code']), self.packet['bits'])

    async def test_malformed_and_nonmatching_events_are_ignored(self):
        for raw in ('not JSON', '', 'null', '[]', '"text"', '1', 'true', '{}'):
            with self.subTest(raw=raw):
                self.assertFalse(self.matches(raw))
        alternatives = {
            'source': ['other', None], 'origin': ['transmit', None],
            'format': ['raw', None],
            'protocol': [99, str(self.packet['protocol']), True, float(self.packet['protocol']), None],
            'bits': [self.packet['bits'] - 1, str(self.packet['bits']), float(self.packet['bits']), None],
            'code': [self.packet['code'][:-1], 'not binary', 123, None],
        }
        for key, values in alternatives.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    self.assertFalse(self.matches(json.dumps(dict(self.packet, **{key: value}))))
            packet = dict(self.packet)
            del packet[key]
            with self.subTest(missing=key):
                self.assertFalse(self.matches(json.dumps(packet)))

    async def test_receive_action_is_counter_only_with_bounded_interval(self):
        automation = self.config['automation'][0]
        self.assertNotIn('counter', self.config)
        self.assertEqual(automation['mode'], 'single')
        self.assertEqual(automation['actions'], [
            {'action': 'counter.increment', 'target': {'entity_id': 'counter.rf_received_example'}},
            {'delay': {'milliseconds': 750}},
        ])

    async def test_nonempty_text_selector_survives_real_package_merge(self):
        selector = self.config['script']['rf_send_code']['fields']['code']['selector']
        self.assertEqual(selector['text'], {'multiline': False})
        self.assertNotEqual(self.hass.states.get('script.rf_send_code').state, 'unavailable')

    async def test_old_empty_selector_reproduces_package_merge_failure(self):
        broken = deepcopy(self.package)
        broken['script']['rf_send_code']['fields']['code']['selector']['text'] = {}
        merged = await merge_packages_config(self.hass, {}, {'broken_rf_example': broken})
        selector = merged['script']['rf_send_code']['fields']['code']['selector']
        self.assertEqual(selector, {})
        with self.assertRaisesRegex(vol.Invalid, 'Only one type can be specified'):
            validate_selector(selector)

    async def test_transmit_preserves_leading_zeroes_and_defaults_repeats(self):
        code = '000000010010001101000101'
        await self.send(code=code, protocol=1)
        self.assertEqual(self.calls, [{'code': code, 'protocol': 1, 'repeats': 3}])

    async def test_transmit_accepts_supported_boundaries(self):
        for code, protocol, repeats in [('00000000', 1, 1), ('0' + '1' * 63, 8, 10)]:
            await self.send(code=code, protocol=protocol, repeats=repeats)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.calls[-1], {'code': '0' + '1' * 63, 'protocol': 8, 'repeats': 10})

    async def test_invalid_transmit_inputs_never_reach_native_action(self):
        valid = {'code': '000000010010001101000101', 'protocol': 1, 'repeats': 3}
        alternatives = {
            'code': ['', '0' * 7, '1' * 65, '00000002', '00000000\n', ' 00000000', 12345678, None, True],
            'protocol': [0, 9, -1, 1.5, 'no', True, False, None],
            'repeats': [0, 11, -1, 2.5, 'no', True, False, None],
        }
        for key, values in alternatives.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    fields = dict(valid, **{key: value})
                    self.assertTrue(self.reject_transmit.async_render(fields))
                    # HA records stop/error as an aborted script; the top-level
                    # service call can return normally. Verify the output gate.
                    await self.send(**fields)
                    self.assertEqual(self.calls, [])
        for key in ('code', 'protocol'):
            fields = dict(valid)
            del fields[key]
            with self.subTest(missing=key):
                self.assertTrue(self.reject_transmit.async_render(fields))
                await self.send(**fields)
                self.assertEqual(self.calls, [])
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
