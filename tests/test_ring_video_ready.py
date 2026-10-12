"""Exercise bounded readiness against a loopback MJPEG server, never real cameras."""
import asyncio
import gc
import importlib.util
import os
from pathlib import Path
import unittest

try:
    from aiohttp import web
except ImportError:
    web = None

ROOT = Path(os.environ.get('RESILIENCE_TEST_ROOT', Path(__file__).resolve().parents[1]))


@unittest.skipUnless(web, 'aiohttp is provided by the deployed HA image')
class RingVideoReadyTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        spec = importlib.util.spec_from_file_location('ring_video_ready', ROOT / 'config/housekeeping/notification_video_ready.py')
        self.helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.helper)
        self.signals = []
        self.loop_errors = []
        self.loop = asyncio.get_running_loop()
        self.previous_handler = self.loop.get_exception_handler()
        self.loop.set_exception_handler(lambda loop, context: self.loop_errors.append(context))

    async def asyncTearDown(self):
        try:
            # aiohttp reports unclosed response objects through the event loop,
            # even if the session already closed the underlying TCP connection.
            gc.collect()
            await asyncio.sleep(0)
            self.assertEqual([context.get('message') for context in self.loop_errors], [])
        finally:
            self.loop.set_exception_handler(self.previous_handler)

    async def server(self, handler):
        app = web.Application()
        app.router.add_get('/', handler)
        runner = web.AppRunner(app, shutdown_timeout=0.1)
        await runner.setup()
        site = web.TCPSite(runner, '127.0.0.1', 0)
        await site.start()
        self.addAsyncCleanup(runner.cleanup)
        return f'http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}/'

    async def frame_ready(self, chunks, limit=1024 * 1024):
        class Content:
            async def iter_chunked(self, size):
                for chunk in chunks:
                    # Mirror aiohttp's upper bound while allowing short reads.
                    assert len(chunk) <= size
                    yield chunk
        return await self.helper.first_frame_ready(Content(), max_bytes=limit)

    async def test_jpeg_markers_can_cross_every_chunk_boundary(self):
        payload = b'--boundary\r\n\xff\xd9ignored\xff\xd8jpeg\xff\xd9'
        for split in range(1, len(payload)):
            with self.subTest(split=split):
                self.assertTrue(await self.frame_ready([payload[:split], payload[split:]]))
        self.assertTrue(await self.frame_ready([bytes([byte]) for byte in payload]))
        for payload in (b'\xff\xd9', b'\xff\xd8partial', b'headers only', b''):
            with self.subTest(incomplete=payload):
                self.assertFalse(await self.frame_ready([bytes([byte]) for byte in payload]))

    async def test_complete_frame_cannot_bypass_byte_limit_in_its_final_chunk(self):
        payload = b'header\xff\xd8jpeg\xff\xd9'
        for chunks in ([payload], [payload[:-1], payload[-1:]],
                       [bytes([byte]) for byte in payload]):
            with self.subTest(chunks=len(chunks)):
                with self.assertRaisesRegex(ValueError, 'size limit'):
                    await self.frame_ready(chunks, limit=len(payload) - 1)
                self.assertTrue(await self.frame_ready(chunks, limit=len(payload)))
        # Subsequent multipart bytes in the same read do not enlarge frame one.
        self.assertTrue(await self.frame_ready([payload + b'next-frame'], limit=len(payload)))
        with self.assertRaisesRegex(ValueError, 'size limit'):
            await self.frame_ready([b'no JPEG here'], limit=5)

    async def test_waits_for_complete_frame_then_releases_its_connection(self):
        released = asyncio.Event()
        async def stream(request):
            response = web.StreamResponse()
            await response.prepare(request)
            await response.write(b'--boundary\r\n\xff\xd8partial')
            await asyncio.sleep(0.03)
            self.assertEqual(self.signals, [])
            await response.write(b'jpeg\xff\xd9')
            try:
                while True:
                    await asyncio.sleep(0.01)
                    await response.write(b'next frame')
            except (ConnectionResetError, asyncio.CancelledError):
                released.set()
            return response
        url = await self.server(stream)
        ready = await self.helper.warm_stream(url, startup=1, hold=0.08, signal=self.signals.append)
        self.assertTrue(ready)
        self.assertEqual(self.signals, [True])
        await asyncio.wait_for(released.wait(), timeout=1)

    async def test_startup_deadline_bounds_a_server_that_never_sends_frames(self):
        async def stream(request):
            response = web.StreamResponse()
            await response.prepare(request)
            await asyncio.sleep(5)
            return response
        url = await self.server(stream)
        ready = await asyncio.wait_for(self.helper.warm_stream(url, startup=0.05, hold=5,
                                                              signal=self.signals.append), timeout=1)
        self.assertFalse(ready)
        self.assertEqual(self.signals, [False])

    async def test_eof_and_http_failure_never_signal_readiness(self):
        for status, body in [(200, b'\xff\xd8truncated'), (503, b'offline')]:
            async def stream(request):
                return web.Response(status=status, body=body)
            self.signals.clear()
            url = await self.server(stream)
            self.assertFalse(await self.helper.warm_stream(url, startup=1, signal=self.signals.append))
            self.assertEqual(self.signals, [False])

    async def test_oversized_complete_frame_never_signals_readiness(self):
        async def stream(request):
            payload = b'\xff\xd8' + b'x' * (self.helper.MAX_STARTUP_BYTES - 3) + b'\xff\xd9'
            return web.Response(body=payload)
        url = await self.server(stream)
        self.assertFalse(await self.helper.warm_stream(url, startup=0.1, hold=0.05,
                                                       signal=self.signals.append))
        self.assertEqual(self.signals, [False])

    async def test_hold_deadline_applies_even_when_source_stops_sending(self):
        async def stream(request):
            response = web.StreamResponse()
            await response.prepare(request)
            await response.write(b'\xff\xd8jpeg\xff\xd9')
            await asyncio.sleep(5)
            return response
        url = await self.server(stream)
        self.assertTrue(await asyncio.wait_for(self.helper.warm_stream(url, startup=1, hold=0.05,
                                                                       signal=self.signals.append), timeout=1))
        self.assertEqual(self.signals, [True])

    async def test_cancellation_during_startup_closes_the_only_subscriber(self):
        connected = asyncio.Event()
        released = asyncio.Event()
        async def stream(request):
            response = web.StreamResponse()
            await response.prepare(request)
            connected.set()
            try:
                while True:
                    await response.write(b'waiting for frame')
                    await asyncio.sleep(0.01)
            except (ConnectionResetError, asyncio.CancelledError):
                released.set()
            return response
        url = await self.server(stream)
        task = asyncio.create_task(self.helper.warm_stream(url, startup=5, hold=5,
                                                          signal=self.signals.append))
        await asyncio.wait_for(connected.wait(), timeout=1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        await asyncio.wait_for(released.wait(), timeout=1)
        self.assertEqual(self.signals, [])

    async def test_retries_initial_relay_failure_without_resetting_startup_budget(self):
        attempts = []
        async def stream(request):
            attempts.append(True)
            if len(attempts) == 1:
                return web.Response(status=503)
            return web.Response(body=b'\xff\xd8jpeg\xff\xd9')
        url = await self.server(stream)
        self.assertTrue(await asyncio.wait_for(self.helper.warm_stream(url, startup=1, hold=0.05,
                                                                       signal=self.signals.append), timeout=2))
        self.assertEqual(len(attempts), 2)
        self.assertEqual(self.signals, [True])
