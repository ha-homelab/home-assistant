"""Reuse notification JPEGs in a private, short-lived floorplan cache.

No network, encoder or subscriber: feed only bytes the readiness worker already
receives. A cache failure must never affect delivery of the phone notification.
"""
import base64
import fcntl
import json
import os
from pathlib import Path
import tempfile
import time
import uuid

MAX_BYTES = 1024 * 1024


class NotificationFrameCache:
    def __init__(self, root=None):
        self.root = Path(root) if root else Path(__file__).resolve().parents[1] / '.storage/notification_frames'
        self.path = self.root / 'living_room_onvif.json'
        self.event_id = uuid.uuid4().hex
        self.buffer = bytearray()
        self.last_write = -float('inf')
        self.lock = None
        try:
            self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
            self.lock = os.open(self.root / 'living_room_onvif.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            if self.lock is not None:
                os.close(self.lock)
            self.lock = None

    def feed(self, chunk):
        if self.lock is None:
            return
        try:
            pending = memoryview(chunk)
            while pending:
                if len(self.buffer) == MAX_BYTES:
                    # The incomplete frame is too large. Preserve only a possible
                    # first marker byte so the next frame can start across reads.
                    self.buffer[:] = b'\xff' if self.buffer.endswith(b'\xff') else b''
                size = min(len(pending), MAX_BYTES - len(self.buffer))
                self.buffer.extend(pending[:size])
                pending = pending[size:]
                while self.buffer:
                    start = self.buffer.find(b'\xff\xd8')
                    if start < 0:
                        self.buffer[:] = b'\xff' if self.buffer.endswith(b'\xff') else b''
                        break
                    end = self.buffer.find(b'\xff\xd9', start + 2)
                    if end < 0:
                        del self.buffer[:start]
                        break
                    frame = bytes(self.buffer[start:end + 2])
                    del self.buffer[:end + 2]
                    now = time.monotonic()
                    if now - self.last_write < 1:
                        continue
                    self.last_write = now
                    payload = {'event_id': self.event_id, 'captured_at': time.time(),
                               'jpeg': base64.b64encode(frame).decode('ascii')}
                    temporary = None
                    try:
                        with tempfile.NamedTemporaryFile(mode='w', dir=self.root, prefix='.frame-', delete=False) as output:
                            temporary = Path(output.name)
                            json.dump(payload, output, separators=(',', ':'))
                        os.replace(temporary, self.path)
                    finally:
                        if temporary:
                            temporary.unlink(missing_ok=True)
        except (OSError, ValueError):
            self.close()

    def close(self):
        if self.lock is not None:
            try:
                self.path.unlink(missing_ok=True)
            except OSError:
                pass  # Readers reject stale frames after five seconds as well.
            os.close(self.lock)
            self.lock = None
        self.buffer.clear()
