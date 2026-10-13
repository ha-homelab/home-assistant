"""Exercise the real frame parser in one private temporary directory per input."""

import base64
import importlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "config/housekeeping"))
cache_module = importlib.import_module("notification_frame_cache")
MAX_BYTES = cache_module.MAX_BYTES
NotificationFrameCache = cache_module.NotificationFrameCache


def notification_frames(data: bytes) -> None:
    with tempfile.TemporaryDirectory(prefix="synthetic-frame-") as temporary:
        cache = NotificationFrameCache(Path(temporary) / "cache")
        try:
            assert cache.lock is not None  # nosec B101 - isolated root is writable
            chunk_size = 1 + (data[0] % 64 if data else 0)
            for position in range(0, len(data), chunk_size):
                cache.feed(data[position : position + chunk_size])
                assert len(cache.buffer) <= MAX_BYTES  # nosec B101 - memory bound
                if cache.path.exists():
                    payload = json.loads(cache.path.read_text())
                    frame = base64.b64decode(payload["jpeg"], validate=True)
                    assert frame.startswith(b"\xff\xd8")  # nosec B101
                    assert frame.endswith(b"\xff\xd9")  # nosec B101
                    assert frame in data  # nosec B101 - no invented or mixed source bytes
                    assert payload["event_id"] == cache.event_id  # nosec B101
                    assert cache.path.stat().st_mode & 0o777 == 0o600  # nosec B101
            if data[:1] == b"\xff":
                cache.feed(b"x" * (MAX_BYTES + 1))
                assert not cache.buffer  # nosec B101 - oversized input resets buffer
            assert not list(cache.root.glob(".frame-*"))  # nosec B101 - atomic cleanup
        finally:
            cache.close()
        assert cache.lock is None and not cache.buffer  # nosec B101
        assert not cache.path.exists()  # nosec B101 - close removes owned frame
