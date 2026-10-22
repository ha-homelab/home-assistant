#!/usr/bin/env python3
"""Generate a private, native Lovelace Roomba fleet view without contacting HA.

Input: {"states": [...], "profiles": [{"entity": "vacuum.example", "name":
"Example", "model": "960", "battery": "sensor.example_battery", "network":
"binary_sensor.example_network", "statistics": ["sensor.example_missions"]}]}.
Optional profile keys: charging, bin_full, dock_power, last_recovery, telemetry,
capability_note, and map. A map requires verified:true plus either an image/
camera entity or a local navigation_path. No map coordinates or tokens are
copied from the inventory. Existing dashboard content is preserved by the merge.
Supplying a map asserts that its association was independently checked.

This script never starts a robot, changes its power, or saves to Home Assistant.
When applying the output, read the latest dashboard before calling
patch_dashboard; a pure local merge cannot lock a concurrent HA editor.
"""
from __future__ import annotations

import argparse
import copy
import html
import json
import os
from pathlib import Path
import re


ENTITY = re.compile(r"[a-z][a-z0-9_]*\.[a-z0-9_]+\Z")
NAVIGATION = re.compile(r"/[A-Za-z0-9_/-]+\Z")
PROFILE_KEYS = {
    "entity", "name", "model", "battery", "charging", "bin_full", "network",
    "dock_power", "last_recovery", "telemetry", "statistics", "capability_note", "map",
}
SENSOR_DOMAINS = {
    "battery": {"sensor"}, "charging": {"binary_sensor"},
    "bin_full": {"binary_sensor"}, "network": {"binary_sensor"},
    "dock_power": {"switch"}, "last_recovery": {"input_datetime", "sensor"},
    "telemetry": {"sensor"},
}
SENSOR_NAMES = {
    "battery": "Battery", "charging": "Charging", "bin_full": "Bin full",
    "network": "Network", "dock_power": "Dock power",
    "last_recovery": "Last connection recovery",
    "telemetry": "Local telemetry",
}
COMMANDS = ((8192, "start_pause"), (8, "stop"), (16, "return_home"), (512, "locate"))
UNAVAILABLE = ("unknown", "unavailable")


def _entity(value, domains):
    if (not isinstance(value, str) or not ENTITY.fullmatch(value)
            or value.split(".", 1)[0] not in domains):
        raise ValueError("Invalid entity selection")
    return value


def _label(value, maximum=120):
    if (not isinstance(value, str) or not value.strip() or len(value) > maximum
            or any(marker in value for marker in ("{{", "{%", "{#"))
            or any(ord(char) < 32 for char in value)):
        raise ValueError("Labels must be plain, nonempty text without templates")
    return value.strip()


def _profile_identity(profiles):
    if not isinstance(profiles, list) or not 1 <= len(profiles) <= 32:
        raise ValueError("Select between one and 32 robot profiles")
    result = {}
    for profile in profiles:
        if not isinstance(profile, dict) or profile.keys() - PROFILE_KEYS:
            raise ValueError("Unknown robot profile field")
        entity = _entity(profile.get("entity"), {"vacuum"})
        if entity in result:
            raise ValueError("A vacuum is selected more than once")
        result[entity] = _label(profile.get("name", entity))
    return result


def _validate(inventory):
    if not isinstance(inventory, dict) or not isinstance(inventory.get("states"), list):
        raise ValueError("Inventory must contain a states array")
    states = {}
    for row in inventory["states"]:
        if not isinstance(row, dict) or not isinstance(row.get("entity_id"), str):
            raise ValueError("Invalid state record")
        if row["entity_id"] in states:
            raise ValueError("Duplicate entity ID in inventory")
        if not isinstance(row.get("attributes", {}), dict):
            raise ValueError("Invalid state attributes")
        states[row["entity_id"]] = row
    profiles = inventory.get("profiles")
    names = _profile_identity(profiles)

    def selected(value, domains):
        entity = _entity(value, domains)
        if entity not in states:
            raise ValueError("A selected entity is missing from the inventory")
        return entity

    result = []
    for source in profiles:
        entity = selected(source["entity"], {"vacuum"})
        profile = {"entity": entity, "name": names[entity]}
        seen = {entity}
        for key, domains in SENSOR_DOMAINS.items():
            if key in source:
                value = selected(source[key], domains)
                if value in seen:
                    raise ValueError("An entity is selected more than once in a profile")
                seen.add(value)
                profile[key] = value
        for key, maximum in (("model", 120), ("capability_note", 500)):
            if key in source:
                profile[key] = _label(source[key], maximum)
        stats = source.get("statistics", [])
        if not isinstance(stats, list) or len(stats) > 16:
            raise ValueError("Statistics must be a list of at most 16 sensors")
        for stat in stats:
            selected(stat, {"sensor", "binary_sensor"})
            if stat in seen:
                raise ValueError("A statistic is selected more than once")
            seen.add(stat)
        profile["statistics"] = list(stats)
        features = states[entity].get("attributes", {}).get("supported_features")
        # Missing capabilities must not imply movement support. The native tile
        # also checks capabilities when rendering each configured command.
        profile["commands"] = [command for bit, command in COMMANDS
                               if type(features) is int and features >= 0 and features & bit]
        if "map" in source:
            mapping = source["map"]
            if (not isinstance(mapping, dict) or mapping.get("verified") is not True
                    or mapping.keys() - {"verified", "entity", "navigation_path"}
                    or ("entity" in mapping) == ("navigation_path" in mapping)):
                raise ValueError("A map needs verification and exactly one image or local navigation target")
            if "entity" in mapping:
                image = selected(mapping["entity"], {"image", "camera"})
                if states[image].get("state") in (*UNAVAILABLE, None):
                    raise ValueError("The selected map must be available when verified")
                profile["map"] = {"entity": image}
            else:
                target = mapping["navigation_path"]
                if (not isinstance(target, str) or not NAVIGATION.fullmatch(target)
                        or target.startswith("//") or "/../" in target):
                    raise ValueError("Map navigation must be a local dashboard path")
                profile["map"] = {"navigation_path": target}
        result.append(profile)
    return result


