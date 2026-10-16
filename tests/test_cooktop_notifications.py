"""Exercise cooktop state edges in isolated HA with fake delivery services.

The shipped automation, shared notify_optional sequence, HTML5 schema and
notification_service_available Python script run unchanged. No live HA instance,
device integration, notification provider or production configuration is used.
COOKTOP_TEST_ROOT may point to a copied source bundle in the installed HA image.
"""
from copy import deepcopy
from datetime import timedelta
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

try:
    from homeassistant import loader
    from homeassistant.bootstrap import async_load_base_functionality
    from homeassistant.components.html5.services import SERVICE_SEND_MESSAGE_SCHEMA
    from homeassistant.config_entries import ConfigEntries
    from homeassistant.core import HomeAssistant
    from homeassistant.exceptions import HomeAssistantError
    from homeassistant.helpers import config_validation as cv
    from homeassistant.helpers.script import Script
    from homeassistant.setup import async_setup_component
    import yaml
except ImportError:
    HA_AVAILABLE = False
else:
    HA_AVAILABLE = True

ROOT = Path(os.environ.get('COOKTOP_TEST_ROOT', Path(__file__).resolve().parents[1]))
COOKTOP = 'binary_sensor.range_operating_state'
MUTE = 'input_boolean.notifications_off'
VITALY = 'notify.mobile_app_als_iphone_89310'
MARIA = 'notify.mobile_app_marias_iphone'
TITLE = 'Kitchen: cooktop on'
MESSAGE = 'At least one cooktop burner is on.'


