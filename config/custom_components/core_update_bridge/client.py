"""Authenticated status and single-shot approval; never follow redirects."""
from copy import deepcopy
import re
from urllib.parse import urlsplit

import aiohttp

VERSION = re.compile(r'20\d{2}\.(?:[1-9]|1[0-2])\.(?:0|[1-9]\d*)(?:b[1-9]\d*)?\Z')
CANDIDATE = re.compile(r'[0-9a-f]{32}\Z')
ACTIVE = {'preparing', 'backup', 'preflight', 'deploying', 'verifying'}
STAGES = ACTIVE | {'idle', 'available', 'succeeded', 'failed', 'recovery_required'}


class BridgeError(Exception):
    """A safe message that contains no credentials or remote response body."""


def validate_settings(url, authorization):
    parsed = urlsplit(url)
    if (parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/')):
        raise ValueError('Use the updater base URL without credentials, a path or query')
    if not isinstance(authorization, str) or not authorization.startswith('Bearer ') or len(authorization) < 39:
        raise ValueError('The updater authorization must contain its existing Bearer credential')
    return url.rstrip('/')


def validate_status(data):
    if not isinstance(data, dict) or data.get('stage') not in STAGES:
        raise BridgeError('Invalid updater status')
    if not VERSION.fullmatch(data.get('installed_version') or ''):
        raise BridgeError('The installed Core version is not known yet')
    latest = data.get('latest_version') or data['installed_version']
    if not VERSION.fullmatch(latest):
        raise BridgeError('Invalid offered Core version')
    return deepcopy(data)


def captured_approval(data, version):
    if (not isinstance(version, str) or not VERSION.fullmatch(version)
            or data.get('stage') != 'available'
            or version != data.get('target_version') or version != data.get('latest_version')
            or not CANDIDATE.fullmatch(data.get('candidate_id') or '')):
        raise BridgeError('This version is not an available Core update; refresh the update dialog')
    return {'action': 'install', 'target_version': version, 'candidate_id': data['candidate_id']}


class Client:
    def __init__(self, session, url, authorization):
        self.session = session
        self.url = validate_settings(url, authorization)
        self.authorization = authorization

    async def request(self, path, payload=None):
        try:
            async with self.session.request('POST' if payload is not None else 'GET', self.url + path,
                    json=payload, headers={'Authorization': self.authorization}, allow_redirects=False,
                    timeout=aiohttp.ClientTimeout(total=15)) as response:
                expected = 202 if payload is not None else 200
                if response.status != expected:
                    raise BridgeError(f'Updater refused the request (HTTP {response.status})')
                return await response.json()
        except (aiohttp.ClientError, TimeoutError, ValueError) as error:
            message = ('Approval was not confirmed; inspect update status before trying again'
                       if payload is not None else 'Updater is unavailable')
            raise BridgeError(message) from error

    async def status(self):
        return validate_status(await self.request('/status'))

    async def approve(self, displayed, version):
        approval = captured_approval(displayed, version)
        current = await self.status()
        if captured_approval(current, version) != approval:
            raise BridgeError('The update candidate changed; refresh the update dialog')
        result = await self.request('/approve', approval)
        if (not isinstance(result, dict) or result.get('accepted') is not True
                or any(result.get(key) != approval[key] for key in ('candidate_id', 'target_version'))):
            raise BridgeError('Approval was not confirmed; inspect update status before trying again')
        return current | {'stage': 'preparing'}
