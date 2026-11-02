#!/usr/bin/env python3
"""Synchronize the LifeSize HA radio controls with a reviewed PBX catalog."""
import argparse
import copy
import json
from pathlib import Path
import re

import yaml


def sync_catalog(package, catalog):
    stations = catalog.get("stations", {})
    if not stations:
        raise ValueError("The radio catalog must not be empty")
    sources = {}
    numbers = set()
    for station in stations.values():
        number = station.get("extension", "")
        name = station.get("name", "").strip()
        if not isinstance(number, str) or not re.fullmatch(r"7[0-9]{2}", number) or not name:
            raise ValueError("Radio entries need a name and reviewed 7xx extension")
        if number in numbers:
            raise ValueError("Duplicate radio extension")
        numbers.add(number)
        sources[f"{name} · {number}"] = number
    sources = dict(sorted(sources.items(), key=lambda item: item[1]))
    result = copy.deepcopy(package)
    result["input_select"]["lifesize_222_station"]["options"] = list(sources)
    destination = result["input_select"]["lifesize_222_destination"]["options"]
    destination.extend(number for number in sources.values() if number not in destination)
    radio = result["script"]["lifesize_222_radio"]
    radio["fields"]["source"]["selector"]["select"]["options"] = list(sources)
    mappings = [step["variables"] for step in radio["sequence"]
                if "stations" in step.get("variables", {})]
    if len(mappings) != 1:
        raise ValueError("Expected one existing guarded radio mapping")
    mappings[0]["stations"] = sources
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = sync_catalog(yaml.safe_load(args.package.read_text()), json.loads(args.catalog.read_text()))
    args.output.touch(mode=0o600, exist_ok=True)
    args.output.chmod(0o600)
    args.output.write_text(yaml.safe_dump(result, sort_keys=False, allow_unicode=True, width=120))


if __name__ == "__main__":
    main()