@unittest.skipUnless(HA_AVAILABLE, 'Home Assistant runtime is not installed')
class CooktopNotificationsTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='cooktop-notification-test-')
        self.addCleanup(self.temp.cleanup)
        self.hass = HomeAssistant(self.temp.name)
        self.addAsyncCleanup(self.hass.async_stop, force=True)
        loader.async_setup(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self.hass.config.skip_pip = True
        self.assertTrue(await async_load_base_functionality(self.hass))
        scripts = Path(self.temp.name) / 'python_scripts'
        scripts.mkdir()
        shutil.copyfile(ROOT / 'config/python_scripts/notification_service_available.py',
                        scripts / 'notification_service_available.py')
        self.assertTrue(await async_setup_component(self.hass, 'python_script', {'python_script': {}}))
        self.deliveries = []
        self.router_calls = []
        self.warnings = []
        self.fail_browser = False
        self.hass.services.async_register('html5', 'send_message', self.record,
                                         schema=SERVICE_SEND_MESSAGE_SCHEMA)
        for service in (VITALY, MARIA):
            domain, name = service.split('.')
            self.hass.services.async_register(domain, name, self.record)
        self.hass.services.async_register('system_log', 'write', self.record)
        package = yaml.safe_load((ROOT / 'config/packages/runtime_resilience.yaml').read_text())
        router = package['script']['notify_optional']
        self.router = Script(self.hass, cv.SCRIPT_SCHEMA(deepcopy(router['sequence'])),
                             'notify_optional', 'script', script_mode=router.get('mode', 'single'),
                             max_runs=router.get('max', 10))
        # Observe the one caller boundary, then execute the actual shared router.
        self.hass.services.async_register('script', 'notify_optional', self.optional)
        self.hass.states.async_set(MUTE, 'off')

    async def optional(self, call):
        self.router_calls.append(deepcopy(dict(call.data)))
        await self.router.async_run(dict(call.data), context=call.context)

    async def record(self, call):
        service = f'{call.domain}.{call.service}'
        data = deepcopy(dict(call.data))
        if service == 'system_log.write':
            self.warnings.append(data)
            return
        self.deliveries.append((service, data))
        if service == 'html5.send_message' and self.fail_browser:
            raise HomeAssistantError('Simulated browser delivery failure')

    async def load(self, initial='off'):
        if initial is not None:
            self.hass.states.async_set(COOKTOP, initial)
        package = yaml.safe_load((ROOT / 'config/packages/cooktop_notifications.yaml').read_text())
        self.assertEqual(len(package['automation']), 1)
        config = package['automation'][0]
        self.assertEqual(config['id'], 'ha_homelab_cooktop_started_notifications')
        self.assertEqual(config['alias'], 'Kitchen: notify when the cooktop starts')
        self.assertTrue(await async_setup_component(self.hass, 'automation', package))
        await self.hass.async_start()
        await self.hass.async_block_till_done()
        automations = self.hass.states.async_all('automation')
        self.assertEqual(len(automations), 1)
        self.automation = automations[0].entity_id
        self.assertEqual(automations[0].state, 'on')

    async def state(self, entity, value, attributes=None):
        if value is None:
            self.hass.states.async_remove(entity)
        else:
            self.hass.states.async_set(entity, value, attributes)
        await self.hass.async_block_till_done()

    def last_triggered(self):
        return self.hass.states.get(self.automation).attributes.get('last_triggered')

    def assert_one_delivery_pair(self):
        self.assertEqual(self.router_calls, [{
            'notify_service': 'html5.send_message', 'notification_category': 'cooktop',
            'notify_data': {'entity_id': 'notify.chrome', 'title': TITLE,
                            'message': MESSAGE, 'data': {'url': '/'}}}])
        self.assertEqual(self.deliveries, [
            ('html5.send_message', {'entity_id': ['notify.chrome'], 'title': TITLE,
                                    'message': MESSAGE, 'data': {'url': '/'}}),
            (VITALY, {'title': TITLE, 'message': MESSAGE, 'data': {'url': '/'}}),
        ])
        self.assertFalse(any(service == MARIA for service, _ in self.deliveries))

    async def test_confirmed_start_sends_exactly_chrome_and_owner_phone_once(self):
        await self.load()
        self.assertIsNone(self.last_triggered())
        await self.state(COOKTOP, 'on')
        self.assert_one_delivery_pair()
        self.assertIsNotNone(self.last_triggered())

    async def test_turning_off_does_not_send_even_after_cooldown(self):
        await self.load()
        await self.state(COOKTOP, 'on')
        with patch('homeassistant.util.dt.now', return_value=self.last_triggered() + timedelta(seconds=61)):
            await self.state(COOKTOP, 'off')
        self.assert_one_delivery_pair()

    async def test_repeated_on_and_attribute_updates_do_not_send_after_cooldown(self):
        await self.load()
        await self.state(COOKTOP, 'on')
        with patch('homeassistant.util.dt.now', return_value=self.last_triggered() + timedelta(seconds=61)):
            await self.state(COOKTOP, 'on')
            await self.state(COOKTOP, 'on', {'friendly_name': 'Cooktop refreshed'})
        self.assert_one_delivery_pair()

    async def test_missing_unknown_and_unavailable_recovery_are_not_starts(self):
        await self.load(initial=None)
        for previous in (None, 'unknown', 'unavailable'):
            with self.subTest(previous=previous):
                await self.state(COOKTOP, previous)
                await self.state(COOKTOP, 'on')
                self.assertEqual(self.router_calls, [])
                self.assertEqual(self.deliveries, [])
                self.assertIsNone(self.last_triggered())

    async def test_startup_with_existing_on_state_does_not_replay(self):
        await self.load(initial='on')
        self.assertEqual(self.router_calls, [])
        self.assertEqual(self.deliveries, [])
        self.assertIsNone(self.last_triggered())

    async def test_oven_changes_do_not_trigger_cooktop_message(self):
        await self.load()
        for entity, values in {
            'sensor.range_oven_machine_state': ['ready', 'running', 'ready'],
            'sensor.range_oven_mode': ['off', 'bake', 'off'],
            'sensor.range_temperature_measurement': ['20', '180', '20'],
        }.items():
            for value in values:
                await self.state(entity, value)
        self.assertEqual(self.router_calls, [])
        self.assertEqual(self.deliveries, [])
        self.assertIsNone(self.last_triggered())

    async def test_mute_requires_confirmed_off_and_unmuting_does_not_replay(self):
        await self.load()
        for muted in ('on', 'unknown', 'unavailable', None):
            with self.subTest(mute=muted):
                await self.state(MUTE, muted)
                await self.state(COOKTOP, 'off')
                await self.state(COOKTOP, 'on')
                self.assertEqual(self.router_calls, [])
                self.assertIsNone(self.last_triggered())
        await self.state(MUTE, 'off')
        self.assertEqual(self.deliveries, [])
        await self.state(COOKTOP, 'off')
        await self.state(COOKTOP, 'on')
        self.assert_one_delivery_pair()

    async def test_rapid_off_on_is_suppressed(self):
        await self.load()
        await self.state(COOKTOP, 'on')
        first = self.last_triggered()
        await self.state(COOKTOP, 'off')
        await self.state(COOKTOP, 'on')
        self.assert_one_delivery_pair()
        self.assertEqual(self.last_triggered(), first)

    async def test_cooldown_expires_at_exactly_sixty_seconds(self):
        await self.load()
        await self.state(COOKTOP, 'on')
        first = self.last_triggered()
        with patch('homeassistant.util.dt.now', return_value=first + timedelta(seconds=59)):
            await self.state(COOKTOP, 'off')
            await self.state(COOKTOP, 'on')
        self.assert_one_delivery_pair()
        self.assertEqual(self.last_triggered(), first)
        expected = deepcopy(self.deliveries)
        with patch('homeassistant.util.dt.now', return_value=first + timedelta(seconds=60)):
            await self.state(COOKTOP, 'off')
            await self.state(COOKTOP, 'on')
        self.assertEqual(len(self.router_calls), 2)
        self.assertEqual(self.deliveries, expected + expected)

    async def test_browser_delivery_failure_still_sends_owner_phone_copy(self):
        self.fail_browser = True
        await self.load()
        await self.state(COOKTOP, 'on')
        self.assert_one_delivery_pair()

    async def test_missing_browser_service_still_sends_owner_phone_copy(self):
        self.hass.services.async_remove('html5', 'send_message')
        await self.load()
        await self.state(COOKTOP, 'on')
        self.assertEqual(len(self.router_calls), 1)
        self.assertEqual(self.deliveries, [
            (VITALY, {'title': TITLE, 'message': MESSAGE, 'data': {'url': '/'}})])
        self.assertEqual(len(self.warnings), 1)
        self.assertIn('html5.send_message', self.warnings[0]['message'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
