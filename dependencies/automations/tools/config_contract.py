"""Read YAML and compare the behavior of the imported automations."""

import copy
import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
METADATA = frozenset({'id', 'alias', 'description', 'trace'})
TOP_LEVEL_ALIASES = {'trigger': 'triggers', 'condition': 'conditions', 'action': 'actions'}


class UniqueKeyLoader(yaml.SafeLoader):
    """Reject duplicate mapping keys instead of silently discarding one."""


def unique_mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ValueError(f'duplicate YAML key {key!r} on line {key_node.start_mark.line + 1}')
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def read_yaml(path):
    return yaml.load(Path(path).read_text(), Loader=UniqueKeyLoader)


def behavior(value):
    """Ignore reviewed metadata and normalize only documented equivalent defaults."""
    result = copy.deepcopy(value)
    for key in METADATA:
        result.pop(key, None)
    result.setdefault('mode', 'single')
    for old, new in TOP_LEVEL_ALIASES.items():
        if old in result:
            if new in result:
                raise ValueError(f'both {old} and {new} are present')
            result[new] = result.pop(old)
    return result


def fingerprint(value):
    canonical = json.dumps(behavior(value), sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(canonical.encode()).hexdigest()


def read_manifest():
    return json.loads((ROOT / 'migration/automations.json').read_text())


def validate_inventory(manifest, files):
    """Allow only explicit retirements from the original 130-rule inventory."""
    active = manifest['automations']
    retired = manifest.get('retired_automations', [])
    original = active + retired
    assert len(active) == manifest['automation_count'], 'Unexpected automation count'
    assert sorted(e['order'] for e in original) == list(range(1, 131)), 'Original automation inventory changed'
    for key in ('id', 'entity_id', 'file'):
        assert len({e[key] for e in original}) == 130, f'Duplicate original {key}'
    assert files == [e['file'] for e in active], 'Include order or file inventory changed'
    assert [e['order'] for e in active] == sorted(e['order'] for e in active), 'Registration order changed'
    for entry in retired:
        retirement = entry.get('retirement', {})
        assert retirement.get('date') and retirement.get('reason'), 'Retirement needs a date and reason'


def seed_value(value, entry):
    """Use original aliases and stable identities with reviewed current behavior."""
    seeded = copy.deepcopy(value)
    for key in (*METADATA, 'mode'):
        seeded.pop(key, None)
    seeded.update(entry['previous_metadata'])
    # The identity seed keeps legacy names, not superseded execution behavior.
    # A reviewed mode change must survive just like its current actions do.
    if entry.get('behavior_change'):
        seeded['mode'] = value.get('mode', 'single')
    seeded['id'] = entry['id']
    for old, new in TOP_LEVEL_ALIASES.items():
        if old in entry['previous_top_level_keys'] and new in seeded:
            seeded[old] = seeded.pop(new)
    return seeded
