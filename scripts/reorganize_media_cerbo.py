#!/usr/bin/env python3
"""Move a private Cerbo dashboard into the main Lovelace navigation.

These pure transformations perform no network requests or service calls. Pass
fresh private dashboard configurations; never commit their generated output.
"""
import copy
import re


def _entity_refs(value):
    found = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ("entity", "entity_id"):
                found.update([item] if isinstance(item, str) else item if isinstance(item, list) else [])
            elif key == "entities" and isinstance(item, list):
                found.update(x for x in item if isinstance(x, str))
            found.update(_entity_refs(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_entity_refs(item))
    return found


def _controller_group(entity):
    """Classify GX controls by their meaning, not phone-name substrings."""
    name = entity.split(".", 1)[-1].removeprefix("gx_device_")
    if match := re.search(r"(?:^|_)schedule_charge_(\d+)_", name):
        return 60 + int(match[1]), f"Charging schedule {int(match[1]) + 1}"
    if "firmware" in name or name in ("available_version", "installed_version", "system_state"):
        return 0, "Firmware and system health"
    if name.startswith("dynamic_ess_") or name == "dess_mode":
        return 10, "Dynamic ESS"
    if name.startswith("ess_max_charge_") or name in ("dvcc", "dvcc_state"):
        return 20, "Charging limits and DVCC"
    if name.startswith("ess_") or name in ("active_soc_limit", "scheduled_soc", "ac_power_setpoint", "ac_export_limit"):
        return 30, "Energy storage and grid control"
    if name.startswith("dc_battery_") or name == "dc_consumption":
        return 40, "Battery and DC power"
    if name.startswith(("pv_", "ac_coupled_pv_")):
        return 45, "Solar power"
    if name.startswith(("grid_", "ac_", "consumption_", "critical_loads_")):
        return 50, "Grid and AC loads"
    return 90, "Controller settings and statuses"


def _controller_sections(controller):
    # Keep custom entity row options (names, icons, secondary info) when present.
    rows = {}
    other_cards = []
    for card in controller.get("cards", []):
        if card.get("type") != "entities":
            other_cards.append(copy.deepcopy(card))
            continue
        for row in card.get("entities", []):
            entity = row if isinstance(row, str) else row.get("entity")
            if entity:
                rows.setdefault(entity, copy.deepcopy(row))
    for entity in sorted(_entity_refs(controller)):
        rows.setdefault(entity, entity)
    groups = {}
    for entity in rows:
        groups.setdefault(_controller_group(entity), []).append(entity)

    def row_order(entity):
        # A schedule is usable when its switch, days and time stay together.
        fields = ("enabled", "days", "start", "duration", "soc")
        field = entity.rsplit("_", 1)[-1]
        return (fields.index(field) if field in fields else len(fields), entity)

    sections = []
    for (order, title), entities in sorted(groups.items()):
        entities.sort(key=row_order if 60 <= order < 90 else lambda x: x)
        cards = [{"type": "heading", "heading": title, "grid_options": {"columns": 12}}]
        for offset in range(0, len(entities), 12):
            card = {"type": "entities", "show_header_toggle": False,
                    "entities": [rows[e] for e in entities[offset:offset + 12]],
                    "grid_options": {"columns": 12}}
            if offset:
                card["title"] = f"{title} · {offset // 12 + 1}"
            cards.append(card)
        sections.append({"type": "grid", "cards": cards})
    if other_cards:
        sections.append({"type": "grid", "cards": other_cards})
    return sections


def _rewrite_navigation(value, targets):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ("navigation_path", "back_path") and isinstance(item, str):
                for old, new in targets.items():
                    if item == old or item.startswith(old + "?") or item.startswith(old + "#"):
                        value[key] = new + item[len(old):]
                        break
            else:
                _rewrite_navigation(item, targets)
    elif isinstance(value, list):
        for item in value:
            _rewrite_navigation(item, targets)


def _prune_controller_links(value, controller_url):
    if isinstance(value, dict):
        if any(isinstance(value.get(key), dict)
               and value[key].get("navigation_path") == controller_url
               for key in ("tap_action", "icon_tap_action")):
            return None
        return {key: _prune_controller_links(item, controller_url) for key, item in value.items()}
    if isinstance(value, list):
        return [item for original in value
                if (item := _prune_controller_links(original, controller_url)) is not None]
    return value


def migrate_cerbo_view(main_config, cerbo_config):
    """Return main Lovelace with an inline controller and hidden device subviews.

    The old dashboard is not modified here. Its sidebar visibility can be changed
    separately while retaining old URLs for bookmarks. Existing unrelated views
    and dashboard-level settings survive; conflicting view paths are rejected.
    Reapplying this transformation to its result is idempotent.
    """
    result = copy.deepcopy(main_config)
    source = copy.deepcopy(cerbo_config)
    old_views = source.get("views", [])
    paths = [view.get("path") for view in old_views]
    if len(paths) != len(set(paths)) or None in paths:
        raise ValueError("Cerbo source views need unique explicit paths")
    by_path = {view["path"]: view for view in old_views}
    if "home" not in by_path or "gx" not in by_path:
        raise ValueError("Cerbo source must contain home and gx views")

    main_path = "cerbo-gx"
    home_url = f"/lovelace/{main_path}"
    targets = {"/cerbo-gx": home_url, "/cerbo-gx/home": home_url, "/cerbo-gx/gx": home_url}
    for path in paths:
        if path not in ("home", "gx"):
            targets[f"/cerbo-gx/{path}"] = f"/lovelace/cerbo-{path}"

    overview = _prune_controller_links(by_path["home"], "/cerbo-gx/gx")
    overview.update(path=main_path, subview=False, type="sections", max_columns=3)
    overview.pop("back_path", None)
    sections = overview.get("sections", [])
    overview["sections"] = sections[:1] + _controller_sections(by_path["gx"]) + sections[1:]
    for section in overview["sections"]:
        for card in section.get("cards", []):
            card.setdefault("grid_options", {})["columns"] = 12

    generated = [overview]
    for view in old_views:
        if view["path"] in ("home", "gx"):
            continue
        view.update(path="cerbo-" + view["path"], subview=True, back_path=home_url)
        generated.append(view)
    _rewrite_navigation(generated, targets)
    generated_by_path = {view["path"]: view for view in generated}
    if len(generated_by_path) != len(generated):
        raise ValueError("Generated Cerbo view paths collide")

    kept = []
    for view in result.get("views", []):
        replacement = generated_by_path.get(view.get("path"))
        if replacement is None:
            kept.append(view)
            continue
        # A matching title or path does not establish ownership. Only replace
        # an unchanged generated view; preserve later user edits as a conflict.
        if view != replacement:
            raise ValueError(f"Existing view conflicts with Cerbo path: {view.get('path')}")
    result["views"] = kept + generated
    _rewrite_navigation(result, targets)
    if not _entity_refs(source) <= _entity_refs(generated):
        raise ValueError("Cerbo migration would discard entity controls")
    return result
