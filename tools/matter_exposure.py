#!/usr/bin/env python3
"""Plan or add explicit household entities to an existing RiDDiX Matter Hub."""
import argparse
import copy
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib import error, parse, request

CONFIG_KEYS = frozenset({
    'id', 'name', 'port', 'icon', 'countryCode', 'priority', 'serialNumberSuffix',
    'uniqueIdSuffix', 'sessionMaxAgeHours', 'filter', 'featureFlags',
})
RESPONSE_KEYS = frozenset({'basicInformation', 'status', 'commissioning', 'deviceCount'})
FABRIC_KEYS = ('fabricIndex', 'fabricId', 'nodeId', 'rootNodeId', 'rootVendorId')
# These household controls do not execute arbitrary scripts or maintenance actions.
DOMAINS = frozenset({'light', 'switch', 'cover', 'fan', 'climate'})
DEFAULT_MANIFEST = Path(__file__).resolve().parents[1] / 'docs/matter-household-exposure.json'


class ExposureError(Exception):
    """An intentionally sanitized error, safe to display without API payloads."""


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client:
    def __init__(self, url, timeout=45):
        parsed = parse.urlsplit(url)
        if (parsed.scheme not in {'http', 'https'} or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise ExposureError('Use an HTTP(S) base URL without credentials, query or fragment.')
        self.url = url.rstrip('/')
        if not self.url.endswith('/api'):
            self.url += '/api'
        self.timeout = timeout
        self.opener = request.build_opener(NoRedirect())

    def call(self, path, method='GET', data=None):
        headers = {'Content-Type': 'application/json'}
        # Optional reverse-proxy bearer auth; never accept or print it on the CLI.
        if token := os.environ.get('MATTER_HUB_TOKEN'):
            headers['Authorization'] = 'Bearer ' + token
        req = request.Request(self.url + path, method=method, headers=headers,
                              data=None if data is None else json.dumps(data).encode())
        try:
            with self.opener.open(req, timeout=self.timeout) as response:
                body = response.read(32 * 1024 * 1024 + 1)
                if len(body) > 32 * 1024 * 1024:
                    raise ExposureError('HAMH response exceeds the supported size.')
                return json.loads(body) if body else None
        except error.HTTPError as exc:
            raise ExposureError(f'HAMH returned HTTP {exc.code} during {method}; no request retried.') from None
        except (error.URLError, TimeoutError, OSError, ValueError):
            raise ExposureError(f'HAMH {method} failed or returned invalid JSON; no request retried.') from None


def read_manifest(path):
    try:
        manifest = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        raise ExposureError('Could not read the JSON exposure manifest.') from None
    entities = manifest.get('entities') if isinstance(manifest, dict) else None
    if not isinstance(entities, list) or not entities:
        raise ExposureError('The manifest must have a nonempty entities list.')
    result, names = {}, set()
    for item in entities:
        if not isinstance(item, dict) or set(item) != {'entity_id', 'name'}:
            raise ExposureError('Each manifest entity needs exactly entity_id and name.')
        entity, name = item['entity_id'], item['name']
        if (not isinstance(entity, str) or not re.fullmatch(r'[a-z]+\.[a-z0-9_]+', entity)
                or entity.split('.')[0] not in DOMAINS):
            raise ExposureError('Manifest contains a wildcard, invalid entity, or unsupported control domain.')
        if (not isinstance(name, str) or not name.strip() or name != name.strip()
                or len(name.encode('utf-8')) > 32 or any(ord(c) < 32 for c in name)):
            raise ExposureError(f'{entity}: use a printable Matter name of at most 32 UTF-8 bytes.')
        if entity in result or name.casefold() in names:
            raise ExposureError('Duplicate entity or voice name in manifest.')
        result[entity] = name
        names.add(name.casefold())
    return result


def config(bridge):
    if not isinstance(bridge, dict) or set(bridge) - CONFIG_KEYS - RESPONSE_KEYS:
        raise ExposureError('Unsupported bridge response fields; review the installed API before applying.')
    if not {'id', 'name', 'port', 'filter'} <= bridge.keys():
        raise ExposureError('Bridge configuration is incomplete.')
    filters = bridge['filter']
    if (not isinstance(filters, dict) or not isinstance(filters.get('include'), list)
            or not isinstance(filters.get('exclude'), list)):
        raise ExposureError('Bridge filters are incomplete.')
    return {key: copy.deepcopy(value) for key, value in bridge.items() if key in CONFIG_KEYS}


def fabrics(bridge):
    commissioning = bridge.get('commissioning', {})
    entries = commissioning.get('fabrics')
    if not isinstance(entries, list) or not entries or commissioning.get('isCommissioned') is not True:
        raise ExposureError('This tool requires an existing commissioned bridge; it never pairs a new one.')
    identities = []
    for entry in entries:
        stable = {key: entry[key] for key in FABRIC_KEYS if key in entry}
        if not stable:
            raise ExposureError('Cannot verify controller fabric identity.')
        identities.append(json.dumps(stable, sort_keys=True))
    return sorted(identities)


def endpoints(graph):
    result = {}
    def visit(node):
        if not isinstance(node, dict) or 'endpoint' not in node or 'id' not in node:
            raise ExposureError('Unsupported Matter device graph.')
        endpoint = node['endpoint']
        if endpoint in result:
            raise ExposureError('Matter device graph contains a duplicate endpoint.')
        result[endpoint] = node
        for child in node.get('parts', []):
            visit(child)
    visit(graph)
    return result


def endpoint_identity(node):
    basic = node.get('state', {}).get('bridgedDeviceBasicInformation', {})
    return node['id'], basic.get('uniqueId'), basic.get('serialNumber')


def entity_id(node):
    return node.get('state', {}).get('homeAssistantEntity', {}).get('entity', {}).get('entity_id')


def mapping_index(response, bridge_id):
    if not isinstance(response, dict) or response.get('bridgeId') != bridge_id:
        raise ExposureError('Unexpected entity-mapping response.')
    entries = response.get('mappings')
    if not isinstance(entries, list):
        raise ExposureError('Unexpected entity-mapping list.')
    result = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get('entityId'), str):
            raise ExposureError('Unsupported entity-mapping schema; no mappings overwritten.')
        key = entry['entityId']
        if key in result:
            raise ExposureError('Duplicate entity mapping; resolve it in HAMH first.')
        result[key] = {k: copy.deepcopy(v) for k, v in entry.items() if k != 'entityId'}
    return result


