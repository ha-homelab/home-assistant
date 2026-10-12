"""Real HA template updates and persistent, read-only policy diagnostics."""
import os
from pathlib import Path
import tempfile
import unittest

import yaml

try:
    from homeassistant import loader
    from homeassistant.bootstrap import async_load_base_functionality
    from homeassistant.config_entries import ConfigEntries
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.restore_state import RestoreStateData
    from homeassistant.setup import async_setup_component
    from homeassistant.util import dt as dt_util
except ImportError:
    if os.environ.get('REQUIRE_HA_RUNTIME') == '1':
        raise
    HA_AVAILABLE = False
else:
    HA_AVAILABLE = True

ROOT = Path(__file__).resolve().parents[1]
LOW = 'binary_sensor.victron_battery_low'
POLICY = 'sensor.victron_overnight_policy'
LAST = 'input_text.victron_last_overnight_decision'
NIGHT_RULE = 'automation.daily_at_0_01_am_set_charging_states_and_ensure_victron_off'
LOW_RULE = 'automation.battery_voltage_below_50v_for_five_minutes'


@unittest.skipUnless(HA_AVAILABLE, 'Home Assistant runtime is not installed')
class VictronPolicyTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = yaml.safe_load((ROOT / 'config/packages/victron_policy.yaml').read_text())
        self.hass = await self.create_hass()

    async def create_hass(self, voltage='52'):
        hass = HomeAssistant(self.temp.name)
        loader.async_setup(hass)
        hass.config_entries = ConfigEntries(hass, {})
        hass.config.skip_pip = True
        self.assertTrue(await async_load_base_functionality(hass))
        for entity, value in {
            'sensor.battery_voltage': voltage,
            'input_boolean.off_grid_mode': 'off',
            'input_boolean.winter': 'on',
            'input_boolean.summer': 'off',
            'switch.victron_quattro': 'on',
            'switch.inverter_only_charging': 'off',
            NIGHT_RULE: 'on', LOW_RULE: 'on',
        }.items():
            hass.states.async_set(entity, value)
        for domain in ('input_text', 'template'):
            self.assertTrue(await async_setup_component(hass, domain, self.config))
        await hass.async_start()
        await hass.async_block_till_done()
        return hass

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.temp.cleanup()

    async def update(self, entity, value):
        self.hass.states.async_set(entity, value)
        await self.hass.async_block_till_done()

    async def test_low_sensor_rejects_bad_telemetry_and_resets_its_interval(self):
        for value in ('49', 'unknown', '49', 'unavailable', '49', '0', '-1', 'nan', 'inf', '50', '71'):
            await self.update('sensor.battery_voltage', value)
            self.assertEqual(self.hass.states.get(LOW).state, 'on' if value == '49' else 'off', value)
            if value in ('unknown', 'unavailable', '0', '-1', 'nan', 'inf', '71'):
                self.assertEqual(self.hass.states.get(POLICY).attributes['battery_protection'], 'Waiting for valid battery telemetry')

    async def test_unchanged_voltage_does_not_reset_low_interval(self):
        await self.update('sensor.battery_voltage', '49')
        before = self.hass.states.get(LOW).last_changed
        await self.update('sensor.battery_voltage', '49.1')
        self.assertEqual(self.hass.states.get(LOW).last_changed, before)

    async def test_restart_requires_new_low_interval_and_restores_last_decision(self):
        await self.update('sensor.battery_voltage', '49')
        text = '2026-10-08 00:01:00 | skipped: Off-grid mode on'
        await self.hass.services.async_call('input_text', 'set_value',
            {'entity_id': LAST, 'value': text}, blocking=True)
        await RestoreStateData.async_save_persistent_states(self.hass)
        await self.hass.async_stop(force=True)
        restarted_at = dt_util.utcnow()
        self.hass = await self.create_hass(voltage='49')
        self.assertEqual(self.hass.states.get(LOW).state, 'on')
        self.assertGreaterEqual(self.hass.states.get(LOW).last_changed, restarted_at)
        self.assertEqual(self.hass.states.get(LAST).state, text)
        self.assertEqual(self.hass.states.get(POLICY).attributes['last_overnight_decision'], text)

    async def test_policy_reports_operator_blocks_and_winter_without_voltage(self):
        await self.update('sensor.battery_voltage', 'unavailable')
        self.assertEqual(self.hass.states.get(POLICY).state, 'Winter: off at 00:01')
        await self.update('input_boolean.off_grid_mode', 'on')
        self.assertEqual(self.hass.states.get(POLICY).state, 'Blocked: Off-grid')
        await self.update('input_boolean.off_grid_mode', 'unknown')
        self.assertEqual(self.hass.states.get(POLICY).state, 'Blocked: mode unavailable')
        await self.update('input_boolean.off_grid_mode', 'off')
        await self.update(NIGHT_RULE, 'off')
        self.assertEqual(self.hass.states.get(POLICY).state, 'Automation disabled/unavailable')

    async def test_policy_reports_non_winter_reserve_and_summer(self):
        await self.update('input_boolean.winter', 'off')
        await self.update('sensor.battery_voltage', '51')
        self.assertEqual(self.hass.states.get(POLICY).state, 'Low reserve: off at 00:01')
        await self.update('sensor.battery_voltage', '52')
        self.assertEqual(self.hass.states.get(POLICY).state, 'Skipped: battery at least 52 V')
        await self.update('sensor.battery_voltage', 'unavailable')
        self.assertEqual(self.hass.states.get(POLICY).state, 'Waiting for battery telemetry')
        await self.update('input_boolean.summer', 'on')
        self.assertEqual(self.hass.states.get(POLICY).state, 'Skipped: Summer/unknown season')


if __name__ == '__main__':
    unittest.main()
