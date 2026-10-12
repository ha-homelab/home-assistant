"""Run the evening package with fake devices in an isolated HA instance."""
import asyncio
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
except ImportError:
    if os.environ.get('REQUIRE_HA_RUNTIME') == '1':
        raise
    HA_AVAILABLE = False
else:
    HA_AVAILABLE = True

ROOT = Path(os.environ.get('DINING_MEDIA_TEST_ROOT', Path(__file__).resolve().parents[1]))
LAMP = 'switch.living_lamp'
MEDIA = 'switch.dining_media_guard'
STICKY = 'input_boolean.living_room_sticky'


@unittest.skipUnless(HA_AVAILABLE, 'Home Assistant runtime is not installed')
class DiningMediaEveningTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='dining-media-test-')
        self.hass = HomeAssistant(self.temp.name)
        loader.async_setup(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self.hass.config.skip_pip = True
        self.assertTrue(await async_load_base_functionality(self.hass))
        self.calls = []
        self.hass.services.async_register('switch', 'turn_off', self.turn_off)
        self.hass.states.async_set(LAMP, 'on')
        self.hass.states.async_set(MEDIA, 'on')
        self.hass.states.async_set(STICKY, 'off')
        self.hass.states.async_set('sun.sun', 'below_horizon', {'elevation': -5})
        self.hass.states.async_set('switch.fireplace_switch', 'unavailable')
        self.hass.states.async_set('switch.living_guard2', 'unavailable')
        self.config = yaml.safe_load((ROOT / 'config/packages/dining_media_guard_evening.yaml').read_text())
        trigger = self.config['automation'][0]['triggers'][0]
        self.assertEqual(trigger['for'], '00:15:00')
        # Only the test copy shortens the wait; all triggers, guards and actions stay real.
        trigger['for'] = {'milliseconds': 250}

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.temp.cleanup()

    async def turn_off(self, call):
        targets = call.data['entity_id']
        self.calls.extend([targets] if isinstance(targets, str) else targets)

    async def load(self):
        self.assertTrue(await async_setup_component(self.hass, 'automation', self.config))
        await self.hass.async_start()
        await self.hass.async_block_till_done()

    async def settle(self, seconds=.35):
        await asyncio.sleep(seconds)
        await self.hass.async_block_till_done()

    async def test_waits_then_switches_only_media_without_legacy_devices(self):
        await self.load()
        self.hass.states.async_set(LAMP, 'off')
        await self.settle(.04)
        self.assertEqual(self.calls, [])
        await self.settle()
        self.assertEqual(self.calls, [MEDIA])

    async def test_lamp_returning_on_cancels_pending_shutdown(self):
        await self.load()
        self.hass.states.async_set(LAMP, 'off')
        await self.settle(.04)
        self.hass.states.async_set(LAMP, 'on')
        await self.settle()
        self.assertEqual(self.calls, [])

    async def test_sticky_enabled_during_wait_blocks_shutdown(self):
        await self.load()
        self.hass.states.async_set(LAMP, 'off')
        await self.settle(.04)
        self.hass.states.async_set(STICKY, 'on')
        await self.settle()
        self.assertEqual(self.calls, [])

    async def test_daylight_boundary_and_unknown_sun_block_shutdown(self):
        await self.load()
        for elevation in (-2, 15, None):
            with self.subTest(elevation=elevation):
                self.hass.states.async_set(LAMP, 'on')
                self.hass.states.async_set('sun.sun', 'unknown' if elevation is None else 'above_horizon',
                                           {} if elevation is None else {'elevation': elevation})
                await self.settle(.02)
                self.hass.states.async_set(LAMP, 'off')
                await self.settle()
                self.assertEqual(self.calls, [])

    async def test_dining_arc_does_not_trigger_media_shutdown(self):
        await self.load()
        self.hass.states.async_set('switch.dining_arc_lamp', 'on')
        await self.settle(.02)
        self.hass.states.async_set('switch.dining_arc_lamp', 'off')
        await self.settle()
        self.assertEqual(self.calls, [])

    async def test_loading_with_lamp_already_off_does_not_send_command(self):
        self.hass.states.async_set(LAMP, 'off')
        await self.load()
        await self.settle()
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
