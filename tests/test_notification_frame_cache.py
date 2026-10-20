"""Private cache contract and reuse of an existing subscriber; no real cameras."""
import asyncio
import base64
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'config/housekeeping' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cache_module = load('notification_frame_cache')


class FrameCacheTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cache = cache_module.NotificationFrameCache(Path(self.temp.name) / 'cache')
        self.addCleanup(self.cache.close)

    def test_chunk_boundaries_throttle_private_permissions_and_cleanup(self):
        for chunk in [b'--boundary\r\n\xff', b'\xd8image', b'\xff', b'\xd9']:
            self.cache.feed(chunk)
        data = json.loads(self.cache.path.read_text())
        self.assertEqual(base64.b64decode(data['jpeg']), b'\xff\xd8image\xff\xd9')
        self.assertEqual(len(data['event_id']), 32)
        self.assertEqual(self.cache.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.cache.root.stat().st_mode & 0o777, 0o700)
        self.cache.feed(b'\xff\xd8too soon\xff\xd9')
        self.assertEqual(json.loads(self.cache.path.read_text()), data)
        self.cache.last_write -= 2
        self.cache.feed(b'\xff\xd8next\xff\xd9')
        self.assertEqual(json.loads(self.cache.path.read_text())['event_id'], data['event_id'])
        self.cache.close()
        self.assertFalse(self.cache.path.exists())

    def test_overlapping_worker_cannot_replace_or_remove_owner_frames(self):
        self.cache.feed(b'\xff\xd8owner\xff\xd9')
        other = cache_module.NotificationFrameCache(self.cache.root)
        self.assertIsNone(other.lock)
        other.feed(b'\xff\xd8other\xff\xd9')
        other.close()
        self.assertEqual(json.loads(self.cache.path.read_text())['event_id'], self.cache.event_id)

    def test_limit_sized_frame_survives_next_frame_in_the_same_chunk(self):
        frame = b'\xff\xd8' + b'x' * (cache_module.MAX_BYTES - 4) + b'\xff\xd9'
        self.cache.feed(frame[:-1])
        self.cache.feed(frame[-1:] + b'\xff\xd8next\xff\xd9')
        data = json.loads(self.cache.path.read_text())
        self.assertEqual(base64.b64decode(data['jpeg']), frame)
        self.assertLessEqual(len(self.cache.buffer), cache_module.MAX_BYTES)

    def test_large_chunk_preserves_complete_frames_and_trailing_marker(self):
        frame = b'\xff\xd8first\xff\xd9'
        self.cache.feed(frame + b'x' * cache_module.MAX_BYTES + b'\xff')
        self.assertEqual(base64.b64decode(json.loads(self.cache.path.read_text())['jpeg']), frame)
        self.cache.last_write -= 2
        self.cache.feed(b'\xd8next\xff\xd9')
        self.assertEqual(base64.b64decode(json.loads(self.cache.path.read_text())['jpeg']),
                         b'\xff\xd8next\xff\xd9')

    def test_oversized_incomplete_frame_recovers_at_split_start_marker(self):
        self.cache.feed(b'\xff\xd8' + b'x' * (cache_module.MAX_BYTES - 3) + b'\xff')
        self.assertEqual(len(self.cache.buffer), cache_module.MAX_BYTES)
        self.cache.feed(b'\xd8recovered\xff\xd9')
        self.assertEqual(base64.b64decode(json.loads(self.cache.path.read_text())['jpeg']),
                         b'\xff\xd8recovered\xff\xd9')
        self.assertLessEqual(len(self.cache.buffer), cache_module.MAX_BYTES)

    def test_oversized_and_incomplete_input_is_bounded_and_write_failures_are_optional(self):
        self.cache.feed(b'\xff\xd8' + b'x' * cache_module.MAX_BYTES)
        self.assertFalse(self.cache.path.exists())
        self.assertLessEqual(len(self.cache.buffer), cache_module.MAX_BYTES)
        with patch.object(cache_module.os, 'replace', side_effect=OSError('disk full')):
            self.cache.feed(b'\xff\xd8frame\xff\xd9')
        self.assertIsNone(self.cache.lock)
        self.assertEqual(list(self.cache.root.glob('.frame-*')), [])


@unittest.skipUnless(importlib.util.find_spec('aiohttp'), 'aiohttp is provided by the HA runtime image')
class ExistingSubscriberTest(unittest.IsolatedAsyncioTestCase):
    async def test_reuses_one_connection_and_deletes_frames_after_bounded_hold(self):
        from aiohttp import web
        helper = load('notification_video_ready')
        with tempfile.TemporaryDirectory() as root:
            cache = cache_module.NotificationFrameCache(root)
            calls = []
            async def stream(request):
                calls.append(True)
                response = web.StreamResponse()
                await response.prepare(request)
                await response.write(b'\xff\xd8first\xff\xd9')
                await asyncio.sleep(.5)
                return response
            app = web.Application()
            app.router.add_get('/', stream)
            runner = web.AppRunner(app, shutdown_timeout=.1)
            await runner.setup()
            self.addAsyncCleanup(runner.cleanup)
            site = web.TCPSite(runner, '127.0.0.1', 0)
            await site.start()
            def ready(value):
                self.assertTrue(value)
                self.assertTrue(cache.path.exists())
            port = site._server.sockets[0].getsockname()[1]
            self.assertTrue(await helper.warm_stream(f'http://127.0.0.1:{port}/', startup=1, hold=.08, signal=ready, frame_sink=cache))
            self.assertEqual(len(calls), 1)
            self.assertFalse(cache.path.exists())


if __name__ == '__main__':
    unittest.main()
