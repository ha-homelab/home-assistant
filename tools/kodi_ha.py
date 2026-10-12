#!/usr/bin/env python3
"""Home Assistant shortcuts for ~/k; credentials stay outside the synced script."""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, Request


class ClientError(Exception):
    """An actionable error safe to print without credentials or response bodies."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward the bearer token to a redirected host/login page.
        return None


def connection():
    server = os.environ.get('HASS_SERVER') or os.environ.get('HOMEASSISTANT_URL')
    token = os.environ.get('HASS_TOKEN') or os.environ.get('HOMEASSISTANT_TOKEN')
    if bool(server) != bool(token):
        raise ClientError('Set both HASS_SERVER and HASS_TOKEN, or use the private config file.')
    if not server:
        path = Path(os.environ.get('KODI_HA_CONFIG', '~/.config/kodi-ha/connection.json')).expanduser()
        try:
            if stat.S_IMODE(path.stat().st_mode) & 0o077:
                raise ClientError('The HA credential file must have mode 0600.')
            config = json.loads(path.read_text())
            server, token = config['server'], config['token']
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise ClientError('Configure ~/.config/kodi-ha/connection.json with server and token.') from error
    if not isinstance(server, str) or not isinstance(token, str) or not token.strip():
        raise ClientError('Invalid HA connection settings.')
    parsed = urlsplit(server)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
        raise ClientError('HA server must be an HTTP(S) origin without credentials or a path.')
    return server.rstrip('/'), token


class Client:
    def __init__(self, server, token):
        self.server, self.token = server, token
        self.opener = build_opener(NoRedirect())

    def request(self, method, path, data=None):
        payload = json.dumps(data).encode() if data is not None else None
        request = Request(self.server + '/api/' + path, data=payload, method=method,
                          headers={'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'})
        try:
            with self.opener.open(request, timeout=20) as response:
                return json.load(response)
        except HTTPError as error:
            raise ClientError(f'Home Assistant returned HTTP {error.code} for {path}.') from error
        except (URLError, OSError, ValueError) as error:
            raise ClientError('Home Assistant request failed; check connectivity and configuration.') from error

    def call(self, service, entities, dry_run=False):
        if not re.fullmatch(r'[a-z_]+\.[a-z_]+', service):
            raise ClientError('Invalid service; use domain.service.')
        domain, action = service.split('.')
        entities = list(dict.fromkeys(entities))
        for entity in entities:
            if not re.fullmatch(r'[a-z_]+\.[a-z0-9_]+', entity):
                raise ClientError('Invalid entity ID.')
            if domain != 'homeassistant' and entity.split('.')[0] != domain:
                raise ClientError(f'{entity} does not belong to the {domain} service domain.')
        states = []
        # Validate every member before the one POST; never partly run a broken group.
        for entity in entities:
            state = self.request('GET', 'states/' + entity)
            if state.get('state') == 'unavailable':
                raise ClientError(f'{entity} is unavailable; no command was sent.')
            states.append({'entity_id': entity, 'name': state.get('attributes', {}).get('friendly_name', entity), 'state': state['state']})
        if dry_run:
            return {'dry_run': True, 'service': service, 'targets': states}
        payload = {'entity_id': entities} if entities else {}
        self.request('POST', f'services/{domain}/{action}', payload)
        return {'service': service, 'targets': states, 'accepted': True}

    def integration(self, domain):
        if not re.fullmatch(r'[a-z0-9_]+', domain):
            raise ClientError('Invalid integration domain.')
        entries = self.request('GET', 'config/config_entries/entry?domain=' + domain)
        matches = [entry for entry in entries if entry.get('domain') == domain and not entry.get('disabled_by')]
        if len(matches) != 1:
            raise ClientError(f'Expected one enabled {domain} registration; found {len(matches)}. No reload sent.')
        return matches[0]

    def reload(self, domain, dry_run=False):
        entry = self.integration(domain)
        if dry_run:
            return {'dry_run': True, 'reload_domain': domain, 'entry_id': entry['entry_id']}
        return self.request('POST', 'config/config_entries/entry/' + entry['entry_id'] + '/reload', {})

    def check(self):
        config = self.request('GET', 'config')
        entries = {domain: self.integration(domain) for domain in ('localtuya', 'mqtt')}
        return {'version': config['version'], 'state': config['state'],
                'integrations': {domain: {k: entry.get(k) for k in ('entry_id', 'state')}
                                 for domain, entry in entries.items()}}


def run_alias(client, alias, commands, dry_run=False):
    if alias not in commands:
        raise ClientError('Unknown Home Assistant shortcut.')
    command = commands[alias]
    if 'retired' in command:
        raise ClientError(command['retired'])
    if command.get('check'):
        return client.check()
    if 'reload_domain' in command:
        return client.reload(command['reload_domain'], dry_run=dry_run)
    return client.call(command['service'], command['entities'], dry_run=dry_run)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('alias')
    parser.add_argument('--dry-run', action='store_true', default=os.environ.get('KODI_HA_DRY_RUN') == '1',
                        help='Validate and show the command without sending a POST.')
    args = parser.parse_args(argv)
    try:
        commands = json.loads(Path(__file__).with_name('kodi_ha_commands.json').read_text())
        # Retired/unknown commands need no credentials and make no network requests.
        if args.alias not in commands or 'retired' in commands[args.alias]:
            run_alias(None, args.alias, commands)
        result = run_alias(Client(*connection()), args.alias, commands, args.dry_run)
    except (ClientError, OSError, ValueError) as error:
        print('HA: ' + str(error), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
