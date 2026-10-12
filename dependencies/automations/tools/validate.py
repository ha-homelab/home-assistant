#!/usr/bin/env python3
"""Validate identities, ordering, YAML structure and imported runtime behavior."""

import argparse
import json
import re
from pathlib import Path

from config_contract import ROOT, fingerprint, read_manifest, read_yaml, seed_value, validate_inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, help='Private original /config snapshot for independent comparison')
    args = parser.parse_args()
    manifest = read_manifest()
    entries = manifest['automations']
    files = sorted(str(path.relative_to(ROOT)) for path in (ROOT / 'config').rglob('*.yaml'))
    validate_inventory(manifest, files)
    ids, aliases, entities = set(), set(), set()
    baseline_cache = {}
    for entry in entries:
        path = ROOT / entry['file']
        config = read_yaml(path)
        assert isinstance(config, list) and len(config) == 1, f'{path}: expected one-item automation list'
        value = config[0]
        assert isinstance(value, dict), f'{path}: automation must be a mapping'
        for field, seen in [('id', ids), ('alias', aliases)]:
            assert isinstance(value.get(field), str) and value[field].strip(), f'{path}: missing {field}'
            assert value[field] == entry[field], f'{path}: {field} differs from migration map'
            assert value[field] not in seen, f'{path}: duplicate {field}'
            seen.add(value[field])
        assert entry['entity_id'] not in entities, f'{path}: duplicate existing entity ID'
        entities.add(entry['entity_id'])
        if entry['previous_id'] is not None:
            assert value['id'] == entry['previous_id'], f'{path}: existing registry identity changed'
        else:
            assert re.fullmatch(r'ha_homelab_[a-z0-9_]+', value['id']), f'{path}: invalid new identity'
        assert isinstance(value.get('description'), str) and value['description'].strip(), f'{path}: missing description'
        assert value.get('mode') in {'single', 'restart', 'queued', 'parallel'}, f'{path}: invalid mode'
        assert value.get('trace', {}).get('stored_traces') == 5, f'{path}: unexpected trace retention'
        if 'use_blueprint' in value:
            blueprint = value['use_blueprint']
            assert blueprint['path'] == 'ha_homelab/motion_light_off.yaml', f'{path}: unexpected blueprint'
            inputs = blueprint['input']
            assert inputs['motion_triggers'] and inputs['target_entities'], f'{path}: empty motion/light inputs'
            for trigger in inputs['motion_triggers']:
                assert trigger.get('trigger', trigger.get('platform')) == 'state' and trigger['to'] == 'off'
                assert trigger.get('entity_id'), f'{path}: missing motion entity'
                duration = trigger.get('for', {})
                assert isinstance(duration, dict) and all(
                    key in {'days', 'hours', 'minutes', 'seconds', 'milliseconds'}
                    and isinstance(number, (int, float)) and number >= 0
                    for key, number in duration.items()
                ), f'{path}: inactivity durations must be static nonnegative mappings'
            assert all(entity.startswith(('light.', 'switch.')) for entity in inputs['target_entities'])
        else:
            assert 'triggers' in value and 'actions' in value, f'{path}: missing trigger/action section'
        assert fingerprint(value) == entry['behavior_sha256'], f'{path}: runtime behavior differs from imported baseline'
        seeded = seed_value(value, entry)
        assert seeded['alias'] == entry['previous_alias'], f'{path}: seed changed the original alias'
        assert fingerprint(seeded) == entry['behavior_sha256'], f'{path}: seed changed runtime behavior'
        if args.baseline:
            source = args.baseline / entry['source_file']
            if source not in baseline_cache:
                baseline_cache[source] = read_yaml(source)
            original = baseline_cache[source][entry['source_index']]
            assert fingerprint(original) == entry.get('imported_behavior_sha256', entry['behavior_sha256']), f'{path}: independent original comparison failed'
            if not entry.get('behavior_change'):
                original_with_id = dict(original, id=entry['id'])
                assert seeded == original_with_id, f'{path}: seed changes more than the new ID'
    for archived in manifest['inactive_sources']:
        path = ROOT / archived['file']
        assert path.is_file() and path.name.endswith('.yaml.disabled'), f'{path}: archive is missing or active'
        assert not path.is_relative_to(ROOT / 'config'), f'{path}: archive is in the active include tree'
    print(json.dumps({'automations': len(entries), 'preserved_existing_ids': manifest['preserved_existing_ids'],
                      'new_ids': len(entries) - manifest['preserved_existing_ids'],
                      'reviewed_behavior_changes': sum(bool(e.get('behavior_change')) for e in entries),
                      'seed': 'legacy aliases retained', 'independent_baseline_checked': bool(args.baseline)}))


if __name__ == '__main__':
    main()
