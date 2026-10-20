"""Exercise real room motion actions and camera fades in an isolated HA runtime."""
from copy import deepcopy
from datetime import datetime
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

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

ROOT = Path(os.environ.get('STICKY_TEST_ROOT', Path(__file__).resolve().parents[1]))

# Room ownership is the behavior contract, independent of the conditions being
# implemented in the source. File prefixes are stable automation identifiers.
ROOM_CASES = (
    ('015', 'bathroom', ('light.bathroom_mirror_light',)),
    ('018', 'bathroom', ('switch.bath2',)),
    ('021', 'bedroom', ('light.bedroom_lamp',)),
    ('033', 'dining_room', ('switch.dining_wall_light_2', 'switch.dining_arc_lamp', 'light.adining_lamp_m')),
    ('037', 'hallway', ('light.hall_1_m', 'light.hall_2_m')),
    ('040', 'hallway', ('light.hall_1_m', 'light.hall_2_m')),
    ('045', 'kitchen', ('light.kitchen_lamp_m',)),
    ('046', 'kitchen', ('light.kitchen_lamp_m',)),
    ('050', 'kitchen', ('switch.led_under_cabinet',)),
    ('053', 'kitchen', ('switch.tea_table',)),
    ('064', 'lobby', ('switch.dining_wall_light_2',)),
    ('068', 'mishka_room', ('light.hall_2_m',)),
    ('083', 'porch', ('light.porch_one', 'light.porch_two')),
    ('108', 'living_room', ('switch.dining_media_guard', 'switch.fireplace_switch', 'switch.living_guard2')),
)


