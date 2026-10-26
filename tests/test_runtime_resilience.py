"""Execute resilience changes in isolated HA, with no real notification/device I/O.

The helper tests run in root CI. Deployment validation additionally requires the
bundled libraries: their actual scripts, timers and baseline sequences run here.
"""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
import shutil
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    from homeassistant import loader
    from homeassistant.bootstrap import async_load_base_functionality
    from homeassistant.config import async_hass_config_yaml, merge_packages_config
    from homeassistant.config_entries import ConfigEntries
    from homeassistant.core import HomeAssistant, State, Context, SupportsResponse
    from homeassistant.exceptions import HomeAssistantError
    from homeassistant.helpers import config_validation as cv
    from homeassistant.helpers.script import Script, _ScriptRun
    from homeassistant.helpers.template import Template
    from homeassistant.setup import async_setup_component
    from homeassistant.components.html5.services import SERVICE_SEND_MESSAGE_SCHEMA
    from homeassistant.components.mqtt import MQTT_PUBLISH_SCHEMA
    import yaml
except ImportError:
    if os.environ.get("REQUIRE_HA_RUNTIME") == "1":
        raise
    HA_AVAILABLE = False
else:
    HA_AVAILABLE = True

ROOT = Path(os.environ.get('RESILIENCE_TEST_ROOT', Path(__file__).resolve().parents[1]))


