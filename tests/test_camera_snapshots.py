"""Regression coverage for empty images, first capture and concurrent callers."""
import asyncio
import importlib.util
from io import BytesIO
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import json

ROOT = Path(os.environ.get('RESILIENCE_TEST_ROOT', Path(__file__).resolve().parents[1]))
try:
    from PIL import Image
except ImportError:
    Image = None


@unittest.skipUnless(Image, 'Pillow is provided by the deployed Home Assistant image')
class SnapshotFilesTest(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('camera_alert', ROOT / 'config/housekeeping/camera_alert.py')
        self.helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.helper)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def jpeg(self, color):
        output = BytesIO()
        Image.new('RGB', (32, 24), color).save(output, 'JPEG')
        return output.getvalue()

    def commit(self, content):
        self.helper.run('prepare', 'front', self.directory)
        (self.directory / '.front_camera_alert.pending.jpg').write_bytes(content)
        self.helper.run('commit', 'front', self.directory)

    def slots(self):
        return [(self.directory / f'front_camera_alert{s}.jpg').read_bytes() for s in ('', '2', '3', '4')]

    def test_bootstrap_rotation_and_duplicate_retained_frame(self):
        frames = [self.jpeg(c) for c in ('red', 'green', 'blue', 'white', 'black')]
        self.commit(frames[0])
        self.assertEqual(self.slots(), [frames[0]] * 4)
        for frame in frames[1:]:
            self.commit(frame)
        self.assertEqual(self.slots(), list(reversed(frames[1:])))
        self.commit(frames[-1])
        self.assertEqual(self.slots(), list(reversed(frames[1:])))

    def test_published_snapshots_keep_owner_only_permissions(self):
        frame = self.jpeg('red')
        self.commit(frame)
        paths = [self.directory / f'front_camera_alert{s}.jpg' for s in ('', '2', '3', '4')]
        self.assertEqual([path.stat().st_mode & 0o777 for path in paths], [0o600] * 4)
        # An unchanged capture also repairs snapshots produced by older versions.
        for path in paths:
            path.chmod(0o644)
        self.commit(frame)
        self.assertEqual([path.stat().st_mode & 0o777 for path in paths], [0o600] * 4)
        self.assertEqual(self.slots(), [frame] * 4)

    def test_invalid_or_truncated_capture_keeps_all_four_good_images(self):
        frame = self.jpeg('red')
        self.commit(frame)
        expected = self.slots()
        for broken in (b'', b'<html>offline</html>', frame[:100]):
            with self.assertRaises(ValueError):
                self.commit(broken)
            self.assertEqual(self.slots(), expected)
            self.assertFalse((self.directory / '.front_camera_alert.pending.jpg').exists())

    def test_missing_history_and_zero_byte_files_are_repaired_from_real_image(self):
        (self.directory / 'front_camera_alert.jpg').write_bytes(b'')
        (self.directory / 'front_camera_alert3.jpg').write_bytes(b'')
        frame = self.jpeg('blue')
        self.commit(frame)
        self.assertEqual(self.slots(), [frame] * 4)

    def test_retained_frame_refreshes_age_without_rewriting_or_redecoding_copies(self):
        frame = self.jpeg('red')
        self.commit(frame)
        paths = [self.directory / f'front_camera_alert{s}.jpg' for s in ('', '2', '3', '4')]
        for path in paths:
            os.utime(path, (1, 1))
        inodes = [path.stat().st_ino for path in paths]
        with patch.object(self.helper, 'atomic_write', wraps=self.helper.atomic_write) as write, \
                patch.object(self.helper, 'valid_jpeg', wraps=self.helper.valid_jpeg) as validate:
            self.commit(frame)
        self.assertEqual(write.call_count, 0)
        self.assertEqual(validate.call_count, 1)
        self.assertEqual(self.slots(), [frame] * 4)
        self.assertEqual([path.stat().st_ino for path in paths], inodes)
        self.assertTrue(all(path.stat().st_mtime > 1 for path in paths))

    def test_changed_frame_only_writes_changed_slots_and_preserves_order(self):
        first, second = self.jpeg('red'), self.jpeg('green')
        self.commit(first)
        with patch.object(self.helper, 'atomic_write', wraps=self.helper.atomic_write) as write, \
                patch.object(self.helper, 'valid_jpeg', wraps=self.helper.valid_jpeg) as validate:
            self.commit(second)
        self.assertEqual([call.args[0].name for call in write.call_args_list], ['front_camera_alert.jpg'])
        self.assertEqual(validate.call_count, 2)
        self.assertEqual(self.slots(), [second, first, first, first])
        third = self.jpeg('blue')
        self.commit(third)
        self.assertEqual(self.slots(), [third, second, first, first])

    def test_retained_frame_repairs_only_missing_or_corrupt_history(self):
        frame = self.jpeg('red')
        self.commit(frame)
        (self.directory / 'front_camera_alert2.jpg').unlink()
        (self.directory / 'front_camera_alert3.jpg').write_bytes(b'not an image')
        with patch.object(self.helper, 'atomic_write', wraps=self.helper.atomic_write) as write:
            self.commit(frame)
        self.assertEqual([call.args[0].name for call in write.call_args_list],
                         ['front_camera_alert3.jpg', 'front_camera_alert2.jpg'])
        self.assertEqual(self.slots(), [frame] * 4)

    def test_failed_atomic_replacement_preserves_previous_latest_and_removes_temporary(self):
        first, second = self.jpeg('red'), self.jpeg('green')
        self.commit(first)
        with patch.object(self.helper.os, 'replace', side_effect=OSError('Simulated disk failure')):
            with self.assertRaises(OSError):
                self.commit(second)
        self.assertEqual(self.slots(), [first] * 4)
        self.assertFalse(any(path.name.startswith('.') for path in self.directory.iterdir()))

    def test_prepare_discards_stale_pending_and_rejects_path_injection(self):
        pending = self.directory / '.front_camera_alert.pending.jpg'
        pending.write_bytes(self.jpeg('green'))
        self.helper.run('prepare', 'front', self.directory)
        self.assertFalse(pending.exists())
        with self.assertRaises(ValueError):
            self.helper.run('prepare', '../front', self.directory)

    def test_agent_login_and_snapshot_use_only_the_selected_local_agent(self):
        credentials = self.directory / 'auth.json'
        credentials.write_text(json.dumps({'username': 'fixture-user', 'password': 'fixture-password'}))
        credentials.chmod(0o600)
        frame = self.jpeg('blue')
        requests = []
        def respond(request, timeout):
            requests.append(request)
            if len(requests) == 1:
                self.assertEqual(timeout, 10)
                self.assertEqual(json.loads(request.data)['username'], 'fixture-user')
                return BytesIO(b'{"token":"fixture-token"}')
            self.assertEqual(request.get_header('Authorization'), 'Bearer fixture-token')
            self.assertEqual(timeout, 20)
            return BytesIO(frame)
        with patch.object(self.helper.urllib.request, 'urlopen', side_effect=respond):
            self.assertEqual(self.helper.fetch_agent('backdoor', credentials), frame)
        base = 'http://agent-tenantscamera.kerberos.svc.cluster.local'
        self.assertEqual([r.full_url for r in requests], [base + '/api/login', base + '/api/camera/snapshot/jpeg'])
        credentials.chmod(0o644)
        with self.assertRaises(ValueError):
            self.helper.fetch_agent('backdoor', credentials)

    def test_agent_failure_and_non_image_response_preserve_saved_files(self):
        self.commit(self.jpeg('red'))
        expected = self.slots()
        with patch.object(self.helper, 'fetch_agent', side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):
                self.helper.run('fetch', 'front', self.directory)
        with patch.object(self.helper, 'fetch_agent', return_value=b'<html>offline</html>'):
            with self.assertRaises(ValueError):
                self.helper.run('fetch', 'front', self.directory)
        self.assertEqual(self.slots(), expected)


