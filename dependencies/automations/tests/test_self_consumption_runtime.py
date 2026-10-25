"""Run rule 085 in isolated HA; every device/notification service is a recorder.

Deployment validation supplies the unchanged root select_devices.py through
SELF_CONSUMPTION_SELECTOR. No running HA instance or real device is controlled.
"""
import os
from copy import deepcopy
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import yaml

try:
    from homeassistant import loader
    from homeassistant.bootstrap import async_load_base_functionality
    from homeassistant.components.light import LIGHT_TURN_OFF_SCHEMA, LIGHT_TURN_ON_SCHEMA
    from homeassistant.config_entries import ConfigEntries
    from homeassistant.core import Context, HomeAssistant
    from homeassistant.exceptions import HomeAssistantError
    from homeassistant.helpers import config_validation as cv
    from homeassistant.helpers.script import Script, _ScriptRun
    from homeassistant.setup import async_setup_component
except ImportError:
    if os.environ.get("REQUIRE_HA_RUNTIME") == "1":
        raise
    HA_AVAILABLE = False
else:
    HA_AVAILABLE = True

ROOT = Path(__file__).resolve().parents[1]
RULE = ROOT / 'config/085_self_consumption_select_controllable_loads_from_grid_power.yaml'


@unittest.skipUnless(HA_AVAILABLE, 'Deployment test requires Home Assistant runtime')
class SelfConsumptionRuntimeTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        selector = Path(os.environ.get('SELF_CONSUMPTION_SELECTOR', '/config/python_scripts/select_devices.py'))
        if not selector.is_file():
            if os.environ.get('REQUIRE_HA_RUNTIME') == '1':
                self.fail('Required SELF_CONSUMPTION_SELECTOR is missing')
            self.skipTest('Supply the root select_devices.py using SELF_CONSUMPTION_SELECTOR')
        self.temp = tempfile.TemporaryDirectory(prefix='self-consumption-test-')
        self.hass = HomeAssistant(self.temp.name)
        loader.async_setup(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self.hass.config.skip_pip = True
        self.assertTrue(await async_load_base_functionality(self.hass))
        scripts = Path(self.temp.name) / 'python_scripts'
        scripts.mkdir()
        shutil.copyfile(selector, scripts / 'select_devices.py')
        self.assertTrue(await async_setup_component(self.hass, 'python_script', {'python_script': {}}))
        self.calls, self.delays, self.notices = [], [], []
        self.failures = set()
        self.after_notice = self.after_call = None
        for room in ('living_room', 'dining_room', 'lobby', 'kitchen'):
            self.hass.states.async_set(f'input_boolean.{room}_sticky', 'off')
        for name, schema in [('turn_on', LIGHT_TURN_ON_SCHEMA), ('turn_off', LIGHT_TURN_OFF_SCHEMA)]:
            self.hass.services.async_register('light', name, self.record, schema=cv.make_entity_service_schema(schema))
            self.hass.services.async_register('switch', name, self.record, schema=cv.make_entity_service_schema({}))
        async def notify(call):
            self.notices.append(dict(call.data))
            if self.after_notice:
                self.after_notice()
        self.hass.services.async_register('script', 'notify_mqtt', notify)
        async def delay(run):
            self.delays.append(run._get_pos_time_period_template('delay').total_seconds())
        self.delay_patch = patch.object(_ScriptRun, '_async_step_delay', delay)
        self.delay_patch.start()
        self.config = yaml.safe_load(RULE.read_text())[0]
        self.hass.states.async_set('input_boolean.modern_self_consuming', 'off')

    async def asyncTearDown(self):
        self.delay_patch.stop()
        await self.hass.async_stop(force=True)
        self.temp.cleanup()

    async def record(self, call):
        data = deepcopy(dict(call.data))
        self.calls.append((f'{call.domain}.{call.service}', data))
        if self.after_call:
            self.after_call()
        if any(entity in self.failures for entity in data['entity_id']):
            raise HomeAssistantError('Simulated independent device failure')

    async def run_actions(self, power, states):
        self.hass.states.async_set('sensor.home_123_1s', str(power))
        self.hass.states.async_set('sensor.battery_w', '0')
        for entity, state in states.items():
            self.hass.states.async_set(entity, state)
        script = Script(self.hass, cv.SCRIPT_SCHEMA(deepcopy(self.config['actions'])),
                        'self-consumption-fixture', 'automation', script_mode=self.config['mode'])
        # Only the isolated action engine runs; the production enable helper is
        # neither invoked nor changed. Its real rule guard is asserted below.
        await script.async_run({}, context=Context())
        self.assertEqual(self.delays, [5])
        self.assertEqual(self.hass.states.get('input_boolean.modern_self_consuming').state, 'off')

    async def test_turn_off_payload_passes_actual_light_schema(self):
        await self.run_actions(90, {'light.dining_lights_dimmer_l': 'on'})
        self.assertEqual(self.calls, [('light.turn_off', {'entity_id': ['light.dining_lights_dimmer_l']})])

    async def test_turn_on_retains_brightness(self):
        await self.run_actions(-300, {'light.dining_lights_dimmer_l': 'off'})
        self.assertEqual(self.calls, [('light.turn_on', {'entity_id': ['light.dining_lights_dimmer_l'], 'brightness': 100})])

    async def test_tea_table_uses_switch_schema_without_brightness(self):
        await self.run_actions(-300, {'switch.tea_table': 'off'})
        self.assertEqual(self.calls, [('switch.turn_on', {'entity_id': ['switch.tea_table']})])

    async def test_garage_floodlight_keeps_108w_and_excludes_door_power(self):
        import json
        watt_map = json.loads(self.config['actions'][0]['variables']['watt_map'])
        self.assertEqual(watt_map['switch.garage_floodlight'], 108)
        self.assertNotIn('switch.garage_door_power', watt_map)
        await self.run_actions(108, {'switch.garage_floodlight': 'on'})
        self.assertEqual(self.calls, [('switch.turn_off', {'entity_id': ['switch.garage_floodlight']})])

    async def test_failed_switch_does_not_skip_later_selected_light(self):
        self.failures.add('switch.switch06')
        await self.run_actions(840, {'switch.switch06': 'on', 'light.dining_lights_dimmer_l': 'on'})
        self.assertEqual(self.calls, [
            ('switch.turn_off', {'entity_id': ['switch.switch06']}),
            ('light.turn_off', {'entity_id': ['light.dining_lights_dimmer_l']})])

    async def test_failed_light_does_not_skip_later_selected_switch(self):
        self.failures.add('light.dining_lights_dimmer_l')
        await self.run_actions(180, {'light.dining_lights_dimmer_l': 'on', 'switch.living_room_light_l': 'on'})
        self.assertEqual(self.calls, [
            ('light.turn_off', {'entity_id': ['light.dining_lights_dimmer_l']}),
            ('switch.turn_off', {'entity_id': ['switch.living_room_light_l']})])

    async def test_actual_selector_still_skips_missing_unknown_and_unavailable(self):
        await self.run_actions(1000, {'switch.switch06': 'unavailable', 'switch.air_purifier_living': 'unknown',
                                      'switch.tea_table': 'on'})
        self.assertEqual(self.calls, [('switch.turn_off', {'entity_id': ['switch.tea_table']})])

    async def test_each_room_sticky_blocks_energy_driven_on_and_off(self):
        cases = (
            ('living_room', 'switch.living_room_light_l'),
            ('dining_room', 'light.dining_lights_dimmer_l'),
            ('dining_room', 'switch.dining_wall_light_2'),
            ('lobby', 'switch.dining_wall_light_2'),
            ('kitchen', 'switch.tea_table'),
        )
        for room, target in cases:
            for state in ('on', 'unknown', 'unavailable', None):
                for power, lamp in ((1000, 'on'), (-1000, 'off')):
                    with self.subTest(room=room, target=target, state=state, power=power):
                        self.calls.clear()
                        self.delays.clear()
                        for _, previous in cases:
                            self.hass.states.async_remove(previous)
                        for helper in ('living_room', 'dining_room', 'lobby', 'kitchen'):
                            self.hass.states.async_set(f'input_boolean.{helper}_sticky', 'off')
                        entity = f'input_boolean.{room}_sticky'
                        if state is None:
                            self.hass.states.async_remove(entity)
                        else:
                            self.hass.states.async_set(entity, state)
                        await self.run_actions(power, {target: lamp})
                        self.assertEqual(self.calls, [])

    async def test_blocked_light_is_excluded_before_load_selection(self):
        self.hass.states.async_set('input_boolean.dining_room_sticky', 'on')
        await self.run_actions(840, {'switch.switch06': 'on', 'light.dining_lights_dimmer_l': 'on'})
        self.assertEqual(self.calls, [('switch.turn_off', {'entity_id': ['switch.switch06']})])

    async def test_sticky_change_during_notification_blocks_selected_light(self):
        self.after_notice = lambda: self.hass.states.async_set('input_boolean.kitchen_sticky', 'on')
        await self.run_actions(-300, {'switch.tea_table': 'off'})
        self.assertEqual(self.calls, [])
        self.assertTrue(self.notices)

    async def test_sticky_rechecked_between_selected_targets(self):
        self.after_call = lambda: self.hass.states.async_set('input_boolean.living_room_sticky', 'on')
        await self.run_actions(180, {'light.dining_lights_dimmer_l': 'on', 'switch.living_room_light_l': 'on'})
        self.assertEqual(self.calls, [('light.turn_off', {'entity_id': ['light.dining_lights_dimmer_l']})])

    async def test_schedule_guard_mode_and_empty_selection_are_preserved(self):
        self.assertEqual(self.config['triggers'], [{'platform': 'time_pattern', 'seconds': '/2'}])
        self.assertEqual(self.config['conditions'], [{'condition': 'state',
                         'entity_id': 'input_boolean.modern_self_consuming', 'state': 'on'}])
        self.assertEqual(self.config['mode'], 'single')
        await self.run_actions(1000, {})
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
