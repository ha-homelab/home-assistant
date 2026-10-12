"""Exercise RM433 navigation and the d1 presence gate without contacting a player."""

import asyncio
from copy import deepcopy
from datetime import timedelta
import json
import os
from pathlib import Path
import tempfile
import unittest
from urllib.parse import parse_qs, urlparse

try:
    from homeassistant import loader
    from homeassistant.bootstrap import async_load_base_functionality
    from homeassistant.config import async_hass_config_yaml
    from homeassistant.config_entries import ConfigEntries
    from homeassistant.core import HomeAssistant, SupportsResponse
    from homeassistant.exceptions import HomeAssistantError
    from homeassistant.helpers.template import Template
    from homeassistant.setup import async_setup_component
    from homeassistant.util import dt as dt_util
except ImportError:
    if os.environ.get('REQUIRE_HA_RUNTIME') == '1':
        raise
    HA_AVAILABLE = False
else:
    HA_AVAILABLE = True

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(HA_AVAILABLE, 'Requires the deployed Home Assistant runtime')
class OttD1RemoteTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ott-d1-remote-test-')
        self.hass = HomeAssistant(self.temp.name)
        loader.async_setup(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self.hass.config.skip_pip = True
        root = Path(self.temp.name)
        (root / 'packages').mkdir()
        (root / 'packages/ott_d1_remote.yaml').write_text(
            (ROOT / 'config/packages/ott_d1_remote.yaml').read_text()
        )
        (root / 'configuration.yaml').write_text(
            'homeassistant:\n  packages: !include_dir_named packages\n'
        )
        (root / 'secrets.yaml').write_text(
            'ott_control_authorization: Bearer test-only-not-a-real-credential\n'
            'ott_control_devices_url: https://control.example.invalid/ott-control/api/devices\n'
            'ott_control_d1_input_url: https://control.example.invalid/ott-control/api/requests?'
            'device_id=dev_c0b414dd92b2b5a36fffde703a6968f5\n'
        )
        config = await async_hass_config_yaml(self.hass)
        automation = self.automation = config['automation'][0]
        self.triggers = automation['triggers']
        actions = automation['actions']
        self.trigger_gate = Template(actions[0]['value_template'], self.hass)
        sequence = next(action['repeat']['sequence'] for action in actions if 'repeat' in action)
        condition = next(action['variables']['ready'] for action in sequence
                         if 'ready' in action.get('variables', {}))
        self.gate = Template(condition, self.hass)
        command = config['rest_command']['ott_d1_input']
        self.device_id = parse_qs(urlparse(command['url']).query)['device_id'][0]
        self.payload = Template(command['payload'], self.hass)
        dispatch = next(
            action for action in actions
            if action.get('action') == 'rest_command.ott_d1_input'
        )
        self.key = Template(dispatch['data']['key'], self.hass)

    async def asyncTearDown(self):
        try:
            if self.hass.services.has_service('automation', 'turn_off'):
                await self.hass.services.async_call(
                    'automation', 'turn_off', {'entity_id': 'all', 'stop_actions': True},
                    blocking=True,
                )
            await self.hass.async_stop(force=True)
        finally:
            self.temp.cleanup()

    def presence(self, **overrides):
        device = {
            'id': self.device_id,
            'last_seen': (dt_util.utcnow() - timedelta(seconds=1)).isoformat(),
            'pending': 0,
        }
        device.update(overrides)
        return {'status': 200, 'content': {'devices': [device]}}

    def allowed(self, presence):
        return self.gate.async_render({'presence': presence})

    async def test_fresh_idle_player_is_allowed(self):
        self.assertIs(self.allowed(self.presence()), True)

    async def test_missing_and_malformed_responses_are_rejected(self):
        for response in (
            None, {}, [], 'not JSON',
            {'status': 200},
            {'status': 403, 'content': self.presence()['content']},
            {'status': 200, 'content': 'not an object'},
            {'status': 200, 'content': {'devices': None}},
            {'status': 200, 'content': {'devices': 'not a list'}},
            {'status': 200, 'content': {'devices': [None, 'invalid', {}]}},
            self.presence(id='another-player'),
            self.presence(last_seen=None),
            self.presence(last_seen='invalid date'),
            self.presence(last_seen=123),
            self.presence(pending=False),
            self.presence(pending='0'),
        ):
            with self.subTest(response=response):
                self.assertIs(self.allowed(response), False)

    async def test_stale_future_and_busy_players_are_rejected(self):
        for overrides in (
            {'last_seen': (dt_util.utcnow() - timedelta(seconds=30)).isoformat()},
            {'last_seen': (dt_util.utcnow() + timedelta(seconds=30)).isoformat()},
            {'pending': 1},
        ):
            with self.subTest(overrides=overrides):
                self.assertIs(self.allowed(self.presence(**overrides)), False)

    async def test_duplicate_target_is_rejected(self):
        response = self.presence()
        response['content']['devices'].append(
            deepcopy(response['content']['devices'][0])
        )
        self.assertIs(self.allowed(response), False)

    async def test_exact_six_buttons_are_mapped_to_navigation(self):
        expected = {
            'button_1': 'up', 'button_2': 'left',
            'button_3': 'down', 'button_4': 'right',
            'button_7': 'back', 'button_8': 'ok',
        }
        self.assertEqual(len(self.triggers), len(expected))
        self.assertEqual(
            {trigger['subtype']: trigger['id'] for trigger in self.triggers},
            expected,
        )
        for trigger in self.triggers:
            with self.subTest(button=trigger['subtype']):
                self.assertEqual(trigger['trigger'], 'device')
                self.assertEqual(trigger['domain'], 'mqtt')
                self.assertEqual(trigger['type'], 'button_short_press')
                self.assertEqual(trigger['device_id'], '8ac1a57250698f6b441439e5a6e9c5a0')

    async def test_each_navigation_key_emits_typed_input(self):
        for expected in ('up', 'down', 'left', 'right', 'back', 'ok'):
            with self.subTest(key=expected):
                variables = {'trigger': {'id': expected}}
                self.assertIs(self.trigger_gate.async_render(variables), True)
                key = self.key.async_render(variables)
                self.assertEqual(key, expected)
                payload = json.loads(self.payload.async_render(
                    {'key': key}, parse_result=False
                ))
                self.assertEqual(payload, {'action': 'input', 'params': {'key': expected}})

    async def test_unassigned_and_invalid_triggers_are_rejected(self):
        for variables in (
            {}, {'trigger': {}}, {'trigger': {'id': None}},
            *({'trigger': {'id': key}} for key in (
                '', 'button_5', 'button_6', 'previous', 'next', 'volume_up',
            )),
        ):
            with self.subTest(variables=variables):
                self.assertIs(self.trigger_gate.async_render(variables), False)

    async def load_runtime(self, presence_handler=None, input_handler=None):
        """Run the real automation with local event triggers and fake REST services."""
        self.assertTrue(await async_load_base_functionality(self.hass))
        self.get_calls = 0
        self.posts = []

        async def get_presence(call):
            self.get_calls += 1
            return await presence_handler() if presence_handler else self.presence()

        async def post_input(call):
            self.posts.append(call.data['key'])
            if input_handler:
                return await input_handler()
            return {'status': 202, 'content': {'id': 'test-only', 'status': 'queued'}}

        self.hass.services.async_register('rest_command', 'ott_d1_presence', get_presence,
                                          supports_response=SupportsResponse.ONLY)
        self.hass.services.async_register('rest_command', 'ott_d1_input', post_input,
                                          supports_response=SupportsResponse.ONLY)
        automation = deepcopy(self.automation)
        automation['alias'] = 'OTT d1 test'
        automation['triggers'] = [
            {'trigger': 'event', 'event_type': 'test_rm433',
             'event_data': {'key': trigger['id']}, 'id': trigger['id']}
            for trigger in self.triggers
        ]
        self.assertTrue(await async_setup_component(self.hass, 'automation',
                                                    {'automation': [automation]}))
        await self.hass.async_start()
        self.entity = 'automation.ott_d1_test'
        self.assertEqual(self.hass.states.get(self.entity).state, 'on')

    def press(self, key):
        self.hass.bus.async_fire('test_rm433', {'key': key})

    def active_runs(self):
        return self.hass.states.get(self.entity).attributes.get('current', 0)

    async def until(self, predicate, timeout=4):
        async with asyncio.timeout(timeout):
            while not predicate():
                await asyncio.sleep(0.01)

    async def test_busy_player_is_rechecked_then_receives_one_input(self):
        async def presence():
            return self.presence(pending=1 if self.get_calls < 3 else 0)

        await self.load_runtime(presence)
        self.press('left')
        await self.until(lambda: len(self.posts) == 1 and self.active_runs() == 0)
        self.assertEqual(self.get_calls, 3)
        self.assertEqual(self.posts, ['left'])

    async def test_close_presses_remain_in_fifo_order(self):
        release = asyncio.Event()

        async def post():
            if len(self.posts) == 1:
                await release.wait()
            return {'status': 202}

        await self.load_runtime(input_handler=post)
        self.press('down')
        await self.until(lambda: self.posts == ['down'])
        self.press('left')
        await self.until(lambda: self.active_runs() == 2)
        release.set()
        await self.until(lambda: len(self.posts) == 2 and self.active_runs() == 0)
        self.assertEqual(self.posts, ['down', 'left'])

    async def test_busy_deadline_discards_input_without_later_replay(self):
        busy = True

        async def presence():
            return self.presence(pending=int(busy))

        await self.load_runtime(presence)
        self.press('right')
        await self.until(lambda: self.get_calls > 1 and self.active_runs() == 0)
        self.assertFalse(self.posts)
        busy = False
        await asyncio.sleep(0.2)
        self.assertFalse(self.posts)

    async def test_queue_wait_does_not_reset_deadline_or_send_after_slow_get(self):
        release = asyncio.Event()

        async def presence():
            await release.wait()
            return self.presence()

        await self.load_runtime(presence)
        self.press('up')
        await self.until(lambda: self.get_calls == 1)
        self.press('left')
        await self.until(lambda: self.active_runs() == 2)
        await asyncio.sleep(2.1)
        release.set()
        await self.until(lambda: self.active_runs() == 0)
        self.assertEqual(self.get_calls, 1, 'Expired queued input must not start a fresh GET')
        self.assertFalse(self.posts, 'A slow successful GET must not permit a late POST')

    async def test_queue_is_bounded_to_four_including_active_run(self):
        release = asyncio.Event()

        async def presence():
            await release.wait()
            return self.presence()

        await self.load_runtime(presence)
        self.press('up')
        await self.until(lambda: self.get_calls == 1)
        for key in ('down', 'left', 'right', 'back'):
            self.press(key)
        await self.until(lambda: self.active_runs() == 4)
        await asyncio.sleep(0.05)
        self.assertEqual(self.active_runs(), 4)
        release.set()
        await self.until(lambda: self.active_runs() == 0)
        self.assertEqual(self.posts, ['up', 'down', 'left', 'right'])

    async def test_post_timeout_is_not_retried(self):
        async def post():
            raise HomeAssistantError('Simulated POST timeout after possible delivery')

        await self.load_runtime(input_handler=post)
        self.press('ok')
        await self.until(lambda: self.posts == ['ok'] and self.active_runs() == 0)
        await asyncio.sleep(0.2)
        self.assertEqual(self.posts, ['ok'])
        self.assertEqual(self.get_calls, 1)


if __name__ == '__main__':
    unittest.main()
