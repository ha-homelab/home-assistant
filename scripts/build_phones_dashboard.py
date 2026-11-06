#!/usr/bin/env python3
"""Build a private, offline-inclusive Phones dashboard from an explicit inventory.

The manifest is deployment data, not a source file: keep it out of public Git.
No network requests, entity enablement, service calls, or availability filtering.
"""
import argparse
import copy
import json
from pathlib import Path

if __package__:
    from .private_output import UnsafeOutputError, private_output
else:
    from private_output import UnsafeOutputError, private_output


def entity_refs(value):
    """Read explicit entity references without mistaking service names for entities."""
    found = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ("entity", "entity_id"):
                found.update([item] if isinstance(item, str) else item if isinstance(item, list) else [])
            elif key == "entities" and isinstance(item, list):
                found.update(x for x in item if isinstance(x, str))
            found.update(entity_refs(item))
    elif isinstance(value, list):
        for item in value:
            found.update(entity_refs(item))
    return found


def group_for(entity):
    domain, name = entity.split(".", 1)
    if domain == "update" or any(x in name for x in ("firmware", "update_channel", "update_status", "install_updates")):
        return "Updates"
    if any(x in name for x in ("timer", "alarm", "reminder", "sounding", "schedule")):
        return "Timers and alarms"
    if any(x in name for x in ("bluetooth", "ble_")):
        return "Bluetooth"
    if domain == "assist_satellite" or any(x in name for x in ("assistant", "wake_word", "microphone", "mic_", "voice", "finished_speaking", "nearest_device")):
        return "Voice assistant"
    if any(x in name for x in ("call", "phone", "sip_", "dial", "answer", "hang_up", "do_not_disturb", "dtmf", "registered", "autoanswer")):
        return "Calls"
    if any(x in name for x in ("screen", "display", "brightness", "dark_mode", "ring_", "orientation")):
        return "Display and lights"
    if domain == "media_player" or any(x in name for x in ("music", "playback", "radio_", "volume", "airplay", "dlna", "spotify", "now_playing")):
        return "Audio"
    if domain in ("sensor", "binary_sensor", "event", "device_tracker"):
        return "Status and diagnostics"
    return "Settings and actions"


def build(manifest):
    base = manifest["url_path"]
    devices = manifest["devices"]
    keys = [d["key"] for d in devices]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate device view")
    title = manifest.get("title", "Phones")
    overview = {"title": title, "path": "home", "icon": manifest.get("icon", "mdi:phone-classic"),
                "type": "sections", "max_columns": 3, "sections": []}
    views = [overview]
    for family in dict.fromkeys(d["family"] for d in devices):
        cards = [{"type": "heading", "heading": family}]
        for d in [d for d in devices if d["family"] == family]:
            card = {"type": "tile", "entity": d["status"], "name": d["title"],
                          "icon": d.get("icon", "mdi:phone-classic"),
                          "tap_action": {"action": "navigate", "navigation_path": f'/{base}/{d["key"]}'},
                          "icon_tap_action": {"action": "navigate", "navigation_path": f'/{base}/{d["key"]}'}}
            if manifest.get("persistent_labels"):
                # A missing state during startup must not replace the device name
                # with a generic error card. Mushroom renders the explicit label.
                card.update(type="custom:mushroom-template-card", primary=d["title"],
                            secondary="{{ states('" + d["status"] + "') | replace('_', ' ') | title }}",
                            layout="horizontal", icon_color="blue")
                card.pop("name")
            cards.append(card)
        overview["sections"].append({"type": "grid", "cards": cards})
    for d in devices:
        cards = []
        if d.get("note"):
            cards.append({"type": "markdown", "content": d["note"]})
        if d.get("player"):
            cards.append({"type": "media-control", "entity": d["player"]})
        cards.extend(copy.deepcopy(d.get("cards", [])))
        covered = entity_refs(cards)
        groups = {}
        for entity in sorted(set(d["entities"]) - covered):
            groups.setdefault(group_for(entity), []).append(entity)
        for group in ("Voice assistant", "Calls", "Timers and alarms", "Bluetooth", "Audio",
                      "Display and lights", "Settings and actions", "Updates", "Status and diagnostics"):
            items = groups.get(group, [])
            for offset in range(0, len(items), 12):
                cards.append({"type": "entities", "title": group + (f" · {offset // 12 + 1}" if offset else ""),
                              "show_header_toggle": False, "entities": items[offset:offset + 12]})
        view = {"title": d["title"], "path": d["key"], "subview": True,
                "back_path": f"/{base}/home", "cards": cards}
        if not set(d["entities"]) <= entity_refs(view):
            raise ValueError("Incomplete device controls")
        views.append(view)
    views.extend(copy.deepcopy(manifest.get("extra_views", [])))
    if len({v["path"] for v in views}) != len(views):
        raise ValueError("Duplicate dashboard view path")
    return {"title": title, "views": views}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = build(json.loads(args.manifest.read_text()))
    try:
        with private_output(args.output, (args.manifest,)) as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
    except UnsafeOutputError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
