#!/usr/bin/env python3
"""Render the one-time identity migration stage without contacting Home Assistant."""

import argparse
from pathlib import Path

import yaml

from config_contract import ROOT, read_manifest, read_yaml, seed_value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path, help='New or empty destination, outside the active config/ tree')
    args = parser.parse_args()
    output = args.output.resolve()
    if output == ROOT / 'config' or output.is_relative_to(ROOT / 'config'):
        parser.error('seed output must not overwrite final configuration')
    if output.exists() and any(output.iterdir()):
        parser.error('seed output directory must be empty')
    output.mkdir(parents=True, exist_ok=True)
    manifest = read_manifest()
    for entry in manifest['automations']:
        value = read_yaml(ROOT / entry['file'])[0]
        seeded = seed_value(value, entry)
        destination = output / Path(entry['file']).relative_to('config')
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text('# One-time identity seed: legacy alias and stable ID with reviewed current behavior.\n'
                               + yaml.safe_dump([seeded], allow_unicode=True, sort_keys=False, width=100))
    print(f'Rendered {manifest["automation_count"]} identity seed files to {output}')


if __name__ == '__main__':
    main()