@unittest.skipUnless(HA_AVAILABLE, 'Home Assistant runtime is not installed')
class StickyLightingTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='sticky-lighting-test-')
        self.hass = HomeAssistant(self.folder.name)
        loader.async_setup(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self.hass.config.skip_pip = True
        self.hass.config.time_zone = 'America/Los_Angeles'
        dt_util.set_default_time_zone(ZoneInfo('America/Los_Angeles'))
        self.assertTrue(await async_load_base_functionality(self.hass))
        self.calls = []
        self.notifications = []
        self.after_call = None
        self.after_notification = None
        for domain in ('light', 'switch'):
            for service in ('turn_on', 'turn_off'):
                self.hass.services.async_register(domain, service, self.record_command)
        for service in ('notify_mqtt_log', 'notify_optional', 'capture_camera_alert'):
            self.hass.services.async_register('script', service, self.record_notification)
        self.reset_states()

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.folder.cleanup()

    def reset_states(self):
        self.calls.clear()
        self.notifications.clear()
        self.after_call = self.after_notification = None
        self.hass.states.async_set('sun.sun', 'below_horizon', {'elevation': -5, 'rising': False})
        for _, room, targets in ROOM_CASES:
            self.hass.states.async_set(f'input_boolean.{room}_sticky', 'off')
            for entity_id in targets:
                self.hass.states.async_set(entity_id, 'on')

    async def record_command(self, call):
        targets = call.data['entity_id']
        for entity_id in [targets] if isinstance(targets, str) else targets:
            self.calls.append((entity_id, call.service, dict(call.data)))
            self.hass.states.async_set(entity_id, 'on' if call.service == 'turn_on' else 'off')
        if self.after_call:
            self.after_call()

    async def record_notification(self, call):
        self.notifications.append(call.service)
        if self.after_notification:
            self.after_notification()

    def automation(self, prefix):
        paths = list((ROOT / 'dependencies/automations/config').glob(f'{prefix}_*.yaml'))
        if not paths and os.environ.get('REQUIRE_PRIVATE_DEPENDENCIES') != '1':
            self.skipTest('Private automation dependency is not installed')
        self.assertEqual(len(paths), 1, f'Missing or ambiguous automation {prefix}')
        return yaml.safe_load(paths[0].read_text())[0]

    async def run_sequence(self, sequence):
        # 21:00 is inside both retained bedroom schedules and the porch fade.
        moment = datetime(2026, 10, 20, 21, tzinfo=ZoneInfo('America/Los_Angeles'))
        trigger = {'from_state': State('binary_sensor.motion', 'on'),
                   'to_state': State('binary_sensor.motion', 'off')}
        script = Script(self.hass, cv.SCRIPT_SCHEMA(sequence), 'Sticky behavior test', 'automation')
        with patch('homeassistant.util.dt.now', return_value=moment):
            await script.async_run({'trigger': trigger}, context=Context())
        await self.hass.async_block_till_done()

    async def run_automation(self, prefix):
        spec = self.automation(prefix)
        await self.run_sequence([*spec.get('conditions', []), *spec['actions']])

    async def test_every_room_blocks_motion_and_dimming_until_sticky_is_off(self):
        for prefix, room, targets in ROOM_CASES:
            for sticky_state in ('on', 'unknown', 'unavailable', None):
                with self.subTest(automation=prefix, sticky=sticky_state):
                    self.reset_states()
                    sticky = f'input_boolean.{room}_sticky'
                    if sticky_state is None:
                        self.hass.states.async_remove(sticky)
                    else:
                        self.hass.states.async_set(sticky, sticky_state)
                    await self.run_automation(prefix)
                    self.assertEqual(self.calls, [])
            with self.subTest(automation=prefix, sticky='off'):
                self.reset_states()
                await self.run_automation(prefix)
                self.assertEqual([call[0] for call in self.calls], list(targets))

    async def test_enabling_sticky_while_logging_prevents_later_light_commands(self):
        for prefix, room in (('033', 'dining_room'), ('040', 'hallway'),
                             ('045', 'kitchen'), ('046', 'kitchen'), ('050', 'kitchen')):
            with self.subTest(automation=prefix):
                self.reset_states()
                self.after_notification = lambda room=room: self.hass.states.async_set(
                    f'input_boolean.{room}_sticky', 'on')
                await self.run_automation(prefix)
                self.assertTrue(self.notifications)
                self.assertEqual(self.calls, [])

    async def test_shared_targets_honor_other_room_without_blocking_siblings(self):
        cases = (
            ('033', 'lobby', ['switch.dining_arc_lamp', 'light.adining_lamp_m']),
            ('064', 'dining_room', []),
            ('040', 'mishka_room', ['light.hall_1_m']),
            ('037', 'mishka_room', ['light.hall_1_m']),
            ('068', 'hallway', []),
        )
        for prefix, other_room, allowed in cases:
            with self.subTest(automation=prefix, other_room=other_room):
                self.reset_states()
                self.hass.states.async_set(f'input_boolean.{other_room}_sticky', 'on')
                await self.run_automation(prefix)
                self.assertEqual([call[0] for call in self.calls], allowed)

    async def test_sticky_is_rechecked_between_independent_devices(self):
        for prefix, room, first in (('033', 'dining_room', 'switch.dining_wall_light_2'),
                                   ('040', 'hallway', 'light.hall_1_m'),
                                   ('083', 'porch', 'light.porch_one'),
                                   ('108', 'living_room', 'switch.dining_media_guard')):
            with self.subTest(automation=prefix):
                self.reset_states()
                self.after_call = lambda room=room: self.hass.states.async_set(
                    f'input_boolean.{room}_sticky', 'on')
                await self.run_automation(prefix)
                self.assertEqual([call[0] for call in self.calls], [first])

    def porch_sequence(self):
        path = ROOT / 'dependencies/scripts/config/notifications/backdoor_motion.yaml'
        if not path.exists() and os.environ.get('REQUIRE_PRIVATE_DEPENDENCIES') != '1':
            self.skipTest('Private script dependency is not installed')
        sequence = deepcopy(yaml.safe_load(path.read_text())['backdoormotion']['sequence'])

        def shorten_delays(value):
            if isinstance(value, dict):
                if 'delay' in value:
                    value['delay'] = {'milliseconds': 1}
                for item in value.values():
                    shorten_delays(item)
            elif isinstance(value, list):
                for item in value:
                    shorten_delays(item)

        shorten_delays(sequence)
        return sequence

    async def test_camera_notifications_continue_while_porch_sticky_blocks_light(self):
        self.hass.states.async_set('input_boolean.porch_sticky', 'on')
        await self.run_sequence(self.porch_sequence())
        self.assertIn('capture_camera_alert', self.notifications)
        self.assertIn('notify_optional', self.notifications)
        self.assertEqual(self.calls, [])

    async def test_porch_sticky_enabled_mid_fade_stops_dimming_and_final_off(self):
        self.after_call = lambda: self.hass.states.async_set('input_boolean.porch_sticky', 'on')
        await self.run_sequence(self.porch_sequence())
        self.assertEqual([(call[0], call[1]) for call in self.calls],
                         [('light.backdoor_porch', 'turn_on')])
        self.assertEqual(self.hass.states.get('light.backdoor_porch').state, 'on')


if __name__ == '__main__':
    unittest.main()
