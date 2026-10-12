"""Execute the Venus keepalive automation with HA and mocked MQTT publication."""
import asyncio
from copy import deepcopy
import json
import logging
import os
from pathlib import Path
import tempfile
import unittest

import yaml

try:
    from homeassistant import loader
    from homeassistant.bootstrap import async_load_base_functionality
    from homeassistant.components.automation import AutomationEntity, _async_process_if
    from homeassistant.components.automation.config import PLATFORM_SCHEMA
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
RULE_PATH = ROOT / 'config' / '118_victron_keep_mqtt_telemetry_active.yaml'
SERIAL = 'victron/R/b827ebea1ece/system/0/Serial'
GRID = 'victron/R/b827ebea1ece/vebus/290/Ac/ActiveIn/Connected'
BATTERY = 'victron/R/b827ebea1ece/system/0/Dc/Battery/Voltage'
SUPPRESSED = {'keepalive-options': ['suppress-republish']}
ENTITY_ID = 'automation.victron_mqtt_keep_alive'


def load_rule():
    return yaml.safe_load(RULE_PATH.read_text())[0]


class VictronKeepaliveTriggerTest(unittest.TestCase):
    def test_periodic_and_mqtt_birth_triggers_remain_bound(self):
        self.assertEqual(load_rule()['triggers'], [
            {'platform': 'time_pattern', 'seconds': '/5', 'id': 'heartbeat'},
            {'platform': 'mqtt', 'topic': 'homeassistant/status',
             'payload': 'online', 'id': 'mqtt_connected'},
        ])


@unittest.skipUnless(HA_AVAILABLE, 'Home Assistant runtime is not installed')
class VictronKeepaliveRuntimeTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.hass = HomeAssistant(self.temp.name)
        loader.async_setup(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self.hass.config.skip_pip = True
        self.assertTrue(await async_load_base_functionality(self.hass))
        # Keep the real automation traces in memory without loading a frontend.
        self.hass.data[DATA_TRACE] = {}
        self.calls = []
        self.first_publish = asyncio.Event()
        self.release_publish = asyncio.Event()
        self.release_publish.set()
        self.tasks = []
        self.hass.services.async_register('mqtt', 'publish', self.record)

        rule = load_rule()
        config = PLATFORM_SCHEMA(deepcopy(rule))
        condition = await _async_process_if(self.hass, config['alias'], config)
        self.assertIsNotNone(condition)
        script = Script(
            self.hass, config['actions'], config['alias'], 'automation',
            script_mode=config['mode'], max_runs=config['max'],
            max_exceeded=config['max_exceeded'],
        )
        self.automation = AutomationEntity(
            config['id'], config['alias'], config['triggers'], condition, script,
            # Do not attach real time/MQTT triggers. Deliver their rendered
            # variables below, exercising the real conditions and queued runs.
            False, None, None, rule, None, config['trace'],
        )
        self.automation.entity_id = ENTITY_ID
        self.component = EntityComponent(logging.getLogger(__name__), 'automation', self.hass)
        await self.component.async_add_entities([self.automation])
        self.assertEqual(self.current(), 0)

    async def asyncTearDown(self):
        self.release_publish.set()
        for task in self.tasks:
            if not task.done():
                task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        await self.hass.async_stop(force=True)
        self.temp.cleanup()

    async def record(self, call):
        self.calls.append((call.domain, call.service, dict(call.data)))
        if len(self.calls) == 1:
            self.first_publish.set()
            await self.release_publish.wait()

    def current(self):
        state = self.hass.states.get(ENTITY_ID)
        self.assertIsNotNone(state)
        return state.attributes['current']

    async def trigger(self, trigger_id):
        trigger = {'id': trigger_id}
        if trigger_id == 'mqtt_connected':
            trigger.update(platform='mqtt', topic='homeassistant/status', payload='online')
        else:
            trigger.update(platform='time_pattern')
        return await self.automation.async_trigger({'trigger': trigger}, Context())

    def start_trigger(self, trigger_id):
        task = asyncio.create_task(self.trigger(trigger_id))
        self.tasks.append(task)
        return task

    def assert_publish_trace(self, expected):
        actual = []
        for domain, service, data in self.calls:
            self.assertEqual((domain, service), ('mqtt', 'publish'))
            self.assertEqual(set(data), {'topic', 'payload'})
            # These are exact read requests, never W/ settings writes or
            # subscriptions/wildcards that could hide other traffic.
            self.assertIn(data['topic'], {SERIAL, GRID, BATTERY})
            actual.append((data['topic'], json.loads(data['payload'])))
        self.assertEqual(actual, expected)

    async def test_heartbeat_suppresses_tree_and_refreshes_both_expiring_inputs(self):
        await self.trigger('heartbeat')
        self.assert_publish_trace([(SERIAL, SUPPRESSED), (GRID, {}), (BATTERY, {})])
        self.assertEqual(self.current(), 0)

    async def test_mqtt_birth_bootstraps_tree_and_refreshes_both_expiring_inputs(self):
        await self.trigger('mqtt_connected')
        self.assert_publish_trace([(SERIAL, {}), (GRID, {}), (BATTERY, {})])
        self.assertEqual(self.current(), 0)

    async def test_overlapping_heartbeat_preserves_queue_slot_for_mqtt_birth(self):
        self.release_publish.clear()
        heartbeat = self.start_trigger('heartbeat')
        await asyncio.wait_for(self.first_publish.wait(), timeout=2)
        self.assertEqual(self.current(), 1)

        # Admission must reject this tick before it can occupy the queued slot.
        # Wrapping only the actions in Script would not test this ordering.
        await asyncio.wait_for(self.trigger('heartbeat'), timeout=2)
        self.assertEqual(self.current(), 1)
        self.assert_publish_trace([(SERIAL, SUPPRESSED)])

        birth = self.start_trigger('mqtt_connected')
        async with asyncio.timeout(2):
            while self.current() != 2:
                await asyncio.sleep(0.001)
        self.assertFalse(birth.done())
        self.assert_publish_trace([(SERIAL, SUPPRESSED)])

        self.release_publish.set()
        await asyncio.wait_for(asyncio.gather(heartbeat, birth), timeout=2)
        expected = [
            (SERIAL, SUPPRESSED), (GRID, {}), (BATTERY, {}),
            (SERIAL, {}), (GRID, {}), (BATTERY, {}),
        ]
        self.assert_publish_trace(expected)
        self.assertEqual(self.current(), 0)

        # A dropped overlapping tick must not suppress later normal heartbeats.
        await self.trigger('heartbeat')
        self.assert_publish_trace(expected + [(SERIAL, SUPPRESSED), (GRID, {}), (BATTERY, {})])
        self.assertEqual(self.current(), 0)


if __name__ == '__main__':
    unittest.main()
