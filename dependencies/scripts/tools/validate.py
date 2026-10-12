#!/usr/bin/env python3
"""Validate the deployed script tree without contacting Home Assistant or devices."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

import yaml

DISPLAY_FIELDS = {'alias', 'description', 'icon', 'fields'}
SCRIPT_FIELDS = DISPLAY_FIELDS | {'sequence', 'mode', 'max', 'max_exceeded', 'variables', 'trace'}
IDENTIFIER = re.compile(r'^[a-z0-9_]+$')
SECRET_KEY = re.compile(r'^(?:password|passwd|api_key|access_token|refresh_token|token|client_secret|authorization|private_key)$', re.I)
SECRET_PATTERNS = (
    re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    re.compile(r'gh[pousr]_[A-Za-z0-9]{30,}'),
    re.compile(r'github_pat_[A-Za-z0-9_]{40,}'),
    re.compile(r'AKIA[A-Z0-9]{16}'),
    re.compile(r'eyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}'),
    re.compile(r'https?://[^\s/:]+:[^\s/@]+@'),
    re.compile(r'(?i)[?&](?:api_key|access_token|token|password)=[A-Za-z0-9._~+/%=-]{8,}'),
)

class ValidationError(ValueError):
    """A repository contract is violated."""

class StrictLoader(yaml.SafeLoader):
    """Match safe YAML loading while refusing silently overwritten keys."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict:
        self.flatten_mapping(node)
        mapping = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                duplicate = key in mapping
            except TypeError as exc:
                raise ValidationError(f'Non-scalar YAML key at line {key_node.start_mark.line + 1}') from exc
            if duplicate:
                raise ValidationError(f'Duplicate YAML key {key!r} at line {key_node.start_mark.line + 1}')
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


def secret_reference(loader: StrictLoader, node: yaml.ScalarNode) -> dict:
    """Represent secret names, never resolve credentials in repository checks."""
    name = loader.construct_scalar(node)
    if not re.fullmatch(r'[A-Za-z0-9_]+', name):
        raise ValidationError('Invalid !secret name')
    return {'__ha_secret_reference__': name}

StrictLoader.add_constructor('!secret', secret_reference)


def load_yaml(path: Path) -> Any:
    try:
        return yaml.load(path.read_text(), Loader=StrictLoader)
    except (yaml.YAMLError, ValidationError) as exc:
        # YAML exception snippets can contain credentials, so print the path only.
        if isinstance(exc, ValidationError):
            raise ValidationError(f'{path}: {exc}') from exc
        raise ValidationError(f'{path}: invalid YAML') from exc


