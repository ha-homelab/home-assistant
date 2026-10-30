"""Exercise the real LG Power scripts without a television or network I/O."""
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

ROOT = Path(__file__).resolve().parents[1]
TV = 'media_player.living_room_tv_77'
OTHER_TV = 'media_player.lg2'
START = 'script.living_room_tv_start_ott'
APP = 'Media Station X'
ACTIVE_STATES = ('on', 'playing', 'paused', 'idle', 'buffering')


@unittest.skipUnless(HA_AVAILABLE, 'Requires the deployed Home Assistant runtime')
class LGOTTPowerTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='lg-ott-power-test-')
        self.hass = HomeAssistant(self.temp.name)
        loader.async_setup(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self.hass.config.skip_pip = True
        self.assertTrue(await async_load_base_functionality(self.hass))
        self.events = []
        self.wake_requested = asyncio.Event()
        self.source_requested = asyncio.Event()
        self.wake_confirms = True
        self.select_confirms = True
        self.select_raises = False
        self.tv('off')
        self.hass.states.async_set(OTHER_TV, 'playing', {'source': 'Other input'})
        for action, handler in (
            ('turn_on', self.wake), ('turn_off', self.off),
            ('select_source', self.select),
        ):
            self.hass.services.async_register('media_player', action, handler)
        config = yaml.safe_load((ROOT / 'config/packages/lg_tv_ott_power.yaml').read_text())
        runtime = deepcopy(config)

        def shorten(value):
            if isinstance(value, list):
                for item in value:
                    shorten(item)
            elif isinstance(value, dict):
                if 'wait_template' in value:
                    self.assertIn(value['timeout'], ('00:02:00', '00:00:30'))
                    value['timeout'] = {'milliseconds': 400}
                for item in value.values():
                    shorten(item)

        shorten(runtime)
        self.assertTrue(await async_setup_component(self.hass, 'script', runtime))
        await self.hass.async_block_till_done()

    async def asyncTearDown(self):
        try:
            self.assertEqual(self.hass.states.get(OTHER_TV).state, 'playing')
            self.assertEqual(self.hass.states.get(OTHER_TV).attributes['source'], 'Other input')
            await self.hass.async_stop(force=True)
        finally:
            self.temp.cleanup()

    def tv(self, state, *, source='Live TV', apps=(APP, 'Live TV')):
        attrs = {'source': source}
        if apps is not None:
            attrs['source_list'] = list(apps)
        self.hass.states.async_set(TV, state, attrs)

    def record(self, call):
        # Every fake device handler fails immediately on an unintended target.
        self.assertEqual(call.data['entity_id'], [TV])
        self.events.append(call.service)

    async def wake(self, call):
        self.record(call)
        self.wake_requested.set()
        if self.wake_confirms:
            state = self.hass.states.get(TV)
            self.hass.states.async_set(TV, 'on', dict(state.attributes))

    async def off(self, call):
        self.record(call)
        self.tv('off')

    async def select(self, call):
        self.record(call)
        self.assertEqual(call.data['source'], APP)
        self.assertIn(self.hass.states.get(TV).state, ACTIVE_STATES)
        self.source_requested.set()
        if self.select_raises:
            raise HomeAssistantError('Simulated app launch failure')
        if self.select_confirms:
            self.tv('on', source=APP)

    async def request(self, name='living_room_tv_start_ott'):
        return await asyncio.wait_for(
            self.hass.services.async_call('script', name, blocking=True), 2
        )

    async def power(self):
        await self.request('living_room_tv_power_ott')

    async def finish_start(self):
        async with asyncio.timeout(2):
            while self.hass.states.get(START).state != 'off':
                await asyncio.sleep(.001)

    def start_execution(self):
        runs = self.hass.data['trace'][START].runs
        return list(runs.values())[-1].as_short_dict()['script_execution']

    async def test_off_tv_wakes_then_opens_app(self):
        await self.power()
        await self.finish_start()
        self.assertEqual(self.events, ['turn_on', 'select_source'])
        self.assertEqual(self.hass.states.get(TV).attributes['source'], APP)
        self.assertEqual(self.start_execution(), 'finished')

    async def test_launch_waits_for_actual_tv_readiness(self):
        self.wake_confirms = False
        task = asyncio.create_task(self.request())
        await asyncio.wait_for(self.wake_requested.wait(), 1)
        self.assertEqual(self.events, ['turn_on'])
        self.tv('on')
        await task
        self.assertEqual(self.events, ['turn_on', 'select_source'])

    async def test_app_catalog_can_arrive_after_power_on(self):
        self.tv('off', apps=None)
        task = asyncio.create_task(self.request())
        await asyncio.wait_for(self.wake_requested.wait(), 1)
        self.assertEqual(self.events, ['turn_on'])
        self.tv('on')
        await task
        self.assertEqual(self.events, ['turn_on', 'select_source'])

    async def test_start_is_idempotent_when_msx_is_already_active(self):
        for state in ACTIVE_STATES:
            with self.subTest(state=state):
                self.tv(state, source=APP)
                await self.request()
                self.assertEqual(self.events, [])

    async def test_active_other_app_selects_msx_without_wake(self):
        for state in ACTIVE_STATES:
            with self.subTest(state=state):
                self.events.clear()
                self.tv(state, source='Plex')
                await self.request()
                self.assertEqual(self.events, ['select_source'])

    async def test_power_on_active_tv_only_turns_it_off(self):
        for state in ACTIVE_STATES:
            with self.subTest(state=state):
                self.events.clear()
                self.tv(state, source=APP)
                await self.power()
                self.assertEqual(self.events, ['turn_off'])
                self.assertEqual(self.hass.states.get(TV).state, 'off')
                self.assertEqual(self.hass.states.get(START).state, 'off')

    async def test_unconfirmed_power_never_launches_app(self):
        self.wake_confirms = False
        for state in ('off', 'unknown', 'unavailable'):
            with self.subTest(state=state):
                self.events.clear()
                self.tv(state)
                await self.request()
                self.assertEqual(self.events, ['turn_on'])
                self.assertEqual(self.hass.states.get(TV).state, state)
                self.assertEqual(self.hass.states.get(START).state, 'off')
                self.assertEqual(self.start_execution(), 'aborted')

    async def test_missing_or_uninstalled_app_never_selects_source(self):
        for apps in (None, (), ('Live TV', 'Plex')):
            with self.subTest(apps=apps):
                self.tv('on', apps=apps)
                await self.request()
                self.assertEqual(self.events, [])
                self.assertEqual(self.start_execution(), 'aborted')

    async def test_launch_requires_source_confirmation(self):
        self.select_confirms = False
        self.tv('on')
        await self.request()
        self.assertEqual(self.events, ['select_source'])
        self.assertEqual(self.hass.states.get(TV).attributes['source'], 'Live TV')
        self.assertEqual(self.start_execution(), 'aborted')

    async def test_app_launch_failure_is_not_a_success(self):
        self.select_raises = True
        self.tv('on')
        with self.assertRaises(HomeAssistantError):
            await self.request()
        self.assertEqual(self.events, ['select_source'])
        self.assertEqual(self.hass.states.get(TV).attributes['source'], 'Live TV')

    async def test_duplicate_power_presses_while_off_share_one_start(self):
        self.wake_confirms = False
        await self.power()
        await asyncio.wait_for(self.wake_requested.wait(), 1)
        await self.power()
        # A duplicate must return before the original wake's deadline, leaving
        # Power available to turn the TV off once it becomes active.
        self.assertEqual(self.hass.states.get(START).state, 'on')
        await self.power()
        self.assertEqual(self.hass.states.get(START).state, 'on')
        self.assertEqual(self.events, ['turn_on'])
        self.tv('on')
        await self.finish_start()
        self.assertEqual(self.events, ['turn_on', 'select_source'])

    async def test_power_off_cancels_waiting_app_launch(self):
        self.tv('off', apps=None)
        await self.power()
        await asyncio.wait_for(self.wake_requested.wait(), 1)
        self.assertEqual(self.hass.states.get(TV).state, 'on')
        self.assertEqual(self.hass.states.get(START).state, 'on')
        await self.power()
        self.assertEqual(self.events, ['turn_on', 'turn_off'])
        self.assertEqual(self.hass.states.get(START).state, 'off')
        # A delayed catalog update must not revive the cancelled launch.
        self.tv('off')
        await self.hass.async_block_till_done()
        self.assertEqual(self.events, ['turn_on', 'turn_off'])

    async def test_power_off_cancels_waiting_app_confirmation(self):
        self.select_confirms = False
        await self.power()
        await asyncio.wait_for(self.source_requested.wait(), 1)
        self.assertEqual(self.hass.states.get(START).state, 'on')
        await self.power()
        self.assertEqual(self.events, ['turn_on', 'select_source', 'turn_off'])
        self.assertEqual(self.hass.states.get(START).state, 'off')
        self.tv('off', source=APP)
        await self.hass.async_block_till_done()
        self.assertEqual(self.events, ['turn_on', 'select_source', 'turn_off'])

    async def test_tv_lost_while_waiting_for_catalog_is_not_targeted(self):
        self.tv('off', apps=None)
        task = asyncio.create_task(self.request())
        await asyncio.wait_for(self.wake_requested.wait(), 1)
        self.tv('unavailable')
        await task
        self.assertEqual(self.events, ['turn_on'])
        self.assertEqual(self.start_execution(), 'aborted')


if __name__ == '__main__':
    unittest.main()
