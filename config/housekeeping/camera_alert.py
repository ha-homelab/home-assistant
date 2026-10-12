"""Publish validated motion JPEGs without destroying the last good snapshot."""
import argparse
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
import urllib.request

from PIL import Image

KEYS = ('front', 'backdoor', 'garage', 'porch', 'ring')
AGENTS = {'front': 'front', 'backdoor': 'tenants', 'garage': 'garage', 'porch': 'porch'}


def fetch_agent(key, credentials_path=Path('/config/kerberos-snapshot-auth.json')):
    """Use the agent's existing camera connection, without starting another RTSP client."""
    base = f'http://agent-{AGENTS[key]}camera.kerberos.svc.cluster.local'
    if credentials_path.stat().st_mode & 0o077:
        raise ValueError('Snapshot credentials must be private (mode 0600)')
    credentials = json.loads(credentials_path.read_text())
    request = urllib.request.Request(base + '/api/login',
        data=json.dumps({k: credentials[k] for k in ('username', 'password')}).encode(),
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=10) as response:
        token = json.load(response)['token']
    request = urllib.request.Request(base + '/api/camera/snapshot/jpeg',
        headers={'Authorization': 'Bearer ' + token})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read()


def valid_jpeg(data):
    try:
        with Image.open(BytesIO(data)) as image:
            if image.format != 'JPEG':
                return False
            image.load()
            return image.width > 0 and image.height > 0
    except (OSError, ValueError):
        return False


def atomic_write(path, data):
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def run(operation, key, directory=Path('/config/www')):
    if key not in KEYS:
        raise ValueError('Unknown camera key')
    pending = directory / f'.{key}_camera_alert.pending.jpg'
    if operation == 'prepare':
        pending.unlink(missing_ok=True)
        return
    if operation == 'fetch':
        image = fetch_agent(key)
        if not valid_jpeg(image):
            raise ValueError('Agent returned an invalid JPEG')
        atomic_write(pending, image)
        return
    if operation != 'commit':
        raise ValueError('Unknown operation')
    try:
        current = pending.read_bytes()
        if not valid_jpeg(current):
            raise ValueError('Camera returned an invalid JPEG; previous snapshots preserved')
        slots = [directory / f'{key}_camera_alert{suffix}.jpg' for suffix in ('', '2', '3', '4')]
        previous = [p.read_bytes() if p.exists() else b'' for p in slots]
        # Repeated Ring events can yield the same retained image. Do not rotate it twice.
        history = previous[1:] if previous[0] == current else previous[:3]
        # Bootstrap and retained frames often occupy several slots. Decode each
        # distinct payload once, but still repair every missing/corrupt slot.
        validated = {current: True, b'': False}
        for index in range(3, 0, -1):
            path, data = slots[index], history[index - 1]
            if data not in validated:
                validated[data] = valid_jpeg(data)
            # At bootstrap missing/corrupt history is seeded with this real image.
            payload = data if validated[data] else current
            if previous[index] == payload:
                # Preserve successful-capture freshness without rewriting and
                # fsyncing the same JPEG (or changing its inode) on every event.
                os.utime(path)
            else:
                atomic_write(path, payload)
        if previous[0] == current:
            os.utime(slots[0])
        else:
            atomic_write(slots[0], current)
    finally:
        pending.unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('prepare', 'fetch', 'commit'))
    parser.add_argument('key', choices=KEYS)
    args = parser.parse_args()
    run(args.operation, args.key)
