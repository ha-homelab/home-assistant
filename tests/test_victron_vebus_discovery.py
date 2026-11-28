"""Follow the announced VE.Bus instance and keep the reviewed MQTT identities."""
import json
import os
from pathlib import Path
import tempfile
import unittest

import yaml

try:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.template import Template
except ImportError:
    if os.environ.get('REQUIRE_HA_RUNTIME') == '1':
        raise
    HA_AVAILABLE = False
else:
    HA_AVAILABLE = True

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'config/packages/victron_vebus_discovery.yaml'
DISCOVERY_ID = 'victron_vebus_instance_discovery'
GRID_READ_ID = 'victron_refresh_vebus_grid_input'
HELPER = 'input_text.victron_vebus_grid_topic'
SWITCH_CONFIG = 'homeassistant/switch/victron_quattro/config'
GRID_CONFIG = 'homeassistant/binary_sensor/victron_grid_connected/config'
NUMBER_CONFIG = 'homeassistant/number/multiplus_ac_current_limit/config'


def load_rule(rule_id):
    package = yaml.safe_load(PACKAGE.read_text())
    return next(rule for rule in package['automation'] if rule['id'] == rule_id)


class DiscoveryStructureTest(unittest.TestCase):
    def test_no_device_instance_or_entity_is_pinned_in_the_static_configuration(self):
        mqtt = json.dumps(yaml.safe_load((ROOT / 'config/mqtt.yaml').read_text()))
        for pinned in ('vebus/289', 'victron_quattro', 'victron_grid_connected',
                       'multiplus_ac_current_limit'):
            self.assertNotIn(pinned, mqtt)

    def test_discovery_configurations_are_retained_and_never_write_to_the_device(self):
        rule = load_rule(DISCOVERY_ID)
        publishes = [step['data'] for step in rule['actions']
                     if step.get('service') == 'mqtt.publish']
        self.assertEqual([publish['topic'] for publish in publishes],
                         [SWITCH_CONFIG, GRID_CONFIG, NUMBER_CONFIG])
        self.assertTrue(all(publish['retain'] is True for publish in publishes))
        self.assertNotIn('/W/', json.dumps([publish['topic'] for publish in publishes]))

    def test_grid_read_is_a_five_second_read_of_the_announced_topic(self):
        rule = load_rule(GRID_READ_ID)
        self.assertEqual(rule['triggers'], [{'platform': 'time_pattern', 'seconds': '/5'}])
        publish = next(step['data'] for step in rule['actions']
                       if step.get('service') == 'mqtt.publish')
        self.assertIn(HELPER, publish['topic'])
        self.assertEqual(json.loads(publish['payload']), {})


