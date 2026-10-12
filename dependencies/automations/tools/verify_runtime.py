#!/usr/bin/env python3
"""Check an exported Home Assistant state list against the migration contract."""

import argparse
import json
from pathlib import Path

from config_contract import ROOT, read_manifest, read_yaml


def expected_execution_mode(entry, phase):
    """Keep the historical before check; validate reviewed modes after migration."""
    if phase != 'before' and entry.get('behavior_change'):
        return read_yaml(ROOT / entry['file'])[0].get('mode', 'single')
    return entry['previous_metadata'].get('mode', 'single')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('states', type=Path, help='JSON from hass-cli -o json raw get /api/states')
    parser.add_argument('--phase', choices=['before', 'seed', 'final'], required=True)
    parser.add_argument('--before', type=Path, help='Fresh pre-migration state export for state comparison')
    args = parser.parse_args()
    states = json.loads(args.states.read_text())
    by_id = {state['entity_id']: state for state in states}
    previous = {state['entity_id']: state for state in json.loads(args.before.read_text())} if args.before else {}
    manifest = read_manifest()
    entries = manifest['automations']
    retired_entities = {e['entity_id'] for e in manifest.get('retired_automations', [])}
    assert not retired_entities & by_id.keys(), 'Retired automation entities remain in the runtime'
    expected_ids = {entry['id'] for entry in entries}
    expected_entities = {entry['entity_id'] for entry in entries}
    active_entities = {state['entity_id'] for state in states
                       if state['entity_id'].startswith('automation.') and state['state'] in {'on', 'off'}}
    assert active_entities == expected_entities, 'Available automation set changed; investigate missing or added rules'
    for entry in entries:
        entity_id = entry['entity_id']
        assert entity_id in by_id, f'{entity_id}: entity ID changed or disappeared'
        state = by_id[entity_id]
        attributes = state.get('attributes', {})
        assert state['state'] in {'on', 'off'}, f'{entity_id}: automation is unavailable'
        expected_alias = entry['alias'] if args.phase == 'final' else entry['previous_alias']
        assert attributes.get('friendly_name') == expected_alias, f'{entity_id}: unexpected display name'
        expected_id = entry['previous_id'] if args.phase == 'before' else entry['id']
        assert attributes.get('id') == expected_id, f'{entity_id}: unexpected registry identity'
        expected_mode = expected_execution_mode(entry, args.phase)
        assert attributes.get('mode') == expected_mode, f'{entity_id}: execution mode changed'
        if args.phase == 'before':
            assert attributes.get('current', 0) == 0, f'{entity_id}: action is running; recheck before reload'
        if previous:
            expected_state = entry.get('expected_state', previous[entity_id]['state']) if args.phase == 'final' else previous[entity_id]['state']
            assert state['state'] == expected_state, f'{entity_id}: enabled state changed unexpectedly'
    if args.phase != 'before':
        registered = [state for state in states if state.get('attributes', {}).get('id') in expected_ids]
        assert len(registered) == len(entries), 'Duplicate or missing migrated automation IDs'
    print(f'Runtime {args.phase} check passed for {len(entries)} automations; entity IDs are stable.')


if __name__ == '__main__':
    main()