try:
    from homeassistant import loader
    from homeassistant.bootstrap import async_load_base_functionality
    from homeassistant.config_entries import ConfigEntries
    from homeassistant.core import HomeAssistant, SupportsResponse, Context
    from homeassistant.exceptions import HomeAssistantError
    from homeassistant.helpers.script import Script
    from homeassistant.helpers import config_validation as cv
    from homeassistant.setup import async_setup_component
    import yaml
except ImportError:
    HA_AVAILABLE = False
else:
    HA_AVAILABLE = True


@unittest.skipUnless(HA_AVAILABLE, 'Requires the deployed Home Assistant image')
class SnapshotWorkflowTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.hass = HomeAssistant(self.temp.name)
        loader.async_setup(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self.hass.config.skip_pip = True
        await async_load_base_functionality(self.hass)
        self.events = []
        self.fail_camera = False
        self.returncode = 0
        self.fetch_returncode = 0
        self.refresh_ring = True
        async def shell(call):
            self.events.append((call.service, call.data['camera_key']))
            code = self.fetch_returncode if call.service == 'camera_alert_fetch' else self.returncode
            return {'returncode': code, 'stdout': '', 'stderr': ''}
        async def snapshot(call):
            self.events.append(('snapshot', call.data['filename']))
            await asyncio.sleep(0.01)
            if self.fail_camera:
                raise HomeAssistantError('Camera offline')
        for action in ('prepare', 'fetch', 'commit'):
            self.hass.services.async_register('shell_command', 'camera_alert_' + action, shell,
                                              supports_response=SupportsResponse.ONLY)
        self.hass.services.async_register('camera', 'snapshot', snapshot)
        async def refresh_ring(call):
            self.events.append(('ring_refresh', None))
            if self.refresh_ring:
                self.hass.states.async_set('camera.front_door_snapshot', 'idle', {'timestamp': time.time()})
        self.hass.services.async_register('button', 'press', refresh_ring)
        config = yaml.safe_load((ROOT / 'config/packages/camera_snapshots.yaml').read_text())
        for step in config['script']['capture_camera_alert']['sequence']:
            for action in step.get('then', []):
                if 'wait_template' in action:
                    action['timeout'] = {'milliseconds': 20}
        self.assertTrue(await async_setup_component(self.hass, 'script', {'script': config['script']}))
        await self.hass.async_block_till_done()

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.temp.cleanup()

    async def capture(self, key):
        await self.hass.services.async_call('script', 'capture_camera_alert', {'camera_key': key}, blocking=True)

    async def test_concurrent_requests_are_serialized(self):
        await asyncio.gather(self.capture('front'), self.capture('garage'))
        self.assertEqual([e[0] for e in self.events], ['camera_alert_prepare', 'snapshot', 'camera_alert_commit',
            'camera_alert_prepare', 'camera_alert_fetch', 'camera_alert_commit'])
        self.assertEqual(self.events[1][1], '/config/www/.front_camera_alert.pending.jpg')
        self.assertEqual(self.events[4][1], 'garage')

    async def test_failed_agent_fetch_never_rotates_history(self):
        self.fetch_returncode = 1
        await self.capture('garage')
        self.assertEqual(self.events, [('camera_alert_prepare', 'garage'), ('camera_alert_fetch', 'garage')])

    async def test_backdoor_uses_existing_agent_connection(self):
        await self.capture('backdoor')
        self.assertEqual(self.events, [('camera_alert_prepare', 'backdoor'),
            ('camera_alert_fetch', 'backdoor'), ('camera_alert_commit', 'backdoor')])

    async def test_failed_camera_does_not_commit_or_block_next_capture(self):
        self.fail_camera = True
        with self.assertRaises(HomeAssistantError):
            await self.capture('porch')
        self.assertNotIn('camera_alert_commit', [e[0] for e in self.events])
        self.fail_camera = False
        await self.capture('front')
        self.assertEqual(self.events[-1], ('camera_alert_commit', 'front'))

    async def test_unknown_key_and_failed_prepare_cannot_write_camera_image(self):
        # HA's explicit stop(error=true) records failure but does not propagate
        # an exception across the script service boundary. Verify the I/O guard.
        await self.capture('front; touch bad')
        self.assertEqual(self.events, [])
        self.returncode = 1
        await self.capture('front')
        self.assertEqual(self.events, [('camera_alert_prepare', 'front')])

    async def test_ring_refreshes_old_cache_and_reuses_recent_motion_frame(self):
        self.hass.states.async_set('camera.front_door_snapshot', 'idle', {'timestamp': 1})
        await self.capture('ring')
        self.assertEqual(self.events[0][0], 'ring_refresh')
        self.assertEqual(self.events[-1], ('camera_alert_commit', 'ring'))
        self.events.clear()
        await self.capture('ring')
        self.assertNotIn('ring_refresh', [e[0] for e in self.events])

    async def test_ring_refresh_timeout_preserves_previous_files(self):
        self.hass.states.async_set('camera.front_door_snapshot', 'idle', {'timestamp': 1})
        self.refresh_ring = False
        await self.capture('ring')
        self.assertEqual(self.events, [('ring_refresh', None)])

    async def test_motion_bridge_accepts_only_known_motion_and_ring_rising_edge(self):
        directory = ROOT / 'dependencies/automations/config'
        if not directory.is_dir():
            self.skipTest('Private submodule required for deployment validation')
        config = yaml.safe_load(next(directory.glob('044_*.yaml')).read_text())[0]
        ring_trigger = next(t for t in config['triggers'] if t['id'] == 'ring')
        self.assertEqual((ring_trigger['from'], ring_trigger['to']), ('off', 'on'))
        published = []
        async def publish(call):
            published.append(dict(call.data))
        self.hass.services.async_register('mqtt', 'publish', publish)
        async def start_timer(call):
            entity = call.data['entity_id']
            if isinstance(entity, list):
                entity = entity[0]
            self.hass.states.async_set(entity, 'active')
        self.hass.services.async_register('timer', 'start', start_timer)
        for camera in ('front', 'garage', 'backdoor', 'porch'):
            self.hass.states.async_set('timer.camera_motion_' + camera, 'idle')
        script = Script(self.hass, cv.SCRIPT_SCHEMA(config['actions']), 'bridge', 'automation')
        async def motion(payload):
            await script.async_run({'trigger': {'id': 'kerberos', 'payload_json': {'payload': payload}}}, context=Context())
        for key, topic in [('front_camera', 'front'), ('Garage_camera', 'garage'), ('Tenants_camera', 'backdoor'), ('Porch_camera', 'porch')]:
            await motion({'action': 'motion', 'device_id': key})
            self.assertEqual(published[-1]['topic'], 'kios/' + topic)
            await motion({'action': 'motion', 'device_id': key})
        self.assertEqual(len(published), 4, 'Repeated frames must not cause a notification storm')
        for payload in ({'action': 'heartbeat', 'device_id': 'front_camera'}, {'action': 'motion', 'device_id': 'unknown'}, None, []):
            await motion(payload)
        await script.async_run({'trigger': {'id': 'kerberos'}}, context=Context())
        self.assertEqual(len(published), 4)
        self.hass.states.async_set('timer.camera_motion_front', 'idle')
        await motion({'action': 'motion', 'device_id': 'front_camera'})
        self.assertEqual(len(published), 5, 'A new event after cooldown must reach notifications')
        await script.async_run({'trigger': {'id': 'ring'}}, context=Context())
        self.assertEqual(published[-1], {'topic': 'kios/ring', 'payload': '{"name":"Ring"}'})


if __name__ == '__main__':
    unittest.main(verbosity=2)
