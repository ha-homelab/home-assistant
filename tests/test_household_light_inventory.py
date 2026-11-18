"""Keep current room lighting controls in the explicit household shutdown."""
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'dependencies/scripts/config/lighting/household_lights_and_media_off.yaml'


class HouseholdLightInventoryTest(unittest.TestCase):
    def test_current_dining_controls_are_in_household_shutdown(self):
        script = yaml.safe_load(SOURCE.read_text())['turn_off_living_room']
        targets = {
            entity
            for action in script['sequence']
            if action.get('service') in {'homeassistant.turn_off', 'light.turn_off', 'switch.turn_off'}
            for entity in action['entity_id']
        }
        # These are three independent active Dining controls, rather than the
        # unavailable legacy Dining wall relay retained for compatibility.
        current_dining_controls = {
            'switch.dining_wall_light_2',
            'switch.dining_arc_lamp',
            'light.adining_lamp_m',
        }
        self.assertFalse(current_dining_controls - targets,
                         f'Missing Dining controls: {sorted(current_dining_controls - targets)}')
        self.assertLessEqual({'light.bedroom_lamp', 'switch.living_lamp'}, targets)
        self.assertFalse({'switch.pump_power_enable', 'switch.moen_flo_water_monitor_power',
                          'switch.laundry'} & targets)


if __name__ == '__main__':
    unittest.main()
