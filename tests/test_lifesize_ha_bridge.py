import contextlib
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch


class NativeError(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class LifeSizeBridgeTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.executed = []
        self.connections = 0
        owner = self

        class Phone:
            def __init__(self, *_): pass
            def connection(self):
                owner.connections += 1
                return contextlib.nullcontext()
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

    def add_second_station(self):
        config = json.loads(self.path.read_text())
        config["allowed_destinations"].extend(["711", "201"])
        config["radio_destinations"].append("711")
        self.path.write_text(json.dumps(config))

    def test_radio_play_does_not_interrupt_a_normal_call(self):
        self.calls = [{"id": "1", "number": "201", "incoming": False, "state": "Connected"}]
        with self.assertRaises(NativeError):
            self.bridge.execute(self.path, "radio_play", 701)
        self.assertEqual(self.executed, [])

    def test_playing_the_same_station_is_a_noop(self):
        self.calls = [{"id": "1", "number": "701", "incoming": False, "state": "Connected"}]
        result = self.bridge.execute(self.path, "radio_play", 701)
        self.assertFalse(result["changed"])
        self.assertEqual(self.executed, [])

    def test_switch_station_hangs_up_only_the_old_radio_then_dials(self):
        self.add_second_station()
        self.calls = [{"id": "1", "number": "701", "incoming": False, "state": "Connected"}]
        def execute(args, *_):
            self.executed.append(args.command)
            if args.command == "hangup":
                self.calls = []
        with patch.object(self.bridge.native, "execute_action", execute):
            self.bridge.execute(self.path, "radio_play", 711)
        self.assertEqual(self.executed, ["hangup", "call"])

    def test_new_call_during_station_switch_aborts_without_another_hangup(self):
        self.add_second_station()
        self.calls = [{"id": "1", "number": "701", "incoming": False, "state": "Connected"}]
        def execute(args, *_):
            self.executed.append(args.command)
            self.calls = [{"id": "2", "number": "201", "incoming": True, "state": "Connected"}]
        with patch.object(self.bridge.native, "execute_action", execute), self.assertRaises(NativeError):
            self.bridge.execute(self.path, "radio_play", 711)
        self.assertEqual(self.executed, ["hangup"])

    def test_radio_play_cannot_dial_an_allowlisted_nonradio_destination(self):
        self.add_second_station()
        with self.assertRaises(NativeError):
            self.bridge.execute(self.path, "radio_play", 201)
        self.assertEqual(self.executed, [])

    def test_native_sip_prefix_is_radio_but_remote_sip_address_is_not(self):
        self.calls = [{"id": "8", "number": "sip:701", "incoming": False, "state": "Connected"}]
        self.assertEqual(self.bridge.execute(self.path, "status", 0)["state"], "playing")
        self.assertFalse(self.bridge.execute(self.path, "radio_play", 701)["changed"])
        self.bridge.execute(self.path, "radio_stop", 0)
        self.assertEqual(self.executed, ["hangup"])
        for number in ("sip:701@example.org", "ſip:701", "sİp:701", "sip:٧٠١"):
            self.calls[0]["number"] = number
            with self.subTest(number=number), self.assertRaises(NativeError):
                self.bridge.execute(self.path, "radio_stop", 0)

    def test_mutation_waits_for_poll_lock_then_connects_and_executes_once(self):
        attempts, held, sleeps = [], [], []

        @contextlib.contextmanager
        def lock(_):
            attempts.append(1)
            if len(attempts) <= 2:
                raise NativeError("lifesize_command_already_running")
            held.append(True)
            try:
                yield
            finally:
                held.pop()

        def execute(args, *_):
            self.assertEqual(held, [True])
            self.executed.append(args.command)

        with patch.object(self.bridge.native, "device_lock", lock), \
                patch.object(self.bridge.time, "sleep", sleeps.append), \
                patch.object(self.bridge.native, "execute_action", execute):
            self.bridge.execute(self.path, "radio_play", 701)
        self.assertEqual(len(attempts), 3)
        self.assertEqual(sleeps, [0.2, 0.2])
        self.assertEqual(self.connections, 1)
        self.assertEqual(self.executed, ["call"])
        self.assertEqual(held, [])

    def test_mutation_lock_wait_is_bounded_without_connecting(self):
        elapsed, attempts = [0.0], []

        @contextlib.contextmanager
        def lock(_):
            attempts.append(1)
            raise NativeError("lifesize_command_already_running")
            yield

        def sleep(seconds):
            elapsed[0] += seconds

        with patch.object(self.bridge.native, "device_lock", lock), \
                patch.object(self.bridge, "MUTATION_LOCK_WAIT", 0.5), \
                patch.object(self.bridge.time, "monotonic", lambda: elapsed[0]), \
                patch.object(self.bridge.time, "sleep", sleep), \
                self.assertRaisesRegex(NativeError, "lifesize_command_already_running"):
            self.bridge.execute(self.path, "radio_play", 701)
        self.assertEqual(elapsed[0], 0.5)
        self.assertEqual(len(attempts), 4)
        self.assertEqual(self.connections, 0)
        self.assertEqual(self.executed, [])

    def test_status_contention_and_lock_permission_failure_never_wait(self):
        for action, reason in (("status", "lifesize_command_already_running"),
                               ("radio_play", "lifesize_lock_permissions")):
            @contextlib.contextmanager
            def lock(_):
                raise NativeError(reason)
                yield
            with self.subTest(action=action), \
                    patch.object(self.bridge.native, "device_lock", lock), \
                    patch.object(self.bridge.time, "sleep") as sleep, \
                    self.assertRaisesRegex(NativeError, reason):
                self.bridge.execute(self.path, action, 701)
            sleep.assert_not_called()
        self.assertEqual(self.connections, 0)
        self.assertEqual(self.executed, [])

    def test_busy_error_after_dispatch_is_never_retried(self):
        def execute(args, *_):
            self.executed.append(args.command)
            raise NativeError("lifesize_command_already_running")

        with patch.object(self.bridge.native, "execute_action", execute), \
                patch.object(self.bridge.time, "sleep") as sleep, \
                self.assertRaisesRegex(NativeError, "lifesize_command_already_running"):
            self.bridge.execute(self.path, "radio_play", 701)
        sleep.assert_not_called()
        self.assertEqual(self.connections, 1)
        self.assertEqual(self.executed, ["call"])


if __name__ == "__main__":
    unittest.main()
