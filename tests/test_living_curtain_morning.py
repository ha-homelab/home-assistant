"""Exercise living-room RF-first movement and Wi-Fi fallbacks without devices."""
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
    from homeassistant.components.automation.config import async_validate_config_item
    from homeassistant.helpers.script import Script
    from homeassistant.config import async_hass_config_yaml
    from homeassistant.config_entries import ConfigEntries
    from homeassistant.core import Context, HomeAssistant
    from homeassistant.exceptions import HomeAssistantError
    from homeassistant.setup import async_setup_component
except ImportError:
    if os.environ.get('REQUIRE_HA_RUNTIME') == '1':
        raise
    HA_AVAILABLE = False
else:
    HA_AVAILABLE = True

ROOT = Path(os.environ.get('CURTAIN_TEST_ROOT', Path(__file__).resolve().parents[1]))
MAIN = 'cover.living_curtains_l'
SHEER = 'cover.living_light_curtains_l'
POWER = 'switch.living_guard'
OVERRIDE = 'input_boolean.curtains_sticky'
ROOM_OVERRIDE = 'input_boolean.living_room_sticky'
SECRETS = {
    'living_main_curtain_rf_remote_id': 0x123456,
    'living_main_curtain_rf_channel': 1,
    'living_sheer_curtain_rf_remote_id': 0x234567,
    'living_sheer_curtain_rf_channel': 2,
}


