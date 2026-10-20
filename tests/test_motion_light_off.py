"""Run the actual blueprint in isolated HA instances with fake lighting services.

Use the deployed HA Python runtime. No production state, services or integrations
are used; availability grace and retry waits are shortened in the test copy.
"""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

try:
    from homeassistant import loader
    from homeassistant.bootstrap import async_load_base_functionality
    from homeassistant.config_entries import ConfigEntries
    from homeassistant.core import HomeAssistant
    from homeassistant.exceptions import HomeAssistantError
    from homeassistant.setup import async_setup_component
    from homeassistant.util.yaml import load_yaml
except ImportError:
    if os.environ.get("REQUIRE_HA_RUNTIME") == "1":
        raise
    HA_AVAILABLE = False
else:
    HA_AVAILABLE = True

ROOT = Path(os.environ.get('MOTION_TEST_ROOT', Path(__file__).resolve().parents[1]))
BLUEPRINT = 'blueprints/automation/ha_homelab/motion_light_off.yaml'


@unittest.skipUnless(HA_AVAILABLE, 'Home Assistant runtime is not installed')
class MotionLightOffTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if os.environ.get('REQUIRE_PRIVATE_DEPENDENCIES') == '1':
            self.assertTrue((ROOT / 'dependencies/automations/config').is_dir(),
                            'Required private automation submodule is missing')
        self.directory = tempfile.TemporaryDirectory(prefix='motion-light-test-')
        path = Path(self.directory.name) / BLUEPRINT
        path.parent.mkdir(parents=True)
        source = (ROOT / 'config' / BLUEPRINT).read_text()
        self.assertIn('seconds: 3', source)
        self.blueprint_path = path
        path.write_text(source.replace('seconds: 3', 'milliseconds: 10')
                       .replace('seconds: 60', 'milliseconds: 80'))
        self.hass = HomeAssistant(self.directory.name)
        loader.async_setup(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self.hass.config.skip_pip = True
        self.assertTrue(await async_load_base_functionality(self.hass))
        self.calls = []
        self.fail = set()
        self.after_service = None
        self.after_calls = []
        for domain in ('light', 'switch'):
            self.hass.services.async_register(domain, 'turn_off', self.turn_off)
        self.inputs = {
            'motion_triggers': [{'platform': 'state', 'entity_id': 'binary_sensor.motion',
                                 'to': 'off', 'for': {'minutes': 5}}],
            'target_entities': ['light.first', 'light.second'],
            'guards': [{'condition': 'state', 'entity_id': 'input_boolean.sticky', 'state': 'off'}],
        }
        self.set_state('binary_sensor.motion', 'off', 600)
        self.set_state('input_boolean.sticky', 'off')
        self.set_state('light.first', 'unavailable')
        self.set_state('light.second', 'off')

    async def asyncTearDown(self):
        # Recovery scripts intentionally wait for future state changes. Stop
        # those actions explicitly before draining HA's tasks during shutdown.
        try:
            try:
                if self.hass.services.has_service('automation', 'turn_off'):
                    entities = self.hass.states.async_entity_ids('automation')
                    if entities:
                        async with asyncio.timeout(5):
                            await self.hass.services.async_call(
                                'automation', 'turn_off',
                                {'entity_id': entities, 'stop_actions': True}, blocking=True)
            finally:
                async with asyncio.timeout(10):
                    await self.hass.async_stop(force=True)
        finally:
            self.directory.cleanup()

    def set_state(self, entity, state, age=0, attributes=None):
        # Age fixture state without advancing real timers or touching live HA.
        self.hass.states.async_set_internal(entity, state, attributes or {}, False,
                                            None, None, time.time() - age)

    async def turn_off(self, call):
        entities = call.data['entity_id']
        entities = [entities] if isinstance(entities, str) else entities
        for entity in entities:
            self.calls.append((entity, dict(call.data)))
            if entity in self.fail:
                raise HomeAssistantError('simulated transient device failure')
            self.set_state(entity, 'off')
            if self.after_service:
                self.after_service()

    async def load(self, configs=None):
        config = {'id': 'motion_test', 'alias': 'Motion test', 'use_blueprint': {
            'path': 'ha_homelab/motion_light_off.yaml', 'input': deepcopy(self.inputs)}}
        configs = configs if configs is not None else [config]
        # Keep the same fixture on disk so automation.reload uses HA's real path.
        (Path(self.directory.name) / 'configuration.yaml').write_text(
            json.dumps({'automation': configs}))
        self.assertTrue(await async_setup_component(self.hass, 'automation', {'automation': configs}))
        await self.hass.async_start()
        await self.settle()
        if len(configs) == 1 and configs[0]['id'] == 'motion_test':
            self.assertEqual(self.hass.states.get('automation.motion_test').state, 'on')

    async def settle(self):
        # async_block_till_done waits for recovery scripts that are correctly
        # still alive. A bounded event-loop yield processes the short grace;
        # tests expecting delayed work use until() with an explicit assertion.
        await asyncio.sleep(0.04)

    async def reconcile(self):
        self.hass.bus.async_fire('automation_reloaded')
        await self.settle()

    async def real_reload(self):
        await self.hass.services.async_call('automation', 'reload', {}, blocking=True)
        await self.settle()

    async def retry_wait(self):
        await asyncio.sleep(0.12)

    async def until(self, predicate):
        async with asyncio.timeout(2):
            while not predicate():
                await asyncio.sleep(0.01)

    async def record_after(self, call):
        self.after_calls.append(dict(call.data))

    def targets(self):
        return [entity for entity, _ in self.calls]

    async def test_unavailable_recovery(self):
        await self.load()
        self.assertFalse(self.calls)
        self.set_state('light.first', 'on')
        await self.settle()
        self.assertEqual(self.targets(), ['light.first'])

    async def test_unknown_then_off_then_manual_on_is_not_recovery(self):
        self.set_state('light.first', 'unknown')
        await self.load()
        self.set_state('light.first', 'off')
        await self.settle()
        self.set_state('light.first', 'on')
        await self.settle()
        await self.reconcile()
        self.assertFalse(self.calls)

    async def test_does_not_turn_off_before_timeout(self):
        self.set_state('binary_sensor.motion', 'on')
        self.set_state('binary_sensor.motion', 'off', 60)
        await self.load()
        self.set_state('light.first', 'on')
        await self.settle()
        await self.reconcile()
        self.assertFalse(self.calls)

    async def test_new_motion_blocks_recovery(self):
        await self.load()
        self.set_state('binary_sensor.motion', 'on')
        self.set_state('light.first', 'on')
        await self.settle()
        self.set_state('binary_sensor.motion', 'off')
        await self.reconcile()
        self.assertFalse(self.calls)

    async def test_override_blocks_then_rechecks(self):
        self.set_state('input_boolean.sticky', 'on')
        await self.load()
        self.set_state('light.first', 'on')
        await self.settle()
        self.assertFalse(self.calls)
        self.set_state('input_boolean.sticky', 'off')
        await self.until(lambda: bool(self.calls))
        self.assertEqual(self.targets(), ['light.first'])

    async def test_shared_target_sticky_blocks_only_its_own_light(self):
        self.inputs['target_sticky_helpers'] = {
            'light.first': ['input_boolean.other_room_sticky']}
        self.set_state('input_boolean.other_room_sticky', 'on')
        self.set_state('light.first', 'on', 900)
        self.set_state('light.second', 'on', 900)
        await self.load()
        self.assertEqual(self.targets(), ['light.second'])
        self.assertEqual(self.hass.states.get('light.first').state, 'on')
        self.set_state('input_boolean.other_room_sticky', 'off')
        await self.reconcile()
        self.assertEqual(self.targets(), ['light.second', 'light.first'])

    async def test_shared_target_unknown_and_missing_sticky_fail_closed(self):
        self.inputs['target_sticky_helpers'] = {
            'light.first': ['input_boolean.other_room_sticky']}
        self.set_state('light.first', 'on', 900)
        await self.load()
        self.assertFalse(self.calls)
        for state in ('unknown', 'unavailable', 'on'):
            self.set_state('input_boolean.other_room_sticky', state)
            await self.reconcile()
            self.assertFalse(self.calls)
        self.set_state('input_boolean.other_room_sticky', 'off')
        await self.reconcile()
        self.assertEqual(self.targets(), ['light.first'])

    async def test_shared_sticky_is_rechecked_between_target_commands(self):
        self.inputs['target_sticky_helpers'] = {
            'light.second': ['input_boolean.other_room_sticky']}
        self.set_state('input_boolean.other_room_sticky', 'off')
        self.set_state('light.first', 'on', 900)
        self.set_state('light.second', 'on', 900)
        self.after_service = lambda: self.set_state('input_boolean.other_room_sticky', 'on')
        await self.load()
        self.assertEqual(self.targets(), ['light.first'])
        self.assertEqual(self.hass.states.get('light.second').state, 'on')

    async def test_enabling_sticky_blocks_an_already_pending_recovery_retry(self):
        await self.load()
        self.fail.add('light.first')
        self.set_state('light.first', 'on')
        await self.until(lambda: bool(self.calls))
        self.set_state('input_boolean.sticky', 'on')
        self.fail.clear()
        self.calls.clear()
        await self.retry_wait()
        self.assertFalse(self.calls)
        self.assertEqual(self.hass.states.get('light.first').state, 'on')
        self.set_state('input_boolean.sticky', 'off')
        await self.until(lambda: bool(self.calls))
        self.assertEqual(self.targets(), ['light.first'])

    async def test_shared_sticky_blocks_recovery_and_rechecks_every_retry(self):
        self.inputs['target_sticky_helpers'] = {
            'light.first': ['input_boolean.other_room_sticky']}
        self.set_state('input_boolean.other_room_sticky', 'on')
        await self.load()
        self.set_state('light.first', 'on')
        await self.retry_wait()
        self.assertFalse(self.calls)
        self.fail.add('light.first')
        self.set_state('input_boolean.other_room_sticky', 'off')
        await self.until(lambda: bool(self.calls))
        self.set_state('input_boolean.other_room_sticky', 'on')
        self.calls.clear()
        self.fail.clear()
        await self.retry_wait()
        self.assertFalse(self.calls)
        self.assertEqual(self.hass.states.get('light.first').state, 'on')

    async def test_failed_device_does_not_block_sibling_and_retries(self):
        self.set_state('light.second', 'unknown')
        await self.load()
        self.fail.add('light.first')
        self.set_state('light.first', 'on')
        self.set_state('light.second', 'on')
        await self.reconcile()
        self.assertIn('light.second', self.targets())
        self.assertEqual(self.hass.states.get('light.first').state, 'on')
        self.fail.clear()
        self.calls.clear()
        await self.until(lambda: bool(self.calls))
        self.assertEqual(self.targets(), ['light.first'])

    async def test_unavailable_sibling_is_skipped(self):
        self.set_state('light.second', 'on', 900)
        await self.load()
        self.assertEqual(self.targets(), ['light.second'])

    async def test_unknown_motion_does_not_count_as_inactivity(self):
        self.set_state('binary_sensor.motion', 'unavailable')
        await self.load()
        self.set_state('light.first', 'on')
        await self.settle()
        await self.reconcile()
        self.assertFalse(self.calls)

    async def test_newer_sensor_cancels_stale_alternative_timeout(self):
        self.inputs['motion_triggers'].append({'platform': 'state',
            'entity_id': 'binary_sensor.presence', 'to': 'off'})
        self.set_state('binary_sensor.presence', 'off', 900)
        self.set_state('binary_sensor.motion', 'on')
        self.set_state('binary_sensor.motion', 'off', 60)
        await self.load()
        self.set_state('light.first', 'on')
        await self.settle()
        await self.reconcile()
        self.assertFalse(self.calls)

    async def test_latest_alternative_uses_its_own_timeout(self):
        self.inputs['motion_triggers'].append({'platform': 'state',
            'entity_id': 'binary_sensor.presence', 'to': 'off', 'for': {'seconds': 1}})
        self.set_state('binary_sensor.presence', 'off', 30)
        await self.load()
        self.set_state('light.first', 'on')
        await self.settle()
        self.assertEqual(self.targets(), ['light.first'])

    async def test_missing_alternative_allows_working_sensor(self):
        self.inputs['motion_triggers'].append({'platform': 'state',
            'entity_id': 'binary_sensor.missing', 'to': 'off'})
        await self.load()
        self.set_state('light.first', 'on')
        await self.settle()
        self.assertEqual(self.targets(), ['light.first'])

    async def test_motion_is_rechecked_between_devices(self):
        self.after_service = lambda: self.set_state('binary_sensor.motion', 'on')
        self.set_state('light.first', 'on', 900)
        self.set_state('light.second', 'on', 900)
        await self.load()
        self.assertEqual(self.targets(), ['light.first'])

    async def test_switch_and_per_entity_transition(self):
        self.inputs['target_entities'] = ['light.first', 'switch.lamp']
        self.inputs['entity_off_data'] = {'light.first': {'transition': 2}}
        self.set_state('light.first', 'on', 900)
        self.set_state('switch.lamp', 'on', 900)
        await self.load()
        self.assertEqual(self.targets(), ['light.first', 'switch.lamp'])
        self.assertEqual(self.calls[0][1]['transition'], 2)
        self.assertNotIn('transition', self.calls[1][1])

    async def test_startup_reconciles_on_light_older_than_motion_clear(self):
        self.set_state('light.first', 'on', 900)
        await self.load()
        self.assertEqual(self.targets(), ['light.first'])

    async def test_startup_preserves_on_light_newer_than_motion_clear(self):
        self.set_state('light.first', 'on', 100)
        await self.load()
        await self.reconcile()
        self.assertFalse(self.calls)

    async def test_motion_timer_still_fires(self):
        self.inputs['motion_triggers'][0]['for'] = {'milliseconds': 10}
        self.set_state('binary_sensor.motion', 'on')
        self.set_state('light.first', 'on')
        await self.load()
        self.assertFalse(self.calls)
        self.set_state('binary_sensor.motion', 'off')
        await self.settle()
        self.assertEqual(self.targets(), ['light.first'])

    async def test_manual_on_remains_on_after_elapsed_timeout_and_real_reload(self):
        # A same-state write intentionally preserves last_changed in HA.
        self.set_state('binary_sensor.motion', 'on')
        self.set_state('binary_sensor.motion', 'off', 7200)
        self.set_state('light.first', 'off')
        await self.load()
        self.set_state('light.first', 'on', 3600)
        await self.settle()
        await self.reconcile()
        await self.real_reload()
        self.assertFalse(self.calls)
        self.assertEqual(self.hass.states.get('light.first').state, 'on')

    async def test_recovery_does_not_arm_manually_on_sibling(self):
        await self.load()
        self.set_state('light.second', 'on')
        self.set_state('light.first', 'on')
        await self.settle()
        await self.reconcile()
        self.assertEqual(self.targets(), ['light.first'])
        self.assertEqual(self.hass.states.get('light.second').state, 'on')

    async def test_recovery_retry_does_not_arm_manually_on_sibling(self):
        await self.load()
        self.fail.add('light.first')
        self.set_state('light.second', 'on')
        self.set_state('light.first', 'on')
        await self.until(lambda: len(self.calls) >= 2)
        self.assertEqual(set(self.targets()), {'light.first'})
        self.fail.clear()
        await self.until(lambda: self.hass.states.get('light.first').state == 'off')
        await self.reconcile()
        self.assertEqual(set(self.targets()), {'light.first'})
        self.assertEqual(self.hass.states.get('light.second').state, 'on')

    async def test_failed_recovery_stops_when_user_starts_new_on_generation(self):
        await self.load()
        self.fail.add('light.first')
        self.set_state('light.first', 'on')
        await self.until(lambda: bool(self.calls))
        self.set_state('light.first', 'off')
        self.set_state('light.first', 'on')
        self.fail.clear()
        self.calls.clear()
        await self.retry_wait()
        await self.reconcile()
        self.assertFalse(self.calls)
        self.assertEqual(self.hass.states.get('light.first').state, 'on')

    async def test_recovery_grace_does_not_survive_manual_off_on(self):
        await self.load()
        self.set_state('light.first', 'on')
        self.set_state('light.first', 'off')
        self.set_state('light.first', 'on')
        await self.retry_wait()
        await self.reconcile()
        self.assertFalse(self.calls)

    async def test_manual_on_sibling_is_rechecked_between_device_commands(self):
        self.set_state('light.first', 'on', 900)
        self.set_state('light.second', 'on', 900)

        def manually_restart_second():
            self.set_state('light.second', 'off')
            self.set_state('light.second', 'on')

        self.after_service = manually_restart_second
        await self.load()
        self.assertEqual(self.targets(), ['light.first'])
        self.assertEqual(self.hass.states.get('light.second').state, 'on')

    async def test_recovery_waits_until_motion_timeout_is_due(self):
        self.inputs['motion_triggers'][0]['for'] = {'milliseconds': 200}
        self.set_state('binary_sensor.motion', 'on')
        await self.load()
        # Start the short test timeout after setup has finished.
        self.set_state('binary_sensor.motion', 'off')
        self.set_state('light.first', 'on')
        await self.settle()
        self.assertFalse(self.calls)
        await self.until(lambda: bool(self.calls))
        self.assertEqual(self.targets(), ['light.first'])

    async def test_recovery_attributes_do_not_create_new_on_generation(self):
        self.set_state('input_boolean.sticky', 'on')
        await self.load()
        self.set_state('light.first', 'on', attributes={'brightness': 50})
        await self.settle()
        original = self.hass.states.get('light.first').last_changed
        self.set_state('light.first', 'on', attributes={'brightness': 200})
        self.assertEqual(self.hass.states.get('light.first').last_changed, original)
        self.set_state('input_boolean.sticky', 'off')
        await self.until(lambda: bool(self.calls))
        self.assertEqual(self.targets(), ['light.first'])

    async def test_sun_guard_blocks_recovery_and_then_allows_retry(self):
        self.inputs['guards'].append({'condition': 'template', 'value_template':
            '{{ state_attr("sun.sun", "elevation") < 0.60 }}'})
        self.set_state('sun.sun', 'above_horizon', attributes={'elevation': 20})
        await self.load()
        self.set_state('light.first', 'on')
        await self.retry_wait()
        self.assertFalse(self.calls)
        self.set_state('sun.sun', 'below_horizon', attributes={'elevation': -5})
        await self.until(lambda: bool(self.calls))
        self.assertEqual(self.targets(), ['light.first'])

    async def test_time_guard_blocks_recovery_and_then_allows_retry(self):
        self.inputs['guards'].append({'condition': 'time',
                                     'after': '13:00:00', 'before': '14:00:00'})
        self.set_state('binary_sensor.motion', 'on')
        self.set_state('binary_sensor.motion', 'off', 172800)
        midday = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0)
        with patch('homeassistant.helpers.condition.dt_util.now', return_value=midday) as clock:
            await self.load()
            self.set_state('light.first', 'on')
            await self.retry_wait()
            self.assertFalse(self.calls)
            clock.return_value = midday.replace(hour=13, minute=30)
            await self.until(lambda: bool(self.calls))
            self.assertEqual(self.targets(), ['light.first'])

    async def test_unchanged_reload_preserves_valid_recovery_provenance(self):
        from homeassistant.components.automation import DATA_COMPONENT

        self.set_state('input_boolean.sticky', 'on')
        await self.load()
        self.set_state('light.first', 'on')
        await self.settle()
        original = self.hass.data[DATA_COMPONENT].get_entity('automation.motion_test')
        await self.real_reload()
        self.assertIs(self.hass.data[DATA_COMPONENT].get_entity('automation.motion_test'), original)
        self.set_state('input_boolean.sticky', 'off')
        await self.until(lambda: bool(self.calls))
        self.assertEqual(self.targets(), ['light.first'])

    async def test_changed_config_reload_does_not_invent_lost_recovery_provenance(self):
        from homeassistant.components.automation import DATA_COMPONENT

        self.set_state('input_boolean.sticky', 'on')
        await self.load()
        self.set_state('light.first', 'on')
        await self.settle()
        original = self.hass.data[DATA_COMPONENT].get_entity('automation.motion_test')
        # HA preserves running actions on an unchanged reload. Changing the
        # actual config forces removal/recreation and loss of volatile evidence.
        config_path = Path(self.directory.name) / 'configuration.yaml'
        config = json.loads(config_path.read_text())
        config['automation'][0]['description'] = 'Force a real config replacement in this test.'
        config_path.write_text(json.dumps(config))
        await self.real_reload()
        self.assertIsNot(self.hass.data[DATA_COMPONENT].get_entity('automation.motion_test'), original)
        self.set_state('input_boolean.sticky', 'off')
        await self.retry_wait()
        await self.reconcile()
        self.assertFalse(self.calls)

    async def test_after_actions_require_an_actual_eligible_attempt(self):
        self.inputs['after_actions'] = [{'action': 'script.record_after'}]
        self.hass.services.async_register('script', 'record_after', self.record_after)
        self.set_state('light.first', 'off')
        await self.load()
        self.set_state('light.first', 'on')
        await self.settle()
        await self.reconcile()
        self.assertFalse(self.calls)
        self.assertFalse(self.after_calls)
        self.set_state('light.first', 'unknown')
        self.set_state('light.first', 'on')
        await self.settle()
        self.assertEqual(self.targets(), ['light.first'])
        self.assertEqual(len(self.after_calls), 1)

    async def test_all_shipped_instances_preserve_manual_on_through_minute_and_reload(self):
        directory = ROOT / 'dependencies/automations/config'
        if not directory.is_dir():
            self.skipTest('Private automation submodule is required')
        configs = []
        target_entities = set()
        for path in sorted(directory.glob('*.yaml')):
            config = load_yaml(str(path))[0]
            if config.get('use_blueprint', {}).get('path') != 'ha_homelab/motion_light_off.yaml':
                continue
            config = deepcopy(config)
            self.assertEqual(config.get('mode', 'parallel'), 'parallel', path.name)
            inputs = config['use_blueprint']['input']
            self.assertNotIn('recovery_from_states', inputs, path.name)
            # Neutralize guards so a closed schedule cannot mask unsafe logic.
            # Target lists, timeout definitions, modes and IDs remain real.
            inputs['guards'] = []
            inputs['after_actions'] = []
            for helpers in inputs.get('target_sticky_helpers', {}).values():
                for helper in helpers:
                    self.set_state(helper, 'off')
            for trigger in inputs['motion_triggers']:
                entities = trigger['entity_id']
                entities = [entities] if isinstance(entities, str) else entities
                for entity in entities:
                    self.set_state(entity, 'off', 10000)
            target_entities.update(inputs['target_entities'])
            configs.append(config)
        self.assertEqual(len(configs), 11)
        for entity in target_entities:
            self.set_state(entity, 'off')
        # Exercise the actual time-pattern callback, on a one-second cadence.
        source = self.blueprint_path.read_text()
        self.assertIn("minutes: '/1'", source)
        self.blueprint_path.write_text(source.replace("minutes: '/1'", "seconds: '/1'"))
        await self.load(configs)
        for entity in target_entities:
            self.set_state(entity, 'on', 3600)
        await self.settle()
        await asyncio.sleep(1.1)
        self.assertFalse(self.calls, 'A scheduled retry overrode manual ON')
        await self.real_reload()
        await asyncio.sleep(1.1)
        self.assertFalse(self.calls, 'Reload or its next retry overrode manual ON')
        for entity in target_entities:
            self.assertEqual(self.hass.states.get(entity).state, 'on', entity)

    async def test_all_shipped_timeouts_preserve_lights_while_room_sticky_is_on(self):
        directory = ROOT / 'dependencies/automations/config'
        if not directory.is_dir():
            self.skipTest('Private automation submodule is required')
        configs = []
        targets = set()
        # Expected ownership is independent of each configuration's guards.
        owners = {
            '013': 'bathroom', '017': 'bathroom', '020': 'bedroom',
            '031': 'dining_room', '038': 'hallway', '047': 'kitchen',
            '048': 'kitchen', '051': 'kitchen', '054': 'kitchen',
            '063': 'lobby', '082': 'porch',
        }
        for prefix in owners:
            paths = list(directory.glob(f'{prefix}_*.yaml'))
            self.assertEqual(len(paths), 1, prefix)
            config = deepcopy(load_yaml(str(paths[0]))[0])
            self.assertEqual(config['use_blueprint']['path'], 'ha_homelab/motion_light_off.yaml')
            inputs = config['use_blueprint']['input']
            # Notifications are not light control; retain every real guard,
            # timeout, target and shared-room mapping.
            inputs['after_actions'] = []
            for trigger in inputs['motion_triggers']:
                entities = trigger['entity_id']
                for entity in [entities] if isinstance(entities, str) else entities:
                    self.set_state(entity, 'off', 172800)
            targets.update(inputs['target_entities'])
            configs.append(config)
        self.set_state('sun.sun', 'below_horizon', attributes={'elevation': -5})
        for room in set(owners.values()) | {'mishka_room'}:
            self.set_state(f'input_boolean.{room}_sticky', 'on')
        for entity in targets:
            self.set_state(entity, 'on', 259200)
        evening = datetime.now(timezone.utc).replace(hour=21, minute=0, second=0)
        with patch('homeassistant.helpers.condition.dt_util.now', return_value=evening):
            await self.load(configs)
            await self.reconcile()
            await self.real_reload()
            self.assertFalse(self.calls)
            for entity in targets:
                self.assertEqual(self.hass.states.get(entity).state, 'on', entity)
            # Positive control: no closed time/sun/availability guard can mask
            # an ineffective sticky fixture. Every target must now turn off.
            for room in set(owners.values()) | {'mishka_room'}:
                self.set_state(f'input_boolean.{room}_sticky', 'off')
            await self.reconcile()
            self.assertEqual(set(self.targets()), targets)

    async def test_all_shipped_instances_validate(self):
        from homeassistant.components.automation.config import async_validate_config_item
        # Set up the blueprint integration, then validate every migrated instance.
        if not (ROOT / 'dependencies/automations/config').is_dir():
            self.skipTest('Private automation submodule not checked out; required for deployment validation')
        await self.load()
        expected = {
            '013_bathroom_turn_off_lights_after_motion_clears.yaml',
            '017_bathroom_two_turn_off_lights_after_motion_clears.yaml',
            '020_bedroom_turn_off_lights_after_motion_clears.yaml',
            '031_dining_room_turn_off_lights_after_motion_clears.yaml',
            '038_hallway_turn_off_lights_after_motion_clears.yaml',
            '047_kitchen_turn_off_the_table_lamp_after_motion_clears.yaml',
            '048_kitchen_turn_off_the_table_lamp_after_prolonged_inactivity.yaml',
            '051_kitchen_turn_off_counter_lights_after_motion_clears.yaml',
            '054_kitchen_turn_off_tea_area_lights_after_motion_clears.yaml',
            '063_lobby_turn_off_lights_after_motion_clears.yaml',
            '082_porch_turn_off_lights_after_motion_clears.yaml',
        }
        validated = set()
        for path in (ROOT / 'dependencies/automations/config').glob('*.yaml'):
            config = load_yaml(str(path))[0]
            if 'use_blueprint' in config:
                self.assertIsNotNone(await async_validate_config_item(self.hass, 'automation', config), str(path))
                validated.add(path.name)
        self.assertEqual(validated, expected)

    def counter_inputs(self):
        path = ROOT / 'dependencies/automations/config/051_kitchen_turn_off_counter_lights_after_motion_clears.yaml'
        if not path.is_file():
            self.skipTest('Private automation submodule is required for counter integration tests')
        rule = load_yaml(str(path))[0]
        self.inputs = deepcopy(rule['use_blueprint']['input'])
        self.hass.services.async_register('script', 'notify_mqtt_log', self.noop)
        self.set_state('input_boolean.kitchen_sticky', 'off')
        self.set_state('binary_sensor.rf_counter_motion', 'off', 900)
        self.set_state('switch.led_under_cabinet', 'off')

    def tea_inputs(self):
        path = ROOT / 'dependencies/automations/config/054_kitchen_turn_off_tea_area_lights_after_motion_clears.yaml'
        if not path.is_file():
            self.skipTest('Private automation submodule is required for Tea table integration tests')
        self.inputs = deepcopy(load_yaml(str(path))[0]['use_blueprint']['input'])
        self.set_state('input_boolean.kitchen_sticky', 'off')
        self.set_state('sun.sun', 'below_horizon', attributes={'elevation': -5})
        self.set_state('binary_sensor.rf_tea_motion', 'off', 900)
        self.set_state('switch.tea_table', 'off')

    async def test_tea_manual_on_survives_reconciliation_and_reload(self):
        self.tea_inputs()
        await self.load()
        self.set_state('switch.tea_table', 'on')
        await self.settle()
        await self.reconcile()
        await self.real_reload()
        self.assertFalse(self.calls)
        self.assertEqual(self.hass.states.get('switch.tea_table').state, 'on')

    async def test_tea_unknown_recovery_is_turned_off_when_timeout_elapsed(self):
        self.tea_inputs()
        self.set_state('switch.tea_table', 'unknown')
        await self.load()
        self.set_state('switch.tea_table', 'on')
        await self.settle()
        self.assertEqual(self.targets(), ['switch.tea_table'])

    async def test_tea_new_motion_cycle_arms_its_three_minute_timeout(self):
        self.tea_inputs()
        self.set_state('switch.tea_table', 'on', 1200)
        await self.load()
        self.assertEqual(self.targets(), ['switch.tea_table'])

    async def noop(self, call):
        pass

    async def test_counter_manual_on_is_not_recovery_despite_old_motion(self):
        self.counter_inputs()
        await self.load()
        self.set_state('switch.led_under_cabinet', 'on')
        await self.settle()
        await self.reconcile()
        self.assertFalse(self.calls)

    async def test_counter_repeated_manual_on_remains_manual(self):
        self.counter_inputs()
        self.set_state('switch.led_under_cabinet', 'on', 400)
        await self.load()
        self.set_state('switch.led_under_cabinet', 'off')
        self.set_state('switch.led_under_cabinet', 'on')
        await self.reconcile()
        self.assertFalse(self.calls)

    async def test_counter_manual_on_has_no_seven_minute_expiry(self):
        self.counter_inputs()
        self.set_state('binary_sensor.rf_counter_motion', 'on')
        self.set_state('binary_sensor.rf_counter_motion', 'off', 7200)
        self.set_state('switch.led_under_cabinet', 'on', 3600)
        await self.load()
        await self.reconcile()
        self.assertFalse(self.calls)

    async def test_counter_new_motion_cycle_allows_shutdown_after_timeout(self):
        self.counter_inputs()
        self.set_state('switch.led_under_cabinet', 'on', 1200)
        await self.load()
        self.assertEqual(self.targets(), ['switch.led_under_cabinet'])

    async def test_counter_fresh_motion_waits_for_its_timeout(self):
        self.counter_inputs()
        self.set_state('switch.led_under_cabinet', 'on', 900)
        self.set_state('binary_sensor.rf_counter_motion', 'on')
        self.set_state('binary_sensor.rf_counter_motion', 'off', 30)
        await self.load()
        await self.reconcile()
        self.assertFalse(self.calls)

    async def test_counter_sticky_blocks_then_resumes_shutdown(self):
        self.counter_inputs()
        self.set_state('switch.led_under_cabinet', 'on', 1200)
        self.set_state('input_boolean.kitchen_sticky', 'on')
        await self.load()
        await self.reconcile()
        self.assertFalse(self.calls)
        self.set_state('input_boolean.kitchen_sticky', 'off')
        await self.reconcile()
        self.assertEqual(self.targets(), ['switch.led_under_cabinet'])

    async def test_counter_attribute_update_does_not_cancel_motion_timeout(self):
        self.counter_inputs()
        self.set_state('input_boolean.kitchen_sticky', 'on')
        self.set_state('switch.led_under_cabinet', 'on', 1200, {'icon': 'mdi:led-strip-variant'})
        await self.load()
        self.set_state('switch.led_under_cabinet', 'on', attributes={'icon': 'mdi:lightbulb'})
        self.set_state('input_boolean.kitchen_sticky', 'off')
        await self.reconcile()
        self.assertEqual(self.targets(), ['switch.led_under_cabinet'])

    async def test_counter_unavailable_recovery_checks_without_manual_grace(self):
        self.counter_inputs()
        self.set_state('switch.led_under_cabinet', 'unavailable')
        await self.load()
        self.set_state('switch.led_under_cabinet', 'on')
        await self.settle()
        self.assertEqual(self.targets(), ['switch.led_under_cabinet'])

    async def test_counter_unknown_recovery_checks_without_manual_grace(self):
        self.counter_inputs()
        self.set_state('switch.led_under_cabinet', 'unknown')
        await self.load()
        self.set_state('switch.led_under_cabinet', 'on')
        await self.settle()
        self.assertEqual(self.targets(), ['switch.led_under_cabinet'])

    async def test_counter_sticky_blocks_unknown_recovery(self):
        self.counter_inputs()
        self.set_state('input_boolean.kitchen_sticky', 'on')
        self.set_state('switch.led_under_cabinet', 'unknown')
        await self.load()
        self.set_state('switch.led_under_cabinet', 'on')
        await self.settle()
        self.assertFalse(self.calls)

    async def test_counter_failed_recovery_can_retry_but_new_manual_on_cancels_it(self):
        self.counter_inputs()
        self.set_state('switch.led_under_cabinet', 'unknown')
        await self.load()
        self.fail.add('switch.led_under_cabinet')
        self.set_state('switch.led_under_cabinet', 'on')
        await self.settle()
        self.assertEqual(self.targets(), ['switch.led_under_cabinet'])
        self.fail.clear()
        self.calls.clear()
        await self.until(lambda: bool(self.calls))
        self.assertEqual(self.targets(), ['switch.led_under_cabinet'])
        self.calls.clear()
        self.set_state('switch.led_under_cabinet', 'on')
        await self.settle()
        await self.reconcile()
        self.assertFalse(self.calls)


if __name__ == '__main__':
    unittest.main(verbosity=2)
