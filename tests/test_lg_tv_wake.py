"""Exercise ESPHome WOL and LG wake fallback without network or real devices."""
import asyncio
import os
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

import yaml

try:
    from homeassistant import loader
    from homeassistant.bootstrap import async_load_base_functionality
    from homeassistant.components.automation.config import async_validate_config_item
    from homeassistant.config_entries import ConfigEntries
    from homeassistant.core import Context, HomeAssistant
    from homeassistant.exceptions import HomeAssistantError
    from homeassistant.helpers.script import Script
    from homeassistant.helpers.trace import script_execution_get, trace_clear
    from homeassistant.setup import async_setup_component
except ImportError:
    if os.environ.get('REQUIRE_HA_RUNTIME') == '1':
        raise
    HA_AVAILABLE = False
else:
    HA_AVAILABLE = True

ROOT = Path(__file__).resolve().parents[1]
TV = 'media_player.living_room_tv_77'
POWER = 'switch.living_tv_guard'
GRACE = 'timer.living_room_tv_wake_grace'


@unittest.skipUnless(HA_AVAILABLE, 'Requires the installed Home Assistant runtime')
class LGWakeTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='lg-wake-test-')
        self.hass = HomeAssistant(self.temp.name)
        loader.async_setup(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self.hass.config.skip_pip = True
        self.assertTrue(await async_load_base_functionality(self.hass))
        self.hass.states.async_set(TV, 'off')
        self.hass.states.async_set(POWER, 'on')
        self.events = []
        self.wol_sent = asyncio.Event()
        self.power_requested = asyncio.Event()
        self.power_confirms = True
        self.power_raises = False
        self.power_release = None
        self.power_boots_tv = False
        self.wol_raises = False
        self.wol_wakes = False
        self.wol_delay = 0
        self.wol_release = None
        self.ir_wakes = True
        self.hass.services.async_register('esphome', 'rf_wake_living_tv', self.wake)
        self.hass.services.async_register('remote', 'send_command', self.remote)
        self.hass.services.async_register('switch', 'turn_on', self.power_on)
        package = yaml.safe_load((ROOT / 'config/packages/lg_tv_wake_on_lan.yaml').read_text())
        self.assertNotIn('shell_command', package)
        self.assertEqual(package['timer']['living_room_tv_wake_grace'], {
            'name': 'Living room TV wake grace', 'duration': '00:02:00', 'restore': False})
        self.assertTrue(await async_setup_component(self.hass, 'timer', {'timer': package['timer']}))
        self.assertTrue(await async_setup_component(self.hass, 'script', {'script': package['script']}))
        await self.hass.async_block_till_done()
        rule = package['automation'][0]
        self.assertEqual(rule['triggers'], [{'trigger': 'webostv.turn_on', 'entity_id': TV}])
        self.assertEqual(rule['mode'], 'single')
        self.assertEqual(rule['id'], 'living_room_tv_wake_on_lan')
        runtime = deepcopy(rule)

        def shorten_waits(value):
            if isinstance(value, list):
                for item in value:
                    shorten_waits(item)
            elif isinstance(value, dict):
                if 'wait_template' in value:
                    self.assertIn(value['timeout'], ('00:00:10', '00:00:30', '00:00:45'))
                    value['timeout'] = {'milliseconds': 100 if value['timeout'] == '00:00:30' else 50}
                for item in value.values():
                    shorten_waits(item)

        shorten_waits(runtime['actions'])
        config = await async_validate_config_item(self.hass, 'automation', runtime)
        self.script = Script(self.hass, config['actions'], config['alias'], 'automation',
                             script_mode=config['mode'])

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.temp.cleanup()

    async def wake(self, call):
        self.assertEqual(dict(call.data), {})
        self.events.append('wol')
        self.wol_sent.set()
        if self.wol_release is not None:
            await self.wol_release.wait()
        if self.wol_raises:
            raise HomeAssistantError('Simulated ESPHome API failure')
        if self.wol_wakes:
            if self.wol_delay:
                async def wake_later():
                    await asyncio.sleep(self.wol_delay)
                    self.hass.states.async_set(TV, 'on')
                self.hass.async_create_task(wake_later())
            else:
                self.hass.states.async_set(TV, 'on')

    async def remote(self, call):
        self.events.append('ir')
        self.assertEqual(dict(call.data), {
            'entity_id': ['remote.harmonyhub'], 'device': 'LG TV', 'command': 'PowerOn'})
        if self.ir_wakes:
            self.hass.states.async_set(TV, 'on')

    async def power_on(self, call):
        self.assertEqual(dict(call.data), {'entity_id': [POWER]})
        self.events.append('power')
        self.power_requested.set()
        if self.power_release is not None:
            await self.power_release.wait()
        if self.power_raises:
            raise HomeAssistantError('Simulated outlet API failure')
        if self.power_confirms:
            self.hass.states.async_set(POWER, 'on')
            if self.power_boots_tv:
                self.hass.states.async_set(TV, 'on')

    async def run_wake(self):
        trace_clear()
        await self.script.async_run(context=Context())
        self.execution = script_execution_get()

    async def test_confirmed_wol_does_not_send_ir(self):
        self.wol_wakes = True
        await self.run_wake()
        self.assertEqual(self.events, ['wol'])
        self.assertEqual(self.execution, 'finished')

    async def test_delayed_confirmation_prevents_ir_fallback(self):
        self.wol_wakes = True
        self.wol_delay = 0.005
        await self.run_wake()
        self.assertEqual(self.events, ['wol'])
        self.assertEqual(self.hass.states.get(TV).state, 'on')

    async def test_missing_esphome_action_still_falls_back_to_discrete_power_on(self):
        self.hass.services.async_remove('esphome', 'rf_wake_living_tv')
        await self.run_wake()
        self.assertEqual(self.events, ['ir'])
        self.assertEqual(self.hass.states.get(TV).state, 'on')
        self.assertEqual(self.execution, 'finished')

    async def test_esphome_exception_still_falls_back(self):
        self.wol_raises = True
        await self.run_wake()
        self.assertEqual(self.events, ['wol', 'ir'])

    async def test_successful_packet_send_without_tv_confirmation_falls_back(self):
        await self.run_wake()
        self.assertEqual(self.events, ['wol', 'ir'])

    async def test_slow_esphome_call_cannot_delay_harmony_fallback(self):
        self.wol_release = asyncio.Event()
        try:
            await asyncio.wait_for(self.run_wake(), timeout=2)
            self.assertEqual(self.events, ['wol', 'ir'])
            self.assertEqual(self.execution, 'finished')
        finally:
            self.wol_release.set()
            await self.hass.async_block_till_done()

    async def test_failed_both_paths_is_not_reported_as_success(self):
        self.ir_wakes = False
        await self.run_wake()
        # Top-level HA scripts record stop(error=true) without propagating it.
        self.assertEqual(self.execution, 'aborted')
        self.assertEqual(self.events, ['wol', 'ir'])
        self.assertEqual(self.hass.states.get(TV).state, 'off')

    async def test_missing_action_and_unconfirmed_ir_aborts(self):
        self.hass.services.async_remove('esphome', 'rf_wake_living_tv')
        self.ir_wakes = False
        await self.run_wake()
        self.assertEqual(self.events, ['ir'])
        self.assertEqual(self.execution, 'aborted')

    async def test_unknown_tv_state_is_not_success(self):
        self.hass.states.async_set(TV, 'unknown')
        self.ir_wakes = False
        await self.run_wake()
        self.assertEqual(self.events, ['wol', 'ir'])
        self.assertEqual(self.execution, 'aborted')

    async def test_unavailable_tv_can_recover_through_harmony(self):
        self.hass.states.async_set(TV, 'unavailable')
        await self.run_wake()
        self.assertEqual(self.events, ['wol', 'ir'])
        self.assertEqual(self.execution, 'finished')

    async def test_already_on_is_untouched(self):
        for state in ('on', 'playing', 'paused', 'idle', 'buffering'):
            with self.subTest(state=state):
                self.hass.states.async_set(TV, state)
                await self.run_wake()
                self.assertEqual(self.events, [])

    async def test_duplicate_requests_do_not_send_duplicate_wake_commands(self):
        first = asyncio.create_task(self.run_wake())
        await asyncio.wait_for(self.wol_sent.wait(), timeout=2)
        first_deadline = self.hass.states.get(GRACE).attributes['finishes_at']
        await self.run_wake()
        self.assertEqual(self.hass.states.get(GRACE).attributes['finishes_at'], first_deadline)
        await first
        self.assertEqual(self.events, ['wol', 'ir'])


    async def test_cold_wake_restores_power_despite_sticky_and_waits_before_wol(self):
        self.hass.states.async_set(POWER, 'off')
        for room in ('living_room', 'dining_room'):
            self.hass.states.async_set(f'input_boolean.{room}_sticky', 'on')
        self.wol_wakes = True
        task = asyncio.create_task(self.run_wake())
        await asyncio.wait_for(self.power_requested.wait(), timeout=2)
        await asyncio.sleep(.02)
        self.assertEqual(self.events, ['power'])
        self.assertEqual(self.hass.states.get(POWER).state, 'on')
        self.assertEqual(self.hass.states.get(GRACE).state, 'active')
        await task
        self.assertEqual(self.events, ['power', 'wol'])
        self.assertEqual(self.execution, 'finished')
        self.assertEqual(self.hass.states.get('input_boolean.living_room_sticky').state, 'on')

    async def test_tv_starting_with_power_needs_no_wake_packet(self):
        self.hass.states.async_set(POWER, 'off')
        self.power_boots_tv = True
        await self.run_wake()
        self.assertEqual(self.events, ['power'])
        self.assertEqual(self.execution, 'finished')

    async def test_new_request_uses_fixed_grace_not_a_previously_changed_timer(self):
        await self.hass.services.async_call('timer', 'start',
            {'entity_id': GRACE, 'duration': '00:10:00'}, blocking=True)
        self.wol_wakes = True
        await self.run_wake()
        self.assertEqual(self.hass.states.get(GRACE).attributes['duration'], '0:02:00')

    async def test_unknown_unavailable_or_missing_outlet_aborts_without_commands(self):
        for state in ('unknown', 'unavailable', None):
            with self.subTest(state=state):
                if state is None:
                    self.hass.states.async_remove(POWER)
                else:
                    self.hass.states.async_set(POWER, state)
                await self.run_wake()
                self.assertEqual(self.events, [])
                self.assertEqual(self.execution, 'aborted')

    async def test_unconfirmed_power_does_not_attempt_wol_or_ir(self):
        self.hass.states.async_set(POWER, 'off')
        self.power_confirms = False
        await self.run_wake()
        self.assertEqual(self.events, ['power'])
        self.assertEqual(self.execution, 'aborted')

    async def test_outlet_api_failure_does_not_attempt_wol_or_ir(self):
        self.hass.states.async_set(POWER, 'off')
        self.power_raises = True
        await self.run_wake()
        self.assertEqual(self.events, ['power'])
        self.assertEqual(self.execution, 'aborted')

    async def test_missing_outlet_action_remains_a_bounded_failure(self):
        self.hass.states.async_set(POWER, 'off')
        self.hass.services.async_remove('switch', 'turn_on')
        await asyncio.wait_for(self.run_wake(), timeout=2)
        self.assertEqual(self.events, [])
        self.assertEqual(self.execution, 'aborted')

    async def test_stalled_outlet_action_cannot_block_confirmation_deadline(self):
        self.hass.states.async_set(POWER, 'off')
        self.power_release = asyncio.Event()
        self.power_confirms = False
        try:
            await asyncio.wait_for(self.run_wake(), timeout=2)
            self.assertEqual(self.events, ['power'])
            self.assertEqual(self.execution, 'aborted')
        finally:
            self.power_release.set()
            await self.hass.async_block_till_done()

    async def test_power_lost_during_cold_start_aborts(self):
        self.hass.states.async_set(POWER, 'off')
        task = asyncio.create_task(self.run_wake())
        await asyncio.wait_for(self.power_requested.wait(), timeout=2)
        await asyncio.sleep(.02)
        self.hass.states.async_set(POWER, 'unavailable')
        await task
        self.assertEqual(self.events, ['power'])
        self.assertEqual(self.execution, 'aborted')

    async def load_media_automation(self):
        """Load the real companion automation; only shorten its elapsed ages."""
        config = yaml.safe_load((ROOT / 'config/packages/dining_media_guard_evening.yaml').read_text())

        def shorten(value):
            if isinstance(value, dict):
                if 'for' in value:
                    self.assertIn(value['for'], ('00:10:00', '00:02:00'))
                    value['for'] = {'milliseconds': 20}
                for item in value.values():
                    shorten(item)
            elif isinstance(value, list):
                for item in value:
                    shorten(item)
        shorten(config)
        for sensor in ('living_room_presence', 'rf_lobby_motion', 'rf_dinner_motion', 'rf_dinner_two_motion'):
            self.hass.states.async_set(f'binary_sensor.{sensor}', 'off')
        for room in ('living_room', 'dining_room'):
            self.hass.states.async_set(f'input_boolean.{room}_sticky', 'off')
        # Isolate the TV outlet without disabling the actual Dining branch.
        self.hass.states.async_set('switch.dining_media_guard', 'off')

        async def power_off(call):
            self.assertEqual(dict(call.data), {'entity_id': [POWER]})
            self.events.append('power_off')
            self.hass.states.async_set(POWER, 'off')
        self.hass.services.async_register('switch', 'turn_off', power_off)
        self.assertTrue(await async_setup_component(self.hass, 'automation', config))
        await self.hass.async_start()
        await self.hass.async_block_till_done()
        self.off_rule = next(s.entity_id for s in self.hass.states.async_all('automation')
            if s.attributes.get('id') == 'ha_homelab_dining_media_guard_evening_power_off')

    async def inactivity_tick(self):
        # Execute the same rule as the periodic trigger, retaining all conditions.
        await self.hass.services.async_call('automation', 'trigger',
            {'entity_id': self.off_rule, 'skip_condition': False}, blocking=True)

    async def test_cold_manual_wake_survives_idle_tick_and_releases_after_grace(self):
        self.hass.states.async_set(POWER, 'off')
        await self.load_media_automation()
        await asyncio.sleep(.03)
        task = asyncio.create_task(self.run_wake())
        await asyncio.wait_for(self.power_requested.wait(), timeout=2)
        await asyncio.sleep(.03)
        await self.inactivity_tick()
        self.assertEqual(self.events, ['power'])
        self.assertEqual(self.hass.states.get(POWER).state, 'on')
        await task
        self.assertEqual(self.events, ['power', 'wol', 'ir'])
        self.assertEqual(self.execution, 'finished')
        self.hass.states.async_set(TV, 'off')
        await self.inactivity_tick()
        self.assertNotIn('power_off', self.events)
        # Finish the real HA timer to simulate its bounded expiry, then tick.
        await self.hass.services.async_call('timer', 'finish', {'entity_id': GRACE}, blocking=True)
        await self.inactivity_tick()
        self.assertEqual(self.events[-1], 'power_off')

    async def test_warm_manual_wake_is_protected_even_after_outlet_age_grace(self):
        await self.load_media_automation()
        await asyncio.sleep(.03)
        task = asyncio.create_task(self.run_wake())
        await asyncio.wait_for(self.wol_sent.wait(), timeout=2)
        await self.inactivity_tick()
        self.assertEqual(self.events, ['wol'])
        self.assertEqual(self.hass.states.get(POWER).state, 'on')
        await task
        self.assertEqual(self.events, ['wol', 'ir'])
        self.assertEqual(self.execution, 'finished')


if __name__ == '__main__':
    unittest.main()
