"""Regression tests against actual installed HACS source, without HA/devices.

LOCAL_TUYA_COVER_SOURCE must point to the downloaded, unmodified cover.py.
LOCAL_TUYA_COVER_CANDIDATE optionally selects a reviewed port to test directly.
The AST extracts its real class; only HA transport/entity dependencies are stubbed.
"""

import ast
import asyncio
import os
from pathlib import Path
from types import SimpleNamespace
import unittest

from tools.patch_localtuya_cover import patch


class EntityStub:
    def __init__(self, device, config, *args, **kwargs):
        self._device = device
        self._config = config
        self._dp_id = "1"
        self._status = {}
        self.writes = 0

    def has_config(self, key):
        return key in self._config

    def dp_value(self, key):
        return self._status.get(self._config.get(key, key))

    def debug(self, *args):
        pass

    def schedule_update_ha_state(self):
        self.writes += 1


@unittest.skipUnless(os.getenv("LOCAL_TUYA_COVER_SOURCE"), "Requires actual LocalTuya source")
class LocalTuyaCoverPatchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path(os.environ["LOCAL_TUYA_COVER_SOURCE"]).read_text()
        cls.candidate = os.getenv("LOCAL_TUYA_COVER_CANDIDATE")
        source = Path(cls.candidate).read_text() if cls.candidate else patch(cls.source)
        tree = ast.parse(source)
        cover = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "LocalTuyaCover")
        constants = {n.id for n in ast.walk(cover) if isinstance(n, ast.Name) and n.id.isupper()}
        ns = {key: key for key in constants}
        ns.update(LocalTuyaEntity=EntityStub, CoverEntity=type("CoverEntity", (), {}),
                  asyncio=asyncio, time=__import__("time"), DEF_CMD_SET="open_close_stop")
        exec(compile(ast.Module(body=[cover], type_ignores=[]), "localtuya/cover.py", "exec"), ns)
        cls.cover_class = ns["LocalTuyaCover"]

    def setUp(self):
        self.sent = []

        async def set_dp(value, dp):
            self.sent.append((dp, value))

        self.cover = self.cover_class(
            SimpleNamespace(is_connecting=False, set_dp=set_dp),
            {"CONF_POSITIONING_MODE": "MODE_SET_POSITION", "CONF_CURRENT_POSITION_DP": "3",
             "CONF_SET_POSITION_DP": "2", "CONF_POSITION_INVERTED": True}, "1")

    def update(self, status):
        self.cover._status = status
        self.cover.status_updated()

    def test_first_packet_without_position_remains_unknown(self):
        self.update({"1": "open"})
        self.assertIsNone(self.cover.current_cover_position)
        self.assertIsNone(self.cover.is_closed)
        self.assertFalse(self.cover.is_opening)
        self.assertEqual(self.cover._last_state, "open")

    def test_partial_packet_retains_observed_position(self):
        self.update({"1": "stop", "3": 30})
        self.assertEqual(self.cover.current_cover_position, 70)
        self.update({"1": "open"})
        self.assertEqual(self.cover.current_cover_position, 70)

    def test_invalid_numeric_position_does_not_replace_observation(self):
        self.update({"1": "stop", "3": 30})
        for value in (-1, 101, float("nan"), float("inf"), None):
            self.update({"1": "stop", "3": value})
            self.assertEqual(self.cover.current_cover_position, 70)

    def test_absolute_target_with_unknown_position_does_not_invent_progress(self):
        self.update({"1": "open"})
        asyncio.run(self.cover.async_set_cover_position(ATTR_POSITION=35))
        self.assertEqual(self.sent, [("2", 65)])
        self.assertIsNone(self.cover.current_cover_position)
        self.assertFalse(self.cover.is_opening)
        self.assertFalse(self.cover.is_closing)
        self.assertEqual(self.cover.writes, 1)

    def test_endpoints_and_non_inverted_device(self):
        self.update({"1": "stop", "3": 100})
        self.assertEqual(self.cover.current_cover_position, 0)
        self.assertTrue(self.cover.is_closed)
        self.cover._position_inverted = False
        self.update({"1": "stop", "3": 100})
        self.assertEqual(self.cover.current_cover_position, 100)
        self.assertFalse(self.cover.is_closed)

    def test_patch_idempotent_and_rejects_unexpected_source(self):
        if self.candidate:
            self.skipTest("A future-version candidate is tested independently of the old generator")
        patched = patch(self.source)
        self.assertEqual(patch(patched), patched)
        with self.assertRaises(ValueError):
            patch("# Different upstream source\n")


if __name__ == "__main__":
    unittest.main()
