"""Exercise attached low-battery triggers in an isolated Home Assistant.

Device services are recorded and acknowledged only in this test's state machine.
The production five-minute trigger/condition windows are asserted, then shortened
in a copy. The periodic recovery trigger remains a real HA time-pattern trigger.
The companion root tests verify the voltage-to-binary-sensor template itself;
these tests deliberately supply its state events rather than reimplement it.
"""
import asyncio
from copy import deepcopy
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
VOLTAGE = 'sensor.battery_voltage'
INVERTER = 'switch.victron_quattro'
OFF_GRID = 'input_boolean.off_grid_mode'
CHARGE_ONLY = 'switch.inverter_only_charging'
# Keep the real event-loop timer comfortably longer than typical loaded-CI
# scheduler stalls. Event-specific tests remove periodic recovery from the
# copied rule, so a generous timeout cannot hide a missing event trigger.
HOLD_SECONDS = 1.0
SHUTDOWN_TIMEOUT = 3.5


@unittest.skipUnless(HA_AVAILABLE, 'Home Assistant runtime is not installed')
class VictronLowBatteryTriggerTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='victron-trigger-test-')
        self.hass = HomeAssistant(self.temp.name)
        loader.async_setup(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self.hass.config.skip_pip = True
        self.assertTrue(await async_load_base_functionality(self.hass))
        self.calls = []
        self.low_durations = []
        self.called = asyncio.Event()
        self.hass.services.async_register('switch', 'turn_off', self.turn_off)
        self.hass.services.async_register('script', 'notify', self.notify)
        self.set(INVERTER, 'on')
        self.set(OFF_GRID, 'on')
        self.set(CHARGE_ONLY, 'on')
        self.battery('52', 'off')

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.temp.cleanup()

    def set(self, entity_id, state):
        self.hass.states.async_set(entity_id, state)

    def battery(self, voltage, low_state):
        self.set(VOLTAGE, voltage)
        self.set(LOW, low_state)

    async def turn_off(self, call):
        targets = call.data['entity_id']
        targets = [targets] if isinstance(targets, str) else targets
        self.assertEqual(targets, [INVERTER])
        self.calls.append((INVERTER, call.service))
        self.low_durations.append(
            (dt_util.utcnow() - self.hass.states.get(LOW).last_changed).total_seconds())
        self.set(INVERTER, 'off')
        self.called.set()

    async def notify(self, call):
        pass

    def rule(self):
        source = yaml.safe_load(next((ROOT / 'config').glob('122_*.yaml')).read_text())[0]
        rule = deepcopy(source)
        low_triggers = [t for t in rule['triggers']
                        if t.get('entity_id') == LOW and t.get('to') == 'on']
        self.assertEqual(len(low_triggers), 1)
        self.assertEqual(low_triggers[0]['for'], {'minutes': 5})
        low_triggers[0]['for'] = {'milliseconds': int(HOLD_SECONDS * 1000)}

        def condition_nodes(items):
            for item in items:
                yield item
                yield from condition_nodes(item.get('conditions', []))

        low_conditions = [c for c in condition_nodes(rule['conditions'])
                          if c.get('entity_id') == LOW and c.get('state') == 'on']
        self.assertEqual(len(low_conditions), 1)
        self.assertEqual(low_conditions[0]['for'], {'minutes': 5})
        low_conditions[0]['for'] = {'milliseconds': int(HOLD_SECONDS * 1000)}
        periodic = [t for t in rule['triggers']
                    if t.get('platform', t.get('trigger')) == 'time_pattern']
        self.assertEqual(len(periodic), 1)
        self.assertEqual(periodic[0].get('minutes'), '/1')
        periodic[0].pop('minutes')
        periodic[0]['seconds'] = '/1'
        return rule

    async def load(self, *, start=True, periodic=False):
        rule = self.rule()
        if not periodic:
            rule['triggers'] = [t for t in rule['triggers']
                                if t.get('platform', t.get('trigger')) != 'time_pattern']
        config = {'automation': [rule]}
        (Path(self.temp.name) / 'configuration.yaml').write_text(yaml.safe_dump(config))
        self.assertTrue(await async_setup_component(self.hass, 'automation', config))
        if start:
            await self.hass.async_start()
        await self.hass.async_block_till_done()
        automations = self.hass.states.async_all('automation')
        self.assertEqual(len(automations), 1)
        self.assertEqual(automations[0].state, 'on')

    async def settle(self, seconds=0):
        if seconds:
            await asyncio.sleep(seconds)
        await self.hass.async_block_till_done()

    async def expect_shutdown(self):
        await asyncio.wait_for(self.called.wait(), SHUTDOWN_TIMEOUT)
        await self.settle()
        self.assertEqual(self.calls, [(INVERTER, 'turn_off')])
        self.assertGreaterEqual(self.low_durations[0], HOLD_SECONDS)

    async def test_fresh_low_state_waits_full_five_minute_window(self):
        await self.load()
        self.battery('49', 'on')
        await self.settle(HOLD_SECONDS / 10)
        self.assertEqual(self.calls, [])
        await self.expect_shutdown()

    async def test_initial_low_state_is_recovered_by_attached_periodic_trigger(self):
        # Start HA first: this rule cannot receive a homeassistant-start event.
        # It also misses the low-state edge, reproducing attach/reload while low.
        await self.hass.async_start()
        self.battery('49', 'on')
        await self.load(start=False, periodic=True)
        await self.expect_shutdown()

    async def test_startup_does_not_bypass_a_new_low_state_window(self):
        self.battery('49', 'on')
        await self.load(periodic=True)
        # The startup event evaluates the same duration guard as other triggers.
        # Periodic recovery supplies the edge the already-low sensor cannot emit.
        elapsed = (dt_util.utcnow() - self.hass.states.get(LOW).last_changed).total_seconds()
        if elapsed < HOLD_SECONDS:
            self.assertEqual(self.calls, [])
        await self.expect_shutdown()

    async def test_real_automation_reload_recovers_without_another_voltage_crossing(self):
        await self.load(periodic=True)
        self.battery('49', 'on')
        await self.settle(HOLD_SECONDS / 10)
        self.assertEqual(self.calls, [])
        await self.hass.services.async_call('automation', 'reload', {}, blocking=True)
        await self.settle()
        await self.expect_shutdown()

    async def test_unavailable_cancels_hold_and_recovered_low_starts_fresh(self):
        await self.load()
        self.battery('49', 'on')
        await self.settle(HOLD_SECONDS / 10)
        self.battery('unavailable', 'off')
        await self.settle(HOLD_SECONDS + 0.05)
        self.assertEqual(self.calls, [])
        self.battery('49', 'on')
        await self.settle(HOLD_SECONDS / 10)
        self.assertEqual(self.calls, [])
        await self.expect_shutdown()

    async def test_rebound_cancels_hold_and_does_not_count_earlier_low_time(self):
        await self.load()
        self.battery('49', 'on')
        await self.settle(HOLD_SECONDS / 10)
        self.battery('50', 'off')
        await self.settle(HOLD_SECONDS + 0.05)
        self.assertEqual(self.calls, [])
        self.battery('49.8', 'on')
        await self.settle(HOLD_SECONDS / 10)
        self.assertEqual(self.calls, [])
        await self.expect_shutdown()

    async def test_off_grid_enabling_rechecks_previously_blocked_low_battery(self):
        self.set(OFF_GRID, 'off')
        await self.load()
        self.battery('49', 'on')
        await self.settle(HOLD_SECONDS + 0.05)
        self.assertEqual(self.calls, [])
        self.set(OFF_GRID, 'on')
        await self.expect_shutdown()

    async def test_off_grid_enabling_does_not_shorten_the_low_battery_window(self):
        self.set(OFF_GRID, 'off')
        await self.load()
        self.battery('49', 'on')
        await self.settle(HOLD_SECONDS / 10)
        self.set(OFF_GRID, 'on')
        await self.settle()
        self.assertEqual(self.calls, [])
        await self.expect_shutdown()

    async def test_charge_only_exemption_removal_rechecks_low_battery(self):
        self.set(OFF_GRID, 'off')
        await self.load()
        self.battery('49', 'on')
        await self.settle(HOLD_SECONDS + 0.05)
        self.assertEqual(self.calls, [])
        self.set(CHARGE_ONLY, 'off')
        await self.expect_shutdown()

    async def test_returning_inverter_is_checked_after_voltage_hold(self):
        self.set(INVERTER, 'unavailable')
        await self.load()
        self.battery('49', 'on')
        await self.settle(HOLD_SECONDS + 0.05)
        self.assertEqual(self.calls, [])
        self.set(INVERTER, 'on')
        await self.expect_shutdown()

    async def test_execution_rechecks_voltage_even_if_low_binary_sensor_lags(self):
        self.set(OFF_GRID, 'off')
        await self.load()
        self.battery('49', 'on')
        await self.settle(HOLD_SECONDS + 0.05)
        # Model the short propagation gap between a fresh voltage report and
        # the derived low sensor updating. The command guard reads voltage too.
        self.set(VOLTAGE, '52')
        self.set(OFF_GRID, 'on')
        await self.settle(0.08)
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
