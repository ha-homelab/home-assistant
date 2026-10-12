#!/usr/bin/env python3
"""Exit successfully only when an exported HA state list has no running actions.

On failure, stdout contains only the running automation/script entity IDs.
On success, stdout is empty. Read a fresh state export immediately before reload.
"""

import argparse
import json
from pathlib import Path


def running_entity_ids(states):
    if not isinstance(states, list):
        raise ValueError('Expected a JSON list from the Home Assistant states API')
    running = set()
    for state in states:
        if not isinstance(state, dict) or not isinstance(state.get('entity_id'), str):
            raise ValueError('State export contains an invalid entity record')
        entity_id = state['entity_id']
        if not entity_id.startswith(('automation.', 'script.')):
            continue
        attributes = state.get('attributes', {})
        if not isinstance(attributes, dict):
            raise ValueError('State export contains invalid automation/script attributes')
        current = attributes.get('current', 0)
        if not isinstance(current, (int, float)):
            raise ValueError('State export contains an invalid running-action count')
        if current > 0 or (entity_id.startswith('script.') and state.get('state') == 'on'):
            running.add(entity_id)
    return sorted(running)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('states', type=Path, help='Fresh JSON from hass-cli -o json raw get /api/states')
    args = parser.parse_args()
    try:
        running = running_entity_ids(json.loads(args.states.read_text()))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    for entity_id in running:
        print(entity_id)
    return 1 if running else 0


if __name__ == '__main__':
    raise SystemExit(main())
