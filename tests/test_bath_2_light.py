"""The Bath 2 facade keeps the relay active and out of screen notifications."""
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
    from homeassistant.helpers import entity_registry as er
    from homeassistant.setup import async_setup_component
    from homeassistant.components.homeassistant.exposed_entities import ExposedEntities
    from homeassistant.components.homeassistant.const import DATA_EXPOSED_ENTITIES
except ImportError:
    if os.environ.get("REQUIRE_HA_RUNTIME") == "1":
        raise
    HA_AVAILABLE = False
else:
    HA_AVAILABLE = True

ROOT = Path(__file__).resolve().parents[1]

@unittest.skipUnless(HA_AVAILABLE, "Home Assistant runtime is not installed")
class BathTwoLightTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.hass = HomeAssistant(self.folder.name)
        self.hass.config.skip_pip = True
        loader.async_setup(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self.assertTrue(await async_load_base_functionality(self.hass))
        exposure = ExposedEntities(self.hass)
        await exposure.async_initialize()
        self.hass.data[DATA_EXPOSED_ENTITIES] = exposure
        self.registry = er.async_get(self.hass)
        self.registry.async_get_or_create('switch', 'test', 'bath-2-relay',
                                         suggested_object_id='bath_2', original_name='Bath 2')
        self.hass.states.async_set('switch.bath_2', 'off', {'friendly_name': 'Bath 2'})
        self.commands = []
        async def command(call):
            self.commands.append(call.service)
            targets = call.data['entity_id']
            self.assertEqual([targets] if isinstance(targets, str) else targets, ['switch.bath_2'])
            self.hass.states.async_set('switch.bath_2', 'on' if call.service == 'turn_on' else 'off')
        for service in ('turn_on', 'turn_off'):
            self.hass.services.async_register('switch', service, command)
        result = await self.hass.config_entries.flow.async_init('switch_as_x', context={'source': 'user'},
            data={'entity_id': 'switch.bath_2', 'target_domain': 'light', 'invert': False})
        self.assertEqual(result['type'], 'create_entry')
        await self.hass.async_block_till_done()

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.folder.cleanup()

    async def test_commands_and_state_follow_the_enabled_hidden_relay(self):
        source = self.registry.async_get('switch.bath_2')
        self.assertIsNone(source.disabled_by)
        self.assertEqual(source.hidden_by, er.RegistryEntryHider.INTEGRATION)
        self.assertEqual(self.hass.states.get('light.bath_2').state, 'off')
        for service, expected in [('turn_on', 'on'), ('turn_off', 'off')]:
            await self.hass.services.async_call('light', service, {'entity_id': 'light.bath_2'}, blocking=True)
            await self.hass.async_block_till_done()
            self.assertEqual(self.hass.states.get('light.bath_2').state, expected)
        self.assertEqual(self.commands, ['turn_on', 'turn_off'])
        self.hass.states.async_set('switch.bath_2', 'unavailable')
        await self.hass.async_block_till_done()
        self.assertEqual(self.hass.states.get('light.bath_2').state, 'unavailable')

    async def test_neither_relay_nor_light_triggers_screen_notifications(self):
        calls = []
        async def notification(call): calls.append(call)
        self.hass.services.async_register('script', 'notify_optional', notification)
        spec = yaml.safe_load(next((ROOT / 'dependencies/automations/config').glob('112_*.yaml')).read_text())
        self.assertTrue(await async_setup_component(self.hass, 'automation', {'automation': spec}))
        await self.hass.async_start()
        await self.hass.async_block_till_done()
        self.hass.states.async_set('switch.bath2', 'off')
        self.hass.states.async_set('switch.bath2', 'on')
        await self.hass.services.async_call('light', 'turn_on', {'entity_id': 'light.bath_2'}, blocking=True)
        await self.hass.async_block_till_done()
        self.assertFalse(calls)
        self.hass.states.async_set('switch.tea_table', 'off')
        self.hass.states.async_set('switch.tea_table', 'on', {'friendly_name': 'Tea table'})
        await self.hass.async_block_till_done()
        self.assertTrue(calls, 'Other screen notifications must remain enabled')
