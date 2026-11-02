#!/usr/bin/env python3
"""Adapt the separately installed cisco_lifesize driver for local HA commands.

Private config: line, device (the native driver's SSH configuration), and
allowed_destinations. The existing driver verifies host keys and reads settings
back; this adapter preserves its call-state checks and never retries a mutation.
"""
import argparse
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import cisco_lifesize as native


ACTIONS = ("status", "call", "hangup", "radio_stop", "answer", "reject", "ringer", "volume",
           "autoanswer", "automute", "dnd", "mic")


def execute(config_path, action, value):
    config = json.loads(config_path.read_text())
    line = config["line"]
    device = native.validate_config({line: config["device"]}, config_path)[line]
    native.require(action in ACTIONS, "invalid_action")
    if action == "call":
        native.require(str(value) in config["allowed_destinations"] and str(value) != line,
                       "destination_not_allowlisted")
    if action in ("autoanswer", "automute", "dnd", "mic"):
        native.require(value in (0, 1), "invalid_boolean")
    command = "volume" if action in ("ringer", "volume") else "hangup" if action == "radio_stop" else action
    args = SimpleNamespace(command=command, extension=line, number=str(value),
                           context="ringer" if action == "ringer" else "call",
                           direction="set", value=value, steps=1, dry_run=False,
                           enabled="on" if value else "off", mode="mute" if value else "unmute")
    mutation = native.validate_action(args)
    phone = native.Phone(device, 8)
    with native.device_lock(device["host"]), phone.connection():
        observed = phone.snapshot(line)
        if action == "radio_stop":
            calls = observed["calls"]
            if not calls:
                return {"status": "ok", "changed": False}
            native.require(len(calls) == 1 and not calls[0]["incoming"] and
                           calls[0]["number"] in config.get("radio_destinations", []),
                           "active_call_is_not_radio")
        if not mutation:
            settings = phone.settings()
            calls = observed["calls"]
            music = [c for c in calls if c["state"] == "Connected" and
                     not c["incoming"] and c["number"] in config.get("radio_destinations", [])]
            return {"state": "unavailable" if not observed["registered"] else
                    "playing" if music else "idle", "registered": observed["registered"],
                    "calls": calls, "settings": settings}
        setting = args.context + "_volume" if command == "volume" else native.SETTING_COMMANDS.get(command)
        settings = phone.settings((setting,)) if setting else {}
        base = {"selected_line": line, "driver": "lifesize_ssh"}
        status = dict(base, status="ok", **observed, settings=settings)
        return native.execute_action(args, phone, observed, settings, base, status, lambda _: None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("action", choices=ACTIONS)
    parser.add_argument("value", type=int, nargs="?", default=0)
    args = parser.parse_args()
    try:
        print(json.dumps(execute(args.config, args.action, args.value)))
    except native.LifeSizeError as error:
        print(json.dumps({"state": "unavailable", "error": error.reason}))
        if args.action != "status":
            sys.exit(1)


if __name__ == "__main__":
    main()
