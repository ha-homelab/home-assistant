"""Render the actual MQTT/derived battery templates in isolated Home Assistant."""
from pathlib import Path
import json
import os
import tempfile
import unittest

import yaml

try:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.template import Template
except ImportError:
    if os.environ.get('REQUIRE_HA_RUNTIME') == '1':
        raise
    HA_AVAILABLE = False
else:
    HA_AVAILABLE = True

ROOT = Path(__file__).resolve().parents[1]
DISCOVERY = ROOT / 'config/packages/victron_vebus_discovery.yaml'
GRID_CONFIG = 'homeassistant/binary_sensor/victron_grid_connected/config'


@unittest.skipUnless(HA_AVAILABLE, 'Home Assistant runtime is not installed')
class BatteryTelemetryTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.hass = HomeAssistant(self.temp.name)
        mqtt = yaml.safe_load((ROOT / 'config/mqtt.yaml').read_text())
        self.battery = next(s for s in mqtt['sensor'] if s.get('unique_id') == 'battery_voltage')
        self.grid_payload = self.grid_discovery()
        self.grid = {
            'value_template': self.grid_payload['value_template'],
            'availability_template': self.grid_payload['availability'][0]['value_template'],
            'expire_after': self.grid_payload['expire_after'],
        }

    def grid_discovery(self):
        """Render the retained discovery payload the package publishes at runtime."""
        package = yaml.safe_load(DISCOVERY.read_text())
        rule = next(a for a in package['automation']
                    if a['id'] == 'victron_vebus_instance_discovery')
        variables = {}
        for step in rule['actions']:
            variables.update(step.get('variables') or {})
        publish = next(step['data'] for step in rule['actions']
                       if (step.get('data') or {}).get('topic') == GRID_CONFIG)
        values = {'portal': '000000000000', 'instance': '301',
                  'base': 'victron/N/000000000000/vebus/301'}
        for name in ('grid_state', 'grid_availability'):
            values[name] = Template(variables[name], self.hass).async_render()
        # MQTT publishes the rendered text; Home Assistant renders a JSON
        # object template to a wrapper, so ask for the raw text explicitly.
        return json.loads(Template(publish['payload'], self.hass)
                          .async_render(values, parse_result=False))

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.temp.cleanup()

    def render(self, config, key, payload):
        return Template(config[key], self.hass).async_render({'value_json': payload})

    async def test_missing_and_invalid_voltage_is_not_zero(self):
        for value in (None, '', 'unknown', 'unavailable', 'NaN', float('inf'), 0, -1, 71, True, False, {}, []):
            with self.subTest(value=value):
                self.assertIsNone(self.render(self.battery, 'value_template', {'value': value}))
                self.assertEqual(self.render(self.battery, 'availability_template', {'value': value}), 'offline')
        for payload in ({}, None, 'not JSON', []):
            with self.subTest(payload=payload):
                self.assertIsNone(self.render(self.battery, 'value_template', payload))
                self.assertEqual(self.render(self.battery, 'availability_template', payload), 'offline')

    async def test_real_low_voltage_is_preserved(self):
        for voltage in (25.5, 40, 49.2, 52.4, '54.12'):
            self.assertEqual(self.render(self.battery, 'value_template', {'value': voltage}), float(voltage))
            self.assertEqual(self.render(self.battery, 'availability_template', {'value': voltage}), 'online')

    async def test_grid_requires_a_known_binary_measurement(self):
        for value, expected in ((0, 'OFF'), (1, 'ON')):
            self.assertEqual(self.render(self.grid, 'value_template', {'value': value}), expected)
            self.assertEqual(self.render(self.grid, 'availability_template', {'value': value}), 'online')
        for value in (None, True, False, 'NaN', 2, -1, {}, []):
            self.assertEqual(self.render(self.grid, 'availability_template', {'value': value}), 'offline')

    async def test_silence_expires_before_grid_can_arm_shutdown(self):
        # A single replayed retained grid message must expire before the
        # two-minute state condition in the shutdown automations can pass.
        self.assertEqual(self.battery['expire_after'], 90)
        self.assertEqual(self.grid['expire_after'], 90)
        self.assertLess(self.grid['expire_after'], 120)

    async def test_grid_discovery_follows_the_announced_instance(self):
        # Retained discovery owns this entity now: it must keep the reviewed
        # registry identity and follow whatever VE.Bus instance is announced.
        self.assertEqual(self.grid_payload['unique_id'], 'victron_grid_connected')
        self.assertEqual(self.grid_payload['default_entity_id'],
                         'binary_sensor.victron_grid_connected')
        self.assertEqual(self.grid_payload['device_class'], 'connectivity')
        self.assertEqual(self.grid_payload['state_topic'],
                         'victron/N/000000000000/vebus/301/Ac/ActiveIn/Connected')
        self.assertEqual(self.grid_payload['availability'][0]['topic'],
                         self.grid_payload['state_topic'])

    async def test_derived_soc_keeps_unknown_and_real_zero_distinct(self):
        config = next(s for s in yaml.safe_load((ROOT / 'config/template_sensors.yaml').read_text())
                      if s['name'] == 'Battery %')
        for voltage in ('unknown', 'unavailable', '0', 'nan'):
            self.hass.states.async_set('sensor.battery_voltage', voltage)
            self.assertFalse(Template(config['availability'], self.hass).async_render())
            self.assertIsNone(Template(config['state'], self.hass).async_render())
        self.hass.states.async_set('sensor.battery_voltage', '40')
        self.assertTrue(Template(config['availability'], self.hass).async_render())
        self.assertEqual(Template(config['state'], self.hass).async_render(), 0)

    async def test_corrected_soc_falls_back_without_inventing_zero(self):
        sensors = yaml.safe_load((ROOT / 'config/template_sensors.yaml').read_text())
        config = next(s for s in sensors if s.get('unique_id') == 'corrected_battery_soc')
        availability = Template(config['availability'], self.hass)
        state = Template(config['state'], self.hass)
        inputs = (
            'sensor.compensation_sensor_battery_voltage',
            'sensor.battery_w',
            'sensor.smartshunt_500a_50mv_id_289_charge',
        )
        cases = (
            ('80', '280', '100', 75.0),
            ('80', '-180', '100', 85.0),
            ('80', '0', '100', 80.0),
            ('unavailable', 'unavailable', '100', 100.0),
            ('unknown', '-180', '82.7', 82.7),
            ('80', 'unavailable', '100', 100.0),
            ('80', 'unavailable', 'unknown', 80.0),
            ('nan', '0', 'unavailable', None),
            ('unknown', '0', '0', 0.0),
        )
        for estimated, power, measured, expected in cases:
            with self.subTest(estimated=estimated, power=power, measured=measured):
                for entity, value in zip(inputs, (estimated, power, measured), strict=True):
                    self.hass.states.async_set(entity, value)
                self.assertEqual(availability.async_render(), expected is not None)
                self.assertEqual(state.async_render(), expected)