@unittest.skipUnless(HA_AVAILABLE, 'Home Assistant runtime is not installed')
class DiscoveryTemplateTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.hass = HomeAssistant(self.temp.name)

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.temp.cleanup()

    def variables(self, trigger, stored=''):
        """Render the automation variables in their real order."""
        self.hass.states.async_set(HELPER, stored)
        values = {}
        for step in load_rule(DISCOVERY_ID)['actions']:
            for name, value in (step.get('variables') or {}).items():
                values[name] = Template(value, self.hass).async_render(
                    {'trigger': trigger, **values})
        return values

    def payloads(self, values):
        rendered = {}
        for step in load_rule(DISCOVERY_ID)['actions']:
            data = step.get('data') or {}
            if step.get('service') == 'mqtt.publish':
                rendered[data['topic']] = json.loads(
                    Template(data['payload'], self.hass).async_render(
                        values, parse_result=False))
        return rendered

    def render(self, template, value_json):
        return Template(template, self.hass).async_render({'value_json': value_json})

    async def test_announced_instance_binds_every_entity(self):
        values = self.variables({'id': 'vebus_mode',
                                 'topic': 'victron/N/b827ebea1ece/vebus/301/Mode'})
        self.assertEqual(values['portal'], 'b827ebea1ece')
        # Home Assistant renders a numeric template result as an int; the
        # automation only interpolates it into the topic strings.
        self.assertEqual(str(values['instance']), '301')

        payloads = self.payloads(values)
        switch = payloads[SWITCH_CONFIG]
        self.assertEqual(switch['state_topic'], 'victron/N/b827ebea1ece/vebus/301/Mode')
        self.assertEqual(switch['command_topic'], 'victron/W/b827ebea1ece/vebus/301/Mode')

        number = payloads[NUMBER_CONFIG]
        self.assertEqual(number['command_topic'],
                         'victron/W/b827ebea1ece/vebus/301/Ac/ActiveIn/CurrentLimit')
        self.assertEqual(number['state_topic'],
                         'victron/N/b827ebea1ece/vebus/301/Ac/ActiveIn/CurrentLimit')

        grid = payloads[GRID_CONFIG]
        self.assertEqual(grid['state_topic'],
                         'victron/N/b827ebea1ece/vebus/301/Ac/ActiveIn/Connected')

    async def test_payloads_keep_the_reviewed_registry_identities(self):
        payloads = self.payloads(self.variables(
            {'id': 'vebus_mode', 'topic': 'victron/N/b827ebea1ece/vebus/289/Mode'}))
        self.assertEqual(
            {topic: (payload['unique_id'], payload['default_entity_id'])
             for topic, payload in payloads.items()},
            {SWITCH_CONFIG: ('victron_quattro', 'switch.victron_quattro'),
             GRID_CONFIG: ('victron_grid_connected', 'binary_sensor.victron_grid_connected'),
             NUMBER_CONFIG: ('multiplus_ac_current_limit', 'number.cerbo_gx_netz_max_strom')})

    async def test_switch_payloads_match_the_venus_mode_contract(self):
        switch = self.payloads(self.variables(
            {'id': 'vebus_mode', 'topic': 'victron/N/p/vebus/289/Mode'}))[SWITCH_CONFIG]
        self.assertEqual(switch['payload_on'], '{"value":3}')
        self.assertEqual(switch['payload_off'], '{"value":4}')

    async def test_current_limit_accepts_the_installed_sixty_ampere_value(self):
        number = self.payloads(self.variables(
            {'id': 'vebus_mode', 'topic': 'victron/N/p/vebus/289/Mode'}))[NUMBER_CONFIG]
        self.assertEqual((number['min'], number['max'], number['step']), (0, 100, 1))
        self.assertEqual(json.loads(Template(number['command_template'], self.hass)
                                    .async_render({'value': 60}, parse_result=False)),
                         {'value': 60})

    async def test_grid_templates_keep_the_reviewed_measurement_contract(self):
        grid = self.payloads(self.variables(
            {'id': 'vebus_mode', 'topic': 'victron/N/p/vebus/289/Mode'}))[GRID_CONFIG]
        self.assertEqual(grid['expire_after'], 90)
        availability = grid['availability'][0]['value_template']
        for value, state in ((0, 'OFF'), (1, 'ON')):
            self.assertEqual(self.render(grid['value_template'], {'value': value}).strip(), state)
            self.assertEqual(self.render(availability, {'value': value}).strip(), 'online')
        for value in (None, True, False, 'NaN', 2, -1, {}, []):
            self.assertEqual(self.render(availability, {'value': value}).strip(), 'offline')

    async def test_restart_reuses_the_last_announced_topic_without_traffic(self):
        values = self.variables(
            {'id': 'start'},
            stored='victron/R/000000000000/vebus/305/Ac/ActiveIn/Connected')
        self.assertEqual((values['portal'], str(values['instance'])),
                         ('000000000000', '305'))
        grid = self.payloads(values)[GRID_CONFIG]
        self.assertEqual(grid['state_topic'],
                         'victron/N/000000000000/vebus/305/Ac/ActiveIn/Connected')

    async def test_unknown_topics_publish_nothing(self):
        for trigger, stored in (
            ({'id': 'vebus_mode', 'topic': 'victron/N/p/system/0/Serial'}, ''),
            ({'id': 'start'}, ''),
            ({'id': 'start'}, 'unknown'),
            ({'id': 'vebus_mode', 'topic': 'victron/N/p/vebus/not-a-number/Mode'}, ''),
        ):
            with self.subTest(trigger=trigger, stored=stored):
                values = self.variables(trigger, stored)
                self.assertEqual(values['instance'], '')
                condition = next(step['value_template']
                                 for step in load_rule(DISCOVERY_ID)['actions']
                                 if 'value_template' in step)
                self.assertFalse(Template(condition, self.hass).async_render(values))


if __name__ == '__main__':
    unittest.main()