def add_filters(bridge, entities):
    desired = config(bridge)
    included = desired['filter']['include']
    for entity in entities:
        exact = {'type': 'pattern', 'value': entity}
        if exact not in included:
            included.append(exact)
    return desired


def verify_identity(before, after, old_nodes, new_nodes):
    if fabrics(before) != fabrics(after):
        raise ExposureError('Controller fabrics changed. Stop and inspect privately; do not reset or retry.')
    for endpoint, old in old_nodes.items():
        if endpoint not in new_nodes or endpoint_identity(old) != endpoint_identity(new_nodes[endpoint]):
            raise ExposureError('An existing endpoint identity changed or disappeared. Stop and inspect privately.')
        if entity_id(old) != entity_id(new_nodes[endpoint]):
            raise ExposureError('An existing endpoint changed its HA entity. Stop and inspect privately.')


def target_status(nodes, entities):
    missing, unreachable, wrong_name = [], [], []
    for entity, name in entities.items():
        matches = [node for node in nodes.values() if entity_id(node) == entity]
        if len(matches) > 1:
            raise ExposureError(f'Duplicate Matter endpoints for {entity}.')
        if not matches:
            missing.append(entity)
            continue
        basic = matches[0].get('state', {}).get('bridgedDeviceBasicInformation', {})
        if basic.get('reachable') is not True:
            unreachable.append(entity)
        if basic.get('nodeLabel') != name:
            wrong_name.append(entity)
    return {'missing': missing, 'unreachable': unreachable, 'wrong_name': wrong_name}


