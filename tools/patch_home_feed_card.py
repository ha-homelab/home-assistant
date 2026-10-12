#!/usr/bin/env python3
"""Build the Home Feed Card 0.6.5 language compatibility hotfix in a new file.

HACS owns the installed asset. Keep its original file for rollback; re-evaluate
this hotfix after updates instead of applying it to an unreviewed new version.
"""

import argparse
import hashlib
from pathlib import Path

UPSTREAM_SHA256 = "7f6003b1156457b88a511b01b63977ef47fceeb9955054745597a817b222eedd"
MARKER = "// ha-homelab: Home Feed Card 0.6.5 HA language compatibility v1\n"
BEFORE = "this._language=Object.keys(e.resources)[0]"
LANGUAGE_EXPRESSION = 'e.locale?.language||e.language||Object.keys(e.resources||{})[0]||"en"'
AFTER = "this._language=" + LANGUAGE_EXPRESSION


def patch(source: str) -> str:
    """Reject unreviewed source, including a damaged previously patched file."""
    candidate = source
    already_patched = candidate.startswith(MARKER)
    if already_patched:
        candidate = candidate.removeprefix(MARKER)
        if candidate.count(AFTER) != 1:
            raise ValueError("Unexpected patched Home Feed Card source")
        candidate = candidate.replace(AFTER, BEFORE, 1)
    if hashlib.sha256(candidate.encode()).hexdigest() != UPSTREAM_SHA256:
        raise ValueError("Unexpected Home Feed Card version; review upstream before applying")
    if candidate.count(BEFORE) != 1:
        raise ValueError("Unexpected Home Feed Card language setter")
    return source if already_patched else MARKER + candidate.replace(BEFORE, AFTER, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error("Use a separate output file; retain the original for rollback")
    result = patch(args.source.read_text())
    args.output.write_text(result)
    print("Output SHA256:", hashlib.sha256(result.encode()).hexdigest())


if __name__ == "__main__":
    main()
