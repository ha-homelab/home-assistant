"""Exercise the morning schedule with simulated time and no device I/O."""
from copy import deepcopy
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
    from homeassistant.components.trace.const import DATA_TRACE
    from homeassistant.config_entries import ConfigEntries
    from homeassistant.core import Context, HomeAssistant
    from homeassistant.helpers.entity_component import EntityComponent
    from homeassistant.helpers.script import Script
except ImportError:
    if os.environ.get('REQUIRE_HA_RUNTIME') == '1':
        raise
    HA_AVAILABLE = False
else:
    HA_AVAILABLE = True

ROOT = Path(__file__).resolve().parents[1]
ZONE = ZoneInfo('America/Los_Angeles')


class MorningDaylightCases:
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.hass = HomeAssistant(self.temp.name)
        loader.async_setup(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self.hass.config.skip_pip = True
        await self.hass.config.async_set_time_zone(str(ZONE))
        self.assertTrue(await async_load_base_functionality(self.hass))
        self.hass.data[DATA_TRACE] = {}
        self.hass.states.async_set('input_boolean.curtains_sticky', 'off')
        # The scheduled event can run before the sun entity's state update.
        self.hass.states.async_set('sun.sun', 'below_horizon')
        self.calls = []
        for domain, service in self.services:
            self.hass.services.async_register(domain, service, self.record)
        rule = yaml.safe_load(next((ROOT / 'config').glob(self.file_pattern)).read_text())[0]
        self.assertEqual(rule['triggers'], [
            {'platform': 'time', 'at': self.earliest},
            {'platform': 'sun', 'event': 'sunrise'},
        ])
        runtime_rule = deepcopy(rule)
        self.prepare_actions(runtime_rule)
        config = await async_validate_config_item(self.hass, 'automation', runtime_rule)
        condition = await _async_process_if(self.hass, config['alias'], config)
        self.assertIsNotNone(condition)
        script = Script(self.hass, config['actions'], config['alias'], 'automation',
                        script_mode=config['mode'])
        self.automation = AutomationEntity(
            config['id'], config['alias'], config['triggers'], condition, script,
            # Deliver the time and solar events below instead of live timers.
            False, None, None, rule, None, config['trace'],
        )
        self.automation.entity_id = self.entity_id
        component = EntityComponent(logging.getLogger(__name__), 'automation', self.hass)
        await component.async_add_entities([self.automation])

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.temp.cleanup()

    async def record(self, call):
        self.calls.append((call.domain, call.service, dict(call.data)))

    def prepare_actions(self, rule):
        pass

    async def event(self, date, time, sunrise, platform):
        local = datetime.fromisoformat(f'{date}T{time}').replace(tzinfo=ZONE)

        def sun_event(hass, event, day):
            value = sunrise if event == 'sunrise' else '18:30:00'
            return datetime.fromisoformat(f'{day}T{value}').replace(tzinfo=ZONE).astimezone(timezone.utc)

        with patch('homeassistant.util.dt.now', return_value=local), \
             patch('homeassistant.util.dt.utcnow', return_value=local.astimezone(timezone.utc)), \
             patch('homeassistant.components.sun.condition.get_astral_event_date', side_effect=sun_event):
            await self.automation.async_trigger({'trigger': {'platform': platform}}, Context())

    async def test_late_sunrise_blocks_fixed_time_then_opens_at_sunrise(self):
        await self.event('2026-10-07', self.earliest, '07:10:00', 'time')
        self.assertEqual(self.calls, [])
        await self.event('2026-10-07', '07:10:00', '07:10:00', 'sun')
        self.assertEqual(self.calls, self.expected_calls)

    async def test_early_sunrise_waits_until_fixed_time(self):
        await self.event('2026-06-21', '05:45:00', '05:45:00', 'sun')
        self.assertEqual(self.calls, [])
        await self.event('2026-06-21', self.earliest, '05:45:00', 'time')
        self.assertEqual(self.calls, self.expected_calls)

    async def test_winter_standard_time_waits_for_sunrise(self):
        await self.event('2026-12-21', self.earliest, '07:20:00', 'time')
        self.assertEqual(self.calls, [])
        await self.event('2026-12-21', '07:20:00', '07:20:00', 'sun')
        self.assertEqual(self.calls, self.expected_calls)

    async def test_manual_override_blocks_both_events(self):
        self.hass.states.async_set('input_boolean.curtains_sticky', 'on')
        await self.event('2026-10-07', self.earliest, '07:10:00', 'time')
        await self.event('2026-10-07', '07:10:00', '07:10:00', 'sun')
        self.assertEqual(self.calls, [])

    async def test_manual_override_enabled_while_waiting_blocks_sunrise(self):
        await self.event('2026-10-07', self.earliest, '07:10:00', 'time')
        self.hass.states.async_set('input_boolean.curtains_sticky', 'on')
        await self.event('2026-10-07', '07:10:00', '07:10:00', 'sun')
        self.assertEqual(self.calls, [])

    async def test_noon_or_night_cannot_open(self):
        await self.event('2026-10-07', '12:00:00', '07:10:00', 'time')
        await self.event('2026-10-07', '22:00:00', '07:10:00', 'time')
        self.assertEqual(self.calls, [])

    async def test_sunrise_between_room_schedules_respects_earliest_time(self):
        await self.event('2026-08-01', '06:32:00', '06:32:00', 'sun')
        self.assertEqual(self.calls, self.expected_calls if self.earliest < '06:32:00' else [])


@unittest.skipUnless(HA_AVAILABLE, 'Requires the deployed Home Assistant runtime')
class LivingCurtainDaylightTest(MorningDaylightCases, unittest.IsolatedAsyncioTestCase):
    file_pattern = '077_*.yaml'
    earliest = '06:30:00'
    entity_id = 'automation.open_living_curtains_in_the_morning'
    services = [('script', 'living_curtains_move')]
    expected_calls = [('script', 'living_curtains_move', {'curtain': 'both', 'command': 'open'})]


@unittest.skipUnless(HA_AVAILABLE, 'Requires the deployed Home Assistant runtime')
class KitchenDiningCurtainDaylightTest(MorningDaylightCases, unittest.IsolatedAsyncioTestCase):
    file_pattern = '078_*.yaml'
    earliest = '06:35:00'
    entity_id = 'automation.open_curtains_in_the_morning'
    services = [('switch', 'turn_on'), ('cover', 'open_cover'), ('switch', 'turn_off')]
    expected_calls = [
        ('switch', 'turn_on', {'entity_id': ['switch.dining_guard']}),
        ('switch', 'turn_on', {'entity_id': ['switch.kitchen_guard']}),
        ('cover', 'open_cover', {'entity_id': ['cover.kitchen_curtains_l']}),
        ('cover', 'open_cover', {'entity_id': ['cover.dining_curtains_l']}),
        ('switch', 'turn_off', {'entity_id': ['switch.dining_guard']}),
    ]

    def prepare_actions(self, rule):
        # Preserve the production timing; only the private test copy skips waiting.
        self.assertEqual(rule['actions'], [
            {'service': 'switch.turn_on', 'entity_id': 'switch.dining_guard'},
            {'service': 'switch.turn_on', 'entity_id': 'switch.kitchen_guard'},
            {'delay': '00:01:30'},
            {'service': 'cover.open_cover', 'entity_id': 'cover.kitchen_curtains_l'},
            {'service': 'cover.open_cover', 'entity_id': 'cover.dining_curtains_l'},
            {'delay': '00:01:00'},
            {'service': 'switch.turn_off', 'entity_id': 'switch.dining_guard'},
        ])
        for step in rule['actions']:
            if 'delay' in step:
                step['delay'] = 0


if __name__ == '__main__':
    unittest.main(verbosity=2)
