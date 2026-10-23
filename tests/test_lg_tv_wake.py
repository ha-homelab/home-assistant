"""Exercise LG wake fallback with recorded services, never real devices."""
import os
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

import yaml

try:
    from homeassistant import loader
    from homeassistant.bootstrap import async_load_base_functionality
    from homeassistant.components.automation.config import async_validate_config_item
    from homeassistant.config_entries import ConfigEntries
    from homeassistant.core import Context, HomeAssistant, SupportsResponse
    from homeassistant.exceptions import HomeAssistantError
    from homeassistant.helpers.script import Script
    from homeassistant.helpers.trace import script_execution_get, trace_clear
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
        self.relay_result = {'returncode': 0, 'stdout': '', 'stderr': ''}
        self.relay_raises = False
        self.wol_wakes = False
        self.ir_wakes = True
        self.hass.services.async_register(
            'shell_command', 'living_room_tv_wake', self.relay,
            supports_response=SupportsResponse.ONLY)
        self.hass.services.async_register('remote', 'send_command', self.remote)
        rule = yaml.safe_load((ROOT / 'config/packages/lg_tv_wake_on_lan.yaml').read_text())['automation'][0]
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
                    self.assertEqual(value['timeout'], '00:00:45')
                    value['timeout'] = {'milliseconds': 20}
                for item in value.values():
                    shorten_waits(item)

        shorten_waits(runtime['actions'])
        config = await async_validate_config_item(self.hass, 'automation', runtime)
        self.script = Script(self.hass, config['actions'], config['alias'], 'automation')

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.temp.cleanup()

    async def relay(self, call):
        self.events.append('wol')
        if self.relay_raises:
            raise HomeAssistantError('Simulated shell command failure')
        if self.wol_wakes:
            self.hass.states.async_set(TV, 'on')
        return self.relay_result

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

    async def test_ssh_timeout_falls_back_to_discrete_power_on(self):
        self.relay_result['returncode'] = 255
        await self.run_wake()
        self.assertEqual(self.events, ['wol', 'ir'])
        self.assertEqual(self.hass.states.get(TV).state, 'on')

    async def test_shell_exception_still_falls_back(self):
        self.relay_raises = True
        await self.run_wake()
        self.assertEqual(self.events, ['wol', 'ir'])

    async def test_successful_packet_send_without_tv_confirmation_falls_back(self):
        await self.run_wake()
        self.assertEqual(self.events, ['wol', 'ir'])

    async def test_failed_both_paths_is_not_reported_as_success(self):
        self.relay_result['returncode'] = 255
        self.ir_wakes = False
        await self.run_wake()
        # Top-level HA scripts record stop(error=true) without propagating it.
        self.assertEqual(self.execution, 'aborted')
        self.assertEqual(self.events, ['wol', 'ir'])
        self.assertEqual(self.hass.states.get(TV).state, 'off')

    async def test_already_on_is_untouched(self):
        self.hass.states.async_set(TV, 'on')
        await self.run_wake()
        self.assertEqual(self.events, [])


if __name__ == '__main__':
    unittest.main()
