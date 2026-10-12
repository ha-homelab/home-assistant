"""Check notification availability without handling message contents."""
service = data.get("service", "")
if not isinstance(service, str) or service.count(".") != 1 or not (
    service.startswith("notify.") or service == "html5.send_message"
):
    raise ValueError("Expected a notify/HTML5 notification action")
domain, name = service.split(".")
output["available"] = hass.services.has_service(domain, name)
output["delivery_allowed"] = output["available"]

# These destinations are confirmed against the live webOS config/entity registry.
# Do not infer entity IDs from notifier names: the living-room TV was renamed.
tv_entities = {
    "notify.lg2": "media_player.lg2",
    "notify.lg_webos_tv_oled77c5pua_dusqljr": "media_player.living_room_tv_77",
}
tv_entity = tv_entities.get(service)
if tv_entity:
    tv = hass.states.get(tv_entity)
    output["delivery_allowed"] = output["available"] and tv is not None and tv.state in (
        "on", "idle", "playing", "paused", "buffering"
    )