@unittest.skipUnless(HA_AVAILABLE, 'Home Assistant runtime is not installed')
class OffGridRestoreTest(unittest.IsolatedAsyncioTestCase):
    async def test_off_grid_restores_on_and_off_after_restart(self):
        from homeassistant import loader
        from homeassistant.bootstrap import async_load_base_functionality
        from homeassistant.config_entries import ConfigEntries
        from homeassistant.setup import async_setup_component
        from homeassistant.helpers.restore_state import RestoreStateData

        config = yaml.safe_load((ROOT / 'config/input_boolean.yaml').read_text())
        self.assertNotIn('victron_automatic_shutdown_enabled', config)
        self.assertNotIn('initial', config['off_grid_mode'])
        for wanted in ('on', 'off'):
            with self.subTest(wanted=wanted), tempfile.TemporaryDirectory() as tmp:
                for restart in (False, True):
                    hass = HomeAssistant(tmp)
                    loader.async_setup(hass)
                    hass.config_entries = ConfigEntries(hass, {})
                    hass.config.skip_pip = True
                    self.assertTrue(await async_load_base_functionality(hass))
                    try:
                        self.assertTrue(await async_setup_component(hass, 'input_boolean', {
                            'input_boolean': {'off_grid_mode': config['off_grid_mode']}}))
                        await hass.async_block_till_done()
                        if not restart:
                            await hass.services.async_call('input_boolean', 'turn_' + wanted,
                                {'entity_id': 'input_boolean.off_grid_mode'}, blocking=True)
                            await RestoreStateData.async_save_persistent_states(hass)
                        self.assertEqual(hass.states.get('input_boolean.off_grid_mode').state, wanted)
                    finally:
                        await hass.async_stop(force=True)


if __name__ == '__main__':
    unittest.main()