def run(client, bridge_id, entities, apply=False, max_devices=80, settle_seconds=60):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', bridge_id):
        raise ExposureError('Invalid bridge identifier.')
    bridge_path = '/matter/bridges/' + parse.quote(bridge_id, safe='')
    mappings_path = '/entity-mappings/' + parse.quote(bridge_id, safe='')
    before = client.call(bridge_path)
    original_config = config(before)
    if before['id'] != bridge_id or before.get('status') != 'running':
        raise ExposureError('The selected existing bridge must be running.')
    fabric_ids = fabrics(before)
    old_nodes = endpoints(client.call(bridge_path + '/devices'))
    old_mappings = mapping_index(client.call(mappings_path), bridge_id)
    desired = add_filters(before, entities)
    preview = client.call('/matter/filter-preview', 'POST', desired['filter'])
    if (not isinstance(preview, dict) or not isinstance(preview.get('total'), int)
            or not isinstance(preview.get('entities'), list)):
        raise ExposureError('Unexpected filter preview response.')
    if preview['total'] > max_devices or preview.get('truncated'):
        raise ExposureError('Preview exceeds the configured device limit or is truncated; split the reviewed scope.')
    selected = {entry.get('entity_id') for entry in preview['entities']}
    missing = sorted(set(entities) - selected)
    if missing:
        raise ExposureError('Manifest entities missing from preview (absent or excluded): ' + ', '.join(missing))
    renamed = [entity for entity, name in entities.items()
               if old_mappings.get(entity, {}).get('customName') != name]
    summary = {'mode': 'apply' if apply else 'dry-run', 'manifest_entities': len(entities),
               'before_devices': before.get('deviceCount'), 'preview_devices': preview['total'],
               'filters_to_add': len(desired['filter']['include']) - len(original_config['filter']['include']),
               'names_to_set': renamed, 'controller_fabrics': len(fabric_ids)}
    if not apply:
        return summary
    current = client.call(bridge_path)
    if config(current) != original_config or fabrics(current) != fabric_ids:
        raise ExposureError('Bridge changed after planning; rerun dry-run before applying.')
    # PUT replaces each mapping. Fetch the current mapping and preserve every
    # other field, including explicit device type and composed sensor mappings.
    for entity in renamed:
        latest = mapping_index(client.call(mappings_path), bridge_id).get(entity, {})
        update = dict(latest, customName=entities[entity])
        client.call(mappings_path + '/' + parse.quote(entity, safe=''), 'PUT', update)
        saved = mapping_index(client.call(mappings_path), bridge_id).get(entity)
        if saved != update:
            raise ExposureError('Mapping readback differs from the requested merge; stop and inspect privately.')
    current = client.call(bridge_path)
    if config(current) != original_config or fabrics(current) != fabric_ids:
        raise ExposureError('Bridge changed while mappings were applied; no bridge configuration overwritten.')
    if desired != original_config:
        client.call(bridge_path, 'PUT', desired)
    client.call('/home-assistant/refresh', 'POST')
    client.call(bridge_path + '/actions/refresh', 'POST')
    deadline = time.monotonic() + settle_seconds
    while True:
        after = client.call(bridge_path)
        nodes = endpoints(client.call(bridge_path + '/devices'))
        verify_identity(before, after, old_nodes, nodes)
        if config(after) != desired:
            raise ExposureError('Bridge configuration readback differs; stop and inspect privately.')
        count = after.get('deviceCount')
        if type(count) is not int or not 0 <= count <= max_devices:
            raise ExposureError('Refreshed device count is invalid or exceeds the configured limit; stop and inspect privately.')
        status = target_status(nodes, entities)
        if not any(status.values()) or time.monotonic() >= deadline:
            break
        time.sleep(min(2, max(0, deadline - time.monotonic())))
    summary.update(status)
    summary.update({'after_devices': after.get('deviceCount'), 'existing_identities_preserved': True,
                    'controller_fabrics_preserved': True,
                    'verified': after.get('status') == 'running' and not any(status.values()),
                    'controller_voice_test': 'not performed'})
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default=os.environ.get('MATTER_HUB_URL'), help='Existing hub base URL (or MATTER_HUB_URL).')
    parser.add_argument('--bridge', default=os.environ.get('MATTER_HUB_BRIDGE_ID'), help='Existing bridge ID (or MATTER_HUB_BRIDGE_ID).')
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument('--apply', action='store_true', help='Apply the additive plan; default only previews.')
    parser.add_argument('--max-devices', type=int, default=80, help='Maximum preview size (default 80).')
    parser.add_argument('--timeout', type=float, default=45, help='Timeout per API request in seconds.')
    parser.add_argument('--settle-seconds', type=float, default=60, help='Bounded endpoint readiness polling after apply.')
    args = parser.parse_args(argv)
    if not args.url or not args.bridge:
        parser.error('--url and --bridge, or their environment variables, are required')
    if not 1 <= args.max_devices <= 100 or not 0 < args.timeout <= 120 or not 0 <= args.settle_seconds <= 60:
        parser.error('Require max-devices 1..100, timeout (0,120], settle-seconds [0,60].')
    try:
        result = run(Client(args.url, args.timeout), args.bridge, read_manifest(args.manifest),
                     args.apply, args.max_devices, args.settle_seconds)
        print(json.dumps(result, indent=2))
        return 0 if not args.apply or result['verified'] else 1
    except ExposureError as exc:
        print(str(exc), file=sys.stderr)
        if args.apply:
            print('Writes may have partially succeeded. Read back and review before another --apply; no automatic rollback or retry.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
