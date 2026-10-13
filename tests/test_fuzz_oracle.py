"""Replay only synthetic corpus bytes through the real bounded oracle."""

import importlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
oracle = importlib.import_module("fuzz.oracles").notification_frames


class FuzzOracleTest(unittest.TestCase):
    def test_synthetic_corpus(self):
        for seed in sorted((ROOT / "fuzz/corpus/notification-frames").iterdir()):
            with self.subTest(seed=seed.name):
                oracle(seed.read_bytes())

    def test_empty_malformed_and_bounded_noise(self):
        for data in (b"", b"{", b"null", b"[]", bytes(range(256)) * 16):
            oracle(data)
