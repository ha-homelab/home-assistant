"""Run the optional Cisco branch in isolated HA; never contact a phone or camera."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import os
from pathlib import Path
import shlex
import tempfile
import unittest
from unittest.mock import patch

try:
    import yaml
    from homeassistant import loader
    from homeassistant.bootstrap import async_load_base_functionality
    from homeassistant.config_entries import ConfigEntries
    from homeassistant.core import HomeAssistant, Context, SupportsResponse
    from homeassistant.exceptions import HomeAssistantError
    from homeassistant.helpers import config_validation as cv
    from homeassistant.helpers.script import Script
    from homeassistant.helpers.template import Template
    from homeassistant.setup import async_setup_component
except ImportError:
    if os.environ.get('REQUIRE_HA_RUNTIME') == '1':
        raise
    HA_AVAILABLE = False
else:
    HA_AVAILABLE = True

ROOT = Path(os.environ.get('RESILIENCE_TEST_ROOT', Path(__file__).resolve().parents[1]))


@unittest.skipUnless(HA_AVAILABLE, 'Home Assistant runtime is not installed')
class CiscoMotionNotificationsTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='cisco-motion-ha-')
        self.hass = HomeAssistant(self.temp.name)
        loader.async_setup(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self.hass.config.skip_pip = True
        self.assertTrue(await async_load_base_functionality(self.hass))
        self.package = yaml.safe_load((ROOT / 'config/packages/cisco_motion_notifications.yaml').read_text())
        self.receiver_started = False
        self.hass.states.async_set('input_boolean.notifications_off', 'off')
        self.calls = []
        self.release = asyncio.Event()
        self.release.set()
        self.entered = asyncio.Event()
        self.fail_helper = False

        async def helper(call):
            self.calls.append(deepcopy(dict(call.data)))
            self.entered.set()
            await self.release.wait()
            if self.fail_helper:
                raise HomeAssistantError('Synthetic Cisco failure')

        self.hass.services.async_register('shell_command', 'cisco_motion_snapshot', helper)

    async def asyncTearDown(self):
        self.release.set()
        await self.hass.async_block_till_done()
        await self.hass.async_stop(force=True)
        self.temp.cleanup()

    def payload(self, **overrides):
        return {
            'camera_key': 'garage',
            'event_id': '01ABCDEF1234567890ABCDEF12345678_garage',
            'event_at': int(datetime.now(timezone.utc).timestamp()),
            **overrides,
        }

    async def start_receiver(self, additional_automations=None):
        if self.receiver_started:
            return
        self.assertTrue(await async_setup_component(self.hass, 'automation', {
            'automation': [*self.package['automation'], *(additional_automations or [])],
        }))
        await self.hass.async_start()
        self.receiver_started = True

    async def run_helper(self, payload):
        await self.start_receiver()
        self.hass.bus.async_fire('cisco_motion_snapshot_requested', payload)
        await self.hass.async_block_till_done()

    async def test_package_registration_valid_event_and_mute(self):
        await self.start_receiver()
        self.assertIsNotNone(self.hass.states.get('automation.cisco_show_a_motion_snapshot'))
        payload = self.payload()
        await self.run_helper(payload)
        self.assertEqual(self.calls, [payload])
        self.hass.states.async_set('input_boolean.notifications_off', 'on')
        await self.run_helper(self.payload(event_id='other_context_garage'))
        self.assertEqual(self.calls, [payload])
        self.hass.states.async_remove('input_boolean.notifications_off')
        await self.run_helper(self.payload(event_id='missing_mute_garage'))
        self.assertEqual(self.calls, [payload])

    async def test_invalid_stale_and_future_events_never_start_helper(self):
        now = int(datetime.now(timezone.utc).timestamp())
        for payload in [
            self.payload(camera_key='unknown'),
            self.payload(camera_key='garage; touch /tmp/not-run'),
            self.payload(event_id='short'),
            self.payload(event_id='valid_event\n'),
            self.payload(event_id='x' * 97),
            self.payload(event_id='event$(id)'),
            self.payload(event_at=now - 91),
            self.payload(event_at=now + 10),
            self.payload(event_at=now + 0.5),
            self.payload(event_at='not-a-time'),
            {'camera_key': 'garage', 'event_id': 'missing_time'},
        ]:
            with self.subTest(payload=payload):
                await self.run_helper(payload)
        self.assertEqual(self.calls, [])

    async def test_shell_arguments_cannot_interpolate_shell_syntax(self):
        template = Template(self.package['shell_command']['cisco_motion_snapshot'], self.hass)
        valid = self.payload()
        arguments = shlex.split(template.async_render(valid, parse_result=False))
        self.assertEqual(arguments[:4], [
            'python3', '/config/housekeeping/cisco_motion_snapshot.py',
            '--config', '/config/.storage/cisco_motion/config.json',
        ])
        self.assertEqual(arguments[4:], [
            '--camera', valid['camera_key'], '--event-id', valid['event_id'],
            '--event-at', str(valid['event_at']),
        ])
        for bad_id in ['good_event\n', '$(touch /tmp/not-run)', 'a;id', "'quoted'", 'a' * 97]:
            rendered = template.async_render({
                'camera_key': 'garage;id', 'event_id': bad_id,
                'event_at': '123;id',
            }, parse_result=False)
            self.assertEqual(shlex.split(rendered)[4:], [
                '--camera', 'invalid', '--event-id', 'invalid/event', '--event-at', '0',
            ])

    async def test_event_action_is_nonblocking_and_overflow_is_not_queued(self):
        await self.start_receiver()
        self.release.clear()
        producer = Script(self.hass, cv.SCRIPT_SCHEMA([{
            'event': 'cisco_motion_snapshot_requested',
            'event_data': {
                'camera_key': '{{ camera_key }}', 'event_id': '{{ event_id }}',
                'event_at': '{{ event_at }}',
            },
        }]), 'event producer', 'script')
        for number in range(5):
            await asyncio.wait_for(producer.async_run(
                self.payload(event_id=f'context_{number:08d}_garage'), context=Context(),
            ), timeout=1)
        await asyncio.wait_for(self.entered.wait(), timeout=1)
        # Every producer finishes while four helpers remain blocked. The fifth
        # event is dropped and must not run after one of them completes.
        self.assertEqual(len(self.calls), 4)
        self.release.set()
        await self.hass.async_block_till_done()
        self.assertEqual(len(self.calls), 4)

    async def test_helper_failure_is_contained(self):
        self.fail_helper = True
        await self.run_helper(self.payload())
        self.assertEqual(len(self.calls), 1)

    async def test_existing_motion_routes_dispatch_only_after_mobile(self):
        configurations = [yaml.safe_load((ROOT / f'config/packages/{name}.yaml').read_text())
                          for name in ['camera_person_notifications', 'onvif_video_notifications']]
        events = []

        async def mobile(call):
            events.append(('mobile', deepcopy(dict(call.data))))

        async def helper(call):
            events.append(('cisco', deepcopy(dict(call.data))))

        async def prepare(call):
            return {'returncode': 0, 'stdout': '{"ready": true}', 'stderr': ''}

        self.hass.services.async_register('script', 'notify_optional', mobile)
        self.hass.services.async_register('shell_command', 'cisco_motion_snapshot', helper)
        for service in ['ring_notification_video_ready', 'onvif_notification_video_ready']:
            self.hass.services.async_register('shell_command', service, prepare,
                                             supports_response=SupportsResponse.ONLY)
        sources = {
            'sensor.garage_person_active_count_2': ('0', '1', 'garage'),
            'sensor.porch_person_active_count_2': ('0', '1', 'porch'),
            'binary_sensor.front_door_motion_2': ('off', 'on', 'ring'),
            'binary_sensor.living_room_camera_cell_motion_detection': ('off', 'on', 'living_room_onvif'),
        }
        clock = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)
        with patch('homeassistant.util.dt.now', return_value=clock), \
             patch('homeassistant.util.dt.utcnow', return_value=clock), \
             patch('homeassistant.helpers.script.utcnow', return_value=clock):
            for entity, (old, _, _) in sources.items():
                self.hass.states.async_set(entity, old, timestamp=clock.timestamp())
            await self.start_receiver([item for config in configurations for item in config['automation']])
            for entity, (_, new, key) in sources.items():
                context = Context()
                self.hass.states.async_set(entity, new, context=context, timestamp=clock.timestamp())
                await self.hass.async_block_till_done()
                self.assertEqual([kind for kind, _ in events], ['mobile', 'cisco'])
                payload = events[-1][1]
                self.assertEqual(payload, {
                    'camera_key': key, 'event_id': f'{context.id}_{key}',
                    'event_at': int(clock.timestamp()),
                })
                events.clear()
            self.hass.states.async_set('input_boolean.notifications_off', 'on')
            for entity, (old, new, _) in sources.items():
                self.hass.states.async_set(entity, old)
                self.hass.states.async_set(entity, new)
            await self.hass.async_block_till_done()
            self.assertEqual(events, [])


if __name__ == '__main__':
    unittest.main()
