"""Execute actual shutdown actions with HA conditions and mocked switch I/O."""
from copy import deepcopy
from datetime import timedelta
import os
from pathlib import Path
import tempfile
import unittest

import yaml

try:
    from homeassistant import loader
    from homeassistant.bootstrap import async_load_base_functionality
    from homeassistant.config_entries import ConfigEntries
    from homeassistant.core import Context, HomeAssistant, State
    from homeassistant.helpers import config_validation as cv
    from homeassistant.helpers.script import Script
    from homeassistant.util import dt as dt_util
except ImportError:
    if os.environ.get('REQUIRE_HA_RUNTIME') == '1':
        raise
    HA_AVAILABLE = False
else:
    HA_AVAILABLE = True

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(HA_AVAILABLE, 'Home Assistant runtime is not installed')
class VictronBlackStartTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.hass = HomeAssistant(self.temp.name)
        loader.async_setup(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self.hass.config.skip_pip = True
        self.assertTrue(await async_load_base_functionality(self.hass))
        self.calls = []
        self.decisions = []
        for domain, services in {'switch': ['turn_off', 'turn_on'], 'script': ['notify'], 'input_text': ['set_value']}.items():
            for service in services:
                self.hass.services.async_register(domain, service, self.record)
        self.set('switch.victron_quattro', 'on')
        self.set('switch.inverter_only_charging', 'off')
        self.set('input_boolean.summer', 'off')
        self.set('input_boolean.winter', 'on')
        self.set('input_boolean.off_grid_mode', 'off')
        self.set('sensor.battery_voltage', '49')
        self.set('binary_sensor.victron_battery_low', 'on', changed_age=600)
        self.set('binary_sensor.victron_grid_connected', 'on', changed_age=180)

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.temp.cleanup()

    def set(self, entity, state, *, changed_age=0, report_age=0):
        now = dt_util.utcnow()
        # Insert measured age explicitly; time is never advanced on a real HA.
        self.hass.states._states[entity] = State(
            entity, state, {}, last_changed=now - timedelta(seconds=changed_age),
            last_updated=now - timedelta(seconds=report_age),
            last_reported=now - timedelta(seconds=report_age))

    async def record(self, call):
        if call.domain == 'input_text':
            self.decisions.append(call.data['value'])
            self.assertLessEqual(len(call.data['value']), 255)
        if call.domain == 'switch':
            self.calls.append((call.service, dict(call.data)))

    def rule(self, number):
        return yaml.safe_load(next((ROOT / 'config').glob(f'{number:03d}_*.yaml')).read_text())[0]

    async def run_rule(self, number):
        rule = self.rule(number)
        sequence = [{'condition': 'and', 'conditions': deepcopy(rule['conditions'])}] if rule['conditions'] else []
        sequence += deepcopy(rule['actions'])
        script = Script(self.hass, cv.SCRIPT_SCHEMA(sequence), f'rule-{number}', 'automation')
        await script.async_run({}, context=Context())

    async def test_off_grid_blocks_all_overnight_actions_and_import_shutdown(self):
        for mode in ('on', 'unknown', 'unavailable'):
            for number in (121, 125):
                self.import_scenario()
                self.set('input_boolean.off_grid_mode', mode)
                await self.run_rule(number)
                self.assertEqual(self.calls, [], (mode, number))
        self.hass.states.async_remove('input_boolean.off_grid_mode')
        await self.run_rule(125)
        self.assertEqual(self.calls, [])

    async def test_winter_shutdown_needs_no_grid_or_battery_telemetry(self):
        for grid in ('off', 'unknown', 'unavailable', 'on'):
            self.calls.clear()
            self.set('binary_sensor.victron_grid_connected', grid, changed_age=3600, report_age=3600)
            self.set('sensor.battery_voltage', 'unavailable')
            await self.run_rule(125)
            self.assertEqual([c[0] for c in self.calls], ['turn_off', 'turn_on', 'turn_on'])
            self.assertIn('switch.victron_quattro', self.calls[0][1]['entity_id'])
            self.assertIn('switch.inverter_do_not_supply_ev', self.calls[1][1]['entity_id'])
            self.assertIn('switch.inverter_only_charging', self.calls[2][1]['entity_id'])

    async def test_winter_takes_precedence_over_summer(self):
        self.set('input_boolean.summer', 'on')
        await self.run_rule(125)
        self.assertEqual(len(self.calls), 3)

    async def test_non_winter_voltage_policy_and_summer_opt_out(self):
        self.set('input_boolean.winter', 'off')
        for summer, voltage, expected in (
            ('off', '51.9', 3), ('off', '52', 0), ('off', '54', 0),
            ('on', '49', 0), ('off', '0', 0), ('off', 'nan', 0),
            ('off', 'unavailable', 0), ('off', '-1', 0), ('off', 'inf', 0),
        ):
            self.calls.clear()
            self.set('input_boolean.summer', summer)
            self.set('sensor.battery_voltage', voltage)
            await self.run_rule(125)
            self.assertEqual(len(self.calls), expected, (summer, voltage))

    async def test_unchanged_live_voltage_is_not_treated_as_stale(self):
        # MQTT expire_after handles silence. Unchanged receipts do not advance
        # last_reported, even while the entity remains available.
        self.set('input_boolean.winter', 'off')
        self.set('sensor.battery_voltage', '51', changed_age=3600, report_age=3600)
        await self.run_rule(125)
        self.assertEqual(len(self.calls), 3)

    async def test_already_off_does_not_change_charging_flags(self):
        self.set('switch.victron_quattro', 'off')
        await self.run_rule(125)
        self.assertEqual(self.calls, [])

    async def test_daily_trigger_is_only_00_01(self):
        self.assertEqual(self.rule(125)['triggers'], [{'platform': 'time', 'at': '00:01:00'}])

    def import_scenario(self):
        self.set('switch.inverter_only_charging', 'on')
        self.set('switch.victron_quattro', 'on', changed_age=600)
        self.set('sensor.home_123_1s', '400')
        self.set('sensor.current_solar_production', '0')

    async def test_import_policy_requires_confirmed_grid(self):
        self.import_scenario()
        for grid in ('off', 'unknown', 'unavailable'):
            self.set('binary_sensor.victron_grid_connected', grid, changed_age=600)
            await self.run_rule(121)
            self.assertEqual(self.calls, [], grid)
        self.set('binary_sensor.victron_grid_connected', 'on', changed_age=30)
        await self.run_rule(121)
        self.assertEqual(self.calls, [])

    async def test_import_allows_unchanged_live_grid(self):
        self.import_scenario()
        self.set('binary_sensor.victron_grid_connected', 'on', changed_age=3600, report_age=3600)
        await self.run_rule(121)
        self.assertEqual(len(self.calls), 1)

    async def test_import_policy_requires_current_import_and_solar(self):
        for entity, value in (('sensor.home_123_1s', '400'), ('sensor.current_solar_production', '0')):
            self.import_scenario()
            self.set(entity, value, changed_age=600, report_age=91)
            await self.run_rule(121)
            self.assertEqual(self.calls, [], entity)
        for entity, value in (('sensor.home_123_1s', '0'), ('sensor.current_solar_production', 'unknown')):
            self.import_scenario()
            self.set(entity, value)
            await self.run_rule(121)
            self.assertEqual(self.calls, [], entity)

    async def test_low_battery_exception_in_both_modes_without_grid(self):
        for off_grid in ('off', 'on'):
            for grid in ('off', 'unavailable'):
                self.calls.clear()
                self.set('input_boolean.off_grid_mode', off_grid)
                self.set('binary_sensor.victron_grid_connected', grid)
                self.set('sensor.battery_voltage', '49', changed_age=600, report_age=600)
                await self.run_rule(122)
                self.assertEqual(len(self.calls), 1, (off_grid, grid))
                self.assertEqual(self.calls[0][0], 'turn_off')

    async def test_off_grid_low_battery_overrides_a_leftover_charge_only_flag(self):
        self.set('input_boolean.off_grid_mode', 'on')
        self.set('switch.inverter_only_charging', 'on')
        await self.run_rule(122)
        self.assertEqual(len(self.calls), 1)

    async def test_grid_mode_retains_charge_only_reserve_exemption(self):
        self.set('switch.inverter_only_charging', 'on')
        await self.run_rule(122)
        self.assertEqual(self.calls, [])

    async def test_missing_invalid_or_recovered_voltage_cannot_turn_off(self):
        for value in ('unknown', 'unavailable', '0', '-1', 'nan', 'inf', '71', '50', '52'):
            self.set('input_boolean.off_grid_mode', 'on')
            self.set('sensor.battery_voltage', value)
            await self.run_rule(122)
            self.assertEqual(self.calls, [], value)

    async def test_low_voltage_still_requires_five_minutes(self):
        self.assertEqual(self.rule(122)['triggers'][0]['for'], {'minutes': 5})
        for state, age in (('on', 299), ('off', 600), ('unknown', 600), ('unavailable', 600)):
            self.set('binary_sensor.victron_battery_low', state, changed_age=age)
            await self.run_rule(122)
            self.assertEqual(self.calls, [], (state, age))
        self.set('binary_sensor.victron_battery_low', 'on', changed_age=301)
        await self.run_rule(122)
        self.assertEqual(len(self.calls), 1)

    async def test_skipped_midnight_records_reason_and_operator_context(self):
        self.set('input_boolean.off_grid_mode', 'on')
        await self.run_rule(125)
        self.assertEqual(self.calls, [])
        self.assertEqual(len(self.decisions), 1)
        self.assertIn('skipped: Off-grid mode on', self.decisions[0])
        self.assertIn('off_grid=on', self.decisions[0])
        self.assertIn('winter=on', self.decisions[0])

    async def test_midnight_records_requested_not_confirmed(self):
        await self.run_rule(125)
        self.assertEqual(len(self.decisions), 2)
        self.assertIn('attempting: Winter shutdown', self.decisions[0])
        self.assertIn('requested: Winter shutdown', self.decisions[1])
        self.assertNotIn('confirmed', self.decisions[1])

    async def test_missing_diagnostic_helper_does_not_block_shutdown(self):
        from homeassistant.exceptions import HomeAssistantError
        async def failed_record(call):
            raise HomeAssistantError('Diagnostic helper unavailable')
        self.hass.services.async_register('input_text', 'set_value', failed_record)
        await self.run_rule(125)
        self.assertEqual(len(self.calls), 3)

    async def test_mode_change_during_logging_cannot_turn_a_skip_into_shutdown(self):
        self.set('input_boolean.off_grid_mode', 'on')
        async def changed_mode(call):
            await self.record(call)
            self.set('input_boolean.off_grid_mode', 'off')
        self.hass.services.async_register('input_text', 'set_value', changed_mode)
        await self.run_rule(125)
        self.assertEqual(self.calls, [])
        self.assertIn('skipped: Off-grid mode on', self.decisions[0])

    async def test_off_grid_is_rechecked_after_logging(self):
        async def changed_mode(call):
            await self.record(call)
            self.set('input_boolean.off_grid_mode', 'on')
        self.hass.services.async_register('input_text', 'set_value', changed_mode)
        await self.run_rule(125)
        self.assertEqual(self.calls, [])
        self.assertNotIn('requested:', self.decisions[-1])


if __name__ == '__main__':
    unittest.main()
