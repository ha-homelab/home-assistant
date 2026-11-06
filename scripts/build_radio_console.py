#!/usr/bin/env python3
"""Render a private radio console from a reviewed catalog and live player metadata."""
import argparse
import json
from pathlib import Path

if __package__:
    from .private_output import UnsafeOutputError, private_output
else:
    from private_output import UnsafeOutputError, private_output


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
            # Phones should use reviewed PBX presets, including their resolver
            # and port policy; arbitrary URLs remain a separate player route.
            if target.get("kind") != "phone" and int(target.get("caps", 0)) & 512 and item.get("url"):
                continue
            number, name = station["extension"], station["name"]
            labels = (f"{number} — {name}", f"{name} · {number}")
            source = next((label for label in target.get("source_list", []) if label in labels), None)
            if source:
                item["sources"][target["entity"]] = source
            elif target.get("kind") == "phone":
                raise ValueError("Refresh phone source inventory before building the radio console")
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
    result = build_console(json.loads(args.catalog.read_text()), json.loads(args.targets.read_text()))
    try:
        with private_output(args.output, (args.catalog, args.targets)) as output:
            json.dump(result, output, indent=2)
            output.write("\n")
    except UnsafeOutputError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
