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
unchanged. The existing Lovelace brightness tile is retained. There is no
bedroom light group or floorplan binding to replace in the active configuration.
