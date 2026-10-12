"""Render the actual MQTT/derived battery templates in isolated Home Assistant."""
from pathlib import Path
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


@unittest.skipUnless(HA_AVAILABLE, 'Home Assistant runtime is not installed')
class BatteryTelemetryTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.hass = HomeAssistant(self.temp.name)
        mqtt = yaml.safe_load((ROOT / 'config/mqtt.yaml').read_text())
        self.battery = next(s for s in mqtt['sensor'] if s.get('unique_id') == 'battery_voltage')
        self.grid = next(s for s in mqtt['binary_sensor'] if s.get('unique_id') == 'victron_grid_connected')

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
