#!/usr/bin/env python3
"""Warm an approved MJPEG relay briefly before an iOS camera push.

Ring's cloud setup can exceed HA's 10-second MJPEG proxy deadline. A detached,
bounded subscriber waits for one frame, signals readiness, then gives the phone
30 seconds to attach. Closing this subscriber never disconnects other viewers.
"""
import asyncio
import json
from pathlib import Path
import select
import subprocess
import sys

import aiohttp

RELAY_URL = 'http://go2rtc-cameras.kerberos.svc.cluster.local:1984/api/stream.mjpeg?src='
STREAMS = {
    'ring': RELAY_URL + 'ring_notifications',
    'living_room_onvif': 'http://go2rtc-onvif.kerberos.svc.cluster.local:1984/api/stream.mjpeg?src=living_room_onvif_notifications',
}
STREAM_URL = STREAMS['ring']
STARTUP_SECONDS = 35
HOLD_SECONDS = 30
MAX_STARTUP_BYTES = 1024 * 1024


async def first_frame_ready(content, max_bytes=MAX_STARTUP_BYTES, frame_sink=None):
    """Find JPEG markers in one pass, retaining only their one-byte overlap.

    The byte budget includes multipart headers and incomplete frames. Check it
    before accepting an end marker so the final chunk cannot bypass the limit.
    """
    received = 0
    previous = b''
    started = False
    async for chunk in content.iter_chunked(16384):
        if frame_sink:
            frame_sink.feed(chunk)
        received += len(chunk)
        window = previous + chunk
        search_from = 0
        if not started:
            start = window.find(b'\xff\xd8')
            if start >= 0:
                started = True
                search_from = start + 2
        if started:
            end = window.find(b'\xff\xd9', search_from)
            if end >= 0:
                # A read may also contain the next frame. Only bytes through
                # this first frame's end count against its readiness budget.
                if received - len(window) + end + 2 > max_bytes:
                    raise ValueError('No complete JPEG within size limit')
                return True
        if received > max_bytes:
            raise ValueError('No complete JPEG within size limit')
        previous = window[-1:]
    return False


async def warm_stream(url=STREAM_URL, startup=STARTUP_SECONDS, hold=HOLD_SECONDS, signal=None, frame_sink=None):
    """Signal only after a complete JPEG; bound startup and post-ready lifetime."""
    ready = False
    response = None
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None)) as session:
            async with asyncio.timeout(startup):
                while not ready:
                    response = None
                    try:
                        response = await session.get(url)
                        response.raise_for_status()
                        ready = await first_frame_ready(response.content, frame_sink=frame_sink)
                    except (aiohttp.ClientError, ValueError):
                        pass
                    if not ready:
                        if response is not None:
                            response.close()
                        # go2rtc may reject its first request while Ring is still
                        # starting. Retry within the same total startup deadline.
                        await asyncio.sleep(0.5)
            if signal:
                signal(True)
            try:
                async with asyncio.timeout(hold):
                    async for chunk in response.content.iter_chunked(16384):
                        if frame_sink:
                            frame_sink.feed(chunk)
            except TimeoutError:
                pass
            finally:
                response.close()
    except (aiohttp.ClientError, TimeoutError, ValueError):
        if not ready and signal:
            signal(False)
    finally:
        # Startup timeout and task cancellation bypass the post-ready cleanup.
        # Closing the session alone does not release the response object itself.
        if response is not None:
            response.close()
        if frame_sink:
            frame_sink.close()
    return ready


def prepare(camera='ring'):
    if camera not in STREAMS:
        raise ValueError('Unknown notification camera')
    # Separate stdio and session: HA's shell_command returns at readiness, while
    # the finite worker keeps its connection alive. No HA task or encoder is permanent.
    worker = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), '--worker', camera],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        readable, _, _ = select.select([worker.stdout], [], [], STARTUP_SECONDS + 2)
        ready = bool(readable and worker.stdout.readline(64).strip() == b'{"ready": true}')
    finally:
        worker.stdout.close()
    if not ready:
        worker.terminate()
        try:
            worker.wait(timeout=2)
        except subprocess.TimeoutExpired:
            worker.kill()
            worker.wait()
    return ready


if __name__ == '__main__':
    args = sys.argv[1:]
    worker_mode = bool(args and args[0] == '--worker')
    if worker_mode:
        args = args[1:]
    if len(args) > 1 or (args and args[0] not in STREAMS):
        raise SystemExit('Expected an approved notification camera name')
    camera = args[0] if args else 'ring'
    if worker_mode:
        frame_sink = None
        if camera == 'living_room_onvif':
            try:
                from notification_frame_cache import NotificationFrameCache
                frame_sink = NotificationFrameCache()
            except ImportError:
                pass  # Partial restores must not break the phone notification.
        asyncio.run(warm_stream(url=STREAMS[camera],
                                frame_sink=frame_sink,
                                signal=lambda ready: print(json.dumps({'ready': ready}), flush=True)))
    else:
        ready = prepare(camera)
        print(json.dumps({'ready': ready}))
        sys.exit(0 if ready else 1)
