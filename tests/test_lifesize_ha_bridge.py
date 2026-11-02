import contextlib
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch


class NativeError(Exception):
    pass


class LifeSizeBridgeTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.executed = []
        owner = self

        class Phone:
            def __init__(self, *_): pass
            def connection(self): return contextlib.nullcontext()
            def snapshot(self, _): return {"registered": True, "calls": owner.calls}
            def settings(self, *_): return {}

        def require(value, reason):
            if not value:
                raise NativeError(reason)

        native = types.SimpleNamespace(
            Phone=Phone, require=require, LifeSizeError=NativeError,
            validate_config=lambda config, _: config,
            validate_action=lambda args: args.command != "status",
            device_lock=lambda _: contextlib.nullcontext(), SETTING_COMMANDS={},
            execute_action=lambda *args: self.executed.append(args[0].command),
        )
        spec = importlib.util.spec_from_file_location(
            "bridge", Path(__file__).resolve().parents[1] / "scripts/lifesize_ha_bridge.py")
        self.bridge = importlib.util.module_from_spec(spec)
        with patch.dict("sys.modules", {"cisco_lifesize": native}):
            spec.loader.exec_module(self.bridge)
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "config.json"
        self.path.write_text(json.dumps({"line": "222", "device": {"host": "example"},
                                        "allowed_destinations": ["701"], "radio_destinations": ["701"]}))
        self.addCleanup(self.temp.cleanup)

    def test_unapproved_destination_never_reaches_phone_action(self):
        with self.assertRaises(NativeError):
            self.bridge.execute(self.path, "call", 999)
        self.assertEqual(self.executed, [])

    def test_radio_stop_preserves_ordinary_calls(self):
        for number, incoming in [("201", False), ("701", True)]:
            self.calls = [{"number": number, "incoming": incoming, "state": "Connected"}]
            with self.assertRaises(NativeError):
                self.bridge.execute(self.path, "radio_stop", 0)
        self.assertEqual(self.executed, [])

    def test_radio_stop_uses_native_guarded_hangup(self):
        self.calls = [{"number": "701", "incoming": False, "state": "Connected"}]
        self.bridge.execute(self.path, "radio_stop", 0)
        self.assertEqual(self.executed, ["hangup"])

    def test_idle_stop_is_a_noop(self):
        result = self.bridge.execute(self.path, "radio_stop", 0)
        self.assertFalse(result["changed"])
        self.assertEqual(self.executed, [])


if __name__ == "__main__":
    unittest.main()
