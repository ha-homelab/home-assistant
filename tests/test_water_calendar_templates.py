"""Exercise deployed numeric/date templates without device or network I/O."""
import asyncio
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

try:
    import yaml
    from homeassistant import loader
    from homeassistant.bootstrap import async_load_base_functionality
    from homeassistant.config_entries import ConfigEntries
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.template import Template
    from homeassistant.setup import async_setup_component
except ImportError:
    HA_AVAILABLE = False
else:
    HA_AVAILABLE = True


@unittest.skipUnless(HA_AVAILABLE, 'Home Assistant runtime is not installed')
class WaterCalendarTemplateTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='water-calendar-')
        self.hass = HomeAssistant(self.temp.name)
        source = Path(__file__).resolve().parents[1] / 'config/template_sensors.yaml'
        self.configs = {c['name']: c for c in yaml.safe_load(source.read_text())}

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.temp.cleanup()

    async def test_sweeping_matches_second_and_fourth_fridays_across_five_years(self):
        template = Template(self.configs['Street Sweeping 2']['state'], self.hass)
        today = date(2024, 1, 1)
        while today < date(2029, 1, 1):
            expected = today
            while not (expected.weekday() == 4 and
                       (8 <= expected.day <= 14 or 22 <= expected.day <= 28)):
                expected += timedelta(days=1)
            fixed = datetime.combine(today, time(12), timezone.utc)
            actual = template.async_render({'now': lambda: fixed})
            self.assertEqual(actual, (expected - today).days, today.isoformat())
            today += timedelta(days=1)

    async def test_water_sources_unavailable_then_recover_without_fake_zero(self):
        cases = [
            ('water_gal', 'sensor.778_40th_ave_sf_today_s_water_usage', 37.8541, 10.0),
            ('Water cost', 'sensor.778_40th_ave_sf_today_s_water_usage', 37.8541, 0.35),
            ('Water Pressure PSI', 'sensor.778_40th_ave_sf_water_pressure', 100, 14.5),
            ('water_cm', 'sensor.water_level_2_water_level', 28, 28),
            ('water_in_the_tank', 'sensor.water_cm', 28, 39.73),
            ('Water Fill Speed', 'sensor.water_speed', 1.25, 1.25),
        ]
        for name, source, reading, expected in cases:
            with self.subTest(name=name):
                cfg = self.configs[name]
                available = Template(cfg['availability'], self.hass)
                state = Template(cfg['state'], self.hass)
                # Missing entities, transitions through unavailable, and corrupt
                # source data must not become valid zero-valued measurements.
                self.hass.states.async_remove(source)
                self.assertFalse(available.async_render())
                for invalid in ['unknown', 'unavailable', '', 'invalid', 'nan', 'inf']:
                    self.hass.states.async_set(source, invalid)
                    self.assertFalse(available.async_render(), invalid)
                self.hass.states.async_set(source, str(reading))
                self.assertTrue(available.async_render())
                self.assertAlmostEqual(state.async_render(), expected, places=2)
                self.hass.states.async_set(source, '0')
                self.assertTrue(available.async_render())

    async def test_real_template_entities_propagate_source_availability(self):
        loader.async_setup(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self.hass.config.skip_pip = True
        self.assertTrue(await async_load_base_functionality(self.hass))
        names = ['water_cm', 'water_in_the_tank', 'water_gal', 'Water cost',
                 'Water Pressure PSI', 'Water Fill Speed']
        config = {'template': [{'sensor': [self.configs[n] for n in names]}]}
        self.assertTrue(await async_setup_component(self.hass, 'template', config))
        await self.hass.async_start()
        await self.hass.async_block_till_done()
        derived = self.hass.states.async_all('sensor')
        self.assertEqual(len(derived), 6)
        self.assertTrue(all(s.state == 'unavailable' for s in derived))

        async def settle():
            await asyncio.sleep(0.05)
            await self.hass.async_block_till_done()

        for source, value in {
            'sensor.water_level_2_water_level': '28',
            'sensor.778_40th_ave_sf_today_s_water_usage': '37.8541',
            'sensor.778_40th_ave_sf_water_pressure': '100',
            'sensor.water_speed': '1.25',
        }.items():
            self.hass.states.async_set(source, value)
        await settle()
        self.assertEqual(self.hass.states.get('sensor.water_in_the_tank').state, '39.73')
        self.assertTrue(all(self.hass.states.get(s.entity_id).state not in
                            ['unknown', 'unavailable'] for s in derived))
        speed = self.hass.states.get('sensor.water_fill_speed')
        self.assertEqual(speed.attributes['unit_of_measurement'], 'cm/h')
        self.assertEqual(speed.state, '1.25')
        # The existing derivative measures both filling and draining; this
        # display reports filling only, preserving zero for a real negative rate.
        for reading, expected in [('6.00', '6.0'), ('-6.00', '0'), ('0', '0'),
                                  ('3.456', '3.46'), ('unknown', 'unavailable'),
                                  ('unavailable', 'unavailable'), ('nan', 'unavailable'),
                                  ('inf', 'unavailable'), ('2.5', '2.5')]:
            with self.subTest(fill_rate=reading):
                self.hass.states.async_set('sensor.water_speed', reading)
                await settle()
                speed = self.hass.states.get('sensor.water_fill_speed')
                self.assertEqual(speed.state, expected)
                self.assertEqual(speed.attributes['unit_of_measurement'], 'cm/h')
        for value in ['unknown', 'unavailable', 'NaN', 'inf', 'invalid']:
            self.hass.states.async_set('sensor.water_level_2_water_level', value)
            await settle()
            self.assertEqual(self.hass.states.get('sensor.water_cm').state, 'unavailable')
            self.assertEqual(self.hass.states.get('sensor.water_in_the_tank').state, 'unavailable')
        for source, expected in [('25.9', '25'), ('101', '100')]:
            self.hass.states.async_set('sensor.water_level_2_water_level', source)
            await settle()
            self.assertEqual(self.hass.states.get('sensor.water_cm').state, expected)


    async def test_battery_yesterday_handles_startup_missing_attributes_and_recovery(self):
        loader.async_setup(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self.hass.config.skip_pip = True
        self.assertTrue(await async_load_base_functionality(self.hass))
        sensors = [self.configs['Battery in yesterday'], self.configs['Battery out yesterday']]
        with self.assertNoLogs('homeassistant', level='ERROR'):
            self.assertTrue(await async_setup_component(
                self.hass, 'template', {'template': [{'sensor': sensors}]}))
            await self.hass.async_start()
            await self.hass.async_block_till_done()
            for direction, valid in [('in', '3.317'), ('out', '6.595')]:
                source = f'sensor.today_battery_{direction}'
                entity = f'sensor.battery_{direction}_yesterday'
                self.assertEqual(self.hass.states.get(entity).state, 'unavailable')
                for current, attributes, expected in [
                    ('unknown', {}, 'unavailable'),
                    ('unavailable', {}, 'unavailable'),
                    ('10', {}, 'unavailable'),
                    ('10', {'last_period': None}, 'unavailable'),
                    ('10', {'last_period': 'unknown'}, 'unavailable'),
                    ('10', {'last_period': 'nan'}, 'unavailable'),
                    ('10', {'last_period': 'inf'}, 'unavailable'),
                    ('10', {'last_period': '0'}, '0.0'),
                    ('10', {'last_period': valid}, valid),
                    # A retained yesterday value remains known even when the
                    # current-period meter temporarily becomes unavailable.
                    ('unavailable', {'last_period': valid}, valid),
                    ('unknown', {}, 'unavailable'),
                    ('10', {'last_period': valid}, valid),
                ]:
                    with self.subTest(direction=direction, current=current, attributes=attributes):
                        self.hass.states.async_set(source, current, attributes)
                        await asyncio.sleep(0.02)
                        await self.hass.async_block_till_done()
                        self.assertEqual(self.hass.states.get(entity).state, expected)

    async def test_solar_age_handles_startup_no_match_zero_and_recovery(self):
        loader.async_setup(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self.hass.config.skip_pip = True
        self.assertTrue(await async_load_base_functionality(self.hass))
        with self.assertNoLogs('homeassistant', level='ERROR'):
            self.assertTrue(await async_setup_component(self.hass, 'template', {
                'template': [{'sensor': [self.configs['Solar Age']]}]}))
            await self.hass.async_start()
            await self.hass.async_block_till_done()
            self.assertEqual(self.hass.states.get('sensor.solar_age').state, 'unknown')
            for raw, expected in [
                ('unknown', 'unknown'), ('unavailable', 'unknown'),
                ('', 'unknown'), ('not a duration', 'unknown'), ('-1', 'unknown'),
                ('0', '0 days'), ('1', '1 day'), ('2', '2 days'),
                ('30', '1 month'), ('31', '1 month and 1 day'),
                ('365', '1 year'), ('366', '1 year and 1 day'),
                ('395', '1 year and 1 month'),
                ('1196', '3 years, 3 months and 11 days'),
                ('  1196 days', '3 years, 3 months and 11 days'),
                ('1196.9', '3 years, 3 months and 11 days'),
                ('unavailable', 'unknown'), ('0', '0 days'),
            ]:
                with self.subTest(raw=raw):
                    self.hass.states.async_set('sensor.solar_days', raw)
                    await asyncio.sleep(0.02)
                    await self.hass.async_block_till_done()
                    self.assertEqual(self.hass.states.get('sensor.solar_age').state, expected)


if __name__ == '__main__':
    unittest.main()
