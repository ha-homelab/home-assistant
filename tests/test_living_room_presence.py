"""Exercise the real HA automation/script engine with fake switches and clock."""
import asyncio
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
    from homeassistant.core import Context, HomeAssistant
    from homeassistant.helpers import config_validation as cv
    from homeassistant.helpers.script import Script
    from homeassistant.setup import async_setup_component
    from homeassistant.util import dt as dt_util
except ImportError:
    if os.environ.get('REQUIRE_HA_RUNTIME') == '1':
        raise
    HA_AVAILABLE = False
else:
    HA_AVAILABLE = True

ROOT = Path(os.environ.get('PRESENCE_TEST_ROOT', Path(__file__).resolve().parents[1]))
LAMP = 'switch.living_lamp'
PRESENCE = 'binary_sensor.living_room_presence'
STICKY = 'input_boolean.living_room_sticky'


@unittest.skipUnless(HA_AVAILABLE, 'Home Assistant runtime is not installed')
class LivingRoomPresenceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='living-presence-test-')
        self.hass = HomeAssistant(self.temp.name)
        loader.async_setup(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self.hass.config.skip_pip = True
        self.hass.config.time_zone = 'America/Los_Angeles'
        dt_util.set_default_time_zone(ZoneInfo('America/Los_Angeles'))
        self.assertTrue(await async_load_base_functionality(self.hass))
        self.calls = []
        self.hass.services.async_register('switch', 'turn_on', self.command)
        self.hass.services.async_register('switch', 'turn_off', self.command)
        self.hass.states.async_set(LAMP, 'off')
        self.hass.states.async_set(PRESENCE, 'off')
        self.hass.states.async_set(STICKY, 'off')
        self.sun('below_horizon', -5, False)
        self.config = yaml.safe_load((ROOT / 'config/packages/living_room_presence_lamp.yaml').read_text())
        self.spec = self.config['automation'][0]

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.temp.cleanup()

    async def command(self, call):
        targets = call.data['entity_id']
        targets = [targets] if isinstance(targets, str) else targets
        self.assertEqual(targets, [LAMP])
        self.calls.append(call.service)
        self.hass.states.async_set(LAMP, 'on' if call.service == 'turn_on' else 'off')

    def sun(self, state, elevation, rising):
        self.hass.states.async_set('sun.sun', state, {'elevation': elevation, 'rising': rising})

    async def load(self):
        trigger = next(t for t in self.spec['triggers'] if t['id'] == 'absence')
        self.assertEqual(trigger['for'], '00:20:00')
        self.assertEqual(self.spec['variables']['absence_seconds'], 1200)
        trigger['for'] = {'milliseconds': 250}
        self.spec['variables']['absence_seconds'] = .25
        self.assertTrue(await async_setup_component(self.hass, 'automation', self.config))
        await self.hass.async_start()
        await self.settle(.02)

    async def settle(self, seconds=.35):
        await asyncio.sleep(seconds)
        await self.hass.async_block_till_done()

    async def controller(self, trigger='reconcile', clock='2026-10-11T19:00:00'):
        sequence = [{'variables': self.spec['variables']}, *self.spec['conditions'], *self.spec['actions']]
        script = Script(self.hass, cv.SCRIPT_SCHEMA(sequence), 'Presence controller test', 'automation')
        moment = datetime.fromisoformat(clock).replace(tzinfo=ZoneInfo('America/Los_Angeles'))
        with patch('homeassistant.util.dt.now', return_value=moment):
            await script.async_run({'trigger': {'id': trigger}}, context=Context())
            await self.hass.async_block_till_done()

    async def test_presence_then_full_absence_timeout(self):
        await self.load()
        self.hass.states.async_set(PRESENCE, 'on')
        await self.settle(.04)
        self.assertEqual(self.calls, ['turn_on'])
        self.hass.states.async_set(PRESENCE, 'off')
        await self.settle(.04)
        self.assertEqual(self.calls, ['turn_on'])
        await self.settle()
        self.assertEqual(self.calls, ['turn_on', 'turn_off'])

    async def test_renewed_presence_cancels_shutdown(self):
        await self.load()
        self.hass.states.async_set(PRESENCE, 'on')
        await self.settle(.03)
        self.hass.states.async_set(PRESENCE, 'off')
        await self.settle(.05)
        self.hass.states.async_set(PRESENCE, 'on')
        await self.settle()
        self.assertEqual(self.calls, ['turn_on'])

    async def test_sensor_outage_is_not_absence(self):
        await self.load()
        self.hass.states.async_set(PRESENCE, 'on')
        await self.settle(.03)
        self.hass.states.async_set(PRESENCE, 'off')
        await self.settle(.03)
        self.hass.states.async_set(PRESENCE, 'unavailable')
        await self.settle()
        self.assertEqual(self.calls, ['turn_on'])

    async def test_startup_and_lamp_recovery_respect_current_presence(self):
        self.hass.states.async_set(PRESENCE, 'on')
        await self.load()
        self.assertEqual(self.calls, ['turn_on'])
        self.hass.states.async_set(LAMP, 'unavailable')
        await self.settle(.02)
        self.hass.states.async_set(LAMP, 'off')
        await self.settle(.03)
        self.assertEqual(self.calls, ['turn_on', 'turn_on'])

    async def test_reload_reconciles_an_expired_absence(self):
        self.spec['variables']['absence_seconds'] = .05
        self.hass.states.async_set(LAMP, 'on')
        await self.settle(.08)
        # Use the actual clock so the synthetic short absence age is meaningful.
        await self.controller('reload', dt_util.now().replace(tzinfo=None).isoformat())
        self.assertEqual(self.calls, ['turn_off'])

    async def test_evening_threshold_and_existing_presence(self):
        self.hass.states.async_set(PRESENCE, 'on')
        self.sun('above_horizon', .2, False)
        await self.controller('evening')
        self.assertEqual(self.calls, [])
        self.sun('above_horizon', .19, False)
        await self.controller('evening')
        self.assertEqual(self.calls, ['turn_on'])

    async def test_late_sunrise_keeps_lamp_until_sunrise(self):
        self.hass.states.async_set(PRESENCE, 'on')
        self.hass.states.async_set(LAMP, 'on')
        self.sun('below_horizon', -8, True)
        await self.controller('morning', '2026-10-11T06:30:00')
        self.assertEqual(self.calls, [])
        self.sun('above_horizon', -.8, True)
        await self.controller('morning', '2026-10-11T07:14:00')
        self.assertEqual(self.calls, ['turn_off'])

    async def test_early_sunrise_keeps_lamp_until_0630(self):
        self.hass.states.async_set(PRESENCE, 'on')
        self.hass.states.async_set(LAMP, 'on')
        self.sun('above_horizon', -.8, True)
        await self.controller('morning', '2026-06-11T05:45:00')
        self.assertEqual(self.calls, [])
        self.sun('above_horizon', 8, True)
        await self.controller('morning', '2026-06-11T06:30:00')
        self.assertEqual(self.calls, ['turn_off'])

    async def test_daytime_does_not_enforce_switch_state(self):
        self.sun('above_horizon', 40, False)
        self.hass.states.async_set(PRESENCE, 'on')
        await self.controller(clock='2026-10-11T14:00:00')
        self.hass.states.async_set(LAMP, 'on')
        await self.controller(clock='2026-10-11T14:00:00')
        self.assertEqual(self.calls, [])

    async def test_sun_state_change_closes_window_after_sunrise_event(self):
        moment = datetime(2026, 10, 11, 7, 14, tzinfo=ZoneInfo('America/Los_Angeles'))
        self.sun('below_horizon', -1, True)
        self.hass.states.async_set(PRESENCE, 'on')
        with patch('homeassistant.util.dt.now', return_value=moment):
            await self.load()
            self.assertEqual(self.calls, ['turn_on'])
            # The state update can arrive after the sunrise event callback.
            self.sun('above_horizon', -.8, True)
            await self.settle(.05)
        self.assertEqual(self.calls, ['turn_on', 'turn_off'])

    async def test_unknown_sun_blocks_commands(self):
        self.hass.states.async_set(LAMP, 'on')
        self.hass.states.async_set(PRESENCE, 'on')
        self.sun('unavailable', None, None)
        await self.controller('morning', '2026-10-11T07:14:00')
        self.assertEqual(self.calls, [])

    async def test_sticky_blocks_presence_and_all_reconciliation_paths(self):
        self.hass.states.async_set(STICKY, 'on')
        self.hass.states.async_set(PRESENCE, 'on')
        await self.load()
        self.assertEqual(self.calls, [])
        for trigger in ('presence', 'evening', 'startup', 'reload', 'reconcile', 'lamp'):
            with self.subTest(trigger=trigger):
                await self.controller(trigger)
                self.assertEqual(self.calls, [])

    async def test_sticky_enabled_during_absence_preserves_light(self):
        await self.load()
        self.hass.states.async_set(PRESENCE, 'on')
        await self.settle(.03)
        self.assertEqual(self.calls, ['turn_on'])
        self.hass.states.async_set(PRESENCE, 'off')
        await self.settle(.03)
        self.hass.states.async_set(STICKY, 'on')
        await self.settle()
        self.assertEqual(self.calls, ['turn_on'])
        self.assertEqual(self.hass.states.get(LAMP).state, 'on')

    async def test_sticky_blocks_expired_absence_and_morning_shutdown(self):
        self.hass.states.async_set(STICKY, 'on')
        self.hass.states.async_set(LAMP, 'on')
        self.spec['variables']['absence_seconds'] = .01
        await self.settle(.03)
        await self.controller('absence', dt_util.now().replace(tzinfo=None).isoformat())
        await self.controller('reload', dt_util.now().replace(tzinfo=None).isoformat())
        self.sun('above_horizon', 5, True)
        await self.controller('morning', '2026-10-11T08:00:00')
        self.assertEqual(self.calls, [])
        self.assertEqual(self.hass.states.get(LAMP).state, 'on')

    async def test_missing_unknown_or_unavailable_sticky_blocks_light_changes(self):
        self.spec['variables']['absence_seconds'] = .01
        for sticky_state in (None, 'unknown', 'unavailable'):
            with self.subTest(sticky_state=sticky_state):
                if sticky_state is None:
                    self.hass.states.async_remove(STICKY)
                else:
                    self.hass.states.async_set(STICKY, sticky_state)
                self.hass.states.async_set(PRESENCE, 'on')
                self.hass.states.async_set(LAMP, 'off')
                await self.controller('presence')
                self.hass.states.async_set(PRESENCE, 'off')
                self.hass.states.async_set(LAMP, 'on')
                await self.settle(.02)
                await self.controller('absence', dt_util.now().replace(tzinfo=None).isoformat())
                self.assertEqual(self.calls, [])

    async def test_manual_switching_survives_active_presence_with_sticky(self):
        self.hass.states.async_set(STICKY, 'on')
        self.hass.states.async_set(PRESENCE, 'on')
        await self.load()
        for command, expected in (('turn_on', 'on'), ('turn_off', 'off')):
            await self.hass.services.async_call(
                'switch', command, {'entity_id': LAMP}, blocking=True)
            await self.settle(.03)
            await self.controller('reconcile')
            self.assertEqual(self.hass.states.get(LAMP).state, expected)
        self.assertEqual(self.calls, ['turn_on', 'turn_off'])

    async def test_disabling_sticky_allows_normal_presence_control_again(self):
        self.hass.states.async_set(STICKY, 'on')
        self.hass.states.async_set(PRESENCE, 'on')
        await self.controller('presence')
        self.assertEqual(self.calls, [])
        self.hass.states.async_set(STICKY, 'off')
        await self.controller('presence')
        self.assertEqual(self.calls, ['turn_on'])


if __name__ == '__main__':
    unittest.main()
