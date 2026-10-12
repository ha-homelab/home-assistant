"""Run the restored bedroom rule with simulated time and recording services."""
from datetime import datetime, timezone
import logging
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
    from homeassistant.components.automation import AutomationEntity, _async_process_if
    from homeassistant.components.automation.config import async_validate_config_item
    from homeassistant.components.light import LIGHT_TURN_ON_SCHEMA
    from homeassistant.components.trace.const import DATA_TRACE
    from homeassistant.config_entries import ConfigEntries
    from homeassistant.core import Context, HomeAssistant
    from homeassistant.helpers.entity_component import EntityComponent
    from homeassistant.helpers import config_validation as cv
    from homeassistant.helpers.script import Script
except ImportError:
    if os.environ.get("REQUIRE_HA_RUNTIME") == "1":
        raise
    HA_AVAILABLE = False
else:
    HA_AVAILABLE = True

ROOT = Path(__file__).resolve().parents[1]
ZONE = ZoneInfo('America/Los_Angeles')


@unittest.skipUnless(HA_AVAILABLE, 'Deployment test requires Home Assistant runtime')
class BedroomLampTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='bedroom-lamp-test-')
        self.hass = HomeAssistant(self.temp.name)
        loader.async_setup(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self.hass.config.skip_pip = True
        await self.hass.config.async_set_time_zone(str(ZONE))
        self.assertTrue(await async_load_base_functionality(self.hass))
        self.hass.data[DATA_TRACE] = {}
        self.calls = []
        for domain in ['light', 'switch']:
            schema = LIGHT_TURN_ON_SCHEMA if domain == 'light' else {}
            self.hass.services.async_register(domain, 'turn_on', self.record,
                                               schema=cv.make_entity_service_schema(schema))
        rule = yaml.safe_load((ROOT / 'config/021_bedroom_turn_on_lights_after_motion.yaml').read_text())[0]
        self.assertEqual(rule['triggers'], [{'entity_id': 'binary_sensor.rf_bedroom_motion', 'platform': 'state', 'to': 'on'}])
        config = await async_validate_config_item(self.hass, 'automation', rule)
        condition = await _async_process_if(self.hass, config['alias'], config)
        script = Script(self.hass, config['actions'], config['alias'], 'automation', script_mode=config['mode'])
        self.automation = AutomationEntity(config['id'], config['alias'], config['triggers'], condition, script,
                                           False, None, None, rule, None, config['trace'])
        self.automation.entity_id = 'automation.bedroom_motion_triggered'
        component = EntityComponent(logging.getLogger(__name__), 'automation', self.hass)
        await component.async_add_entities([self.automation])

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.temp.cleanup()

    async def record(self, call):
        self.calls.append((call.domain, call.service, dict(call.data)))

    async def motion(self, time='20:00:00', elevation=-5, sticky='off'):
        self.hass.states.async_set('sun.sun', 'below_horizon', {'elevation': elevation})
        self.hass.states.async_set('input_boolean.bedroom_sticky', sticky)
        local = datetime.fromisoformat('2026-10-10T' + time).replace(tzinfo=ZONE)
        with patch('homeassistant.util.dt.now', return_value=local), \
             patch('homeassistant.util.dt.utcnow', return_value=local.astimezone(timezone.utc)):
            await self.automation.async_trigger({'trigger': {'platform': 'state', 'entity_id': 'binary_sensor.rf_bedroom_motion'}}, Context())

    async def test_evening_motion_controls_only_the_matter_lamp(self):
        await self.motion()
        self.assertEqual(self.calls, [('light', 'turn_on', {'entity_id': ['light.bedroom_lamp']})])

    async def test_daylight_blocks_motion(self):
        await self.motion(elevation=10)
        self.assertEqual(self.calls, [])

    async def test_before_evening_blocks_motion(self):
        await self.motion(time='17:30:00')
        self.assertEqual(self.calls, [])

    async def test_after_bedtime_blocks_motion(self):
        await self.motion(time='23:30:00')
        self.assertEqual(self.calls, [])

    async def test_manual_override_blocks_motion(self):
        await self.motion(sticky='on')
        self.assertEqual(self.calls, [])
