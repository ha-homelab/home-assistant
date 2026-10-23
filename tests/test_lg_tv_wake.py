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
        self.events = []
        self.wol_sent = asyncio.Event()
        self.wol_raises = False
        self.wol_wakes = False
        self.wol_delay = 0
        self.wol_release = None
        self.ir_wakes = True
        self.hass.services.async_register('esphome', 'rf_wake_living_tv', self.wake)
        self.hass.services.async_register('remote', 'send_command', self.remote)
        package = yaml.safe_load((ROOT / 'config/packages/lg_tv_wake_on_lan.yaml').read_text())
        self.assertNotIn('shell_command', package)
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
                    self.assertIn(value['timeout'], ('00:00:10', '00:00:45'))
                    value['timeout'] = {'milliseconds': 50}
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
        await self.run_wake()
        await first
        self.assertEqual(self.events, ['wol', 'ir'])


if __name__ == '__main__':
    unittest.main()
