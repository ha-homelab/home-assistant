"""Native Update service and stale approval checks without an actual updater."""
import asyncio
from copy import deepcopy
import importlib.util
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / 'config/custom_components/core_update_bridge'
spec = importlib.util.spec_from_file_location('core_update_client_test', COMPONENT / 'client.py')
client_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client_module)
STATE = {'stage': 'available', 'installed_version': '2026.11.0b2',
         'latest_version': '2026.11.0', 'target_version': '2026.11.0',
         'candidate_id': 'a' * 32, 'pull_request_url': 'https://github.com/example/deploy/pull/23'}


class ApprovalTest(unittest.IsolatedAsyncioTestCase):
    def client(self):
        return client_module.Client(None, 'http://updater.test:8099', 'Bearer ' + 'x' * 48)

    async def test_exact_snapshot_is_sent_once(self):
        client = self.client()
        client.request = AsyncMock(side_effect=[deepcopy(STATE), {'accepted': True,
            'candidate_id': 'a' * 32, 'target_version': '2026.11.0'}])
        result = await client.approve(STATE, '2026.11.0')
        self.assertEqual(result['stage'], 'preparing')
        self.assertEqual(client.request.await_count, 2)
        self.assertEqual(client.request.call_args.args, ('/approve', {
            'action': 'install', 'target_version': '2026.11.0', 'candidate_id': 'a' * 32}))

    async def test_same_version_changed_candidate_cannot_be_approved(self):
        client = self.client()
        client.request = AsyncMock(return_value=STATE | {'candidate_id': 'b' * 32})
        with self.assertRaises(client_module.BridgeError):
            await client.approve(STATE, '2026.11.0')
        client.request.assert_awaited_once_with('/status')

    async def test_stale_missing_or_newer_version_never_contacts_updater(self):
        client = self.client()
        client.request = AsyncMock()
        for version in [None, '2026.10.4', '2026.11.1']:
            with self.assertRaises(client_module.BridgeError):
                await client.approve(STATE, version)
        client.request.assert_not_awaited()

    async def test_timeout_is_not_retried(self):
        client = self.client()
        client.request = AsyncMock(side_effect=[STATE, client_module.BridgeError('Unconfirmed')])
        with self.assertRaises(client_module.BridgeError):
            await client.approve(STATE, '2026.11.0')
        self.assertEqual(client.request.await_count, 2)

    def test_active_and_failed_states_cannot_start_an_install(self):
        for stage in client_module.STAGES - {'available'}:
            with self.assertRaises(client_module.BridgeError):
                client_module.captured_approval(STATE | {'stage': stage}, '2026.11.0')


try:
    from homeassistant import loader
    from homeassistant.bootstrap import async_load_base_functionality
    from homeassistant.config_entries import ConfigEntries
    from homeassistant.core import HomeAssistant
    from homeassistant.setup import async_setup_component
except ImportError:
    if os.environ.get('REQUIRE_HA_RUNTIME') == '1':
        raise
    HA_AVAILABLE = False
else:
    HA_AVAILABLE = True


@unittest.skipUnless(HA_AVAILABLE, 'Requires the Home Assistant runtime')
class NativeUpdateTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.old_modules = {name: value for name, value in sys.modules.items()
                            if name == 'custom_components' or name.startswith('custom_components.core_update_bridge')}
        for name in self.old_modules:
            del sys.modules[name]
        self.temp = tempfile.TemporaryDirectory(prefix='core-update-test-')
        root = Path(self.temp.name)
        shutil.copytree(COMPONENT, root / 'custom_components/core_update_bridge')
        self.hass = HomeAssistant(self.temp.name)
        loader.async_setup(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self.hass.config.skip_pip = True
        self.assertTrue(await async_load_base_functionality(self.hass))
        await loader.async_get_integration(self.hass, 'core_update_bridge')
        from custom_components.core_update_bridge.client import Client
        self.client_type = Client
        self.status = AsyncMock(return_value=deepcopy(STATE))
        async def accept(*args):
            self.status.return_value = STATE | {'stage': 'preparing'}
            return deepcopy(self.status.return_value)
        self.approve = AsyncMock(side_effect=accept)
        self.patches = [patch.object(Client, 'status', self.status), patch.object(Client, 'approve', self.approve),
                        patch('custom_components.core_update_bridge.async_get_clientsession', return_value=None)]
        for item in self.patches:
            item.start()
        self.assertTrue(await async_setup_component(self.hass, 'core_update_bridge', {
            'core_update_bridge': {'url': 'http://updater.test:8099', 'authorization': 'Bearer ' + 'x' * 48}}))
        await self.hass.async_block_till_done()

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        await self.hass.async_block_till_done()
        for item in self.patches:
            item.stop()
        for name in list(sys.modules):
            if name == 'custom_components' or name.startswith('custom_components.core_update_bridge'):
                del sys.modules[name]
        sys.modules.update(self.old_modules)
        self.temp.cleanup()

    async def test_native_install_passes_exact_version_and_reports_progress(self):
        from homeassistant.components.update import UpdateEntityFeature
        state = self.hass.states.get('update.home_assistant_core')
        self.assertIsNotNone(state)
        self.assertEqual(state.state, 'on')
        for feature in (UpdateEntityFeature.INSTALL, UpdateEntityFeature.SPECIFIC_VERSION,
                        UpdateEntityFeature.RELEASE_NOTES, UpdateEntityFeature.PROGRESS):
            self.assertTrue(state.attributes['supported_features'] & feature)
        self.approve.assert_not_awaited()
        await self.hass.services.async_call('update', 'install', {
            'entity_id': state.entity_id, 'version': '2026.11.0'}, blocking=True)
        self.approve.assert_awaited_once_with(STATE, '2026.11.0')
        self.assertTrue(self.hass.states.get(state.entity_id).attributes['in_progress'])

    async def test_native_service_rejects_concurrent_approval(self):
        started, finish = asyncio.Event(), asyncio.Event()
        async def delayed(*args):
            started.set()
            await finish.wait()
            return STATE | {'stage': 'preparing'}
        self.approve.side_effect = delayed
        payload = {'entity_id': 'update.home_assistant_core', 'version': '2026.11.0'}
        first = asyncio.create_task(self.hass.services.async_call('update', 'install', payload, blocking=True))
        await asyncio.wait_for(started.wait(), 5)
        try:
            with self.assertRaises(Exception):
                await self.hass.services.async_call('update', 'install', payload, blocking=True)
        finally:
            finish.set()
            await first
        self.assertEqual(self.approve.await_count, 1)


if __name__ == '__main__':
    unittest.main()
