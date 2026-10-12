"""Run explicit water valve requests in isolated HA with mocked device services.

Only script wait timers use a manually advanced clock. The real 15-second and
five-minute policy windows remain intact; HA still evaluates templates, cancels
waits and calls mocked services. No production devices, network or notifications.
"""
import asyncio
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    import yaml
    from homeassistant import loader
    from homeassistant.bootstrap import async_load_base_functionality
    from homeassistant.config_entries import ConfigEntries
    from homeassistant.const import EVENT_STATE_CHANGED
    from homeassistant.core import HomeAssistant, callback
    from homeassistant.exceptions import HomeAssistantError
    from homeassistant.helpers import script as script_helper
    from homeassistant.setup import async_setup_component
except ImportError:
    if os.environ.get('REQUIRE_HA_RUNTIME') == '1':
        raise
    HA_AVAILABLE = False
else:
    HA_AVAILABLE = True

ROOT = Path(os.environ.get('WATER_TEST_ROOT', Path(__file__).resolve().parents[1]))
if (
    os.environ.get('REQUIRE_PRIVATE_DEPENDENCIES') == '1'
    and not (ROOT / 'dependencies/automations/config').is_dir()
):
    raise RuntimeError('Pinned automation submodule required for HA runtime tests')


class ScriptWaitTimer:
    """A native script timeout callback, scheduled on the test's virtual clock."""

    def __init__(self, test, seconds, callback, args):
        self.test, self.callback, self.args = test, callback, args
        self.deadline = test.elapsed + seconds
        self.cancelled = False
        self.fired = False

    def when(self):
        return self.test.hass.loop.time() + self.deadline - self.test.elapsed

    def cancel(self):
        self.cancelled = True


