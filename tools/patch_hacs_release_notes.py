#!/usr/bin/env python3
"""Generate the scoped DESLOC release-notes fix for reviewed HACS 2.0.5."""

import argparse
import hashlib
from pathlib import Path

UPSTREAM_SHA256 = "0b85cdca94d1b7cade7a89cfe00c165e5b2ab8d240123b48c2e66f0a7d66b1c0"
BEFORE = '''        # Compile release notes from installed version up to the latest
        if self.installed_version in self.repository.data.published_tags:
'''
AFTER = '''        # ha-homelab: keep DESLOC's update dialog limited to its offered release.
        if self.repository.data.full_name == "ha-homelab/ha-desloc":
            latest = next(
                (release for release in self.repository.releases.objects
                 if release.tag_name == self.latest_version),
                None,
            )
            if latest is not None:
                release_notes = f"# {latest.tag_name}\\n\\n{latest.body or ''}\\n\\n"
            release_notes += (
                "[Full release history]"
                "(https://github.com/ha-homelab/ha-desloc/releases)\\n\\n"
            )
        # Preserve HACS behavior for all other repositories.
        elif self.installed_version in self.repository.data.published_tags:
'''


def patch(source: str) -> str:
    """Reject unknown input and accept only the exact original or patched file."""
    original = source
    if AFTER in source:
        if source.count(AFTER) != 1:
            raise ValueError("Unexpected patched HACS source")
        original = source.replace(AFTER, BEFORE, 1)
    if hashlib.sha256(original.encode()).hexdigest() != UPSTREAM_SHA256:
        raise ValueError("Unreviewed HACS source; review the new version before applying")
    if original.count(BEFORE) != 1:
        raise ValueError("Unexpected HACS release-notes implementation")
    return original.replace(BEFORE, AFTER, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error("Write a separate output file and retain the original for rollback")
    result = patch(args.source.read_text())
    with args.output.open("x") as output:
        output.write(result)
    print("Output SHA256:", hashlib.sha256(result.encode()).hexdigest())


if __name__ == "__main__":
    main()