def canonical_runtime(script: dict) -> str:
    """Ignore only top-level UI metadata; never strip fields from action payloads."""
    runtime = {key: value for key, value in script.items() if key not in DISPLAY_FIELDS}
    runtime.setdefault('mode', 'single')
    return json.dumps(runtime, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def read_scripts(root: Path) -> tuple[dict, dict]:
    config = root / 'config'
    scripts, locations = {}, {}
    if not config.is_dir():
        raise ValidationError('Missing deployable config/ directory')
    ignored = list(config.rglob('*.yml'))
    if ignored:
        raise ValidationError('Use .yaml in config/: Home Assistant directory includes ignore .yml')
    for path in sorted(config.rglob('*.yaml')):
        if path.is_symlink():
            raise ValidationError(f'Symlink is not a deployable YAML source: {path}')
        contents = load_yaml(path)
        if not isinstance(contents, dict) or not contents:
            raise ValidationError(f'{path}: expected a nonempty script mapping')
        for key, script in contents.items():
            if not isinstance(key, str) or not IDENTIFIER.fullmatch(key):
                raise ValidationError(f'{path}: invalid script object key')
            if key in scripts:
                raise ValidationError(f'Duplicate script key across files: {key}')
            if not isinstance(script, dict):
                raise ValidationError(f'{key}: expected script configuration mapping')
            unknown = set(script) - SCRIPT_FIELDS
            if unknown:
                raise ValidationError(f'{key}: unsupported script options: {sorted(unknown)}')
            if not isinstance(script.get('sequence'), list) or not script['sequence']:
                raise ValidationError(f'{key}: sequence must be a nonempty list')
            for name in ('alias', 'description', 'icon'):
                if not isinstance(script.get(name), str) or not script[name].strip():
                    raise ValidationError(f'{key}: missing {name}')
            if not script['icon'].startswith('mdi:'):
                raise ValidationError(f'{key}: expected a Material Design icon')
            if script.get('mode') not in {'single', 'restart', 'queued', 'parallel'}:
                raise ValidationError(f'{key}: set an explicit supported execution mode')
            if 'fields' in script:
                fields = script['fields']
                if not isinstance(fields, dict):
                    raise ValidationError(f'{key}: fields must be a mapping')
                for field, data in fields.items():
                    if not isinstance(data, dict) or not {'name', 'description', 'selector'} <= set(data):
                        raise ValidationError(f'{key}.{field}: fields need a name, description, and selector')
                    if field not in json.dumps(script['sequence']):
                        raise ValidationError(f'{key}.{field}: UI field is not referenced by the sequence')
            scripts[key] = script
            locations[key] = str(path.relative_to(root))
    return scripts, locations


def walk_secret_keys(node: Any, location: str) -> list[str]:
    failures = []
    if isinstance(node, dict):
        for key, value in node.items():
            child = f'{location}.{key}'
            if isinstance(key, str) and SECRET_KEY.fullmatch(key) and value:
                is_reference = isinstance(value, dict) and set(value) == {'__ha_secret_reference__'}
                is_template = isinstance(value, str) and ('{{' in value or '{%' in value)
                if not is_reference and not is_template:
                    failures.append(f'{child}: sensitive field must reference !secret')
            failures.extend(walk_secret_keys(value, child))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            failures.extend(walk_secret_keys(value, f'{location}[{index}]'))
    return failures


def scan_secrets(root: Path) -> None:
    failures = []
    for path in root.rglob('*'):
        relative = path.relative_to(root)
        if not path.is_file() or any(part in {'.git', '.venv', '__pycache__', '.pytest_cache'} for part in relative.parts):
            continue
        if path.is_symlink():
            raise ValidationError(f'Repository symlink requires explicit review: {relative}')
        if path.name in {'secrets.yaml', '.env'} or path.suffix in {'.pem', '.key', '.p12', '.pfx'}:
            failures.append(f'{relative}: credential-bearing files must not be committed')
            continue
        try:
            content = path.read_text()
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(content.splitlines(), start=1):
            if any(pattern.search(line) for pattern in SECRET_PATTERNS):
                failures.append(f'{relative}:{number}: possible credential (value suppressed)')
        if path.suffix in {'.yaml', '.yml'}:
            failures.extend(walk_secret_keys(load_yaml(path), str(relative)))
        elif path.suffix == '.json':
            try:
                failures.extend(walk_secret_keys(json.loads(content), str(relative)))
            except json.JSONDecodeError as exc:
                raise ValidationError(f'{relative}: invalid JSON') from exc
    if failures:
        raise ValidationError('\n'.join(failures))


def validate(root: Path) -> dict:
    scan_secrets(root)
    scripts, locations = read_scripts(root)
    baseline = json.loads((root / 'contracts/source-baseline.json').read_text())
    registry = json.loads((root / 'contracts/script-registry.json').read_text())
    if baseline.get('format_version') != 1 or registry.get('format_version') != 1:
        raise ValidationError('Unsupported contract format')
    expected = baseline['scripts']
    # Keep the sanitized import stable. Later reviewed behavior has an explicit contract.
    reviewed_path = root / 'contracts/reviewed-runtime.json'
    reviewed = {}
    retired = {}
    if reviewed_path.exists():
        changes = json.loads(reviewed_path.read_text())
        if changes.get('format_version') != 1 or not changes.get('change'):
            raise ValidationError('Invalid reviewed runtime contract')
        reviewed = changes['scripts']
        retired = changes.get('retired_scripts', {})
        if not set(retired) <= set(expected):
            raise ValidationError('Retirement contract contains unknown script IDs')
        if set(retired) & set(reviewed):
            raise ValidationError('A retired script cannot also have an active runtime contract')
        if any(not value.get('date') or not value.get('reason') for value in retired.values()):
            raise ValidationError('Retirement needs a date and reason')
        if not set(reviewed) <= set(expected):
            raise ValidationError('Reviewed runtime contract contains unknown script IDs')
        if any(canonical_runtime(value) == canonical_runtime(expected[key]) for key, value in reviewed.items()):
            raise ValidationError('Reviewed runtime contract contains an unchanged script')
    if baseline['source']['script_count'] != len(expected):
        raise ValidationError('Source count does not match baseline')
    if set(registry['scripts']) != set(expected) or set(scripts) != set(expected) - set(retired):
        raise ValidationError('Script identifiers changed relative to the source baseline or registry')
    aliases = set()
    for key, script in scripts.items():
        record = registry['scripts'][key]
        if record['entity_id'] != f'script.{key}':
            raise ValidationError(f'{key}: stable entity mapping changed')
        if record['file'] != locations[key]:
            raise ValidationError(f'{key}: registry file location is stale')
        for name in ('alias', 'description', 'icon'):
            if record[name] != script[name]:
                raise ValidationError(f'{key}: registry {name} is stale')
        if script['alias'] in aliases:
            raise ValidationError(f'{key}: duplicate display alias')
        aliases.add(script['alias'])
        if canonical_runtime(script) != canonical_runtime(reviewed.get(key, expected[key])):
            raise ValidationError(f'{key}: executable configuration differs from source baseline')
    digest = hashlib.sha256(''.join(key + canonical_runtime(scripts[key]) for key in sorted(scripts)).encode()).hexdigest()
    return {'script_count': len(scripts), 'yaml_file_count': len(set(locations.values())), 'runtime_sha256': digest, 'status': 'passed'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        print(json.dumps(validate(args.root.resolve()), indent=2))
    except (ValidationError, KeyError, OSError, json.JSONDecodeError) as exc:
        print(f'Validation failed: {exc}', file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
