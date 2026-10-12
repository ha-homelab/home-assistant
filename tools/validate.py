#!/usr/bin/env python3
"""Validate managed YAML, include closure and credential boundaries."""
from pathlib import Path
import re
import sys
from ha_yaml import read, resolve

ROOT = Path(__file__).resolve().parents[1]


def main():
    files = sorted((ROOT / "config").rglob("*.yaml"))
    for path in files:
        read(path)
        text = path.read_text()
        for pattern in (
            r"(?i)(?:password|client_secret|api_key|access_token|db_url)\s*:\s*(?![!\s])\S+",
            r"(?i)https?://[^\s/]+:[^\s/]+@",
            r"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})",
            r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----",
        ):
            if re.search(pattern, text):
                raise ValueError(f"Possible credential literal in {path.relative_to(ROOT)}")
    config = resolve(ROOT / "config/configuration.yaml", permit_missing_components=True)
    assert config["input_number"].keys() == {"nightime"}, "Do not activate formerly shadowed helpers"
    assert config["recorder"]["db_url"] == {"!secret": "recorder_db_url"}
    assert config["recorder"]["purge_keep_days"] == 28
    assert "purge_interval" not in config["recorder"]
    assert config["homeassistant"]["time_zone"] == "America/Los_Angeles"
    print(f"Validated {len(files)} YAML files; includes, duplicate keys and credential checks passed")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, AssertionError) as error:
        print(error, file=sys.stderr)
        raise SystemExit(1)