def _available(entity):
    return [{"condition": "state", "entity": entity, "state_not": state}
            for state in UNAVAILABLE]


def _unavailable(entity):
    return {"condition": "or", "conditions": [
        {"condition": "state", "entity": entity, "state": state} for state in UNAVAILABLE]}


def _conditional(conditions, card):
    return {"type": "conditional", "conditions": conditions, "card": card}


def _tile(entity, name):
    return {"type": "tile", "entity": entity, "name": name,
            "icon": "mdi:robot-vacuum", "vertical": False,
            "tap_action": {"action": "more-info"},
            "icon_tap_action": {"action": "more-info"}}


def _diagnostic(profile):
    entity = profile["entity"]
    conditions = [_unavailable(entity)]
    content = []
    if "dock_power" in profile:
        power = profile["dock_power"]
        conditions.append({"condition": "state", "entity": power, "state": "off"})
        content.extend((f"{{% if is_state('{power}', 'off') %}}",
                        "**Dock power is off.** The robot cannot charge at its dock.", "{% else %}"))
    if "network" in profile:
        network = profile["network"]
        conditions.append({"condition": "state", "entity": network, "state": "off"})
        content.extend((f"{{% if is_state('{network}', 'on') %}}",
                        "**Network reachable; Home Assistant connection unavailable.**",
                        f"{{% elif is_state('{network}', 'off') %}}",
                        "**No network response.** Check the robot's power and Wi-Fi coverage at the dock.",
                        "{% else %}", "**Connection unavailable.** Network status is unknown.", "{% endif %}"))
    else:
        content.append("**Connection unavailable.**")
    if "dock_power" in profile:
        content.append("{% endif %}")
    return _conditional([{"condition": "or", "conditions": conditions}],
                        {"type": "markdown", "content": "\n".join(content)})


def _robot_cards(profile):
    entity = profile["entity"]
    tile = _tile(entity, profile["name"])
    cards = []
    if profile["commands"]:
        tile["features"] = [{"type": "vacuum-commands", "commands": profile["commands"]}]
        tile["features_position"] = "bottom"
        cards.extend((_conditional(_available(entity), tile),
                      _conditional([_unavailable(entity)], _tile(entity, profile["name"]))))
    else:
        cards.append(tile)
    labels = [profile[key] for key in ("model", "capability_note") if key in profile]
    if labels:
        cards.append({"type": "markdown", "content": " · ".join(html.escape(label) for label in labels)})
    cards.append(_diagnostic(profile))
    rows = [{"entity": profile[key], "name": SENSOR_NAMES[key],
             "tap_action": {"action": "more-info"}}
            for key in ("battery", "charging", "bin_full", "network", "telemetry") if key in profile]
    if "dock_power" in profile:
        rows.append({"type": "simple-entity", "entity": profile["dock_power"], "name": "Dock power",
                     "tap_action": {"action": "none"}, "hold_action": {"action": "none"},
                     "double_tap_action": {"action": "none"}})
    if rows:
        cards.append({"type": "entities", "show_header_toggle": False, "entities": rows})
    if "telemetry" in profile:
        # Only the integration's actual message receipt timestamp establishes
        # receipt. Entity updates, connection state and cached poses do not.
        cards.append({"type": "markdown", "content": "\n".join((
            f"{{% set received = state_attr('{profile['telemetry']}', 'last_message_received_at') %}}",
            "{% set observed = as_datetime(received, none) if received is string else none %}",
            "**Last local message:**",
            "{% if received is none %}",
            "Never received",
            "{% elif observed is not none and observed.tzinfo is not none %}",
            "{{ as_local(observed).strftime('%Y-%m-%d %H:%M:%S %Z') }}",
            "{% else %}",
            "Timestamp unavailable",
            "{% endif %}",
        ))})
    if "dock_power" in profile:
        power = profile["dock_power"]
        cards.append(_conditional([{"condition": "state", "entity": power, "state": "off"}], {
            "type": "button", "entity": power, "name": "Power dock on", "icon": "mdi:power-plug",
            "show_state": False,
            "tap_action": {"action": "perform-action", "perform_action": "switch.turn_on",
                           "target": {"entity_id": power}},
            "hold_action": {"action": "none"}}))
    if "map" in profile:
        mapping = profile["map"]
        if "entity" in mapping:
            image = mapping["entity"]
            cards.append(_conditional(_available(image), {
                "type": "picture-entity", "entity": image, "show_name": False, "show_state": False,
                "fit_mode": "contain",
                "tap_action": {"action": "more-info"}, "hold_action": {"action": "none"}}))
        else:
            cards.append({"type": "button", "name": "Open map / cleaning path", "icon": "mdi:map",
                          "tap_action": {"action": "navigate", "navigation_path": mapping["navigation_path"]},
                          "hold_action": {"action": "none"}})
    for card in cards:
        card["grid_options"] = {"columns": "full", "rows": "auto"}
    return cards


