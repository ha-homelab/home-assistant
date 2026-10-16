"""Keep example IDs compatible with Home Assistant's string identifiers."""
from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]


class DeviceBindingTypeTests(unittest.TestCase):
    def test_all_zero_zha_example_is_a_string_not_yaml_integer(self):
        rule = yaml.safe_load((ROOT / "config/023_media_start_the_plex_hub_playlist_from_the_sailor_button.yaml").read_text())[0]
        device_id = rule["triggers"][0]["device_id"]
        self.assertIsInstance(device_id, str)
        self.assertRegex(device_id, r"^[0-9a-f]{32}$")
