"""Exercise numeric cell-extrema availability without device or network I/O."""
import copy
import os
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
    if os.environ.get("REQUIRE_HA_RUNTIME") == "1":
        raise
    HA_AVAILABLE = False
else:
    HA_AVAILABLE = True


@unittest.skipUnless(HA_AVAILABLE, "Home Assistant runtime is not installed")
class BatteryCellExtremaTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix="battery-extrema-test-")
        self.hass = HomeAssistant(self.folder.name)
        loader.async_setup(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self.hass.config.skip_pip = True
        self.assertTrue(await async_load_base_functionality(self.hass))
        names = {
            "Battery Minimum Cell Voltage", "Battery Maximum Cell Voltage",
            "Battery 2 Minimum Cell Voltage", "Battery 2 Maximum Cell Voltage",
        }
        path = Path(__file__).resolve().parents[1] / "config/template_sensors.yaml"
        self.sensors = [
            row for row in yaml.safe_load(path.read_text()) if row["name"] in names
        ]
        self.assertEqual(len(self.sensors), 4)

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.folder.cleanup()

    async def test_missing_invalid_and_partial_cells(self):
        for sensor in self.sensors:
            prefix = (
                "sensor.battery_2_cell_"
                if sensor["name"].startswith("Battery 2 ")
                else "sensor.battery_cell_"
            )
            state = Template(sensor["state"], self.hass)
            available = Template(sensor["availability"], self.hass)
            for invalid in ("unavailable", "unknown", "nan", "inf", "-inf", "invalid"):
                for cell in range(1, 17):
                    self.hass.states.async_set(f"{prefix}{cell}_voltage", invalid)
                self.assertFalse(available.async_render(), (sensor["name"], invalid))
                self.assertIsNone(state.async_render(), (sensor["name"], invalid))
            for cell, value in ((1, "3.12"), (8, "3.27"), (16, "3.04")):
                self.hass.states.async_set(f"{prefix}{cell}_voltage", value)
            self.assertTrue(available.async_render(), sensor["name"])
            expected = 3.04 if "Minimum" in sensor["name"] else 3.27
            self.assertEqual(state.async_render(), expected, sensor["name"])
            for cell in range(1, 17):
                self.hass.states.async_remove(f"{prefix}{cell}_voltage")
            self.assertFalse(available.async_render(), sensor["name"])
            self.assertIsNone(state.async_render(), sensor["name"])

    async def test_real_sensor_becomes_unavailable_and_recovers(self):
        sensor = copy.deepcopy(next(
            row for row in self.sensors if row["name"] == "Battery 2 Minimum Cell Voltage"
        ))
        await self.hass.async_start()
        self.assertTrue(await async_setup_component(
            self.hass, "template", {"template": [{"sensor": [sensor]}]}
        ))
        await self.hass.async_block_till_done()
        entity = "sensor.battery_2_minimum_cell_voltage"
        self.assertEqual(self.hass.states.get(entity).state, "unavailable")
        self.hass.states.async_set("sensor.battery_2_cell_3_voltage", "3.2")
        await self.hass.async_block_till_done()
        self.assertEqual(float(self.hass.states.get(entity).state), 3.2)
        self.hass.states.async_set("sensor.battery_2_cell_3_voltage", "unavailable")
        await self.hass.async_block_till_done()
        self.assertEqual(self.hass.states.get(entity).state, "unavailable")


if __name__ == "__main__":
    unittest.main()
