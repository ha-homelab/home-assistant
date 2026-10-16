"""Detect rotated cell subscriptions using distinct values for every wire index."""
from pathlib import Path
import unittest

import yaml


CONFIG = Path(__file__).resolve().parents[1] / "config/mqtt.yaml"
PREFIX = "victron/N/000000000000/battery"


class BatteryCellNumberingTest(unittest.TestCase):
    def test_displayed_cells_follow_physical_order_in_both_chains(self):
        sensors = {sensor.get("name"): sensor for sensor in yaml.safe_load(CONFIG.read_text())["sensor"]}
        # Distinct values expose both an index rotation and an accidental cross-chain subscription.
        wire = {
            f"{PREFIX}/{instance}/Cell/{index}/Voltage": 3000 + chain * 100 + index
            for chain, instance in enumerate((512, 513))
            for index in range(16)
        }
        for chain, label in enumerate(("Battery", "Battery 2")):
            with self.subTest(chain=label):
                configured = [sensors[f"{label} Cell {number} Voltage"]["state_topic"] for number in range(1, 17)]
                self.assertEqual(len(set(configured)), 16)
                self.assertEqual(
                    [wire[topic] for topic in configured],
                    list(range(3000 + chain * 100, 3016 + chain * 100)),
                    "Human cells 1–16 must read Cerbo indices 0–15 in order",
                )


if __name__ == "__main__":
    unittest.main()
