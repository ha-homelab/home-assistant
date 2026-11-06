#!/usr/bin/env python3
"""Place readable endpoint media cards after the existing Media controls.

Read the live dashboard and a private ``devices`` manifest. Each device supplies
an entity, display name, icon, explicit shortcuts, and (for source shortcuts) the
integration's current source_list. This renderer neither discovers devices nor
starts playback. Deployment data and generated dashboards must remain private.
"""
import copy
from urllib.parse import urlsplit


def _players(value):
    if isinstance(value, dict):
        entity = value.get("entity")
        result = [entity] if isinstance(entity, str) and entity.startswith("media_player.") else []
        for child in value.values():
            result.extend(_players(child))
        return result
    if isinstance(value, list):
        return [entity for child in value for entity in _players(child)]
    return []


def _card(device):
    entity = device["entity"]
    if not isinstance(entity, str) or not entity.startswith("media_player."):
        raise ValueError("Expected a media_player entity")
    if not device.get("name") or not device.get("shortcuts"):
        raise ValueError("Every player needs an explicit name and playback shortcuts")
    shortcuts = copy.deepcopy(device["shortcuts"])
    for shortcut in shortcuts:
        if not shortcut.get("name") or not shortcut.get("id"):
            raise ValueError("Every shortcut needs a name and identifier")
        if shortcut.get("type") == "source":
            if shortcut["id"] not in device.get("source_list", []):
                raise ValueError("Source shortcut is not exposed by this player")
        elif shortcut.get("type") == "music":
            url = urlsplit(shortcut["id"])
            if url.scheme not in ("http", "https") or not url.hostname:
                raise ValueError("Music shortcuts require a directly playable HTTP(S) URL")
            if url.username is not None or url.password is not None:
                raise ValueError("Do not put credentials in media shortcut URLs")
        else:
            raise ValueError("Only supported source or music shortcuts are accepted")
    transport = device.get("transport", "play_pause")
    if transport not in ("play_pause", "play_stop"):
        raise ValueError("Transport must be play_pause or play_stop")
    icon = device.get("icon", "mdi:speaker")
    player = {
        "type": "custom:mini-media-player", "entity": entity,
        "name": device["name"], "icon": icon, "artwork": "cover",
        "info": "scroll", "source": "full",
        "hide": {"power": True, "name": True, "volume_level": False},
        "shortcuts": {"columns": 2, "column_height": 48,
                      "align_text": "left", "buttons": shortcuts},
    }
    if transport == "play_stop":
        # Radio-call endpoints cannot pause. mini-media-player's default button
        # always calls media_play_pause, even when only PLAY is advertised.
        player["hide"].update(play_pause=True, play_stop=False)
    # Some card versions replace their own header with "Unavailable". Keep an
    # independent heading so an offline device is still identifiable.
    return {"type": "vertical-stack", "cards": [
        {"type": "heading", "heading": device["name"], "icon": icon}, player,
    ]}


def migrate_media_view(main_config, players_manifest):
    """Return a sections view with endpoints strictly below the legacy cards.

    Fail closed on missing/ambiguous blocks instead of overwriting an unrelated
    edit. Re-running against this renderer's unchanged output is a no-op.
    Availability never affects whether a device is included.
    """
    devices = players_manifest["devices"]
    replacements = [_card(device) for device in devices]
    # Accept the exact prior renderer output during the one-time transport
    # migration, without accepting arbitrary edits to generated cards.
    previous = [_card({k: v for k, v in device.items() if k != "transport"})
                for device in devices]
    ids = [device["entity"] for device in devices]
    if not ids or len(set(ids)) != len(ids):
        raise ValueError("Player inventory must be nonempty and unique")
    result = copy.deepcopy(main_config)
    views = [v for v in result["views"] if v.get("path") == players_manifest.get("view_path", "media")]
    if len(views) != 1:
        raise ValueError("Expected exactly one Media view")
    view = views[0]
    separator = {"type": "grid", "column_span": 3, "cards": [
        {"type": "heading", "heading": "Phones and Echo", "heading_style": "title",
         "icon": "mdi:speaker-multiple", "grid_options": {"columns": 12}},
    ]}
    endpoint_sections = [separator]
    for wrapper in replacements:
        cards = copy.deepcopy(wrapper["cards"])
        for card in cards:
            card["grid_options"] = {"columns": 12}
        endpoint_sections.append({"type": "grid", "column_span": 1, "cards": cards})
    if view.get("type") == "sections":
        sections = view.get("sections", [])
        if (view.get("max_columns") == 3
                and view.get("dense_section_placement") is False
                and sections[-len(endpoint_sections):] == endpoint_sections
                and sum(section == separator for section in sections) == 1):
            return result
        raise ValueError("Media sections differ from the generated layout; re-read before editing")
    if view.get("panel"):
        raise ValueError("This migration expects an ordinary masonry view")
    cards = view["cards"]
    matches = []
    for index, card in enumerate(cards):
        if card.get("type") == "grid" and _players(card) == ids:
            matches.append((index, 1))
        sequence = cards[index:index + len(ids)]
        if sequence == replacements or sequence == previous:
            matches.append((index, len(ids)))
    if len(matches) != 1:
        raise ValueError("Expected one unambiguous endpoint block; re-read the live dashboard")
    index, count = matches[0]
    del cards[index:index + count]
    # A full-span separator starts a new row after every existing section. With
    # sparse placement, later endpoints cannot fill gaps beside legacy cards.
    view["sections"] = [{"type": "grid", "column_span": 1, "cards": [card]}
                        for card in cards] + endpoint_sections
    del view["cards"]
    view.pop("panel", None)
    view.update(type="sections", max_columns=3, dense_section_placement=False)
    return result
