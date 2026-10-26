#!/usr/bin/env python3
"""Build a private Lovelace view from explicitly selected, exported HA entities.

Input JSON: {"states": [...], "vacuum_entity": "vacuum.example",
"map_entity": "image.example_custom", "controls": {"cleaning": [...],
"dock": [...], "maintenance": [...]}, "room_ids": [...],
"room_names": {"<allowed-id>": "Optional label"},
"other_vacuums": [...]}.
Only entity IDs and validated room metadata are used. No network/device calls.
Requires Xiaomi Vacuum Map Card 2.4.1 and the local roborock-map-card.js resource.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
from pathlib import Path
import re


ENTITY = re.compile(r"[a-z][a-z0-9_]*\.[a-z0-9_]+\Z")
SECTION_DOMAINS = {
    "status": {"sensor", "binary_sensor"},
    "cleaning": {"select", "number", "switch", "time"},
    "dock": {"select", "switch", "sensor", "binary_sensor"},
    "maintenance": {"sensor", "binary_sensor"},
}
SECTION_TITLES = {
    "status": "Status",
    "cleaning": "Cleaning and mopping",
    "dock": "Dock",
    "maintenance": "Maintenance",
}



def _point(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2 or any(
        isinstance(n, bool) or not isinstance(n, (int, float))
        or not math.isfinite(n) or abs(n) > 10_000_000 for n in value
    ):
        raise ValueError("Map coordinates must be finite numeric pairs")
    return list(value)


def _area(points):
    return sum(a[0] * b[1] - b[0] * a[1]
               for a, b in zip(points, points[1:] + points[:1]))


def validate_map(entity, room_ids=None):
    """Validate only supported map metadata; ignore unrelated state attributes."""
    if not isinstance(entity.get("state"), str) or entity["state"] in {"unavailable", "unknown"}:
        raise ValueError("The selected map is unavailable")
    attributes = entity.get("attributes", {})
    picture = attributes.get("entity_picture")
    if not isinstance(picture, str) or not picture.strip():
        raise ValueError("The selected map needs an image source")
    calibration = attributes.get("calibration_points")
    if not isinstance(calibration, list) or len(calibration) not in (3, 4):
        raise ValueError("The selected map needs three or four calibration points")
    for kind in ("map", "vacuum"):
        points = []
        for row in calibration:
            value = row.get(kind, {}) if isinstance(row, dict) else {}
            if not isinstance(value, dict):
                raise ValueError("Invalid calibration point")
            points.append(_point([value.get("x"), value.get("y")]))
        if any(abs(_area(list(triple))) < 1e-9 for triple in itertools.combinations(points, 3)):
            raise ValueError("Calibration points must not be collinear or duplicated")
    rooms = attributes.get("rooms")
    if not isinstance(rooms, dict) or not 1 <= len(rooms) <= 256:
        raise ValueError("The selected map needs room metadata")
    if room_ids is not None:
        if any(str(identifier) not in rooms for identifier in room_ids):
            raise ValueError("An allowed room is missing from the selected map")
        rooms = {str(identifier): rooms[str(identifier)] for identifier in room_ids}
    selections = []
    for key, room in rooms.items():
        if not isinstance(key, str) or not re.fullmatch(r"0|[1-9][0-9]*", key) or int(key) > 65535:
            raise ValueError("Room IDs must be canonical unsigned integers")
        identifier = int(key)
        if not isinstance(room, dict):
            raise ValueError("Each room must be a metadata object")
        if "number" in room and (type(room["number"]) is not int or room["number"] != identifier):
            raise ValueError("Room number differs from its map key")
        outline = room.get("outline")
        if outline is None:
            outline = [[room.get("x0"), room.get("y0")], [room.get("x1"), room.get("y0")],
                       [room.get("x1"), room.get("y1")], [room.get("x0"), room.get("y1")]]
        if not isinstance(outline, list) or not 3 <= len(outline) <= 2048:
            raise ValueError("Room outlines must have between three and 2048 points")
        outline = [_point(point) for point in outline]
        if abs(_area(outline)) < 1e-9:
            raise ValueError("Room outlines must enclose an area")
        center = ([room.get("x"), room.get("y")] if "x" in room or "y" in room
                  else [room.get("pos_x"), room.get("pos_y")])
        center = ([sum(point[n] for point in outline) / len(outline) for n in (0, 1)]
                  if all(value is None for value in center) else _point(center))
        name = room.get("name")
        if name is None or isinstance(name, str) and name.strip().lower() == "unknown":
            name = f"Room {identifier}"
        if not isinstance(name, str) or not name.strip() or len(name) > 128:
            raise ValueError("Room names must be nonempty strings up to 128 characters")
        selections.append({"id": identifier, "outline": outline, "default_state": "unselected",
                           "label": {"text": name.strip(), "x": center[0], "y": center[1], "offset_y": 20},
                           "icon": {"name": "mdi:broom", "x": center[0], "y": center[1]}})
    return sorted(selections, key=lambda room: room["id"])


def _selected(value, states, domains):
    if not isinstance(value, str) or not ENTITY.fullmatch(value) or value.split(".")[0] not in domains:
        raise ValueError("Invalid entity selection")
    if value not in states:
        raise ValueError("A selected entity is missing from the inventory")
    return value


def _action_button(entity, title, icon, service, confirmation=None):
    action = {"action": "perform-action", "perform_action": service, "target": {"entity_id": entity}}
    if confirmation:
        action["confirmation"] = {"text": confirmation}
    return {"type": "button", "entity": entity, "name": title, "icon": icon,
            "show_state": False, "tap_action": action, "hold_action": {"action": "none"}}


def build_view(inventory):
    """Return a deterministic view; never mutate the inventory or call HA."""
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
    vacuum = _selected(inventory.get("vacuum_entity"), states, {"vacuum"})
    map_entity = _selected(inventory.get("map_entity"), states, {"image"})
    room_ids = inventory.get("room_ids")
    if (not isinstance(room_ids, list) or not room_ids
            or any(type(identifier) is not int or not 0 <= identifier <= 65535 for identifier in room_ids)
            or len(room_ids) != len(set(room_ids))):
        raise ValueError("Room IDs must be a nonempty unique list of verified current-map segment IDs")
    room_ids = sorted(room_ids)
    validate_map(states[map_entity], room_ids)
    room_names = inventory.get("room_names", {})
    if not isinstance(room_names, dict) or any(
        not isinstance(identifier, str) or identifier not in {str(room_id) for room_id in room_ids}
        or not isinstance(label, str) or not label.strip() or len(label) > 128
        for identifier, label in room_names.items()
    ):
        raise ValueError("Room names must map allowed segment IDs to nonblank strings up to 128 characters")
    room_names = {identifier: room_names[identifier].strip()
                  for identifier in sorted(room_names, key=int)}
    controls = inventory.get("controls", {})
    if not isinstance(controls, dict) or controls.keys() - SECTION_DOMAINS.keys():
        raise ValueError("Unknown controls section")
    sections = []
    seen = {vacuum, map_entity}
    for key, domains in SECTION_DOMAINS.items():
        entities = controls.get(key, [])
        if not isinstance(entities, list):
            raise ValueError("Controls must be entity ID lists")
        for entity in entities:
            _selected(entity, states, domains)
            if entity in seen:
                raise ValueError("An entity is selected more than once")
            seen.add(entity)
        if entities:
            sections.append({"type": "entities", "title": SECTION_TITLES[key],
                             "show_header_toggle": False, "entities": list(entities)})
    other = inventory.get("other_vacuums", [])
    if not isinstance(other, list):
        raise ValueError("Other vacuums must be an entity ID list")
    for entity in other:
        _selected(entity, states, {"vacuum"})
        if entity in seen:
            raise ValueError("An entity is selected more than once")
        seen.add(entity)
    if other:
        sections.append({"type": "entities", "title": "Other vacuums", "show_header_toggle": False,
                         "entities": list(other)})
    # The local wrapper keeps one live inner map and validates dynamic metadata.
    # Room IDs must be verified segments from the current map.
    map_card = {"type": "custom:homelab-roborock-map-card", "entity": vacuum,
                "map_entity": map_entity, "room_ids": room_ids}
    if room_names:
        map_card["room_names"] = room_names
    actions = {8192: ("Start full clean", "mdi:play", "vacuum.start", "Start cleaning the whole selected map?"),
               4: ("Pause", "mdi:pause", "vacuum.pause", None),
               8: ("Stop", "mdi:stop", "vacuum.stop", None),
               16: ("Return to dock", "mdi:home-import-outline", "vacuum.return_to_base", "Return the vacuum to its dock?")}
    features = states[vacuum].get("attributes", {}).get("supported_features")
    if type(features) is not int or features < 0 or not features & 256:
        raise ValueError("The selected vacuum must advertise send-command support")
    buttons = [_action_button(vacuum, *values) for bit, values in actions.items() if features & bit]
    map_cards = [{"type": "markdown", "content":
              "Select rooms, draw a rectangular zone, or select a destination, then press the map's Run button. "
              "Selection does not start the robot. Room cleaning covers the whole colored segment, which may span several rooms. Use a zone to clean only part of it."},
                 map_card]
    control_cards = []
    if buttons:
        control_cards.append({"type": "grid", "columns": 2, "square": False, "cards": buttons})
    if features & 32:
        control_cards.append({"type": "tile", "entity": vacuum, "name": "Suction power",
                              "tap_action": {"action": "more-info"},
                              "features": [{"type": "vacuum-fan-speed"}]})
    control_cards.extend(sections)
    for card in map_cards + control_cards:
        card["grid_options"] = {"columns": "full", "rows": "auto"}
    return {"title": "Vacuum maps", "path": "vacuum-map", "icon": "mdi:robot-vacuum",
            "type": "sections", "max_columns": 3,
            "sections": [{"type": "grid", "column_span": 2, "cards": map_cards},
                         {"type": "grid", "column_span": 1, "cards": control_cards}]}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        with args.inventory.open("rb") as source:
            raw = source.read(32 * 1024 * 1024 + 1)
        if len(raw) > 32 * 1024 * 1024:
            raise ValueError("Inventory exceeds 32 MiB")
        inventory = json.loads(raw, object_pairs_hook=_unique_object)
        view = build_view(inventory)
        args.output.write_text(json.dumps(view, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.error(str(error))
    print("Generated a standalone vacuum-map view; no device commands were sent.")


if __name__ == "__main__":
    main()
