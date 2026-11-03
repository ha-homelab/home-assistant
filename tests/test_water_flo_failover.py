"""Execute water fallback in isolated HA; all relay and cloud calls are mocked."""
import asyncio
from copy import deepcopy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    import yaml
    from homeassistant import loader
    from homeassistant.bootstrap import async_load_base_functionality
    from homeassistant.config import merge_packages_config
    from homeassistant.config_entries import ConfigEntry, ConfigEntries
    from homeassistant.core import callback
    from homeassistant.helpers import device_registry as dr, entity_registry as er
    from homeassistant.helpers import script as script_helper
    from homeassistant.helpers.template import Template
    from homeassistant.setup import async_setup_component
except ImportError:
    if os.environ.get('REQUIRE_HA_RUNTIME') == '1':
        raise
    HA_AVAILABLE = False
else:
    HA_AVAILABLE = True

ROOT = Path(os.environ.get('WATER_TEST_ROOT', Path(__file__).resolve().parents[1]))
PUMP = 'switch.pump_power_enable'
VALVE = 'switch.shutoff_valve'
ALERTS = 'binary_sensor.synthetic_flo_alerts'
SCRIPT = 'script.water_flo_failover'


@unittest.skipUnless(HA_AVAILABLE, 'Requires the Home Assistant runtime')
class WaterFloFailoverTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from homeassistant.core import HomeAssistant
        self.temp = tempfile.TemporaryDirectory(prefix='water-fallback-test-')
        self.hass = HomeAssistant(self.temp.name)
        loader.async_setup(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self.hass.config.skip_pip = True
        self.assertTrue(await async_load_base_functionality(self.hass))
        entry = ConfigEntry(domain='flo', title='Synthetic Flo', data={}, options={},
                            source='user', unique_id='water-test', version=1, minor_version=1,
                            discovery_keys={}, subentries_data=None)
        self.hass.config_entries._entries[entry.entry_id] = entry
        device = dr.async_get(self.hass).async_get_or_create(
            config_entry_id=entry.entry_id, identifiers={('flo', 'water-test')})
        for entity in (VALVE, ALERTS):
            domain, obj = entity.split('.', 1)
            er.async_get(self.hass).async_get_or_create(
                domain, 'flo', obj, suggested_object_id=obj,
                config_entry=entry, device_id=device.id)
        self.calls, self.notifications, self.waits = [], [], []
        self.auto_pump_ack = True
        self.elapsed = 0
        self.progress = asyncio.Event()
        self.set(PUMP, 'on')
        self.set(VALVE, 'off')
        self.set(ALERTS, 'off')
        self.set('sensor.water_cm', 'unavailable')
        self.set('sensor.water_pressure_psi', '43.8')
        self.set('sensor.kmc_water_and_laundry_power', '100')
        for action in ('turn_off', 'turn_on'):
            self.hass.services.async_register('switch', action, self.switch)
        self.hass.services.async_register('persistent_notification', 'create', self.notify)
        call_later = self.hass.loop.call_later

        def schedule(seconds, callback, *args, context=None):
            if callback is script_helper._set_result_unless_done:
                from test_water_valve_recovery import ScriptWaitTimer
                timer = ScriptWaitTimer(self, seconds, callback, args)
                self.waits.append(timer)
                self.progress.set()
                return timer
            return call_later(seconds, callback, *args, context=context)

        timer_patch = patch.object(self.hass.loop, 'call_later', schedule)
        timer_patch.start()
        self.addCleanup(timer_patch.stop)
        self.package = yaml.safe_load((ROOT / 'config/packages/water_flo_failover.yaml').read_text())
        original = yaml.safe_load((ROOT / 'config/packages/water_valve_recovery.yaml').read_text())
        merged = await merge_packages_config(self.hass, {}, {
            'water_valve_recovery': original, 'water_flo_failover': self.package})
        self.assertTrue(await async_setup_component(self.hass, 'script', merged))
        await self.hass.async_start()

        @callback
        def state_changed(event):
            if event.data['entity_id'] == SCRIPT and event.data.get('new_state'):
                if event.data['new_state'].state == 'off':
                    self.progress.set()
        self.addCleanup(self.hass.bus.async_listen('state_changed', state_changed))

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.temp.cleanup()

    def set(self, entity, state, attributes=None):
        self.hass.states.async_set(entity, state, attributes or {})

    async def switch(self, call):
        entities = call.data['entity_id']
        for entity in [entities] if isinstance(entities, str) else entities:
            self.calls.append((entity, call.service))
            if entity != PUMP or self.auto_pump_ack:
                self.set(entity, call.service.removeprefix('turn_'))

    async def notify(self, call):
        self.notifications.append(dict(call.data))

    async def settle(self):
        await self.hass.async_block_till_done()

    async def request(self):
        self.progress.clear()
        await self.hass.services.async_call('script', 'turn_on', {
            'entity_id': SCRIPT, 'variables': {'reason': 'Synthetic low pressure'}}, blocking=True)
        await asyncio.wait_for(self.progress.wait(), 5)

    async def advance(self, seconds):
        target = self.elapsed + seconds
        while due := sorted((t for t in self.waits if not t.cancelled and t.deadline <= target),
                            key=lambda t: t.deadline):
            timer = due[0]
            self.elapsed = timer.deadline
            timer.cancel()
            timer.callback(*timer.args)
            await self.settle()
        self.elapsed = target

    async def test_missing_tank_level_does_not_block_ordered_fallback(self):
        await self.request()
        self.assertEqual(self.calls, [(PUMP, 'turn_off'), (VALVE, 'turn_on')])
        self.assertEqual(self.hass.states.get(SCRIPT).state, 'off')

    async def test_warning_is_allowed_but_critical_alert_cannot_open_valve(self):
        self.set(ALERTS, 'on', {'warning': 1, 'critical': 0})
        await self.request()
        self.assertEqual(self.calls[-1], (VALVE, 'turn_on'))
        self.calls.clear()
        self.set(PUMP, 'on')
        self.set(VALVE, 'off')
        self.set(ALERTS, 'on', {'warning': 1, 'critical': 1})
        await self.request()
        self.assertEqual(self.calls, [(PUMP, 'turn_off')])

    async def test_pump_acknowledgement_is_required(self):
        self.auto_pump_ack = False
        await self.request()
        await self.advance(15)
        self.assertEqual(self.calls, [(PUMP, 'turn_off')])
        self.assertEqual(self.hass.states.get(SCRIPT).state, 'off')
        self.assertIn('not confirmed', self.notifications[-1]['message'])

    async def test_valve_recovery_opens_once_and_preserves_later_manual_closure(self):
        self.set(VALVE, 'unavailable')
        await self.request()
        await self.advance(240)
        self.set(VALVE, 'off')
        await self.settle()
        self.assertEqual(self.calls, [(PUMP, 'turn_off'), (VALVE, 'turn_on')])
        self.set(VALVE, 'off')
        await self.advance(600)
        self.assertEqual(len(self.calls), 2)

    async def test_expired_valve_request_is_not_replayed(self):
        self.set(VALVE, 'unavailable')
        await self.request()
        await self.advance(300)
        self.set(VALVE, 'off')
        await self.settle()
        self.assertEqual(self.calls, [(PUMP, 'turn_off')])

    async def test_unknown_alert_status_does_not_open(self):
        self.set(ALERTS, 'unavailable')
        await self.request()
        await self.advance(300)
        self.assertEqual(self.calls, [(PUMP, 'turn_off')])

    async def test_new_critical_alert_aborts_offline_valve_wait(self):
        self.set(VALVE, 'unavailable')
        await self.request()
        self.set(ALERTS, 'on', {'critical': 1})
        await self.settle()
        self.set(VALVE, 'off')
        await self.settle()
        self.assertEqual(self.calls, [(PUMP, 'turn_off')])

    async def test_manual_pump_restart_cancels_pending_open(self):
        self.set(VALVE, 'unavailable')
        await self.request()
        self.set(PUMP, 'on')
        await self.settle()
        self.set(VALVE, 'off')
        await self.settle()
        self.assertEqual(self.calls, [(PUMP, 'turn_off')])

    async def test_low_pressure_boundary_and_invalid_readings(self):
        trigger = self.package['automation'][0]['triggers'][0]
        self.assertEqual(trigger['for'], '00:00:30')
        for value, expected in [('0', True), ('8.3', True), ('19.99', True),
                                ('20', False), ('43.8', False), ('-1', False),
                                ('unknown', False), ('unavailable', False), ('nan', False)]:
            self.set('sensor.water_pressure_psi', value)
            self.assertEqual(Template(trigger['value_template'], self.hass).async_render(), expected, value)

    async def test_power_watch_starts_when_pump_enables_under_existing_load(self):
        config = yaml.safe_load(next((ROOT / 'dependencies/automations/config').glob('102_*.yaml')).read_text())[0]
        self.assertEqual(config['triggers'][0]['for'], {'minutes': 2})
        config = deepcopy(config)
        config['triggers'][0]['for'] = {'milliseconds': 30}
        config['actions'] = config['actions'][:1]
        self.set(PUMP, 'off')
        self.set('sensor.kmc_water_and_laundry_power', '701')
        self.assertTrue(await async_setup_component(self.hass, 'automation', {'automation': [config]}))
        await self.settle()
        await asyncio.sleep(.06)
        self.assertEqual(self.calls, [])
        self.set(PUMP, 'on')
        await asyncio.sleep(.08)
        await self.settle()
        self.assertEqual(self.calls, [(PUMP, 'turn_off'), (VALVE, 'turn_on')])

    async def test_low_pressure_dispatches_without_waiting_for_email_or_level(self):
        config = deepcopy(self.package['automation'][0])
        config['triggers'][0]['for'] = {'milliseconds': 30}
        self.assertTrue(await async_setup_component(self.hass, 'automation', {'automation': [config]}))
        self.set('sensor.water_pressure_psi', '8.3')
        await asyncio.sleep(.08)
        await self.settle()
        self.assertEqual(self.calls, [(PUMP, 'turn_off'), (VALVE, 'turn_on')])

    async def test_short_power_spike_does_not_switch_supply(self):
        config = yaml.safe_load(next((ROOT / 'dependencies/automations/config').glob('102_*.yaml')).read_text())[0]
        config['triggers'][0]['for'] = {'milliseconds': 100}
        config['actions'] = config['actions'][:1]
        self.assertTrue(await async_setup_component(self.hass, 'automation', {'automation': [config]}))
        self.set('sensor.kmc_water_and_laundry_power', '701')
        await asyncio.sleep(.02)
        self.set('sensor.kmc_water_and_laundry_power', '700')
        await asyncio.sleep(.15)
        await self.settle()
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
