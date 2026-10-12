import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch, MagicMock

SOURCE = Path(__file__).resolve().parents[1] / 'tools/lg_tv_wol_relay.py'
spec = importlib.util.spec_from_file_location('relay', SOURCE)
relay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(relay)


class RelayTests(unittest.TestCase):
    def test_only_explicit_wake_command_opens_socket(self):
        for command in ('', 'id', 'wake-living-room-tv; id'):
            with self.subTest(command=command), patch.dict(os.environ, {'SSH_ORIGINAL_COMMAND': command}), patch.object(relay.socket, 'socket') as factory, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(relay.main(), 2)
                factory.assert_not_called()

    def test_three_exact_packets_without_stale_source_binding(self):
        sock = MagicMock()
        sock.__enter__.return_value = sock
        sock.sendto.return_value = 102
        # A stale/non-local source address must never be bound.
        sock.bind.side_effect = AssertionError('Do not bind a changing LAN address')
        output = io.StringIO()
        with patch.dict(os.environ, {'SSH_ORIGINAL_COMMAND': 'wake-living-room-tv'}), patch.object(relay.socket, 'socket', return_value=sock), patch.object(relay.time, 'sleep'), contextlib.redirect_stdout(output):
            self.assertEqual(relay.main(), 0)
        expected = b'\xff' * 6 + bytes.fromhex('d0cdbf6670b2') * 16
        self.assertEqual(len(expected), 102)
        self.assertEqual(sock.sendto.call_count, 3)
        for call in sock.sendto.call_args_list:
            self.assertEqual(call.args, (expected, ('192.168.175.255', 9)))
        sock.bind.assert_not_called()
        self.assertEqual(json.loads(output.getvalue()), {'target': 'living_room_tv_77', 'packets_sent': 3})

    def test_send_failure_is_not_reported_as_success(self):
        sock = MagicMock()
        sock.__enter__.return_value = sock
        sock.sendto.return_value = 101
        output = io.StringIO()
        with patch.dict(os.environ, {'SSH_ORIGINAL_COMMAND': 'wake-living-room-tv'}), patch.object(relay.socket, 'socket', return_value=sock), contextlib.redirect_stdout(output), self.assertRaises(OSError):
            relay.main()
        self.assertEqual(output.getvalue(), '')


if __name__ == '__main__':
    unittest.main()
