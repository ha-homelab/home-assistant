"""Exercise media power triggers and safety guards in an isolated HA runtime."""
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
    from homeassistant.exceptions import HomeAssistantError
    from homeassistant.setup import async_setup_component
except ImportError:
    if os.environ.get('REQUIRE_HA_RUNTIME') == '1':
        raise
    HA_AVAILABLE = False
else:
    HA_AVAILABLE = True

ROOT = Path(os.environ.get('DINING_MEDIA_TEST_ROOT', Path(__file__).resolve().parents[1]))
SENSORS = ('binary_sensor.living_room_presence', 'binary_sensor.rf_lobby_motion',
           'binary_sensor.rf_dinner_motion', 'binary_sensor.rf_dinner_two_motion')
MEDIA = 'switch.dining_media_guard'
TV_POWER = 'switch.living_tv_guard'
TV = 'media_player.living_room_tv_77'
LIVING_STICKY = 'input_boolean.living_room_sticky'
DINING_STICKY = 'input_boolean.dining_room_sticky'
GRACE = 'timer.living_room_tv_wake_grace'


@unittest.skipUnless(HA_AVAILABLE, 'Home Assistant runtime is not installed')
class MediaOccupancyTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='media-occupancy-test-')
        self.hass = HomeAssistant(self.temp.name)
        loader.async_setup(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self.hass.config.skip_pip = True
        self.assertTrue(await async_load_base_functionality(self.hass))
        self.calls = []
        self.fail_target = None
        self.after_command = None
        for service in ('turn_on', 'turn_off'):
            self.hass.services.async_register('switch', service, self.command)
        for sensor in SENSORS:
            self.hass.states.async_set(sensor, 'on')
        for outlet in (MEDIA, TV_POWER):
            self.hass.states.async_set(outlet, 'on')
        self.hass.states.async_set(TV, 'off')
        self.hass.states.async_set(GRACE, 'idle')
        # Keep the current room-override policy, including the older Living
        # override on Dining Media. Lobby owns neither outlet.
        for room in ('living_room', 'dining_room', 'lobby'):
            self.hass.states.async_set(f'input_boolean.{room}_sticky', 'off')
        self.config = deepcopy(yaml.safe_load(
            (ROOT / 'config/packages/dining_media_guard_evening.yaml').read_text()))
        self.duration_count = 0

        def shorten(value):
            if isinstance(value, dict):
                if 'for' in value:
                    self.assertIn(value['for'], ('00:10:00', '00:02:00'))
                    self.duration_count += 1
                    value['for'] = {'milliseconds': 150 if value['for'] == '00:02:00' else 250}
                for item in value.values():
                    shorten(item)
            elif isinstance(value, list):
                for item in value:
                    shorten(item)
        shorten(self.config)
        self.assertEqual(self.duration_count, 4)

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.temp.cleanup()

    async def command(self, call):
        targets = call.data['entity_id']
        for target in [targets] if isinstance(targets, str) else targets:
            if target == self.fail_target:
                raise HomeAssistantError('Simulated outlet failure')
            self.calls.append((call.service, target))
            self.hass.states.async_set(target, 'on' if call.service == 'turn_on' else 'off')
            if self.after_command:
                self.after_command(call.service, target)

    async def settle(self, seconds=.4):
        await asyncio.sleep(seconds)
        await self.hass.async_block_till_done()

    async def load(self):
        self.assertTrue(await async_setup_component(self.hass, 'automation', self.config))
        await self.hass.async_start()
        await self.hass.async_block_till_done()

    def set_sensors(self, state):
        for sensor in SENSORS:
            self.hass.states.async_set(sensor, state)

    async def test_each_activity_source_restores_both_with_overrides_off(self):
        self.set_sensors('off')
        await self.load()
        for sensor in SENSORS:
            with self.subTest(sensor=sensor):
                self.set_sensors('off')
                for outlet in (MEDIA, TV_POWER):
                    self.hass.states.async_set(outlet, 'off')
                self.calls.clear()
                self.hass.states.async_set(sensor, 'on')
                await self.settle(.04)
                self.assertCountEqual(self.calls, [('turn_on', MEDIA), ('turn_on', TV_POWER)])

    async def test_ten_minutes_quiet_switches_both_off(self):
        await self.load()
        self.set_sensors('off')
        await self.settle(.05)
        self.assertEqual(self.calls, [])
        await self.settle()
        self.assertCountEqual(self.calls, [('turn_off', MEDIA), ('turn_off', TV_POWER)])

    async def test_latest_sensor_must_complete_its_own_interval(self):
        await self.load()
        for sensor in SENSORS[:-1]:
            self.hass.states.async_set(sensor, 'off')
        await self.settle()
        self.assertEqual(self.calls, [])
        self.hass.states.async_set(SENSORS[-1], 'off')
        await self.settle(.05)
        self.assertEqual(self.calls, [])
        await self.settle()
        self.assertCountEqual(self.calls, [('turn_off', MEDIA), ('turn_off', TV_POWER)])

    async def test_new_activity_cancels_pending_shutdown(self):
        await self.load()
        self.set_sensors('off')
        await self.settle(.05)
        self.hass.states.async_set(SENSORS[0], 'on')
        await self.settle()
        self.assertEqual(self.calls, [])

    async def test_unknown_or_unavailable_sensor_blocks_shutdown(self):
        await self.load()
        for sensor, state in ((SENSORS[0], 'unknown'), (SENSORS[1], 'unavailable')):
            self.set_sensors('on')
            await self.settle(.02)
            self.set_sensors('off')
            self.hass.states.async_set(sensor, state)
            await self.settle()
            self.assertEqual(self.calls, [])

    async def test_non_off_tv_states_protect_tv_but_not_dining(self):
        await self.load()
        for state in ('on', 'playing', 'idle', 'unknown', 'unavailable'):
            with self.subTest(tv=state):
                self.set_sensors('on')
                self.hass.states.async_set(TV, state)
                self.hass.states.async_set(MEDIA, 'on')
                await self.settle(.02)
                self.calls.clear()
                self.set_sensors('off')
                await self.settle()
                self.assertEqual(self.calls, [('turn_off', MEDIA)])
                self.assertEqual(self.hass.states.get(TV_POWER).state, 'on')

    async def test_tv_off_after_timeout_triggers_tv_shutdown(self):
        self.hass.states.async_set(TV, 'playing')
        await self.load()
        self.set_sensors('off')
        await self.settle()
        self.assertEqual(self.calls, [('turn_off', MEDIA)])
        self.hass.states.async_set(TV, 'off')
        await self.settle(.04)
        self.assertEqual(self.calls[-1], ('turn_off', TV_POWER))

    async def test_manual_off_waits_for_new_activity(self):
        await self.load()
        self.hass.states.async_set(TV_POWER, 'off')
        self.hass.states.async_set(MEDIA, 'off')
        await self.settle()
        self.assertEqual(self.calls, [])
        self.hass.states.async_set(SENSORS[1], 'off')
        await self.settle(.02)
        self.hass.states.async_set(SENSORS[1], 'on')
        await self.settle(.04)
        self.assertCountEqual(self.calls, [('turn_on', MEDIA), ('turn_on', TV_POWER)])

    async def test_unavailable_outlet_recovery_restores_occupied_power(self):
        await self.load()
        self.hass.states.async_set(MEDIA, 'unavailable')
        await self.settle(.02)
        self.hass.states.async_set(MEDIA, 'off')
        await self.settle(.04)
        self.assertEqual(self.calls, [('turn_on', MEDIA)])

    async def test_startup_and_reload_reconcile_existing_presence(self):
        self.hass.states.async_set(MEDIA, 'off')
        await self.load()
        self.assertEqual(self.calls, [('turn_on', MEDIA)])
        self.calls.clear()
        self.hass.states.async_set(MEDIA, 'off')
        self.hass.bus.async_fire('automation_reloaded')
        await self.settle(.04)
        self.assertEqual(self.calls, [('turn_on', MEDIA)])

    async def test_recheck_recovers_timer_lost_on_reload_without_early_off(self):
        # Sensors predate automation setup, so there is no off-transition timer.
        self.set_sensors('off')
        await self.load()
        off_rule = next(s.entity_id for s in self.hass.states.async_all('automation')
                        if s.attributes.get('id') == 'ha_homelab_dining_media_guard_evening_power_off')
        async def recheck():
            await self.hass.services.async_call('automation', 'trigger',
                {'entity_id': off_rule, 'skip_condition': False}, blocking=True)
        await recheck()
        self.assertEqual(self.calls, [])
        await self.settle()
        await recheck()
        self.assertCountEqual(self.calls, [('turn_off', MEDIA), ('turn_off', TV_POWER)])

    async def test_outlet_failure_does_not_block_other_outlet(self):
        self.fail_target = MEDIA
        await self.load()
        self.set_sensors('off')
        await self.settle()
        self.assertEqual(self.calls, [('turn_off', TV_POWER)])

    async def test_activity_during_first_shutdown_protects_tv(self):
        await self.load()
        def occupancy_returns(service, target):
            if service == 'turn_off' and target == MEDIA:
                self.hass.states.async_set(SENSORS[0], 'on')
        self.after_command = occupancy_returns
        self.set_sensors('off')
        await self.settle()
        self.assertNotIn(('turn_off', TV_POWER), self.calls)
        self.assertEqual(self.hass.states.get(MEDIA).state, 'on')

    async def test_room_overrides_fail_closed_for_each_restore_source(self):
        self.set_sensors('off')
        await self.load()
        for sticky, blocked in ((LIVING_STICKY, {MEDIA, TV_POWER}),
                                (DINING_STICKY, {MEDIA})):
            for state in ('on', 'unknown', 'unavailable', None):
                for sensor in SENSORS:
                    with self.subTest(sticky=sticky, state=state, sensor=sensor):
                        self.set_sensors('off')
                        for override in (LIVING_STICKY, DINING_STICKY):
                            self.hass.states.async_set(override, 'off')
                        if state is None:
                            self.hass.states.async_remove(sticky)
                        else:
                            self.hass.states.async_set(sticky, state)
                        for outlet in (MEDIA, TV_POWER):
                            self.hass.states.async_set(outlet, 'off')
                        self.calls.clear()
                        self.hass.states.async_set(sensor, 'on')
                        await self.settle(.02)
                        self.assertCountEqual(self.calls, [
                            ('turn_on', outlet) for outlet in {MEDIA, TV_POWER} - blocked])

    async def test_room_overrides_fail_closed_for_shutdown(self):
        await self.load()
        for sticky, blocked in ((LIVING_STICKY, {MEDIA, TV_POWER}),
                                (DINING_STICKY, {MEDIA})):
            for state in ('on', 'unknown', 'unavailable', None):
                with self.subTest(sticky=sticky, state=state):
                    self.set_sensors('on')
                    for override in (LIVING_STICKY, DINING_STICKY):
                        self.hass.states.async_set(override, 'off')
                    if state is None:
                        self.hass.states.async_remove(sticky)
                    else:
                        self.hass.states.async_set(sticky, state)
                    for outlet in (MEDIA, TV_POWER):
                        self.hass.states.async_set(outlet, 'on')
                    await self.settle(.02)
                    self.calls.clear()
                    self.set_sensors('off')
                    await self.settle()
                    self.assertCountEqual(self.calls, [
                        ('turn_off', outlet) for outlet in {MEDIA, TV_POWER} - blocked])

    async def test_sticky_enabled_during_inactivity_wait_blocks_shutdown(self):
        await self.load()
        self.set_sensors('off')
        await self.settle(.04)
        self.hass.states.async_set(LIVING_STICKY, 'on')
        await self.settle()
        self.assertEqual(self.calls, [])

    async def test_sticky_is_rechecked_between_restore_commands(self):
        self.set_sensors('off')
        for outlet in (MEDIA, TV_POWER):
            self.hass.states.async_set(outlet, 'off')
        await self.load()
        self.after_command = lambda *_: self.hass.states.async_set(LIVING_STICKY, 'on')
        self.hass.states.async_set(SENSORS[0], 'on')
        await self.settle(.04)
        self.assertEqual(self.calls, [('turn_on', TV_POWER)])

    async def test_sticky_is_rechecked_between_shutdown_commands(self):
        await self.load()
        self.after_command = lambda *_: self.hass.states.async_set(LIVING_STICKY, 'on')
        self.set_sensors('off')
        await self.settle()
        self.assertEqual(self.calls, [('turn_off', MEDIA)])

    async def test_occupancy_is_rechecked_between_restore_commands(self):
        self.set_sensors('off')
        for outlet in (MEDIA, TV_POWER):
            self.hass.states.async_set(outlet, 'off')
        await self.load()
        self.after_command = lambda *_: self.set_sensors('unknown')
        self.hass.states.async_set(SENSORS[0], 'on')
        await self.settle(.04)
        self.assertEqual(self.calls, [('turn_on', TV_POWER)])

    async def test_sticky_blocks_recovery_and_reconciliation(self):
        self.hass.states.async_set(LIVING_STICKY, 'on')
        self.hass.states.async_set(MEDIA, 'off')
        await self.load()
        self.hass.bus.async_fire('automation_reloaded')
        self.hass.states.async_set(MEDIA, 'unavailable')
        await self.settle(.02)
        self.hass.states.async_set(MEDIA, 'off')
        await self.settle(.04)
        self.assertEqual(self.calls, [])
        self.hass.states.async_set(LIVING_STICKY, 'off')
        await self.settle(.04)
        self.assertEqual(self.calls, [])
        self.hass.states.async_set(SENSORS[0], 'off')
        await self.settle(.02)
        self.hass.states.async_set(SENSORS[0], 'on')
        await self.settle(.04)
        self.assertEqual(self.calls, [('turn_on', MEDIA)])

    async def test_failed_restore_does_not_block_other_outlet(self):
        self.set_sensors('off')
        for outlet in (MEDIA, TV_POWER):
            self.hass.states.async_set(outlet, 'off')
        await self.load()
        self.fail_target = TV_POWER
        self.hass.states.async_set(SENSORS[0], 'on')
        await self.settle(.04)
        self.assertEqual(self.calls, [('turn_on', MEDIA)])


    async def test_new_outlet_power_has_a_grace_even_when_rooms_are_already_quiet(self):
        self.set_sensors('off')
        self.hass.states.async_set(TV_POWER, 'off')
        await self.load()
        await self.settle()
        off_rule = next(s.entity_id for s in self.hass.states.async_all('automation')
            if s.attributes.get('id') == 'ha_homelab_dining_media_guard_evening_power_off')
        self.hass.states.async_set(TV_POWER, 'on')
        self.calls.clear()
        await self.hass.services.async_call('automation', 'trigger',
            {'entity_id': off_rule, 'skip_condition': False}, blocking=True)
        self.assertNotIn(('turn_off', TV_POWER), self.calls)
        await self.settle(.2)
        await self.hass.services.async_call('automation', 'trigger',
            {'entity_id': off_rule, 'skip_condition': False}, blocking=True)
        self.assertEqual(self.calls[-1], ('turn_off', TV_POWER))

    async def test_active_or_unknown_wake_timer_protects_only_tv_power(self):
        await self.load()
        for state in ('active', 'paused', 'unknown', 'unavailable', None):
            with self.subTest(state=state):
                self.set_sensors('on')
                for outlet in (MEDIA, TV_POWER):
                    self.hass.states.async_set(outlet, 'on')
                if state is None:
                    self.hass.states.async_remove(GRACE)
                else:
                    self.hass.states.async_set(GRACE, state)
                self.calls.clear()
                self.set_sensors('off')
                await self.settle()
                self.assertEqual(self.calls, [('turn_off', MEDIA)])
                self.assertEqual(self.hass.states.get(TV_POWER).state, 'on')


if __name__ == '__main__':
    unittest.main()