@unittest.skipUnless(HA_AVAILABLE, 'Home Assistant runtime is not installed')
class LivingCurtainFallbackTest(unittest.IsolatedAsyncioTestCase):
    override = OVERRIDE

    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='living-curtain-test-')
        self.hass = HomeAssistant(self.temp.name)
        loader.async_setup(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self.hass.config.skip_pip = True
        self.assertTrue(await async_load_base_functionality(self.hass))
        folder = Path(self.temp.name)
        (folder / 'packages').mkdir()
        (folder / 'packages/living_curtains_rf.yaml').write_text(
            (ROOT / 'config/packages/living_curtains_rf.yaml').read_text())
        (folder / 'secrets.yaml').write_text(yaml.safe_dump(SECRETS))
        (folder / 'configuration.yaml').write_text(
            'homeassistant:\n  packages: !include_dir_named packages\nscript: {}\n')
        self.config = await async_hass_config_yaml(self.hass)
        scripts = self.config['script']
        move = scripts['living_curtains_move']
        tx = scripts['living_curtain_send_rf']
        self.assertEqual(move['mode'], 'parallel')
        self.assertEqual(tx['mode'], 'queued')
        self.assertEqual(move['sequence'][3]['delay'], {'seconds': 3})
        self.assertEqual(tx['sequence'][-1]['delay'], {'seconds': 2})
        move['sequence'][3]['delay'] = {'milliseconds': 30}
        tx['sequence'][-1]['delay'] = {'milliseconds': 20}
        for branch in move['sequence'][-1]['parallel']:
            wait = branch['sequence'][1]
            self.assertEqual(wait['timeout'], {'seconds': 180})
            self.assertFalse(wait['continue_on_timeout'])
            wait['timeout'] = {'seconds': 1}
        self.events = []
        self.cover_called = {entity: asyncio.Event() for entity in (MAIN, SHEER)}
        self.rf_times = []
        self.fail_rf = False
        self.fail_cover = set()
        self.fail_power = False
        self.after_power = None
        self.after_rf = None
        self.hass.states.async_set(OVERRIDE, 'off')
        self.hass.states.async_set(ROOM_OVERRIDE, 'off')
        self.hass.states.async_set(POWER, 'off')
        for entity in (MAIN, SHEER):
            self.hass.states.async_set(entity, 'closed', {'current_position': 50})
        self.hass.services.async_register('switch', 'turn_on', self.power)
        self.hass.services.async_register('esphome', 'rf_send_dooya_code', self.transmit)
        self.hass.services.async_register('cover', 'open_cover', self.cover)
        self.hass.services.async_register('cover', 'close_cover', self.cover)
        self.assertTrue(await async_setup_component(self.hass, 'script', self.config))
        await self.hass.async_start()
        self.assertTrue(self.hass.services.has_service('script', 'living_curtains_move'))
        self.assertTrue(self.hass.services.has_service('script', 'living_curtain_send_rf'))

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.temp.cleanup()

    async def power(self, call):
        targets = call.data['entity_id']
        self.assertEqual([targets] if isinstance(targets, str) else targets, [POWER])
        self.events.append(('power', POWER))
        self.power_time = asyncio.get_running_loop().time()
        if self.after_power:
            self.after_power()
        if self.fail_power:
            raise HomeAssistantError('Simulated unavailable power telemetry')
        self.hass.states.async_set(POWER, 'on')

    async def transmit(self, call):
        self.rf_times.append(asyncio.get_running_loop().time())
        self.events.append(('rf', dict(call.data)))
        if self.after_rf:
            self.after_rf()
        if self.fail_rf:
            raise HomeAssistantError('Simulated RF API failure')

    async def cover(self, call):
        entity = call.data['entity_id']
        if isinstance(entity, list):
            entity = entity[0]
        self.events.append((call.service, entity))
        self.cover_called[entity].set()
        if entity in self.fail_cover:
            raise HomeAssistantError('Simulated Wi-Fi motor failure')

    async def move(self, command='open', curtain='both'):
        await self.hass.services.async_call('script', 'living_curtains_move',
            {'command': command, 'curtain': curtain}, blocking=True)

    def wifi(self):
        return [event for event in self.events if event[0] in ('open_cover', 'close_cover')]

    async def test_rf_after_power_all_rf_before_wifi_and_stale_position_not_skipped(self):
        await self.move()
        self.assertEqual([event[0] for event in self.events[:3]], ['power', 'rf', 'rf'])
        self.assertGreaterEqual(self.rf_times[0] - self.power_time, .025)
        self.assertGreaterEqual(self.rf_times[1] - self.rf_times[0], .015)
        self.assertCountEqual(self.wifi(), [('open_cover', MAIN), ('open_cover', SHEER)])
        self.assertEqual(self.events[1][1],
            {'remote_id': 0x123456, 'channel': 1, 'button': 1, 'check': 1, 'repeats': 3})
        self.assertEqual(self.events[2][1],
            {'remote_id': 0x234567, 'channel': 2, 'button': 1, 'check': 1, 'repeats': 3})

    async def test_selected_close_uses_observed_close_variant_and_same_wifi_target(self):
        await self.move(command='close', curtain='sheer')
        self.assertEqual(self.events[1][1],
            {'remote_id': 0x234567, 'channel': 2, 'button': 3, 'check': 3, 'repeats': 3})
        self.assertEqual(self.wifi(), [('close_cover', SHEER)])

    async def test_missing_native_service_still_falls_back_for_both(self):
        self.hass.services.async_remove('esphome', 'rf_send_dooya_code')
        await self.move()
        self.assertEqual(self.rf_times, [])
        self.assertCountEqual(self.wifi(), [('open_cover', MAIN), ('open_cover', SHEER)])

    async def test_failing_native_service_still_falls_back_for_both(self):
        self.fail_rf = True
        await self.move()
        self.assertEqual(len(self.rf_times), 2)
        self.assertCountEqual(self.wifi(), [('open_cover', MAIN), ('open_cover', SHEER)])

    async def test_timeout_for_main_does_not_block_sheer_wifi(self):
        self.hass.states.async_set(MAIN, 'unavailable')
        task = asyncio.create_task(self.move())
        await asyncio.wait_for(self.cover_called[SHEER].wait(), timeout=2)
        self.assertEqual(self.wifi(), [('open_cover', SHEER)])
        self.assertFalse(task.done())
        await task
        self.assertEqual(self.wifi(), [('open_cover', SHEER)])

    async def test_late_main_reconnect_gets_its_independent_fallback(self):
        self.hass.states.async_set(MAIN, 'unavailable')
        task = asyncio.create_task(self.move())
        await asyncio.wait_for(self.cover_called[SHEER].wait(), timeout=2)
        self.assertFalse(task.done())
        self.hass.states.async_set(MAIN, 'open', {'current_position': 100})
        await task
        self.assertEqual(self.wifi(), [('open_cover', SHEER), ('open_cover', MAIN)])

    async def test_manual_override_before_start_prevents_power_and_commands(self):
        self.hass.states.async_set(self.override, 'on')
        await self.move()
        self.assertEqual(self.events, [])

    async def test_override_during_warmup_prevents_rf_and_wifi(self):
        self.after_power = lambda: self.hass.states.async_set(self.override, 'on')
        await self.move()
        self.assertEqual(self.events, [('power', POWER)])

    async def test_override_between_rf_calls_prevents_remaining_rf_and_wifi(self):
        self.after_rf = lambda: self.hass.states.async_set(self.override, 'on')
        await self.move()
        self.assertEqual(len(self.rf_times), 1)
        self.assertEqual(self.wifi(), [])

    async def test_override_while_waiting_stops_wifi_when_motor_returns(self):
        self.hass.states.async_set(MAIN, 'unavailable')
        task = asyncio.create_task(self.move())
        await asyncio.wait_for(self.cover_called[SHEER].wait(), timeout=2)
        self.assertFalse(task.done())
        self.hass.states.async_set(self.override, 'on')
        self.hass.states.async_set(MAIN, 'closed')
        await task
        self.assertEqual(self.wifi(), [('open_cover', SHEER)])

    async def test_one_wifi_failure_does_not_block_other(self):
        self.fail_cover = {MAIN}
        await self.move()
        self.assertCountEqual(self.wifi(), [('open_cover', MAIN), ('open_cover', SHEER)])

    async def test_failed_power_telemetry_does_not_block_available_motors(self):
        self.fail_power = True
        await self.move()
        self.assertEqual(len(self.rf_times), 2)
        self.assertCountEqual(self.wifi(), [('open_cover', MAIN), ('open_cover', SHEER)])

    async def test_long_fallback_does_not_block_other_scheduled_target(self):
        self.hass.states.async_set(MAIN, 'unavailable')
        first = asyncio.create_task(self.move())
        await asyncio.wait_for(self.cover_called[SHEER].wait(), timeout=2)
        second = asyncio.create_task(self.move(command='close', curtain='sheer'))
        await second
        self.assertFalse(first.done())
        self.assertEqual(self.wifi(), [('open_cover', SHEER), ('close_cover', SHEER)])
        self.assertEqual(len(self.rf_times), 3)
        await first

    async def test_queued_rf_rechecks_override_before_its_turn(self):
        first_rf = asyncio.Event()
        self.after_rf = first_rf.set
        first = asyncio.create_task(self.hass.services.async_call(
            'script', 'living_curtain_send_rf',
            {'curtain': 'main', 'command': 'open'}, blocking=True))
        await first_rf.wait()
        second = asyncio.create_task(self.hass.services.async_call(
            'script', 'living_curtain_send_rf',
            {'curtain': 'sheer', 'command': 'open'}, blocking=True))
        await asyncio.sleep(0)
        self.hass.states.async_set(self.override, 'on')
        await asyncio.gather(first, second)
        self.assertEqual(len(self.rf_times), 1)


    async def test_unknown_or_unavailable_override_blocks_power_and_commands(self):
        for state in ('unknown', 'unavailable'):
            with self.subTest(state=state):
                self.hass.states.async_set(self.override, state)
                await self.move()
                self.assertEqual(self.events, [])

    async def test_override_cancels_wait_without_waiting_for_motor_recovery(self):
        self.hass.states.async_set(MAIN, 'unavailable')
        task = asyncio.create_task(self.move())
        await asyncio.wait_for(self.cover_called[SHEER].wait(), timeout=2)
        self.hass.states.async_set(self.override, 'on')
        await asyncio.wait_for(task, timeout=.5)
        self.assertEqual(self.wifi(), [('open_cover', SHEER)])


class LivingRoomStickyFallbackTest(LivingCurtainFallbackTest):
    """Run the full dispatch/race matrix for the room override too."""
    override = ROOM_OVERRIDE


class LivingCurtainCallerContractTest(unittest.TestCase):
    def setUp(self):
        self.library = ROOT / 'dependencies/automations'
        self.config = {}
        for number in ('027', '029', '077', '078'):
            path = next((self.library / 'config').glob(number + '_*.yaml'))
            self.config[number] = yaml.safe_load(path.read_text())[0]

    def test_id_schedules_mode_and_trace_preserved(self):
        for number in ('027', '029', '077'):
            baseline = ROOT / 'tests/fixtures/living_curtain_callers' / (number + '.yaml')
            original = yaml.safe_load(baseline.read_text())[0]
            for key in ('id', 'alias', 'mode', 'trace'):
                with self.subTest(number=number, key=key):
                    self.assertEqual(self.config[number][key], original[key])
            if number != '077':
                self.assertEqual(self.config[number]['triggers'], original['triggers'])
        self.assertEqual(self.config['077']['triggers'], [
            {'platform': 'time', 'at': '06:30:00'},
            {'platform': 'sun', 'event': 'sunrise'},
        ])
        self.assertIn({'condition': 'time', 'after': '06:30:00', 'before': '12:00:00'},
                      self.config['077']['conditions'])
        self.assertIn({'condition': 'sun', 'after': 'sunrise', 'before': 'sunset'},
                      self.config['077']['conditions'])

    def test_other_room_evening_sequence_preserves_timing_and_migrated_guard(self):
        branches = self.config['027']['actions'][0]['parallel']
        for branch, room, cover in zip(branches, ('kitchen', 'studio', 'dining'),
                                      ('kitchen_curtains_l', 'studio_curtains', 'dining_curtains_l')):
            sequence = branch['sequence']
            self.assertEqual([step['delay'] for step in sequence if 'delay' in step],
                             ['00:01:30', '01:00:00'])
            self.assertEqual([(step['service'], step['entity_id']) for step in sequence if 'service' in step], [
                ('switch.turn_on', f'switch.{room}_guard'),
                ('cover.close_cover', f'cover.{cover}'),
                ('switch.turn_off', f'switch.{room}_guard'),
            ])
        # Morning Studio movement is intentionally manual only.
        self.assertNotIn('studio', str(self.config['078']['actions']))

    def test_three_callers_choose_the_requested_targets(self):
        for number, curtain, command in [('077', 'both', 'open'), ('029', 'sheer', 'close')]:
            self.assertEqual(self.config[number]['actions'][-1], {
                'action': 'script.living_curtains_move', 'data': {'curtain': curtain, 'command': command}})
        self.assertEqual(self.config['027']['actions'][0]['parallel'][-1]['sequence'][-1], {
            'action': 'script.living_curtains_move', 'data': {'curtain': 'main', 'command': 'close'}})


@unittest.skipUnless(HA_AVAILABLE, 'Home Assistant runtime is not installed')
class StudioCurtainMigrationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='studio-curtain-test-')
        self.hass = HomeAssistant(self.temp.name)
        loader.async_setup(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self.hass.config.skip_pip = True
        self.assertTrue(await async_load_base_functionality(self.hass))
        self.events = []
        self.fail_studio = False
        self.after_call = None
        for room in ('curtains', 'kitchen', 'dining_room', 'studio', 'living_room', 'bedroom', 'mishka_room'):
            self.hass.states.async_set(f'input_boolean.{room}_sticky', 'off')
        for domain, service in [('switch', 'turn_on'), ('switch', 'turn_off'),
                                ('cover', 'open_cover'), ('cover', 'close_cover'),
                                ('script', 'living_curtains_move')]:
            self.hass.services.async_register(domain, service, self.record)

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.temp.cleanup()

    async def record(self, call):
        target = call.data.get('entity_id')
        if isinstance(target, list):
            target = target[0]
        self.events.append((call.domain, call.service, target))
        if self.after_call:
            self.after_call(call, target)
        if self.fail_studio and target == 'cover.studio_curtains':
            raise HomeAssistantError('Simulated unavailable Studio Zigbee motor')

    async def run_rule(self, number):
        path = next((ROOT / 'dependencies/automations/config').glob(f'{number}_*.yaml'))
        rule = yaml.safe_load(path.read_text())[0]
        runtime = deepcopy(rule)
        def skip_delays(value):
            if isinstance(value, list):
                for item in value:
                    skip_delays(item)
            elif isinstance(value, dict):
                if 'delay' in value:
                    value['delay'] = 0
                for item in value.values():
                    skip_delays(item)
        skip_delays(runtime['actions'])
        config = await async_validate_config_item(self.hass, 'automation', runtime)
        script = Script(self.hass, config['actions'], config['alias'], 'automation')
        await script.async_run(context=Context())
        self.assertFalse(any(target in ('cover.office_curtains_r',
                                        'cover.office_curtains_office_curtains')
                             for _, _, target in self.events))

    async def test_morning_preserves_manual_only_studio(self):
        await self.run_rule('078')
        self.assertFalse(any(target in ('switch.studio_guard', 'cover.studio_curtains')
                             for _, _, target in self.events))
        self.assertIn(('cover', 'open_cover', 'cover.kitchen_curtains_l'), self.events)
        self.assertIn(('cover', 'open_cover', 'cover.dining_curtains_l'), self.events)

    async def test_evening_closes_new_cover_before_existing_power_off(self):
        await self.run_rule('027')
        closed = self.events.index(('cover', 'close_cover', 'cover.studio_curtains'))
        off = self.events.index(('switch', 'turn_off', 'switch.studio_guard'))
        self.assertLess(closed, off)
        self.assertIn(('script', 'living_curtains_move', None), self.events)

    async def test_unavailable_studio_does_not_abort_other_morning_targets(self):
        self.fail_studio = True
        await self.run_rule('078')
        self.assertIn(('cover', 'open_cover', 'cover.dining_curtains_l'), self.events)
        self.assertIn(('switch', 'turn_off', 'switch.dining_guard'), self.events)

    async def test_unavailable_studio_does_not_abort_evening_power_off(self):
        self.fail_studio = True
        await self.run_rule('027')
        self.assertIn(('cover', 'close_cover', 'cover.dining_curtains_l'), self.events)
        self.assertIn(('switch', 'turn_off', 'switch.studio_guard'), self.events)


    async def test_sticky_room_does_not_block_other_evening_rooms(self):
        for state in ('on', 'unknown', 'unavailable'):
            with self.subTest(state=state):
                self.events.clear()
                self.hass.states.async_set('input_boolean.studio_sticky', state)
                await self.run_rule('027')
                self.assertFalse(any(target in ('switch.studio_guard', 'cover.studio_curtains')
                                     for _, _, target in self.events))
                self.assertIn(('cover', 'close_cover', 'cover.kitchen_curtains_l'), self.events)
                self.assertIn(('cover', 'close_cover', 'cover.dining_curtains_l'), self.events)

    async def test_room_override_during_warmup_blocks_movement_and_late_poweroff(self):
        def enable_override(call, target):
            if call.service == 'turn_on' and target == 'switch.dining_guard':
                self.hass.states.async_set('input_boolean.dining_room_sticky', 'on')
        self.after_call = enable_override
        await self.run_rule('027')
        self.assertIn(('switch', 'turn_on', 'switch.dining_guard'), self.events)
        self.assertNotIn(('cover', 'close_cover', 'cover.dining_curtains_l'), self.events)
        self.assertNotIn(('switch', 'turn_off', 'switch.dining_guard'), self.events)
        self.assertIn(('cover', 'close_cover', 'cover.kitchen_curtains_l'), self.events)

    async def test_sticky_after_movement_blocks_delayed_poweroff(self):
        def enable_override(call, target):
            if target == 'cover.bedroom_curtains_l':
                self.hass.states.async_set('input_boolean.bedroom_sticky', 'on')
        self.after_call = enable_override
        await self.run_rule('028')
        self.assertIn(('cover', 'close_cover', 'cover.bedroom_curtains_l'), self.events)
        self.assertNotIn(('switch', 'turn_off', 'switch.bedroom_guard'), self.events)
        self.assertIn(('cover', 'close_cover', 'cover.mishka_curtains_two_l'), self.events)

    async def test_global_override_during_warmup_stops_all_remaining_commands(self):
        def enable_override(call, target):
            if call.service == 'turn_on':
                self.hass.states.async_set('input_boolean.curtains_sticky', 'on')
        self.after_call = enable_override
        await self.run_rule('027')
        self.assertTrue(self.events)
        self.assertTrue(all(domain == 'switch' and service == 'turn_on'
                            for domain, service, target in self.events))

    async def test_each_curtain_power_schedule_respects_room_override(self):
        cases = [('024', 'mishka_room', 'switch.mishka_guard'),
                 ('025', 'mishka_room', 'switch.mishka_guard'),
                 ('076', 'mishka_room', 'switch.mishka_guard'),
                 ('076', 'bedroom', 'switch.bedroom_guard'),
                 ('028', 'mishka_room', 'cover.mishka_curtains_one_l'),
                 ('028', 'mishka_room', 'cover.mishka_curtains_two_l'),
                 ('028', 'bedroom', 'switch.bedroom_guard'),
                 ('078', 'dining_room', 'switch.dining_guard'),
                 ('078', 'kitchen', 'switch.kitchen_guard')]
        for rule, room, target in cases:
            with self.subTest(rule=rule, room=room, target=target):
                self.events.clear()
                self.hass.states.async_set(f'input_boolean.{room}_sticky', 'on')
                await self.run_rule(rule)
                self.assertFalse(any(event[2] == target for event in self.events))
                self.hass.states.async_set(f'input_boolean.{room}_sticky', 'off')


if __name__ == '__main__':
    unittest.main(verbosity=2)
