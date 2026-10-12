"""Run the recovery automation in an isolated HA, with real helpers and registry."""
from datetime import timedelta
import os
from pathlib import Path
import tempfile
import unittest

try:
    import yaml
    from homeassistant import loader
    from homeassistant.bootstrap import async_load_base_functionality
    from homeassistant.config_entries import ConfigEntries, ConfigEntry, ConfigEntryState, ConfigEntryDisabler
    from homeassistant.core import HomeAssistant
    from homeassistant.exceptions import HomeAssistantError
    from homeassistant.helpers import entity_registry as er
    from homeassistant.setup import async_setup_component
    from homeassistant.util import dt as dt_util
except ImportError:
    HA_AVAILABLE = False
else:
    HA_AVAILABLE = True

ROOT = Path(os.environ.get('ROOMBA_TEST_ROOT', Path(__file__).resolve().parents[1]))


@unittest.skipUnless(HA_AVAILABLE, 'Requires the deployed Home Assistant image')
class RoombaRecoveryTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='roomba-recovery-test-')
        self.hass = HomeAssistant(self.temp.name)
        loader.async_setup(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self.hass.config.skip_pip = True
        self.assertTrue(await async_load_base_functionality(self.hass))
        self.config = yaml.safe_load((ROOT / 'config/packages/roomba_recovery.yaml').read_text())
        self.robots = self.config['automation'][0]['variables']['robots']
        self.attempts = []
        self.failing_robots = set()
        self.entries = {}
        registry = er.async_get(self.hass)
        for robot in self.robots:
            name = robot['vacuum'].split('.')[1]
            entry = ConfigEntry(domain='roomba', title=name, data={}, options={},
                source='user', unique_id=name, version=1, minor_version=1,
                discovery_keys={}, subentries_data=None, state=ConfigEntryState.LOADED)
            self.hass.config_entries._entries[entry.entry_id] = entry
            entity = registry.async_get_or_create('vacuum', 'roomba', name,
                suggested_object_id=name, config_entry=entry)
            self.assertEqual(entity.entity_id, robot['vacuum'])
            self.entries[name] = entry
            self.set_old(robot['vacuum'], 'docked')
            self.set_old(robot['ping'], 'on')
        self.hass.services.async_register('homeassistant', 'reload_config_entry', self.reload_entry)
        self.assertTrue(await async_setup_component(self.hass, 'input_datetime', self.config))
        self.assertTrue(await async_setup_component(self.hass, 'automation', self.config))
        await self.hass.async_start()
        for robot in self.robots:
            await self.hass.services.async_call('input_datetime', 'set_datetime',
                {'entity_id': robot['cooldown'], 'timestamp': dt_util.utcnow().timestamp() - 3600}, blocking=True)
        self.automation = next(s.entity_id for s in self.hass.states.async_all('automation'))

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.temp.cleanup()

    def robot(self, name='i7'):
        return next(r for r in self.robots if r['vacuum'] == 'vacuum.' + name)

    def set_old(self, entity, state, age=300):
        # Real StateMachine, with a controlled last_changed timestamp.
        self.hass.states.async_remove(entity)
        self.hass.states.async_set(entity, state)
        self.hass.states.get(entity).last_changed = dt_util.utcnow() - timedelta(seconds=age)

    async def reload_entry(self, call):
        entry_id = call.data['entry_id']
        robot = next(r for r in self.robots if self.entries[r['vacuum'].split('.')[1]].entry_id == entry_id)
        # The cooldown must already be persisted in the real date/time helper.
        stamp = self.hass.states.get(robot['cooldown']).attributes['timestamp']
        self.assertLess(abs(dt_util.utcnow().timestamp() - stamp), 5)
        self.attempts.append(robot['vacuum'])
        if robot['vacuum'] in self.failing_robots:
            raise HomeAssistantError('Simulated connection failure')

    async def run_check(self):
        await self.hass.services.async_call('automation', 'trigger',
            {'entity_id': self.automation, 'skip_condition': False}, blocking=True)
        await self.hass.async_block_till_done()

    async def test_healthy_robots_receive_no_actions(self):
        await self.run_check()
        self.assertEqual(self.attempts, [])

    async def test_offline_robot_is_not_reloaded(self):
        r = self.robot()
        self.set_old(r['vacuum'], 'unavailable')
        for state in ['off', 'unknown', 'unavailable']:
            self.set_old(r['ping'], state)
            await self.run_check()
        self.assertEqual(self.attempts, [])

    async def test_only_reconnected_unavailable_robot_is_reloaded(self):
        self.set_old(self.robot()['vacuum'], 'unavailable')
        await self.run_check()
        self.assertEqual(self.attempts, ['vacuum.i7'])

    async def test_waits_for_stable_ping_and_native_reconnection(self):
        r = self.robot()
        self.set_old(r['vacuum'], 'unavailable')
        self.set_old(r['ping'], 'on', age=30)
        await self.run_check()
        self.set_old(r['ping'], 'on')
        self.set_old(r['vacuum'], 'unavailable', age=60)
        await self.run_check()
        self.assertEqual(self.attempts, [])

    async def test_failed_attempt_is_throttled_and_does_not_block_other_robot(self):
        for name in ['i7', 'roomba9']:
            self.set_old(self.robot(name)['vacuum'], 'unavailable')
        self.failing_robots = {'vacuum.i7'}
        await self.run_check()
        await self.run_check()
        self.assertEqual(self.attempts, ['vacuum.i7', 'vacuum.roomba9'])

    async def test_respects_restored_cooldown_and_retries_after_expiry(self):
        r = self.robot()
        self.set_old(r['vacuum'], 'unavailable')
        for age, expected in [(600, []), (901, ['vacuum.i7'])]:
            await self.hass.services.async_call('input_datetime', 'set_datetime',
                {'entity_id': r['cooldown'], 'timestamp': dt_util.utcnow().timestamp() - age}, blocking=True)
            await self.run_check()
            self.assertEqual(self.attempts, expected)

    async def test_manual_disable_is_respected(self):
        self.set_old(self.robot()['vacuum'], 'unavailable')
        object.__setattr__(self.entries['i7'], 'disabled_by', ConfigEntryDisabler.USER)
        await self.run_check()
        self.assertEqual(self.attempts, [])

    async def test_setup_in_progress_and_auth_errors_are_not_reloaded(self):
        self.set_old(self.robot()['vacuum'], 'unavailable')
        entry = self.entries['i7']
        for state in [ConfigEntryState.SETUP_IN_PROGRESS, ConfigEntryState.SETUP_ERROR, ConfigEntryState.NOT_LOADED]:
            entry._async_set_state(self.hass, state, None)
            await self.run_check()
        self.assertEqual(self.attempts, [])

    async def test_setup_retry_entry_can_be_recovered(self):
        self.set_old(self.robot()['vacuum'], 'unavailable')
        self.entries['i7']._async_set_state(self.hass, ConfigEntryState.SETUP_RETRY, None)
        await self.run_check()
        self.assertEqual(self.attempts, ['vacuum.i7'])

    async def test_missing_cooldown_fails_closed(self):
        self.set_old(self.robot()['vacuum'], 'unavailable')
        self.hass.states.async_remove(self.robot()['cooldown'])
        await self.run_check()
        self.assertEqual(self.attempts, [])

    async def test_missing_vacuum_state_is_not_treated_as_offline(self):
        self.hass.states.async_remove(self.robot()['vacuum'])
        await self.run_check()
        self.assertEqual(self.attempts, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