@unittest.skipUnless(HA_AVAILABLE, 'Requires the deployed Home Assistant runtime')
class WaterValveRecoveryTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='water-valve-test-')
        self.hass = HomeAssistant(self.temp.name)
        loader.async_setup(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self.hass.config.skip_pip = True
        self.assertTrue(await async_load_base_functionality(self.hass))
        self.calls = []
        self.fail_valve = False
        self.auto_pump_ack = True
        for action in ['turn_on', 'turn_off']:
            self.hass.services.async_register('switch', action, self.switch)
        self.hass.services.async_register('script', 'notifymax', self.notify)
        self.set('sensor.water_cm', '25')
        self.set('switch.pump_power_enable', 'off')
        self.set('switch.shutoff_valve', 'unavailable')
        self.config = yaml.safe_load((ROOT / 'config/packages/water_valve_recovery.yaml').read_text())
        sequence = self.config['script']['water_valve_after_pump']['sequence']
        waits = [step for step in sequence if 'wait_template' in step]
        self.assertEqual([step['timeout'] for step in waits], ['00:00:15', '00:05:00'])
        self.elapsed, self.wait_timers = 0, []
        self.script_progress = asyncio.Event()
        call_later = self.hass.loop.call_later

        def schedule(seconds, callback, *args, context=None):
            # Do not replace HA startup, template, service or event-loop timers.
            if callback is script_helper._set_result_unless_done:
                self.assertIn(seconds, (15, 300))
                timer = ScriptWaitTimer(self, seconds, callback, args)
                self.wait_timers.append(timer)
                self.script_progress.set()
                return timer
            return call_later(seconds, callback, *args, context=context)

        timer_patch = patch.object(self.hass.loop, 'call_later', schedule)
        timer_patch.start()
        self.addCleanup(timer_patch.stop)
        self.assertTrue(await async_setup_component(self.hass, 'script', self.config))
        await self.hass.async_start()

        @callback
        def completed(event):
            # HA dispatches unmarked synchronous listeners in its executor.
            # Check before touching Event: an off-loop set can strand its waiter.
            self.assertIs(asyncio.get_running_loop(), self.hass.loop)
            if (event.data['entity_id'] == 'script.water_valve_after_pump'
                    and event.data.get('new_state') is not None
                    and event.data['new_state'].state == 'off'
                    and not self.pending()):
                self.script_progress.set()

        self.addCleanup(self.hass.bus.async_listen(EVENT_STATE_CHANGED, completed))

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.temp.cleanup()

    def set(self, entity, state):
        self.hass.states.async_set(entity, state)

    async def switch(self, call):
        entity = call.data['entity_id']
        entity = entity if isinstance(entity, str) else entity[0]
        self.calls.append((entity, call.service))
        if entity == 'switch.shutoff_valve' and self.fail_valve:
            raise HomeAssistantError('Simulated cloud failure')
        if entity != 'switch.pump_power_enable' or self.auto_pump_ack:
            self.set(entity, call.service.removeprefix('turn_'))

    async def notify(self, call):
        pass

    async def request(self, *, pump='off', valve='on', minimum=1, maximum=26):
        self.script_progress.clear()
        variables = {'pump_state': pump, 'valve_state': valve}
        if minimum is not None:
            variables['min_cm'] = minimum
        if maximum is not None:
            variables['max_cm'] = maximum
        await self.hass.services.async_call('script', 'turn_on', {
            'entity_id': 'script.water_valve_after_pump', 'variables': variables}, blocking=True)
        # Wait for an actual native wait registration or completed script state.
        await asyncio.wait_for(self.script_progress.wait(), timeout=5)

    def pending(self):
        return self.hass.states.get('script.water_valve_after_pump').state == 'on'

    async def settle(self):
        await self.hass.async_block_till_done()

    async def advance(self, seconds):
        self.assertTrue(self.wait_timers, 'Native HA must have scheduled a script wait')
        target = self.elapsed + seconds
        while due := sorted((t for t in self.wait_timers
                             if not t.cancelled and t.deadline <= target),
                            key=lambda t: t.deadline):
            timer = due[0]
            self.elapsed = timer.deadline
            timer.cancel()
            timer.fired = True
            timer.callback(*timer.args)
            await self.settle()
        self.elapsed = target

    async def test_available_valve_gets_one_command(self):
        self.set('switch.shutoff_valve', 'off')
        await self.request()
        await self.settle()
        self.assertEqual(self.calls, [('switch.shutoff_valve', 'turn_on')])
        self.assertFalse(self.pending())

    async def test_completed_event_wakes_an_already_waiting_request(self):
        self.script_progress.clear()
        waiter = asyncio.create_task(self.script_progress.wait())
        self.addCleanup(waiter.cancel)
        await asyncio.sleep(0)
        self.assertFalse(waiter.done())
        state = self.hass.states.get('script.water_valve_after_pump')
        self.assertEqual(state.state, 'off')
        self.hass.bus.async_fire(EVENT_STATE_CHANGED, {
            'entity_id': state.entity_id, 'old_state': None, 'new_state': state,
        })
        await asyncio.wait_for(waiter, timeout=5)

    async def test_already_correct_valve_is_not_called(self):
        self.set('switch.shutoff_valve', 'on')
        await self.request()
        self.assertEqual(self.calls, [])
        self.assertFalse(self.pending())

    async def test_return_at_four_minutes_finishes_original_request(self):
        await self.request()
        timer = self.wait_timers[-1]
        self.assertEqual(timer.deadline, 300)
        await self.advance(240)
        self.assertTrue(self.pending())
        self.assertFalse(timer.fired)
        self.set('switch.shutoff_valve', 'off')
        await self.settle()
        self.assertEqual(self.calls, [('switch.shutoff_valve', 'turn_on')])
        self.assertTrue(timer.cancelled, 'Native completion cancels its pending timeout')
        self.assertFalse(timer.fired)
        await self.advance(60)
        self.assertFalse(timer.fired, 'Cancelled timeout must never run later')
        self.assertEqual(self.calls, [('switch.shutoff_valve', 'turn_on')])

    async def test_timeout_drops_request_permanently(self):
        await self.request()
        timer = self.wait_timers[-1]
        await self.advance(299)
        self.assertTrue(self.pending())
        self.assertFalse(timer.fired)
        await self.advance(1)
        self.assertTrue(timer.fired, 'Exercise HA\'s real timeout callback at five minutes')
        self.assertFalse(self.pending())
        self.set('switch.shutoff_valve', 'off')
        await self.settle()
        self.assertEqual(self.calls, [])

    async def test_water_leaving_original_range_cancels_even_if_it_returns(self):
        await self.request()
        self.set('sensor.water_cm', '26')
        await self.settle()
        self.assertFalse(self.pending())
        self.set('sensor.water_cm', '25')
        self.set('switch.shutoff_valve', 'off')
        await self.settle()
        self.assertEqual(self.calls, [])

    async def test_pump_change_cancels_even_if_it_returns(self):
        await self.request()
        self.set('switch.pump_power_enable', 'on')
        await self.settle()
        self.assertFalse(self.pending())
        self.set('switch.pump_power_enable', 'off')
        self.set('switch.shutoff_valve', 'off')
        await self.settle()
        self.assertEqual(self.calls, [])

    async def test_invalid_or_boundary_low_readings_never_open_valve(self):
        self.set('switch.shutoff_valve', 'off')
        for value in ['unknown', 'unavailable', 'NaN', 'inf', '-inf', '0', '1', '26', '27', '28']:
            with self.subTest(value=value):
                self.set('sensor.water_cm', value)
                await self.request()
                self.assertFalse(self.pending())
                self.assertEqual(self.calls, [])

    async def test_invalid_reading_during_wait_cancels(self):
        await self.request()
        self.set('sensor.water_cm', 'unknown')
        await self.settle()
        self.assertFalse(self.pending())
        self.set('sensor.water_cm', '25')
        self.set('switch.shutoff_valve', 'off')
        await self.settle()
        self.assertEqual(self.calls, [])

    async def test_upper_rule_requires_strictly_above_27_and_running_pump(self):
        self.set('switch.shutoff_valve', 'on')
        self.set('switch.pump_power_enable', 'on')
        for value in ['26', '27']:
            self.set('sensor.water_cm', value)
            await self.request(pump='on', valve='off', minimum=27, maximum=None)
            self.assertEqual(self.calls, [])
        self.set('sensor.water_cm', '28')
        await self.request(pump='on', valve='off', minimum=27, maximum=None)
        self.assertEqual(self.calls, [('switch.shutoff_valve', 'turn_off')])

    async def test_late_pump_acknowledgement_is_allowed_without_retrying_pump(self):
        self.set('switch.pump_power_enable', 'on')
        self.set('switch.shutoff_valve', 'off')
        await self.request()
        self.assertTrue(self.pending())
        self.set('switch.pump_power_enable', 'off')
        await self.settle()
        self.assertEqual(self.calls, [('switch.shutoff_valve', 'turn_on')])

    async def test_missing_pump_acknowledgement_expires(self):
        self.set('switch.pump_power_enable', 'on')
        self.set('switch.shutoff_valve', 'off')
        await self.request()
        self.assertEqual(self.wait_timers[-1].deadline, 15)
        await self.advance(15)
        self.assertFalse(self.pending())
        self.set('switch.pump_power_enable', 'off')
        await self.settle()
        self.assertEqual(self.calls, [])

    async def test_completed_request_does_not_undo_manual_or_flo_closure(self):
        self.set('switch.shutoff_valve', 'off')
        await self.request()
        self.set('switch.shutoff_valve', 'off')
        await self.settle()
        self.assertEqual(self.calls, [('switch.shutoff_valve', 'turn_on')])
        self.assertEqual(self.hass.states.get('switch.shutoff_valve').state, 'off')

    async def test_failed_service_is_not_retried_after_manual_or_safety_state_changes(self):
        self.fail_valve = True
        self.set('switch.shutoff_valve', 'off')
        await self.request()
        self.assertFalse(self.pending())
        self.set('switch.shutoff_valve', 'unavailable')
        self.set('switch.shutoff_valve', 'off')
        await self.settle()
        self.assertEqual(self.calls, [('switch.shutoff_valve', 'turn_on')])

    async def test_high_power_requests_preserve_their_own_level_limits(self):
        for minimum, maximum, valid, boundary in [(5, 19, '18', '19'), (None, 23, '22', '23')]:
            with self.subTest(maximum=maximum):
                self.set('sensor.water_cm', valid)
                self.set('switch.shutoff_valve', 'unavailable')
                await self.request(minimum=minimum, maximum=maximum)
                self.assertTrue(self.pending())
                self.set('sensor.water_cm', boundary)
                await self.settle()
                self.assertFalse(self.pending())
                self.set('switch.shutoff_valve', 'off')
                await self.settle()
                self.assertEqual(self.calls, [])

    async def test_new_opposite_command_replaces_pending_request(self):
        await self.request()
        self.assertTrue(self.pending())
        self.set('sensor.water_cm', '28')
        self.set('switch.pump_power_enable', 'on')
        self.set('switch.shutoff_valve', 'on')
        await self.request(pump='on', valve='off', minimum=27, maximum=None)
        await self.settle()
        self.assertEqual(self.calls, [('switch.shutoff_valve', 'turn_off')])
        self.assertFalse(self.pending())

    async def test_unavailable_request_does_not_block_later_pump_shutdown(self):
        directory = ROOT / 'dependencies/automations/config'
        if not directory.is_dir():
            self.skipTest('Private automation submodule required')
        configs = [yaml.safe_load(next(directory.glob(f'{n:03d}_*.yaml')).read_text())[0]
                   for n in [128, 129]]
        self.set('sensor.water_cm', '26')
        self.set('switch.pump_power_enable', 'off')
        self.assertTrue(await async_setup_component(self.hass, 'automation', {'automation': configs}))
        async def wait_for_stage(expected_calls, *, pending):
            # A global HA task drain also waits for the deliberately pending
            # five-minute valve request. Observe the caller and native wait
            # instead, without advancing or shortening the policy timers.
            async def stage_ready():
                while True:
                    automations = self.hass.states.async_all('automation')
                    if (self.calls == expected_calls and self.pending() == pending
                            and len(automations) == len(configs)
                            and all(a.attributes['current'] == 0 for a in automations)
                            and (not pending or any(not t.cancelled for t in self.wait_timers))):
                        return
                    await asyncio.sleep(0.01)
            await asyncio.wait_for(stage_ready(), timeout=5)

        self.set('sensor.water_cm', '28')
        await wait_for_stage([('switch.pump_power_enable', 'turn_on')], pending=True)
        self.assertEqual(self.calls, [('switch.pump_power_enable', 'turn_on')])
        self.assertTrue(self.pending())
        for automation in self.hass.states.async_all('automation'):
            self.assertEqual(automation.attributes['current'], 0)
        self.set('sensor.water_cm', '25')
        await wait_for_stage([
            ('switch.pump_power_enable', 'turn_on'), ('switch.pump_power_enable', 'turn_off'),
        ], pending=True)
        self.assertEqual(self.calls, [('switch.pump_power_enable', 'turn_on'), ('switch.pump_power_enable', 'turn_off')])
        self.set('switch.shutoff_valve', 'off')
        await wait_for_stage([
            ('switch.pump_power_enable', 'turn_on'), ('switch.pump_power_enable', 'turn_off'),
            ('switch.shutoff_valve', 'turn_on'),
        ], pending=False)
        self.assertEqual(self.calls[-1], ('switch.shutoff_valve', 'turn_on'))

    async def test_high_water_does_not_restart_a_manually_or_protectively_stopped_pump(self):
        directory = ROOT / 'dependencies/automations/config'
        if not directory.is_dir():
            self.skipTest('Private automation submodule required')
        config = yaml.safe_load(next(directory.glob('129_*.yaml')).read_text())[0]
        self.set('sensor.water_cm', '28')
        self.set('switch.pump_power_enable', 'on')
        self.assertTrue(await async_setup_component(self.hass, 'automation', {'automation': [config]}))
        self.set('switch.pump_power_enable', 'off')
        self.set('sensor.water_cm', '29')
        self.set('switch.shutoff_valve', 'off')
        await self.settle()
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
