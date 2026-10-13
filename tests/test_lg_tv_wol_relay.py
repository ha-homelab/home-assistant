import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock

SOURCE = Path(__file__).resolve().parents[1] / 'tools/lg_tv_wol_relay.py'
spec = importlib.util.spec_from_file_location('relay', SOURCE)
relay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(relay)


class RelayTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.config = Path(temporary.name) / 'relay.json'
        self.target = {'mac': '02:00:00:00:00:01', 'broadcast': '192.0.2.255'}
        self.config.write_text(json.dumps(self.target))
        config_patch = patch.object(relay, 'CONFIG', self.config)
        config_patch.start()
        self.addCleanup(config_patch.stop)

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
        expected = b'\xff' * 6 + bytes.fromhex('020000000001') * 16
        self.assertEqual(len(expected), 102)
        self.assertEqual(sock.sendto.call_count, 3)
        for call in sock.sendto.call_args_list:
            self.assertEqual(call.args, (expected, ('192.0.2.255', 9)))
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

    def test_missing_target_fails_without_network_io(self):
        self.config.unlink()
        with patch.dict(os.environ, {'SSH_ORIGINAL_COMMAND': 'wake-living-room-tv'}), patch.object(relay.socket, 'socket') as factory, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(relay.main(), 3)
            factory.assert_not_called()

    def test_invalid_target_fails_without_network_io_or_echoing_values(self):
        invalid = [None, {}, self.target | {'mac': 'not-a-mac'},
                   self.target | {'mac': 'ff:ff:ff:ff:ff:ff'},
                   self.target | {'broadcast': 'not-an-address'},
                   self.target | {'broadcast': '127.0.0.1'},
                   self.target | {'broadcast': 123}, self.target | {'command': 'id'}]
        for target in invalid:
            self.config.write_text(json.dumps(target))
            error = io.StringIO()
            with self.subTest(target=target), patch.dict(os.environ, {'SSH_ORIGINAL_COMMAND': 'wake-living-room-tv'}), patch.object(relay.socket, 'socket') as factory, contextlib.redirect_stderr(error):
                self.assertEqual(relay.main(), 3)
                factory.assert_not_called()
                self.assertNotIn('not-a-mac', error.getvalue())
                self.assertNotIn('not-an-address', error.getvalue())


if __name__ == '__main__':
    unittest.main()
