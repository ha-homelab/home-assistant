#!/usr/bin/env python3
"""Prepare a private Lovelace layout from fresh exports; never change live HA."""
import argparse
import json
from pathlib import Path

if __package__:
    from .private_output import UnsafeOutputError, private_output
    from .reorganize_media_cerbo import migrate_cerbo_view
    from .reorganize_media_players import migrate_media_view
else:
    from private_output import UnsafeOutputError, private_output
    from reorganize_media_cerbo import migrate_cerbo_view
    from reorganize_media_players import migrate_media_view


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("main", type=Path, help="Fresh main dashboard JSON")
    parser.add_argument("cerbo", type=Path, help="Existing Cerbo dashboard JSON")
    parser.add_argument("media_manifest", type=Path, help="Private player/preset manifest")
    parser.add_argument("output", type=Path, help="New private main dashboard JSON")
    args = parser.parse_args()
    result = migrate_cerbo_view(json.loads(args.main.read_text()), json.loads(args.cerbo.read_text()))
    result = migrate_media_view(result, json.loads(args.media_manifest.read_text()))
    try:
        with private_output(args.output, (args.main, args.cerbo, args.media_manifest)) as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
    except UnsafeOutputError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
