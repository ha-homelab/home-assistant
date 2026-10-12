#!/usr/bin/env python3
"""Prepare an exact local quality policy from real Energy IDs, never redactions.

Output may contain private entity IDs. Keep it outside Git alongside the private
runtime export. The immutable checked-in base profile defines expected coverage;
runtime discovery can add configured Energy sources but cannot remove coverage.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

from verify_recorder import timestamp, validate_policy

ROOT = Path(__file__).resolve().parents[1]
ENERGY_FIELDS = {"stat_energy_from", "stat_energy_to", "stat_consumption"}


def energy_ids(value):
    """Select actual energy/water counters, not price or generated cost stats."""
    found = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ENERGY_FIELDS and item is not None:
                if not isinstance(item, str) or not item.startswith("sensor."):
                    raise ValueError("Configured non-sensor Energy statistic needs an explicit policy")
                found.add(item)
            elif isinstance(item, (dict, list)):
                found.update(energy_ids(item))
    elif isinstance(value, list):
        for item in value:
            found.update(energy_ids(item))
    return found


def prepare(base, runtime, *, exclusion_entities=None, exclusion_cutoff=None,
            retention_entities=None, retention_cutoff=None):
    validate_policy(base)
    result = deepcopy(base)
    energy = runtime.get("energy")
    if (not isinstance(energy, dict) or not isinstance(energy.get("energy_sources"), list)
            or not isinstance(energy.get("device_consumption"), list)):
        raise ValueError("A complete Energy preference export is required")
    sources = energy_ids(energy)
    if not sources:
        raise ValueError("Configured Energy coverage must not be empty")
    states = runtime.get("states")
    if not isinstance(states, list):
        raise ValueError("A runtime states export is required")
    by_id = {}
    for state in states:
        if not isinstance(state, dict) or not isinstance(state.get("entity_id"), str):
            raise ValueError("Malformed runtime state")
        if state["entity_id"] in by_id:
            raise ValueError("Duplicate runtime entity")
        by_id[state["entity_id"]] = state
    for entity in sorted(sources):
        if entity not in by_id:
            raise ValueError("Configured Energy source is absent from runtime; investigate before continuing")
        if by_id[entity].get("attributes", {}).get("state_class") not in ("total", "total_increasing"):
            raise ValueError("Configured Energy source has no supported cumulative state class")
        required = {
            "runtime_kind": "numeric", "max_reported_age_seconds": None,
            "raw_required": True, "statistics": "total",
        }
        if entity in result["entities"]:
            rule = result["entities"][entity]
            if any(rule[key] != required[key] for key in ("runtime_kind", "raw_required", "statistics")):
                raise ValueError("Energy source conflicts with the immutable base policy")
        else:
            result["entities"][entity] = required
    for name, entities, cutoff in (
        ("exclusions", exclusion_entities, exclusion_cutoff),
        ("retention", retention_entities, retention_cutoff),
    ):
        if entities is None and cutoff is None:
            continue
        if not entities or timestamp(cutoff) is None:
            raise ValueError("Boundary checks require an exact scope and fixed cutoff")
        result[name] = {"entity_ids": sorted(entities), "cutoff_ts": timestamp(cutoff)}
    validate_policy(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=ROOT / "docs/recorder-quality-policy.json")
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--exclusion-entities", type=Path, help="JSON array of exact IDs")
    parser.add_argument("--exclusion-cutoff", help="Fixed effective activation time in UTC")
    parser.add_argument("--retention-entities", type=Path, help="JSON array of exact IDs")
    parser.add_argument("--retention-cutoff", help="Fixed purge request time minus keep_days")
    args = parser.parse_args()
    try:
        result = prepare(
            json.loads(args.base.read_text()), json.loads(args.runtime.read_text()),
            exclusion_entities=json.loads(args.exclusion_entities.read_text()) if args.exclusion_entities else None,
            exclusion_cutoff=args.exclusion_cutoff,
            retention_entities=json.loads(args.retention_entities.read_text()) if args.retention_entities else None,
            retention_cutoff=args.retention_cutoff,
        )
    except (ValueError, TypeError, KeyError, OSError) as error:
        # No input values or file contents in failures.
        print(json.dumps({"quality_passed": False, "policy_error_type": type(error).__name__}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
