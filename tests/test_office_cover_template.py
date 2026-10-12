"""Render the actual office templates with HA states, without device I/O."""
from pathlib import Path
import tempfile
import unittest

try:
    import yaml
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.template import Template
except ImportError:
    HA_AVAILABLE = False
else:
    HA_AVAILABLE = True


@unittest.skipUnless(HA_AVAILABLE, "Home Assistant runtime is not installed")
class OfficeCoverTemplateTest(unittest.IsolatedAsyncioTestCase):
    async def test_connection_and_position_are_independent(self):
        with tempfile.TemporaryDirectory() as folder:
            hass = HomeAssistant(folder)
            source = Path(__file__).resolve().parents[1] / "config/covers.yaml"
            cover = next(c for c in yaml.safe_load(source.read_text()) if c['unique_id'] == 'office_curtains_r')
            available = Template(cover['availability'], hass)
            position = Template(cover['position'], hass)
            entity = 'cover.office_curtains_office_curtains'
            try:
                hass.states.async_set(entity, 'unknown', {'raw_state':'stop'})
                self.assertTrue(available.async_render())
                self.assertIsNone(position.async_render())
                for actual, expected in ((0, 100), (100, 0), (75, 25)):
                    hass.states.async_set(entity, 'open', {'raw_state':'stop', 'current_position':actual})
                    self.assertTrue(available.async_render())
                    self.assertEqual(position.async_render(), expected)
                for state, attrs in (
                    ('unavailable', {'raw_state':'stop', 'current_position':75}),
                    ('unknown', {}),
                    ('unknown', {'raw_state':'stop', 'restored':True}),
                ):
                    hass.states.async_set(entity, state, attrs)
                    self.assertFalse(available.async_render())
            finally:
                await hass.async_stop(force=True)


if __name__ == '__main__':
    unittest.main()