def build_view(inventory):
    """Return a native fleet view from an explicit private entity allowlist."""
    profiles = _validate(inventory)
    sections = [{"type": "grid", "cards": _robot_cards(profile)} for profile in profiles]
    diagnostics = []
    recovery = []
    for profile in profiles:
        if profile["statistics"]:
            diagnostics.append({
                "type": "entities", "title": profile["name"] + " · Statistics",
                "show_header_toggle": False, "entities": list(profile["statistics"]),
                "grid_options": {"columns": "full", "rows": "auto"}})
        if "last_recovery" in profile:
            # input_datetime's default row is an editor even when tap_action
            # is more-info. Force text and suppress actions for diagnostics.
            recovery.append({"type": "simple-entity", "entity": profile["last_recovery"],
                             "name": profile["name"], "tap_action": {"action": "none"},
                             "hold_action": {"action": "none"}, "double_tap_action": {"action": "none"}})
    if recovery:
        diagnostics.append({"type": "entities", "title": "Connection recovery",
                            "show_header_toggle": False, "entities": recovery,
                            "grid_options": {"columns": "full", "rows": "auto"}})
    if diagnostics:
        sections.append({"type": "grid", "cards": diagnostics})
    return {"title": "Roombas", "path": "roombas", "icon": "mdi:robot-vacuum",
            "type": "sections", "max_columns": 3, "sections": sections}


def patch_dashboard(config, view, profiles):
    """Merge into a freshly read dashboard; preserve unrelated content exactly.

    Only legacy custom:vacuum-card entries for the explicitly selected robots
    are replaced. Existing tiles, arbitrary action references, other vacuums,
    and all unrelated views are left untouched. Duplicate generated view paths
    are collapsed to the first occurrence.
    """
    if not isinstance(config, dict) or not isinstance(config.get("views"), list):
        raise ValueError("Dashboard must contain a views array")
    if not isinstance(view, dict) or view.get("path") != "roombas" or view.get("type") != "sections":
        raise ValueError("Expected a generated Roombas view")
    names = _profile_identity(profiles)

    def replace(value):
        if isinstance(value, list):
            return [replace(child) for child in value]
        if not isinstance(value, dict):
            return copy.deepcopy(value)
        if value.get("type") == "custom:vacuum-card" and value.get("entity") in names:
            entity = value["entity"]
            tile = _tile(entity, names[entity])
            tile["tap_action"] = {"action": "navigate", "navigation_path": "/lovelace/roombas"}
            for key in ("visibility", "view_layout", "grid_options"):
                if key in value:
                    tile[key] = copy.deepcopy(value[key])
            return tile
        return {key: replace(child) for key, child in value.items()}

    result = {key: copy.deepcopy(value) for key, value in config.items() if key != "views"}
    result["views"] = []
    installed = False
    for existing in config["views"]:
        if isinstance(existing, dict) and existing.get("path") == "roombas":
            if not installed:
                result["views"].append(copy.deepcopy(view))
                installed = True
        else:
            result["views"].append(replace(existing))
    if not installed:
        result["views"].append(copy.deepcopy(view))
    return result


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _read_json(path):
    with path.open("rb") as source:
        raw = source.read(32 * 1024 * 1024 + 1)
    if len(raw) > 32 * 1024 * 1024:
        raise ValueError("JSON input exceeds 32 MiB")
    return json.loads(raw, object_pairs_hook=_unique_object)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dashboard", type=Path, help="Optionally merge into a freshly exported dashboard")
    args = parser.parse_args()
    try:
        inventory = _read_json(args.inventory)
        view = build_view(inventory)
        output = patch_dashboard(_read_json(args.dashboard), view, inventory["profiles"]) if args.dashboard else view
        os.umask(0o077)
        args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        args.output.chmod(0o600)
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.error(str(error))
    print("Generated a private Roomba dashboard file; no device commands were sent.")


if __name__ == "__main__":
    main()
