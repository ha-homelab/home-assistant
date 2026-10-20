"""Exercise retained motion-light commands in isolated HA with mocked services."""
from copy import deepcopy
import os
from pathlib import Path
import tempfile
import unittest

try:
    import yaml
    from homeassistant import loader
    from homeassistant.bootstrap import async_load_base_functionality
    from homeassistant.config_entries import ConfigEntries
    from homeassistant.core import Context, HomeAssistant, State
    from homeassistant.exceptions import HomeAssistantError
    from homeassistant.helpers import config_validation as cv
    from homeassistant.helpers.script import Script
except ImportError:
    if os.environ.get('REQUIRE_HA_RUNTIME') == '1':
        raise
    HA_AVAILABLE = False
else:
    HA_AVAILABLE = True

ROOT = Path(os.environ.get('DEVICE_RECOVERY_TEST_ROOT', Path(__file__).resolve().parents[1]))


@unittest.skipUnless(HA_AVAILABLE, 'Requires the deployed Home Assistant runtime')
class IndependentDeviceRecoveryTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='independent-device-test-')
        self.hass = HomeAssistant(self.temp.name)
        loader.async_setup(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self.hass.config.skip_pip = True
        self.assertTrue(await async_load_base_functionality(self.hass))
        self.calls = []
        self.failures = set()
        for domain in ['light', 'switch']:
            self.hass.services.async_register(domain, 'turn_on', self.turn_on)
        self.hass.services.async_register('script', 'notify_mqtt_log', self.notify)
        # Device-failure scenarios require automatic lighting to be allowed,
        # including the other room's override for each shared light.
        for room in ('dining_room', 'lobby', 'hallway', 'mishka_room', 'porch'):
            self.set(f'input_boolean.{room}_sticky', 'off')
        await self.hass.async_start()
        await self.hass.async_block_till_done()

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.temp.cleanup()

    def source(self, number):
        return yaml.safe_load(next((ROOT / 'config').glob(f'{number:03d}_*.yaml')).read_text())[0]

    def set(self, entity_id, state):
        self.hass.states.async_set(entity_id, state)

    async def notify(self, call):
        pass

    async def turn_on(self, call):
        entities = call.data['entity_id']
        entities = [entities] if isinstance(entities, str) else entities
        for entity in entities:
            self.calls.append((entity, deepcopy(dict(call.data))))
            if entity in self.failures:
                raise HomeAssistantError('Simulated unavailable device')
            self.set(entity, 'on')

    def targets(self):
        return [entity for entity, _ in self.calls]

    async def test_independent_motion_lights_continue_after_each_device_failure(self):
        rooms = {
            33: ['switch.dining_wall_light_2', 'switch.dining_arc_lamp', 'light.adining_lamp_m'],
            40: ['light.hall_1_m', 'light.hall_2_m'],
            83: ['light.porch_one', 'light.porch_two'],
        }
        for number, targets in rooms.items():
            config = self.source(number)
            for failed in targets:
                with self.subTest(room=number, failed=failed):
                    self.calls.clear()
                    self.failures = {failed}
                    script = Script(self.hass, cv.SCRIPT_SCHEMA(config['actions']),
                                    f'motion_{number}', 'automation', script_mode=config['mode'])
                    await script.async_run({'trigger': {'to_state': State('binary_sensor.test', 'on')}},
                                           context=Context())
                    self.assertEqual(self.targets(), targets)
                    for entity in targets:
                        if entity != failed:
                            self.assertEqual(self.hass.states.get(entity).state, 'on')


if __name__ == '__main__':
    unittest.main(verbosity=2)
