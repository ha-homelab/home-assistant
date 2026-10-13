# Bedroom Lamp motion and shutdown

`light.bedroom_lamp` is the Matter Bedroom Lamp, formerly `light.arc_lamp_m`.
It is separate from `switch.living_lamp`, the former bedroom outlet now used in
the living room, and from the disabled SmartThings `light.purple_lamp`.

## Restored motion rules

- `automation.bedroom_motion_triggered`: RF Bedroom Motion becoming ON turns
  on the lamp with `light.turn_on`, between 18:00 and 23:00 local HA time, only
  when solar elevation is below 0.60 degrees and Bedroom sticky is OFF.
- `automation.bedroom_motion_off`: after three minutes without motion,
  the existing recovery blueprint turns off this lamp with `light.turn_off`.
  The same solar and sticky guards apply; its time window is 18:00–23:10.

These restore the previously retired rules 020/021 for the newly assigned lamp.
The original sensor, windows, timeout and manual override are retained. The
turn-on action does not prescribe brightness or color; the lamp keeps its
configured behavior for a normal turn-on. The former dining motion action for
this lamp is removed; other dining lights and the Dining Arc outlet remain.

## Shutdown controls

The existing Lovelace buttons call these automations directly:

- **Turn off all lights** calls `automation.off_lights`.
- **Turn off lights except living** calls
  `automation.off_lights_except_living_room`.

Each includes Bedroom Lamp once. Their 05:35/05:45 schedules and other targets
remain unchanged, including the living-room exclusion in the second rule.
The shared `script.turn_off_living_room` also includes the lamp once in its
existing household light/media shutdown list. Its other targets and host
shutdown helper are unchanged. No whole-house scenario is executed as a test.

The Matter device identity, pairing and supplied four-lamp remote binding are
unchanged. The Lovelace brightness control is retained. There is no
bedroom light group or floorplan binding to replace in the active configuration.

## Dashboard location

The storage-mode Overview dashboard exposes **Bedroom 2 — Lamp** at the top of
both **Home** and **Lighting**. It targets the same `light.bedroom_lamp` entity
and includes the standard brightness control. The former tile at the bottom of
the Lighting stack, beside the porch/balcony controls, has been moved; there is
only one tile for this lamp in each view. This display name does not rename the
entity or change its Matter pairing.

```yaml
type: tile
entity: light.bedroom_lamp
name: Bedroom 2 — Lamp
icon: mdi:desk-lamp
features:
  - type: light-brightness
```

Dashboard edits are saved through `lovelace/config/save`, after re-reading the
current storage configuration. Preserve all unrelated cards and verify the
saved configuration and rendered tile. Dashboard storage is installation data
and is not committed to this public repository.

## Diagnosing a missed motion activation

Check `binary_sensor.rf_bedroom_motion` history and the trace of
`automation.bedroom_motion_triggered` before changing entity references. A
recorded trigger ending at `condition/0` means that the solar-elevation guard
rejected the event; it does not mean that Matter communication failed. A daytime
motion event does not remain queued until the evening window opens: another
motion event is required.

The MQTT mirror `binary_sensor.sonoff_rf_bridge_bedroom_motion` can help check
reception, but unavailable historical duplicates are not replacement trigger
entities. If there is no new ON event, perform a controlled walk in front of the
physical detector and identify the sensor that actually changes. Keep the
18:00–23:00 activation window, daylight guard, three-minute shutdown and manual
override unless a separate behavior change is requested.