@unittest.skipUnless(HA_AVAILABLE, 'Home Assistant runtime is not installed')
class RuntimeResilienceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='resilience-test-')
        self.hass = HomeAssistant(self.temp.name)
        loader.async_setup(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self.hass.config.skip_pip = True
        self.assertTrue(await async_load_base_functionality(self.hass))
        scripts = Path(self.temp.name) / 'python_scripts'
        scripts.mkdir()
        shutil.copyfile(ROOT / 'config/python_scripts/notification_service_available.py',
                        scripts / 'notification_service_available.py')
        self.assertTrue(await async_setup_component(self.hass, 'python_script', {'python_script': {}}))
        self.events = []
        self.mobile_events = []
        self.failed_services = set()
        self.mqtt_gate = asyncio.Event()
        self.mqtt_gate.set()
        for domain, names in {
            'notify': ['good', 'bad', 'roomba', 'imac21', 'chrome', 'mobile_app_als_iphone2', 'mobile_app_als_iphone_89310', 'alexa_media'],
            'system_log': ['write'], 'light': ['turn_on', 'turn_off', 'toggle'],
            'switch': ['turn_on', 'turn_off'], 'camera': ['snapshot'],
            'input_boolean': ['turn_on', 'turn_off'],
            'homeassistant': ['turn_off'],
            'media_player': ['turn_off', 'play_media', 'volume_set'], 'shell_command': ['shutdown_inew'],
            'persistent_notification': ['create'], 'climate': ['set_temperature'],
        }.items():
            for name in names:
                self.hass.services.async_register(domain, name, self.record)
        self.hass.services.async_register('mqtt', 'publish', self.record, schema=MQTT_PUBLISH_SCHEMA)
        self.hass.services.async_register('html5', 'send_message', self.record, schema=SERVICE_SEND_MESSAGE_SCHEMA)
        config = yaml.safe_load((ROOT / 'config/packages/runtime_resilience.yaml').read_text())
        self.helper = self.make_script(config['script']['notify_optional'], 'notify_optional')
        self.hass.services.async_register('script', 'notify_optional', self.optional)
        # Snapshot persistence has separate file/HA tests. Keep this notification
        # suite focused on the same camera request and following device actions.
        async def capture(call):
            key = call.data['camera_key']
            self.events.append(('camera.snapshot', {
                'entity_id': [f'camera.{key}_camera'],
                'filename': f'/config/www/{key}_camera_alert.jpg'}))
        self.hass.services.async_register('script', 'capture_camera_alert', capture)
        events = self.events
        async def record_delay(run):
            events.append(('delay', run._get_pos_time_period_template('delay').total_seconds()))
        self.delay_patch = patch.object(_ScriptRun, '_async_step_delay', record_delay)
        self.delay_patch.start()

    async def asyncTearDown(self):
        self.mqtt_gate.set()
        self.delay_patch.stop()
        await self.hass.async_stop(force=True)
        self.temp.cleanup()

    def make_script(self, config, name='test'):
        return Script(self.hass, cv.SCRIPT_SCHEMA(deepcopy(config['sequence'])), name, 'script',
                      script_mode=config.get('mode', 'single'), max_runs=config.get('max', 10))

    async def record(self, call):
        data = deepcopy(dict(call.data))
        if isinstance(data.get('entity_id'), str):
            data['entity_id'] = [data['entity_id']]
        service = f'{call.domain}.{call.service}'
        if service == 'notify.mobile_app_als_iphone_89310':
            self.mobile_events.append(data)
        else:
            self.events.append((service, data))
        if service == 'mqtt.publish':
            await self.mqtt_gate.wait()
        if service in self.failed_services or any(entity in self.failed_services for entity in data.get('entity_id', [])):
            raise HomeAssistantError('Simulated provider failure')

    async def optional(self, call):
        await self.helper.async_run(dict(call.data), context=call.context)

    def source_script(self, name):
        directory = ROOT / 'dependencies/scripts/config'
        if not directory.is_dir():
            self.skipTest('Bundled libraries required for deployment validation')
        for path in directory.rglob('*.yaml'):
            config = yaml.safe_load(path.read_text())
            if name in config:
                return config[name]
        self.fail(f'Missing script {name}')

    def automation(self, number):
        directory = ROOT / 'dependencies/automations/config'
        if not directory.is_dir():
            self.skipTest('Bundled libraries required for deployment validation')
        return yaml.safe_load(next(directory.glob(f'{number:03d}_*.yaml')).read_text())[0]

    async def test_package_merge_registers_the_real_script_service(self):
        # HA package merging drops nested empty mappings, including empty selectors.
        # Validate the complete integration path, not only the action sequence.
        self.hass.services.async_remove('script', 'notify_optional')
        package = yaml.safe_load((ROOT / 'config/packages/runtime_resilience.yaml').read_text())
        merged = await merge_packages_config(self.hass, {}, {'runtime_resilience': package})
        self.assertTrue(await async_setup_component(self.hass, 'script', merged))
        await self.hass.async_block_till_done()
        self.assertTrue(self.hass.services.has_service('script', 'notify_optional'))
        self.assertIsNotNone(self.hass.states.get('script.notify_optional'))
        payload = {'message': 'Package integration test'}
        await self.hass.services.async_call('script', 'notify_optional',
            {'notify_service': 'notify.good', 'notify_data': payload}, blocking=True)
        self.assertEqual(self.events, [('notify.good', payload)])
        self.events.clear()
        await self.hass.services.async_call('script', 'notify_optional',
            {'notify_service': 'notify.good', 'notify_data': payload, 'also_chrome': True}, blocking=True)
        self.assertEqual([event[0] for event in self.events], ['notify.good', 'html5.send_message'])

    async def test_optional_delivery_preserves_payload(self):
        payload = {'title': 'test', 'message': 'Quoted "message"\nline', 'data': {'actions': [{'action': 'porch_light_on'}]}}
        await self.helper.async_run({'notify_service': 'notify.good', 'notify_data': payload}, context=Context())
        self.assertEqual(self.events, [('notify.good', payload)])

    async def test_html5_rich_notification_uses_actual_schema_and_chrome_target(self):
        payload = {'entity_id': 'notify.chrome', 'title': 'Home Assistant',
                   'message': 'Ring Motion', 'image': '/local/ring_camera_alert.jpg',
                   'icon': '/local/ring_camera_alert.jpg',
                   'actions': [{'action': 'porch_light_on', 'title': 'Porch light'}],
                   'data': {'url': '/local/ring_camera_alert.jpg'}}
        await self.helper.async_run({'notify_service': 'html5.send_message',
                                     'notify_data': payload}, context=Context())
        self.assertEqual(self.events, [('html5.send_message', dict(payload, entity_id=['notify.chrome']))])

    async def test_current_chrome_callers_preserve_snapshot_urls_and_other_actions(self):
        for name in ['frontmotion', 'garagemotion', 'backdoormotion', 'blinkmotion']:
            self.events.clear()
            with patch('homeassistant.util.dt.now', return_value=datetime(2026, 9, 22, 21, tzinfo=timezone.utc)):
                await self.make_script(self.source_script(name)).async_run(context=Context())
            chrome = [data for action, data in self.events if action == 'html5.send_message']
            if name in ['frontmotion', 'garagemotion', 'backdoormotion', 'blinkmotion']:
                self.assertEqual(chrome, [])
                if name != 'blinkmotion':
                    self.assertTrue(any(action == 'camera.snapshot' for action, _ in self.events))
                continue
            self.assertTrue(chrome, name)
            for payload in chrome:
                self.assertEqual(payload['entity_id'], ['notify.chrome'])
                self.assertTrue(payload['data']['url'].startswith('/'))
                for field in ['icon', 'image']:
                    if field in payload:
                        self.assertTrue(payload[field].startswith('/local/'))
            self.assertFalse(any(action in ['notify.mobile_app_als_iphone2', 'notify.pushbullet']
                                 for action, _ in self.events))

    async def test_tv_snapshot_uses_registered_webos_service_and_supported_icon_field(self):
        self.hass.services.async_register('notify', 'lg_webos_tv_oled77c5pua_dusqljr', self.record)
        self.hass.states.async_set('media_player.living_room_tv_77', 'playing')
        await self.make_script(self.source_script('tv_pic2')).async_run(context=Context())
        self.assertEqual(self.events[0], ('notify.lg_webos_tv_oled77c5pua_dusqljr',
            {'message': 'Someone at the Front Camera', 'data': {'icon': '/config/www/front_camera_alert.jpg'}}))
        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.mobile_events, [])

    async def test_tv_browser_uses_privately_configured_home_assistant_origin(self):
        self.hass.services.async_register('webostv', 'command', self.record)
        self.hass.states.async_set('input_text.base_url', 'https://ha.example.invalid')
        await self.make_script(self.source_script('tv_pic')).async_run(context=Context())
        self.assertEqual(len(self.events), 1)
        service, data = self.events[0]
        self.assertEqual(service, 'webostv.command')
        self.assertEqual(data['entity_id'], ['media_player.living_room_tv_77'])
        self.assertEqual(data['command'], 'system.launcher/open')
        prefix = 'https://ha.example.invalid/local/front_camera_alert.jpg?'
        self.assertTrue(data['payload']['target'].startswith(prefix))
        self.assertGreater(float(data['payload']['target'][len(prefix):]), 0)

    async def test_offline_tvs_are_quietly_skipped_without_losing_chrome_or_following_actions(self):
        destinations = {
            'notify.lg2': 'media_player.lg2',
            'notify.lg_webos_tv_oled77c5pua_dusqljr': 'media_player.living_room_tv_77',
        }
        for service, entity in destinations.items():
            self.hass.services.async_register('notify', service.split('.')[1], self.record)
            script = self.make_script({'sequence': [
                {'action': 'script.notify_optional', 'data': {'notify_service': service,
                    'notify_data': {'message': 'Motion', 'data': {'icon': '/private/snapshot.jpg'}},
                    'also_chrome': True}},
                {'action': 'light.turn_off', 'target': {'entity_id': 'light.fixture'}},
            ]})
            for state in ['off', 'unavailable', 'unknown', 'standby', None]:
                with self.subTest(service=service, state=state):
                    if state is None:
                        self.hass.states.async_remove(entity)
                    else:
                        self.hass.states.async_set(entity, state)
                    self.events.clear()
                    await script.async_run(context=Context())
                    self.assertEqual([action for action, _ in self.events],
                                     ['html5.send_message', 'light.turn_off'])
                    self.assertNotIn('/private/snapshot.jpg', json.dumps(self.events))

    async def test_tv_delivery_resumes_without_reload_and_preserves_original_payload(self):
        for service, entity in [
            ('notify.lg2', 'media_player.lg2'),
            ('notify.lg_webos_tv_oled77c5pua_dusqljr', 'media_player.living_room_tv_77'),
        ]:
            self.hass.services.async_register('notify', service.split('.')[1], self.record)
            payload = {'message': 'Motion', 'data': {'icon': '/config/www/front_camera_alert.jpg'}}
            args = {'notify_service': service, 'notify_data': payload}
            self.hass.states.async_set(entity, 'off')
            self.events.clear()
            await self.helper.async_run(args, context=Context())
            self.assertEqual(self.events, [])
            for state in ['on', 'idle', 'playing', 'paused', 'buffering']:
                with self.subTest(service=service, state=state):
                    self.hass.states.async_set(entity, state)
                    self.events.clear()
                    await self.helper.async_run(args, context=Context())
                    self.assertEqual(self.events, [(service, payload)])

    async def test_tv_guard_does_not_hide_schema_errors_when_delivery_is_attempted(self):
        import voluptuous as vol
        self.hass.services.async_register('notify', 'lg2', self.record,
                                         schema=vol.Schema({vol.Required('message'): str}))
        self.hass.states.async_set('media_player.lg2', 'on')
        with self.assertRaises(vol.Invalid):
            await self.helper.async_run({'notify_service': 'notify.lg2',
                'notify_data': {'unexpected': True}}, context=Context())
        self.assertEqual(self.events, [])

    async def test_chrome_copy_is_explicit_and_does_not_forward_provider_specific_fields(self):
        payload = {'title': 'Sensor', 'message': 'Quoted "message"\n{{ literal }}',
                   'data': {'displaytime': 20000, 'icon': 'warning'}, 'target': ['private-provider-target']}
        await self.helper.async_run({'notify_service': 'notify.good', 'notify_data': payload,
                                     'also_chrome': True}, context=Context())
        self.assertEqual(self.events, [('notify.good', payload), ('html5.send_message', {
            'entity_id': ['notify.chrome'], 'title': 'Sensor', 'message': payload['message'], 'data': {'url': '/'}})])

    async def test_chrome_copy_survives_missing_or_failed_original_provider(self):
        for provider in ['notify.missing', 'notify.bad']:
            self.failed_services.add('notify.bad')
            self.events.clear()
            await self.helper.async_run({'notify_service': provider, 'notify_data': {'message': 'test'},
                                         'also_chrome': True}, context=Context())
            self.assertEqual([e[0] for e in self.events].count('html5.send_message'), 1)

    async def test_chrome_failure_does_not_stop_the_next_household_action(self):
        self.failed_services.add('html5.send_message')
        config = {'sequence': [
            {'action': 'script.notify_optional', 'data': {'notify_service': 'notify.good',
                'notify_data': {'message': 'test'}, 'also_chrome': True}},
            {'action': 'switch.turn_off', 'target': {'entity_id': 'switch.fixture'}},
        ]}
        await self.make_script(config).async_run(context=Context())
        self.assertEqual([e[0] for e in self.events], ['notify.good', 'html5.send_message', 'switch.turn_off'])

    async def test_existing_html5_delivery_is_not_duplicated_by_the_copy_flag(self):
        await self.helper.async_run({'notify_service': 'html5.send_message',
            'notify_data': {'entity_id': 'notify.chrome', 'message': 'test'}, 'also_chrome': True}, context=Context())
        self.assertEqual(len(self.events), 1)

    async def test_expanded_notification_rules_send_one_chrome_copy_per_run(self):
        self.hass.services.async_register('script', 'notify_mqtt', self.record)
        self.hass.services.async_register('script', 'turn_on', self.record)
        for camera in ['front', 'backdoor', 'garage', 'porch']:
            self.hass.services.async_register('shell_command', camera + '_camera_alert_copy', self.record)
        for number in [8, 35, 36, 70, 79, 81, 101, 102, 112, 113, 114, 130]:
            self.events.clear()
            trigger = {'entity_id': 'binary_sensor.rf_lobby_motion',
                       'to_state': State('binary_sensor.rf_lobby_motion', 'on', {'friendly_name': 'Lobby'})}
            await self.make_script({'sequence': self.automation(number)['actions']}).async_run(
                {'trigger': trigger}, context=Context())
            chrome = [data for action, data in self.events if action == 'html5.send_message']
            if number in [8, 35, 36, 70, 81]:
                self.assertEqual(chrome, [])
                continue
            self.assertEqual(len(chrome), 1, number)
            self.assertEqual(chrome[0]['entity_id'], ['notify.chrome'])
            if number in [8, 35, 36, 81]:
                self.assertTrue(chrome[0]['image'].startswith('/local/'))
                self.assertEqual(chrome[0]['data']['url'], chrome[0]['image'])

    async def test_common_desktop_scripts_copy_once_and_keep_existing_destinations(self):
        for name in ['notify', 'notifymax']:
            self.events.clear()
            await self.make_script(self.source_script(name)).async_run({'message': 'Energy notification'}, context=Context())
            services = [e[0] for e in self.events]
            self.assertEqual(services.count('html5.send_message'), 1)
            self.assertEqual(services.count('notify.roomba'), 1)
            self.assertEqual(services.count('notify.imac21'), 1)
            self.assertEqual(services.count('persistent_notification.create'), int(name == 'notifymax'))

    async def test_motion_copy_respects_mute_and_ignores_retired_postbox(self):
        self.hass.services.async_register('script', 'notify_mqtt', self.record)
        config = self.automation(70)
        entity = 'binary_sensor.rf_lobby_motion'
        self.hass.states.async_set('input_boolean.notifications_off', 'on')
        self.hass.states.async_set(entity, 'off', {'friendly_name': 'Lobby'})
        self.hass.states.async_set('binary_sensor.postbox', 'off', {'friendly_name': 'Mailbox'})
        self.assertTrue(await async_setup_component(self.hass, 'automation', {'automation': [config]}))
        await self.hass.async_start()
        self.hass.states.async_set(entity, 'on', {'friendly_name': 'Lobby'})
        await self.hass.async_block_till_done()
        self.assertEqual(self.events, [])
        self.hass.states.async_set('input_boolean.notifications_off', 'off')
        self.hass.states.async_set(entity, 'off', {'friendly_name': 'Lobby'})
        await self.hass.async_block_till_done()
        self.hass.states.async_set(entity, 'on', {'friendly_name': 'Lobby'})
        await self.hass.async_block_till_done()
        self.assertEqual([e[0] for e in self.events].count('html5.send_message'), 0)
        self.assertEqual([e[0] for e in self.events].count('notify.roomba'), 1)
        self.assertEqual(self.mobile_events, [])
        self.events.clear()
        self.hass.states.async_set('binary_sensor.postbox', 'on', {'friendly_name': 'Mailbox'})
        await self.hass.async_block_till_done()
        self.assertEqual(self.events, [])

    async def test_iphone_receives_one_copy_when_tv_is_off(self):
        self.hass.services.async_register('notify', 'lg2', self.record)
        self.hass.states.async_set('media_player.lg2', 'off')
        await self.helper.async_run({'notify_service': 'notify.lg2',
            'notify_data': {'message': 'Dinner motion', 'data': {'icon': '/private/icon.jpg'}},
            'also_chrome': True}, context=Context())
        self.assertEqual(self.mobile_events, [{'title': 'Home Assistant', 'message': 'Dinner motion', 'data': {'url': '/'}}])

    async def test_ring_browser_snapshot_does_not_duplicate_dedicated_phone_alert(self):
        await self.helper.async_run({'notify_service': 'html5.send_message', 'also_chrome': True,
            'notify_data': {'entity_id': 'notify.chrome', 'message': 'Ring Motion',
                'image': '/local/ring_camera_alert.jpg?123',
                'actions': [{'action': 'browser_only', 'title': 'Browser'}]}}, context=Context())
        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.events[0][0], 'html5.send_message')
        self.assertEqual(self.mobile_events, [])

    async def test_iphone_copy_survives_chrome_failure(self):
        self.failed_services.add('html5.send_message')
        await self.helper.async_run({'notify_service': 'html5.send_message',
            'notify_data': {'entity_id': 'notify.chrome', 'message': 'Motion'}}, context=Context())
        self.assertEqual(len(self.mobile_events), 1)

    async def test_concise_motion_names_preserve_mqtt_displays_and_rf_suppression(self):
        mqtt = self.make_script(self.source_script('notify_mqtt'))
        async def publish(call):
            await mqtt.async_run(dict(call.data), context=call.context)
        self.hass.services.async_register('script', 'notify_mqtt', publish)
        for name in ['inew', 'lg_webos_tv_oled77c5pua_dusqljr']:
            self.hass.services.async_register('notify', name, self.record)
        self.hass.states.async_set('media_player.living_room_tv_77', 'on')
        script = self.make_script({'sequence': self.automation(70)['actions']})
        for entity, name, expected, rf in [
            ('binary_sensor.rf_counter_motion', 'RF Counter Motion', 'Counter Motion', True),
            ('binary_sensor.rf_dinner_motion', 'rf Dinner Motion', 'Dinner Motion', True),
            ('binary_sensor.rf_lobby_motion', 'Lobby Motion', 'Lobby Motion', True),
            ('binary_sensor.studio_bathroom_motion', 'Studio Bathroom Motion', 'Studio Bathroom Motion', False),
        ]:
            with self.subTest(entity=entity):
                self.events.clear()
                self.mobile_events.clear()
                await script.async_run({'trigger': {'entity_id': entity,
                    'to_state': State(entity, 'on', {'friendly_name': name})}}, context=Context())
                wire = next(data for service, data in self.events if service == 'mqtt.publish')
                self.assertEqual(json.loads(wire['payload']), {'title': 'Info', 'message': expected})
                self.assertEqual(wire['topic'], 'living_room/notifications')
                self.assertTrue(wire['retain'])
                for destination in ['notify.roomba', 'notify.inew', 'notify.lg_webos_tv_oled77c5pua_dusqljr']:
                    payload = next(data for service, data in self.events if service == destination)
                    self.assertEqual(payload['message'], expected)
                    if 'title' in payload:
                        self.assertEqual(payload['title'], expected)
                self.assertEqual([service for service, _ in self.events].count('html5.send_message'), 0 if rf else 1)
                self.assertEqual(len(self.mobile_events), 0 if rf else 1)
        # Source classification must also block a direct phone request with the shortened label.
        self.mobile_events.clear()
        await self.helper.async_run({'notify_service': 'notify.mobile_app_als_iphone_89310',
            'notify_data': {'message': 'Counter Motion'}, 'notification_category': 'rf_motion'}, context=Context())
        self.assertEqual(self.mobile_events, [])

    async def test_rf_motion_reports_keep_existing_destinations_without_browser_or_phone(self):
        for state in ['on', 'off']:
            for payload in [
                {'title': f'Motion RF Dinner Motion triggered:{state}',
                    'message': f'RF Dinner Motion turned {state}'},
                {'message': f'RF Counter Motion {state}'},
                {'title': f'motion rf counter motion triggered:{state}', 'message': 'Motion'},
            ]:
                with self.subTest(state=state, payload=payload):
                    self.events.clear()
                    self.mobile_events.clear()
                    await self.helper.async_run({'notify_service': 'notify.roomba', 'also_chrome': True,
                        'notify_data': payload}, context=Context())
                    self.assertEqual(self.events, [('notify.roomba', payload)])
                    self.assertEqual(self.mobile_events, [])
                    self.events.clear()
                    await self.helper.async_run({'notify_service': 'html5.send_message',
                        'notify_data': dict(payload, entity_id='notify.chrome')}, context=Context())
                    self.assertEqual(self.events, [])
                    self.assertEqual(self.mobile_events, [])

        # Dedicated Ring motion still reaches the phone, with the live entity.
        await self.helper.async_run({'notify_service': 'notify.mobile_app_als_iphone_89310',
            'notify_data': {'title': 'Ring Front Door: motion detected',
                'message': 'Motion detected', 'data': {'entity_id': 'camera.ring_camera_notifications'}}}, context=Context())
        self.assertEqual(len(self.mobile_events), 1)
        self.assertEqual(self.mobile_events[0]['data']['entity_id'], 'camera.ring_camera_notifications')

    async def test_muted_camera_messages_keep_original_desktop_only(self):
        for payload in [
            {'title': 'Front Camera', 'message': 'Motion detected'},
            {'title': 'Garage Camera', 'message': 'Motion detected'},
            {'title': 'Porch Camera', 'message': 'Motion detected'},
            {'title': 'Backdoor Camera', 'message': 'Motion detected'},
            {'title': 'Kerberos recording', 'message': 'Motion detected'},
            {'title': 'Frigate', 'message': 'Person detected'},
            {'message': 'Someone at the Front Camera'},
            {'message': 'Motion', 'image': '/local/front_camera_alert.jpg?123'},
        ]:
            self.events.clear()
            self.mobile_events.clear()
            await self.helper.async_run({'notify_service': 'notify.roomba',
                'notify_data': payload, 'also_chrome': True}, context=Context())
            self.assertEqual(self.events, [('notify.roomba', payload)])
            self.assertEqual(self.mobile_events, [])
            self.events.clear()
            await self.helper.async_run({'notify_service': 'html5.send_message',
                'notify_data': dict(payload, entity_id='notify.chrome')}, context=Context())
            self.assertEqual(self.events, [])
            self.assertEqual(self.mobile_events, [])

    async def test_light_switch_state_reports_keep_chrome_without_phone(self):
        for number, entity, phone_count in [
            (112, 'light.fixture', 0), (112, 'switch.fixture', 0),
            (113, 'cover.fixture', 1),
        ]:
            self.events.clear()
            self.mobile_events.clear()
            trigger = {'entity_id': entity, 'to_state': State(entity, 'on', {'friendly_name': 'Fixture'})}
            await self.make_script({'sequence': self.automation(number)['actions']}).async_run(
                {'trigger': trigger}, context=Context())
            self.assertEqual(sum(action == 'html5.send_message' for action, _ in self.events), 1)
            self.assertEqual(len(self.mobile_events), phone_count)

    async def test_person_camera_exception_is_phone_only_and_camera_scoped(self):
        for camera, allowed in [('garage', True), ('porch', True), ('front', False), ('backdoor', False)]:
            for service in ['notify.mobile_app_als_iphone_89310', 'html5.send_message']:
                with self.subTest(camera=camera, service=service):
                    self.events.clear()
                    self.mobile_events.clear()
                    payload = {'title': 'Frigate person detected', 'message': 'Person',
                        'data': {'entity_id': f'camera.{camera}_camera_notifications'}}
                    if service == 'html5.send_message':
                        payload['entity_id'] = 'notify.chrome'
                    await self.helper.async_run({'notify_service': service,
                        'notification_category': 'camera_person', 'also_chrome': True,
                        'notify_data': payload}, context=Context())
                    self.assertEqual(self.events, [])
                    self.assertEqual(len(self.mobile_events), int(allowed and service.startswith('notify.mobile_app_')))
                    if self.mobile_events:
                        self.assertEqual(self.mobile_events[0], payload)

    async def test_frigate_person_video_requires_new_active_person_activity(self):
        config = yaml.safe_load((ROOT / 'config/packages/camera_person_notifications.yaml').read_text())
        garage = 'sensor.garage_person_active_count_2'
        porch = 'sensor.porch_person_active_count_2'
        self.hass.states.async_set('input_boolean.notifications_off', 'off')
        for entity in [garage, porch]:
            self.hass.states.async_set(entity, '0')
        self.assertTrue(await async_setup_component(self.hass, 'automation', config))
        await self.hass.async_start()

        async def change(entity, state):
            self.hass.states.async_set(entity, state)
            await self.hass.async_block_till_done()

        await change(garage, '1')
        await change(garage, '2')  # Same active scene: no repeated notification.
        await change(porch, '1')  # Other camera remains independent.
        await change('binary_sensor.garage_motion_2', 'on')
        await change('sensor.front_person_active_count_2', '1')
        self.assertEqual(len(self.mobile_events), 2)
        for payload, camera in zip(self.mobile_events, ['garage', 'porch']):
            self.assertEqual(payload['data']['entity_id'], f'camera.{camera}_camera_notifications')
            self.assertEqual(payload['data']['push'], {'category': 'camera'})
            self.assertEqual(payload['data']['tag'], f'frigate-person-{camera}')
        self.assertEqual(self.events, [])  # No browser or device actions.
        await change(garage, 'unavailable')
        await change(garage, '1')  # Recovery must not replay existing activity.
        await change(porch, '0')
        await change(porch, 'unknown')
        self.assertEqual(len(self.mobile_events), 2)
        await change(garage, '0')
        await change(garage, '1')
        self.assertEqual(len(self.mobile_events), 3)
        await change('input_boolean.notifications_off', 'on')
        await change(garage, '0')
        await change(garage, '1')
        self.assertEqual(len(self.mobile_events), 3)

    async def test_ring_motion_prepares_live_video_without_snapshot_dependency(self):
        config = yaml.safe_load((ROOT / 'config/packages/camera_person_notifications.yaml').read_text())
        entity = 'binary_sensor.front_door_motion_2'
        preparations = []
        async def prepare(call):
            preparations.append(True)
            self.assertEqual(self.mobile_events, [])
            return {'returncode': 0, 'stdout': '{"ready": true}', 'stderr': ''}
        self.hass.services.async_register('shell_command', 'ring_notification_video_ready', prepare,
                                         supports_response=SupportsResponse.ONLY)
        self.hass.states.async_set('input_boolean.notifications_off', 'off')
        self.hass.states.async_set(entity, 'off')
        self.assertTrue(await async_setup_component(self.hass, 'automation', config))
        await self.hass.async_start()
        async def change(name, state):
            self.hass.states.async_set(name, state)
            await self.hass.async_block_till_done()
        with patch('homeassistant.util.dt.now', return_value=datetime(2026, 9, 26, 12, tzinfo=timezone.utc)):
            await change(entity, 'on')
            self.assertEqual(preparations, [True])
            self.assertEqual(len(self.mobile_events), 1)
            extra = self.mobile_events[0]['data']
            self.assertEqual(extra['entity_id'], 'camera.ring_camera_notifications')
            self.assertEqual(extra['push'], {'category': 'camera'})
            self.assertEqual(extra['tag'], 'ring-front-door-motion')
            self.assertNotIn('image', extra)
            self.assertIn('Expand', self.mobile_events[0]['message'])
            self.assertEqual(self.events, [])
            await change(entity, 'on')
            await change(entity, 'unavailable')
            await change(entity, 'on')
            await change('binary_sensor.blink_porch_motion_detected', 'on')
            await change('input_boolean.notifications_off', 'on')
            await change(entity, 'off')
            await change(entity, 'on')
            self.assertEqual(len(self.mobile_events), 1)
            self.assertEqual(preparations, [True])
        await change('input_boolean.notifications_off', 'off')
        with patch('homeassistant.util.dt.now', return_value=datetime(2026, 9, 26, 3, tzinfo=timezone.utc)):
            await change(entity, 'off')
            await change(entity, 'on')
        self.assertEqual(preparations, [True])  # Preserve existing quiet hours.

    async def test_ring_preparation_failure_still_notifies_and_mute_during_wait_wins(self):
        config = yaml.safe_load((ROOT / 'config/packages/camera_person_notifications.yaml').read_text())
        actions = next(a['actions'] for a in config['automation'] if a['id'] == 'ha_homelab_phone_ring_motion_video')
        for result in ['offline', 'service_error', 'muted']:
            with self.subTest(result=result):
                self.mobile_events.clear()
                self.hass.states.async_set('input_boolean.notifications_off', 'off')
                async def prepare(call):
                    if result == 'service_error':
                        raise HomeAssistantError('Simulated failure')
                    if result == 'muted':
                        self.hass.states.async_set('input_boolean.notifications_off', 'on')
                    return {'returncode': 1, 'stdout': '{"ready": false}', 'stderr': ''}
                self.hass.services.async_register('shell_command', 'ring_notification_video_ready', prepare,
                                                 supports_response=SupportsResponse.ONLY)
                await self.make_script({'sequence': actions}).async_run(context=Context())
                self.assertEqual(len(self.mobile_events), 0 if result == 'muted' else 1)
                if self.mobile_events:
                    self.assertIn('may be unavailable', self.mobile_events[0]['message'])
                self.assertEqual(self.events, [])

    async def test_onvif_phone_category_is_scoped_to_living_room_and_never_chrome(self):
        for camera in ['living_room_onvif_notifications', 'front_camera_notifications', 'ring_camera_notifications']:
            for service in ['notify.mobile_app_als_iphone_89310', 'html5.send_message']:
                self.events.clear()
                self.mobile_events.clear()
                payload = {'title': 'Living Room ONVIF: motion detected', 'message': 'Motion',
                           'data': {'entity_id': 'camera.' + camera}}
                if service == 'html5.send_message':
                    payload['entity_id'] = 'notify.chrome'
                await self.helper.async_run({'notify_service': service, 'notify_data': payload,
                    'notification_category': 'camera_onvif', 'also_chrome': True}, context=Context())
                self.assertEqual(self.events, [])
                self.assertEqual(len(self.mobile_events), int(camera == 'living_room_onvif_notifications'
                    and service == 'notify.mobile_app_als_iphone_89310'))

    async def test_tapo_desktop_url_requires_real_motion_and_uses_current_token(self):
        (Path(self.temp.name) / 'configuration.yaml').write_text(
            (ROOT / 'config/packages/tapo_desktop_mqtt.yaml').read_text())
        (Path(self.temp.name) / 'secrets.yaml').write_text(
            'home_assistant_external_url: https://ha.example.invalid\n')
        config = await async_hass_config_yaml(self.hass)
        sensor = 'binary_sensor.kitchen_camera_cell_motion_detection'
        camera = 'camera.kitchen_camera_minorstream'
        self.hass.states.async_set(camera, 'idle', {'access_token': 'first-camera-token'})
        self.hass.states.async_set(sensor, 'on')
        self.assertTrue(await async_setup_component(self.hass, 'automation', config))
        await self.hass.async_start()
        await self.hass.async_block_till_done()
        self.assertEqual(self.events, [])  # Already moving at startup is not new motion.

        async def change(entity, state, attributes=None):
            self.hass.states.async_set(entity, state, attributes)
            await self.hass.async_block_till_done()

        for previous in ['unknown', 'unavailable']:
            await change(sensor, previous)
            await change(sensor, 'on')
        await change('binary_sensor.kitchen_camera_person_detection', 'on')
        await change(sensor, 'on', {'friendly_name': 'Changed attributes'})
        self.assertEqual(self.events, [])
        await change(camera, 'idle', {'access_token': 'rotated-camera-token'})
        await change(sensor, 'off')
        await change(sensor, 'on')
        self.assertEqual(self.events, [('mqtt.publish', {
            'topic': 'homelab/cameras/live/kitchen',
            'payload': 'https://ha.example.invalid/api/camera_proxy_stream/'
                       'camera.kitchen_camera_minorstream?token=rotated-camera-token',
            'qos': 0, 'retain': False,
        })])
        self.assertEqual(self.mobile_events, [])
        for state, attributes in [('unavailable', {'access_token': 'old-token'}), ('idle', {})]:
            await change(camera, state, attributes)
            await change(sensor, 'off')
            await change(sensor, 'on')
        self.assertEqual(len(self.events), 1)  # Never publish an unusable URL.

    async def test_onvif_video_needs_new_motion_and_respects_cooldown_and_mute(self):
        config = yaml.safe_load((ROOT / 'config/packages/onvif_video_notifications.yaml').read_text())
        entity = 'binary_sensor.living_room_camera_cell_motion_detection'
        clock = [datetime(2026, 9, 27, 12, tzinfo=timezone.utc)]
        preparations = []
        async def prepare(call):
            preparations.append(dict(call.data))
            return {'returncode': 0, 'stdout': '{"ready": true}', 'stderr': ''}
        self.hass.services.async_register('shell_command', 'onvif_notification_video_ready', prepare,
                                         supports_response=SupportsResponse.ONLY)
        self.hass.states.async_set('input_boolean.notifications_off', 'off')
        self.hass.states.async_set(entity, 'off')
        self.assertTrue(await async_setup_component(self.hass, 'automation', config))
        await self.hass.async_start()
        async def change(name, state):
            self.hass.states.async_set(name, state)
            await self.hass.async_block_till_done()
        with patch('homeassistant.util.dt.now', side_effect=lambda *a: clock[0]), \
             patch('homeassistant.util.dt.utcnow', side_effect=lambda *a: clock[0]), \
             patch('homeassistant.helpers.script.utcnow', side_effect=lambda *a: clock[0]):
            await change(entity, 'on')
            self.assertEqual(preparations, [{'camera_key': 'living_room_onvif'}])
            self.assertEqual(len(self.mobile_events), 1)
            payload = self.mobile_events[0]
            self.assertEqual(payload['title'], 'Living Room ONVIF: motion detected')
            self.assertEqual(payload['data']['entity_id'], 'camera.living_room_onvif_notifications')
            self.assertEqual(payload['data']['push'], {'category': 'camera'})
            self.assertEqual(self.events, [])
            await change(entity, 'off')
            await change(entity, 'on')  # Repeated short motion burst is suppressed.
            self.assertEqual(len(preparations), 1)
            clock[0] += timedelta(seconds=61)
            await change(entity, 'unavailable')
            await change(entity, 'on')  # Recovery is not a new motion event.
            await change('binary_sensor.dining_room_camera_cell_motion_detection', 'on')
            self.assertEqual(len(preparations), 1)
            await change(entity, 'off')
            await change(entity, 'on')
            self.assertEqual(len(preparations), 2, str(self.hass.states.get('automation.security_living_room_onvif_video_on_vitaly_iphone_air').attributes))
            clock[0] += timedelta(seconds=61)
            await change('input_boolean.notifications_off', 'on')
            await change(entity, 'off')
            await change(entity, 'on')
            self.assertEqual(len(preparations), 2)

    async def test_onvif_unavailable_video_keeps_alert_and_mid_preparation_mute_cancels_it(self):
        config = yaml.safe_load((ROOT / 'config/packages/onvif_video_notifications.yaml').read_text())
        for result in ['offline', 'service_error', 'muted']:
            self.mobile_events.clear()
            self.hass.states.async_set('input_boolean.notifications_off', 'off')
            async def prepare(call):
                if result == 'service_error':
                    raise HomeAssistantError('Simulated failure')
                if result == 'muted':
                    self.hass.states.async_set('input_boolean.notifications_off', 'on')
                return {'returncode': 1, 'stdout': '{"ready": false}', 'stderr': ''}
            self.hass.services.async_register('shell_command', 'onvif_notification_video_ready', prepare,
                                             supports_response=SupportsResponse.ONLY)
            await self.make_script({'sequence': config['automation'][0]['actions']}).async_run(context=Context())
            self.assertEqual(len(self.mobile_events), 0 if result == 'muted' else 1)
            if self.mobile_events:
                self.assertIn('may be unavailable', self.mobile_events[0]['message'])
            self.assertEqual(self.events, [])

    async def test_iphone_failure_does_not_stop_household_actions(self):
        self.failed_services.add('notify.mobile_app_als_iphone_89310')
        await self.make_script({'sequence': [
            {'action': 'script.notify_optional', 'data': {'notify_service': 'notify.good',
                'notify_data': {'message': 'Motion'}, 'also_chrome': True}},
            {'action': 'switch.turn_off', 'target': {'entity_id': 'switch.fixture'}}
        ]}).async_run(context=Context())
        self.assertEqual(self.events[-1][0], 'switch.turn_off')
        self.assertEqual(len(self.mobile_events), 1)

    async def test_other_html5_targets_do_not_notify_owner_phone(self):
        await self.helper.async_run({'notify_service': 'html5.send_message',
            'notify_data': {'entity_id': 'notify.another_browser', 'message': 'Private'}}, context=Context())
        self.assertEqual(self.mobile_events, [])

    async def setup_html5_buttons(self):
        self.browser_entities = ['event.chrome']
        self.event_number = 0
        for entity in self.browser_entities + ['event.unrelated', 'event.g011825', 'event.f011826']:
            self.hass.states.async_set(entity, 'unknown')
        configs = [self.automation(number) for number in [41, 42, 80]]
        self.assertTrue(await async_setup_component(self.hass, 'automation', {'automation': configs}))
        await self.hass.async_start()
        await self.hass.async_block_till_done()
        self.assertFalse(any(name.startswith('html5_notification.')
                             for name in self.hass.bus.async_listeners()))

    async def html5_event(self, entity, event_type, action=None):
        self.event_number += 1
        self.hass.states.async_set(entity, f'2026-09-22T12:00:{self.event_number:02d}+00:00',
                                   {'event_type': event_type, 'action': action})
        await self.hass.async_block_till_done()

    async def test_html5_buttons_route_first_and_repeated_clicks_from_each_browser(self):
        await self.setup_html5_buttons()
        for entity in self.browser_entities:
            for action, service, target in [
                ('studio_sticky', 'input_boolean.turn_on', 'input_boolean.studio_sticky'),
                ('studio_unsticky', 'input_boolean.turn_off', 'input_boolean.studio_sticky'),
                ('porch_light_on', 'light.turn_on', 'light.porch_one'),
            ]:
                for _ in range(2):
                    self.events.clear()
                    await self.html5_event(entity, 'clicked', action)
                    self.assertEqual(self.events, [(service, {'entity_id': [target]})])

    async def test_html5_buttons_ignore_delivery_close_other_actions_and_other_entities(self):
        await self.setup_html5_buttons()
        for event_type, action in [('received', 'studio_sticky'), ('closed', 'porch_light_on'),
                                   ('clicked', 'unrelated'), ('clicked', None)]:
            await self.html5_event('event.chrome', event_type, action)
        await self.html5_event('event.unrelated', 'clicked', 'porch_light_on')
        for entity in ['event.g011825', 'event.f011826']:
            for action in ['studio_sticky', 'studio_unsticky', 'porch_light_on']:
                await self.html5_event(entity, 'clicked', action)
        self.assertEqual(self.events, [])

    async def test_html5_buttons_do_not_replay_old_click_on_attribute_change_or_recovery(self):
        await self.setup_html5_buttons()
        await self.html5_event('event.chrome', 'clicked', 'porch_light_on')
        previous = self.hass.states.get('event.chrome')
        self.events.clear()
        self.hass.states.async_set(previous.entity_id, previous.state,
                                   dict(previous.attributes, friendly_name='Chrome'))
        await self.hass.async_block_till_done()
        self.hass.states.async_set(previous.entity_id, 'unavailable', dict(previous.attributes))
        await self.hass.async_block_till_done()
        self.hass.states.async_set(previous.entity_id, previous.state, dict(previous.attributes))
        await self.hass.async_block_till_done()
        self.assertEqual(self.events, [])
        await self.html5_event('event.chrome', 'clicked', 'porch_light_on')
        self.assertEqual(self.events, [('light.turn_on', {'entity_id': ['light.porch_one']})])

    async def test_missing_provider_logs_without_exposing_message(self):
        await self.helper.async_run({'notify_service': 'notify.missing', 'notify_data': {'message': 'private-text'}}, context=Context())
        self.assertEqual(self.events[0][0], 'system_log.write')
        self.assertIn('notify.missing', self.events[0][1]['message'])
        self.assertNotIn('private-text', json.dumps(self.events))

    async def test_provider_appearing_later_is_used_without_reload(self):
        args = {'notify_service': 'notify.restored', 'notify_data': {'message': 'test'}}
        await self.helper.async_run(args, context=Context())
        self.hass.services.async_register('notify', 'restored', self.record)
        self.events.clear()
        await self.helper.async_run(args, context=Context())
        self.assertEqual(self.events, [('notify.restored', args['notify_data'])])

    async def test_provider_failure_does_not_abort_caller(self):
        self.failed_services.add('notify.bad')
        script = self.make_script({'sequence': [
            {'action': 'script.notify_optional', 'data': {'notify_service': 'notify.bad', 'notify_data': {'message': 'test'}}},
            {'action': 'light.turn_off', 'target': {'entity_id': 'light.fixture'}},
        ]})
        await script.async_run(context=Context())
        self.assertEqual([e[0] for e in self.events], ['notify.bad', 'light.turn_off'])

    async def test_non_notification_actions_are_rejected(self):
        await self.helper.async_run({'notify_service': 'switch.turn_off', 'notify_data': {}}, context=Context())
        self.assertFalse(self.events)

    async def test_invalid_payload_still_fails(self):
        import voluptuous as vol
        self.hass.services.async_register('notify', 'strict', self.record,
                                         schema=vol.Schema({vol.Required('message'): str}))
        with self.assertRaises(vol.Invalid):
            await self.helper.async_run({'notify_service': 'notify.strict', 'notify_data': {'unexpected': True}}, context=Context())
        self.assertFalse(self.events)

    async def test_mqtt_json_escaping_and_wire_schema(self):
        script = self.make_script(self.source_script('notify_mqtt'))
        for message in ['plain', '"quote"\\slash\nnext line', 'Свет включён', '{{ literal }}']:
            await script.async_run({'message': message}, context=Context())
            data = self.events[-1][1]
            self.assertEqual(json.loads(data['payload']), {'title': 'Info', 'message': message})
            self.assertEqual(data['topic'], 'living_room/notifications')
            self.assertTrue(data['retain'])

    async def test_mqtt_burst_is_queued_in_order(self):
        script = self.make_script(self.source_script('notify_mqtt_log'))
        self.mqtt_gate.clear()
        one = asyncio.create_task(script.async_run({'message': 'first'}, context=Context()))
        await asyncio.sleep(0)
        two = asyncio.create_task(script.async_run({'message': 'second'}, context=Context()))
        await asyncio.sleep(0.01)
        self.mqtt_gate.set()
        await asyncio.gather(one, two)
        self.assertEqual([e[1]['payload'] for e in self.events], ['first', 'second'])
        self.assertTrue(all(e[1]['retain'] for e in self.events))

    async def test_media_off_attempts_all_players_after_failure(self):
        config = self.source_script('mediaoff')
        self.failed_services.add('media_player.bathroom_echo_dot')
        await self.make_script(config).async_run(context=Context())
        expected = config['sequence'][0]['repeat']['for_each']
        self.assertEqual([e[1]['entity_id'][0] for e in self.events], expected)
        self.assertEqual(len(expected), 8)
        self.assertNotIn('media_player.our_bedroom_google_home', expected)

    async def test_household_off_failure_does_not_skip_switches_or_shutdown(self):
        self.failed_services.add('homeassistant.turn_off')
        await self.make_script(self.source_script('turn_off_living_room')).async_run(context=Context())
        self.assertEqual([e[0] for e in self.events],
                         ['homeassistant.turn_off', 'switch.turn_off', 'shell_command.shutdown_inew'])
        mixed_targets = self.events[0][1]['entity_id']
        self.assertIn('light.bedroom_lamp', mixed_targets)
        self.assertIn('switch.tea_table', mixed_targets)
        self.assertIn('switch.led_under_cabinet', mixed_targets)
        self.assertNotIn('light.led_under_cabinet_l', mixed_targets)
        self.assertNotIn('light.led_under_cabinet_2_l', mixed_targets)
        switch_targets = self.events[1][1]['entity_id']
        self.assertIn('switch.living_lamp', switch_targets)
        self.assertNotIn('switch.audio_l', switch_targets)
        self.assertNotIn('switch.switch02', switch_targets)

    async def test_lighting_scenarios_never_control_repurposed_water_outlets(self):
        # Exercise the automatic lighting branches with room overrides released.
        # An absent Sticky helper intentionally blocks those branches.
        for room in ('hallway', 'mishka_room', 'kitchen', 'bathroom', 'dining_room',
                     'porch', 'living_room', 'bedroom', 'lobby'):
            self.hass.states.async_set(f'input_boolean.{room}_sticky', 'off')
        forbidden = {
            'switch.fireplace_l', 'switch.stage_led_l', 'switch.flare',
            'switch.sockets_behind_fireplace_3_l',
            'switch.moen_flo_water_monitor_power', 'switch.pump_power_enable',
            'switch.laundry',
        }
        self.hass.services.async_register('script', 'notify', self.record)
        scenarios = {
            'household shutdown': self.source_script('turn_off_living_room'),
            'morning shutdown': {'sequence': self.automation(74)['actions']},
            'surplus lighting': {'sequence': self.automation(91)['actions']},
        }
        for name, config in scenarios.items():
            with self.subTest(scenario=name):
                self.events.clear()
                await self.make_script(config).async_run(context=Context())
                targets = {entity for service, data in self.events
                           if service.startswith(('switch.', 'light.', 'homeassistant.'))
                           for entity in data.get('entity_id', [])}
                self.assertIn('switch.tea_table', targets)
                self.assertFalse(targets & forbidden, targets & forbidden)

    async def test_retained_volume_preset_only_calls_the_retained_echo(self):
        await self.make_script(self.source_script('volume_down')).async_run(context=Context())
        self.assertEqual(self.events, [('media_player.volume_set',
                                      {'entity_id': ['media_player.vitaly_s_echo'], 'volume_level': 0.2})])

    async def test_front_porch_notification_never_pulses_repurposed_switches(self):
        await self.make_script(self.source_script('blinkmotion')).async_run(context=Context())
        self.assertEqual(self.events, [])
        self.assertEqual(self.mobile_events, [])

    async def test_refactored_script_sequences_preserve_commands_and_delays(self):
        self.source_script('backdoormotion')  # Require the private dependency.
        # Compare the allowed lighting sequence; sticky behavior has separate tests.
        self.hass.states.async_set('input_boolean.porch_sticky', 'off')
        baseline = json.loads((ROOT / 'dependencies/scripts/contracts/source-baseline.json').read_text())['scripts']
        for name in ['backdoormotion']:
            with self.subTest(script=name), patch('homeassistant.util.dt.now', return_value=datetime(2026, 9, 22, 21, tzinfo=timezone.utc)):
                self.events.clear()
                await self.make_script(baseline[name], 'before').async_run(context=Context())
                # The owner retired phone/Pushbullet targets and repaired browser routing.
                # Compare physical commands and delays independently of those intentional changes.
                physical = lambda events: [event for event in events if not event[0].startswith(('notify.', 'html5.'))]
                expected = deepcopy(physical(self.events))
                self.events.clear()
                await self.make_script(self.source_script(name), 'after').async_run(context=Context())
                self.assertEqual(physical(self.events), expected)

    async def test_heating_cooldown_handles_first_run_and_recent_run(self):
        value = self.automation(116)['conditions'][0]['value_template']
        template = Template(value, self.hass)
        self.assertTrue(template.async_render({'this': State('automation.heating', 'on', {'last_triggered': None})}))
        self.assertFalse(template.async_render({'this': State('automation.heating', 'on', {'last_triggered': datetime.now(timezone.utc)})}))

    async def test_water_timer_uses_existing_switch_and_fires(self):
        config = self.automation(130)
        trigger = config['triggers'][0]
        self.assertEqual(trigger['entity_id'], 'switch.smart_water_timer_smart_water_timer')
        self.assertEqual(trigger['for'], {'minutes': 5})
        trigger['for'] = {'milliseconds': 10}
        self.hass.states.async_set(trigger['entity_id'], 'off')
        self.assertTrue(await async_setup_component(self.hass, 'automation', {'automation': [config]}))
        await self.hass.async_start()
        self.hass.states.async_set(trigger['entity_id'], 'on')
        await asyncio.sleep(0.04)
        await self.hass.async_block_till_done()
        self.assertEqual(self.events[0], ('switch.turn_off', {'entity_id': [trigger['entity_id']]}))

    async def test_pump_protection_reaches_valve_after_notify_failure(self):
        self.hass.services.async_register('script', 'turn_on', self.record)
        self.failed_services.add('notify.roomba')
        for number in [101, 102]:
            config = self.automation(number)
            trigger = config['triggers'][0]
            self.assertEqual(trigger['entity_id'], 'sensor.kmc_water_and_laundry_power')
            self.assertEqual(trigger['above'], 700)
            self.assertEqual(trigger['for'], {'minutes': 3 if number == 101 else 5})
            self.events.clear()
            await self.make_script({'sequence': config['actions']}).async_run(context=Context())
            self.assertEqual(self.events[0], ('switch.turn_off', {'entity_id': ['switch.pump_power_enable']}))
            self.assertEqual(self.events[-2:], [('delay', 10.0), ('script.turn_on', {
                'entity_id': ['script.water_valve_after_pump'], 'variables': {
                    'pump_state': 'off', 'valve_state': 'on', 'max_cm': 19 if number == 101 else 23,
                    **({'min_cm': 5} if number == 101 else {})}})])


if __name__ == '__main__':
    unittest.main(verbosity=2)
