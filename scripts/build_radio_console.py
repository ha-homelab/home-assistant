#!/usr/bin/env python3
"""Render a private radio console from a reviewed catalog and live player metadata."""
import argparse
import json
import os
from pathlib import Path


def build_console(catalog, targets, phone_limit=4):
    players = [{key: target[key] for key in ("entity", "name", "icon") if key in target}
               for target in targets]
    if len({p["entity"] for p in players}) != len(players):
        raise ValueError("Duplicate player entities")
    stations = []
    for key, station in catalog["stations"].items():
        item = {"id": key, "name": station["name"], "sources": {}}
        # A resolver endpoint is JSON, not audio; HLS needs a capable backend.
        if not station.get("resolver") and not station.get("hls"):
            item["url"] = station["url"]
        for target in targets:
            if int(target.get("caps", 0)) & 512 and item.get("url"):
                continue
            number, name = station["extension"], station["name"]
            labels = (f"{number} — {name}", f"{name} · {number}")
            source = next((label for label in target.get("source_list", []) if label in labels), None)
            if source:
                item["sources"][target["entity"]] = source
        stations.append(item)
    groups = [{"name": group, "entities": [t["entity"] for t in targets if t["group"] == group]}
              for group in dict.fromkeys(t["group"] for t in targets)]
    phones = [t["entity"] for t in targets if t.get("kind") == "phone"]
    return {"type": "custom:radio-console-card", "title": "Radio & speakers",
            "players": players, "stations": stations, "groups": groups,
            "limits": [{"name": "Phone sessions", "entities": phones, "max": phone_limit}] if phones else [],
            "grid_options": {"columns": "full"}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("targets", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.resolve() in (args.catalog.resolve(), args.targets.resolve()):
        parser.error("Output must not overwrite a source file")
    result = build_console(json.loads(args.catalog.read_text()), json.loads(args.targets.read_text()))
    descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as output:
        os.fchmod(output.fileno(), 0o600)
        json.dump(result, output, indent=2)
        output.write("\n")


if __name__ == "__main__":
    main()
