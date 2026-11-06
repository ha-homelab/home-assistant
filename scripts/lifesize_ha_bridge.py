#!/usr/bin/env python3
"""Adapt the separately installed cisco_lifesize driver for local HA commands.

Private config: line, device (the native driver's SSH configuration), and
allowed_destinations. The existing driver verifies host keys and reads settings
back; this adapter preserves its call-state checks and never retries a mutation.
"""
import argparse
from contextlib import contextmanager, ExitStack
import json
from pathlib import Path
import re
import sys
import time
from types import SimpleNamespace

import cisco_lifesize as native


ACTIONS = ("status", "call", "hangup", "radio_play", "radio_stop", "answer", "reject", "ringer", "volume",
           "autoanswer", "automute", "dnd", "mic")
MUTATION_LOCK_WAIT = 25.0
LOCK_RETRY_INTERVAL = 0.2


@contextmanager
def request_lock(host, mutation):
    """Wait for a status poll before mutation, never retry a dispatched command."""
    deadline = time.monotonic() + (MUTATION_LOCK_WAIT if mutation else 0)
    with ExitStack() as stack:
        while True:
            try:
                stack.enter_context(native.device_lock(host))
                break
            except native.LifeSizeError as error:
                remaining = deadline - time.monotonic()
                if (not mutation or error.reason != "lifesize_command_already_running"
                        or remaining <= 0):
                    raise
                time.sleep(min(LOCK_RETRY_INTERVAL, remaining))
        # Keep the caller outside the retry handler. A failed snapshot, command,
        # or readback must release the lock and propagate without another send.
        yield


def radio_number(call):
    """Accept local extensions, including the native phone's sip: prefix."""
    match = re.fullmatch(r"(?:sip:)?([0-9]{3,8})", str(call.get("number", "")), re.IGNORECASE | re.ASCII)
    return match[1] if match else None


def execute(config_path, action, value):
    config = json.loads(config_path.read_text())
    line = config["line"]
    device = native.validate_config({line: config["device"]}, config_path)[line]
    native.require(action in ACTIONS, "invalid_action")
    if action in ("call", "radio_play"):
        native.require(str(value) in config["allowed_destinations"] and str(value) != line,
                       "destination_not_allowlisted")
    if action == "radio_play":
        native.require(str(value) in config.get("radio_destinations", []), "destination_is_not_radio")
    if action in ("autoanswer", "automute", "dnd", "mic"):
        native.require(value in (0, 1), "invalid_boolean")
    command = ("volume" if action in ("ringer", "volume") else "hangup" if action == "radio_stop"
               else "call" if action == "radio_play" else action)
    args = SimpleNamespace(command=command, extension=line, number=str(value),
                           context="ringer" if action == "ringer" else "call",
                           direction="set", value=value, steps=1, dry_run=False,
                           enabled="on" if value else "off", mode="mute" if value else "unmute")
    mutation = native.validate_action(args)
    phone = native.Phone(device, 8)
    with request_lock(device["host"], mutation), phone.connection():
        observed = phone.snapshot(line)
        if action == "radio_play" and observed["calls"]:
            calls = observed["calls"]
            native.require(len(calls) == 1 and not calls[0]["incoming"] and
                           radio_number(calls[0]) in config.get("radio_destinations", []),
                           "active_call_is_not_radio")
            if radio_number(calls[0]) == str(value) and calls[0]["state"] == "Connected":
                return {"status": "ok", "changed": False}
            stop_args = SimpleNamespace(**vars(args))
            stop_args.command = "hangup"
            base = {"selected_line": line, "driver": "lifesize_ssh"}
            native.execute_action(stop_args, phone, observed, {}, base,
                                  dict(base, status="ok", **observed), lambda _: None)
            # Wait only for that radio call to end. Never hang up a new call,
            # and never retry an uncertain native mutation.
            previous_id = calls[0]["id"]
            deadline = time.monotonic() + 8
            while True:
                observed = phone.snapshot(line)
                if not observed["calls"]:
                    break
                native.require(all(c["id"] == previous_id for c in observed["calls"]),
                               "lifesize_call_context_changed")
                native.require(time.monotonic() < deadline, "radio_hangup_not_confirmed")
                time.sleep(0.25)
        if action == "radio_stop":
            calls = observed["calls"]
            if not calls:
                return {"status": "ok", "changed": False}
            native.require(len(calls) == 1 and not calls[0]["incoming"] and
                           radio_number(calls[0]) in config.get("radio_destinations", []),
                           "active_call_is_not_radio")
        if not mutation:
            settings = phone.settings()
            calls = observed["calls"]
            music = [c for c in calls if c["state"] == "Connected" and
                     not c["incoming"] and radio_number(c) in config.get("radio_destinations", [])]
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
