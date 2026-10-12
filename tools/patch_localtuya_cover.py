#!/usr/bin/env python3
"""Apply the bounded LocalTuya 2026.07.0 partial-position hotfix to a copy.

Downloaded HACS source and device credentials are deliberately not vendored.
Pass an unmodified cover.py and an output path; deploy only after testing it.
"""

import argparse
import hashlib
from pathlib import Path

MARKER = "# ha-homelab: tolerate missing absolute cover positions (v1)\n"

REPLACEMENTS = (
    (
        "        self._current_cover_position = 0\n",
        "        self._current_cover_position = (\n"
        "            None if self._config[CONF_POSITIONING_MODE] == MODE_SET_POSITION\n"
        "            and self.has_config(CONF_CURRENT_POSITION_DP) else 0\n"
        "        )\n",
    ),
    ("        self._set_new_position = int | None\n", "        self._set_new_position = None\n"),
    (
        "        if state in (STATE_SET_CLOSING, STATE_SET_OPENING):\n",
        "        if state in (STATE_SET_CLOSING, STATE_SET_OPENING) and curr_pos is not None:\n",
    ),
    (
        "    def is_closed(self):\n        \"\"\"Return if the cover is closed or not.\"\"\"\n",
        "    def is_closed(self):\n        \"\"\"Return if the cover is closed or not.\"\"\"\n"
        "        if self.current_cover_position is None:\n            return None\n",
    ),
    (
        "            if self._position_inverted:\n                curr_pos = 100 - curr_pos\n\n"
        "            self._current_cover_position = curr_pos\n",
        "            # Command-only packets are valid. Keep the last observed position;\n"
        "            # an absent first observation must remain unknown, never 0%.\n"
        "            if isinstance(curr_pos, (int, float)) and 0 <= curr_pos <= 100:\n"
        "                if self._position_inverted:\n                    curr_pos = 100 - curr_pos\n"
        "                self._current_cover_position = curr_pos\n",
    ),
    (
        "            pos_diff = position - curr_pos\n",
        "            if curr_pos is None:\n"
        "                # Absolute targets work without a known starting position.\n"
        "                # Do not invent either progress or movement direction.\n"
        "                self._current_state_action = STATE_STOPPED\n"
        "                self.schedule_update_ha_state()\n                return\n"
        "            pos_diff = position - curr_pos\n",
    ),
)


def patch(source: str) -> str:
    if source.startswith(MARKER):
        return source
    result = source
    for before, after in REPLACEMENTS:
        if result.count(before) != 1:
            raise ValueError("Unexpected LocalTuya source; inspect the new version before applying")
        result = result.replace(before, after, 1)
    result = MARKER + result
    compile(result, "localtuya/cover.py", "exec")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error("Use a separate output file; retain the original for rollback")
    source = args.source.read_text()
    result = patch(source)
    args.output.write_text(result)
    print("Input SHA256:", hashlib.sha256(source.encode()).hexdigest())
    print("Output SHA256:", hashlib.sha256(result.encode()).hexdigest())


if __name__ == "__main__":
    main()
