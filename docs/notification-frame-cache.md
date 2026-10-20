# Portable notification frame-cache library

`ha-notification-frame-cache` packages the repository's existing
`NotificationFrameCache` class. It accepts already-received JPEG byte chunks,
keeps at most one MiB of incomplete input, and stores complete frames in a
private short-lived JSON file. It does not open a camera connection, decode
images, start an encoder or send notifications. It requires Python 3.11 or newer
on a POSIX system with `fcntl` file locking.

Install the exact wheel or source distribution downloaded from a chosen
beta/RC release into an isolated environment. For example:

```sh
python3 -m venv /tmp/frame-cache-test
/tmp/frame-cache-test/bin/python -m pip install ./ha_notification_frame_cache-0.1.0-py3-none-any.whl
```

Use the actual downloaded filename and verify its published SHA-256 first.
Package versions alone do not identify RC origin; retain the release tag and
manifest. There is no automatic PyPI publication.

Always provide a private writable cache directory explicitly:

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from notification_frame_cache import NotificationFrameCache

with TemporaryDirectory() as temporary:
    cache = NotificationFrameCache(Path(temporary) / "frames")
    try:
        cache.feed(b"\xff\xd8synthetic-frame\xff\xd9")
    finally:
        cache.close()
```

The example uses marker bytes for testing; it is not a decodable photograph.
The existing class uses fixed `living_room_onvif.json` and `.lock` filenames
inside the supplied directory. Allocate a separate directory per stream. The
historical default directory is relative to the module; applications using the
standalone distribution should pass an explicit directory instead.

This library retains the existing API and behavior. The frame file is private
mode `0600`; concurrent owners are excluded by the lock. Call `close()` to
remove the owned frame and release resources. A failure to acquire the lock
disables that instance's cache, and write errors stop its caching without
interrupting the caller's notification flow. The parser recognizes JPEG
markers; it is not an image-content validator.

Network chunk boundaries do not limit frame size: a complete frame of up to
one MiB is retained even when the same chunk also contains later data. Larger
chunks are consumed in bounded segments. If an incomplete frame fills the
buffer, parsing resumes at the next start marker, including markers split
across chunks. Complete frames larger than one MiB are discarded.

The distribution excludes the household configuration, endpoints, camera
helpers, authentication data and notification-delivery integration. Installing
it does not configure or update Home Assistant. Use [release packaging and
acceptance](https://github.com/ha-homelab/home-assistant/blob/main/docs/release-packaging.md) for build provenance and validation limits.
