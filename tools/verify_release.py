#!/usr/bin/env python3
"""Verify exported runtime identities and metadata without invoking device actions."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from ha_yaml import read

ROOT = Path(__file__).resolve().parents[1]


def package_definitions(root):
    """Read declared root additions without weakening the child library contract."""
    automations, scripts = {}, {}
    package_root = root / "config/packages"
    for path in sorted(package_root.rglob("*.yaml")):
        if any(part.startswith(".") for part in path.relative_to(package_root).parts):
            continue
        package = read(path)
        assert isinstance(package, dict), f"{path}: package must be a mapping"
        rules = package.get("automation", [])
        if isinstance(rules, dict):
            rules = [rules]
        for config in rules:
            identity = config.get("id")
            assert isinstance(identity, str) and identity, f"{path}: package automation needs a stable string ID"
            assert identity not in automations, f"Duplicate package automation ID: {identity}"
            automations[identity] = execution_metadata(root, "automation", config)
        for key, config in package.get("script", {}).items():
            entity = f"script.{key}"
            assert entity not in scripts, f"Duplicate package script entity: {entity}"
            scripts[entity] = execution_metadata(root, "script", config)
    return automations, scripts


def execution_metadata(root, domain, config):
    """Blueprint scripts inherit their execution mode unless overridden."""
    effective = {}
    if blueprint := config.get("use_blueprint"):
        base = (root / "config/blueprints" / domain).resolve()
        path = (base / blueprint["path"]).resolve()
        assert path.is_relative_to(base), f"Blueprint path escapes {base}"
        effective.update(read(path))
    effective.update(config)
    assert isinstance(effective.get("alias"), str), "Package entities must declare an alias"
    return {"alias": effective["alias"], "mode": effective.get("mode", "single")}


def index_states(states):
    indexed = {state["entity_id"]: state for state in states}
    assert len(indexed) == len(states), "Duplicate runtime entity IDs"
    return indexed


def expected_display_name(entity, config, entity_registry=None):
    """Honor a user override only when registry evidence confirms the source name."""
    entry = (entity_registry or {}).get(entity, {})
    if entry.get("name") is not None:
        assert entry.get("platform") == entity.split(".")[0], f"{entity}: unexpected registry platform"
        assert entry.get("original_name") == config["alias"], f"{entity}: configured name differs from registry"
        return entry["name"]
    return config["alias"]


def verify_metadata(entity, state, config, entity_registry=None):
    assert state["state"] in {"on", "off"}, f"{entity}: entity is unavailable"
    assert state.get("attributes", {}).get("friendly_name") == expected_display_name(entity, config, entity_registry), f"{entity}: unexpected display name"
    assert state.get("attributes", {}).get("mode") == config["mode"], f"{entity}: changed execution mode"


def verify_package_automations(current, before, definitions):
    for identity, config in definitions.items():
        matches = [state for entity, state in current.items()
                   if entity.startswith("automation.") and state.get("attributes", {}).get("id") == identity]
        assert len(matches) == 1, f"{identity}: duplicate or missing package automation ID"
        state = matches[0]
        entity = state["entity_id"]
        verify_metadata(entity, state, config)
        previous = [old for key, old in before.items()
                    if key.startswith("automation.") and old.get("attributes", {}).get("id") == identity]
        assert len(previous) <= 1, f"{identity}: duplicate package automation ID in baseline"
        if previous:
            assert previous[0]["entity_id"] == entity, f"{identity}: package entity ID changed"
            assert previous[0]["state"] == state["state"], f"{entity}: enabled state changed"
        else:
            assert entity not in before, f"{entity}: existing automation registry identity changed"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("states", type=Path)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--phase", choices=("seed", "final"), required=True)
    parser.add_argument("--entity-registry", type=Path, help="Fresh entity-registry export to verify user display-name overrides")
    args = parser.parse_args()
    automations = ROOT / "dependencies/automations"
    scripts = ROOT / "dependencies/scripts"
    current = index_states(json.loads(args.states.read_text()))
    before = index_states(json.loads(args.before.read_text()))
    entity_registry = index_states(json.loads(args.entity_registry.read_text())) if args.entity_registry else {}
    package_automations, package_scripts = package_definitions(ROOT)
    verify_package_automations(current, before, package_automations)
    # The child verifier still receives every other state, including unknown additions.
    # Matching a name or a prefix never exempts an entity from its strict contract.
    with tempfile.TemporaryDirectory(prefix="ha-runtime-library-") as directory:
        filtered = []
        for name, states in (("current", current), ("before", before)):
            path = Path(directory) / f"{name}.json"
            path.write_text(json.dumps([
                state for entity, state in states.items()
                if not (entity.startswith("automation.")
                        and state.get("attributes", {}).get("id") in package_automations)
            ]))
            filtered.append(path)
        subprocess.run([sys.executable, str(automations / "tools/verify_runtime.py"), str(filtered[0]), "--phase", args.phase, "--before", str(filtered[1])], check=True)
    previous_names = {key for key in before if key.startswith("script.")}
    current_names = {key for key in current if key.startswith("script.")}
    additions = package_scripts.keys() - previous_names
    registry = json.loads((scripts / "contracts/script-registry.json").read_text())["scripts"]
    reviewed_path = scripts / 'contracts/reviewed-runtime.json'
    retirements = json.loads(reviewed_path.read_text()).get('retired_scripts', {}) if reviewed_path.exists() else {}
    assert set(retirements) <= set(registry), 'Unknown script retirement'
    assert all(r.get('date') and r.get('reason') for r in retirements.values()), 'Unexplained script retirement'
    retired_entities = {registry[key]['entity_id'] for key in retirements}
    assert not retired_entities & package_scripts.keys(), 'Retired script conflicts with a package'
    assert current_names == (previous_names - retired_entities) | package_scripts.keys(), "Script entity names changed outside declared packages and retirements"
    previous_scripts = {key for key, state in before.items() if key.startswith("script.") and state["state"] in {"on", "off"}}
    current_scripts = {key for key, state in current.items() if key.startswith("script.") and state["state"] in {"on", "off"}}
    assert current_scripts == (previous_scripts - retired_entities) | additions, "Available script entities changed"
    registry = {key: entry for key, entry in registry.items() if key not in retirements}
    assert not package_scripts.keys() & {entry["entity_id"] for entry in registry.values()}, "Package script overrides a library script"
    for key, entry in registry.items():
        entity = entry["entity_id"]
        state = current[entity]
        config = read(scripts / entry["file"])[key]
        assert state["attributes"].get("friendly_name") == expected_display_name(entity, config, entity_registry), f"{entity}: unexpected display name"
        assert state["attributes"].get("mode") == config["mode"], f"{entity}: changed execution mode"
    for entity, config in package_scripts.items():
        verify_metadata(entity, current[entity], config, entity_registry)
    print(f"Verified {len(registry)} folder scripts, {len(package_scripts)} package scripts and {len(package_automations)} package automations; {len(additions)} declared script additions")


if __name__ == "__main__":
    main()
