#!/usr/bin/env python3
"""Prepare a private Lovelace layout from fresh exports; never change live HA."""
import argparse
import json
import os
from pathlib import Path

from reorganize_media_cerbo import migrate_cerbo_view
from reorganize_media_players import migrate_media_view


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("main", type=Path, help="Fresh main dashboard JSON")
    parser.add_argument("cerbo", type=Path, help="Existing Cerbo dashboard JSON")
    parser.add_argument("media_manifest", type=Path, help="Private player/preset manifest")
    parser.add_argument("output", type=Path, help="New private main dashboard JSON")
    args = parser.parse_args()
    if args.output.resolve() in {p.resolve() for p in (args.main, args.cerbo, args.media_manifest)}:
        parser.error("Output must not overwrite an input export")
    result = migrate_cerbo_view(json.loads(args.main.read_text()), json.loads(args.cerbo.read_text()))
    result = migrate_media_view(result, json.loads(args.media_manifest.read_text()))
    descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        os.fchmod(stream.fileno(), 0o600)
        json.dump(result, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
