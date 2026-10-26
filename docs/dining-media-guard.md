# Dining Media guard

The converted JH-G01U outlet is **Dining Media guard**, controlled through
`switch.dining_media_guard`. It restores the former Dining guard 2 role: power
for the dining-room speakers, printer and associated equipment. The separate
`switch.dining_guard` remains the curtain motor supply.

## Identity and adoption

Match the loader and encrypted native API MAC to the privately recorded old
outlet identity before adoption. Do not infer identity from a DHCP hostname:
the reservation retained an unrelated historical lamp name. The old LocalTuya
device was already removed during the earlier three-outlet cleanup; do not
remove another device or the working curtain controller.

The installed profile uses ESPHome 2026.9.1, a GPIO4 relay, a GPIO5 physical
button, and an inverted GPIO12 indicator. Same-model physical and restart
checks were waived by the owner, so they are not reported as new test passes.
Keep native API and OTA credentials private.

Adopt the verified encrypted ESPHome API, name the device and relay, and add a
separate Dining Media guard row beside the existing Dining guard in Lovelace.
Retain the existing curtain row and every manual override control. A Home
Assistant restart is not required.

## Shared occupancy control

The package `config/packages/dining_media_guard_evening.yaml` now owns both
`switch.dining_media_guard` and `switch.living_tv_guard`. The filename and original
shutdown automation ID are retained for deployed-installation compatibility.
The previous Living-lamp/sunset/15-minute rule is replaced, and automation 108 no
longer controls Dining Media guard. Its fireplace and Living guard actions retain
their existing Sticky protections.

Activity in **any** of these sensors restores available, powered-off outlets
whose room overrides permit automatic control:

- `binary_sensor.living_room_presence`
- `binary_sensor.rf_lobby_motion`
- `binary_sensor.rf_dinner_motion`
- `binary_sensor.rf_dinner_two_motion`

Both Dining RF sensors count; the most recent one to clear determines when the
shared inactivity interval can finish. Media power does not depend on daylight
or a lamp's state. This does not turn on lamps or the curtain supply.

Room Sticky overrides protect both automatic turn-on and turn-off:

- Living TV Guard requires `input_boolean.living_room_sticky` to be `off`.
- Dining Media guard requires both `input_boolean.living_room_sticky` and
  `input_boolean.dining_room_sticky` to be `off`. This keeps the original Living
  override and also honors the outlet's Dining room ownership.
- An override that is `on`, `unknown`, `unavailable`, or absent blocks its outlet.
  Dining Sticky does not prevent an otherwise permitted TV outlet command.

These guards are checked immediately before each outlet command. Enabling an
override while the first command runs prevents a later protected command. The
global Curtains Sticky controls curtains only; it is not a media-power override.

After **all four sensors have individually stayed off for ten minutes**:

- Dining Media guard turns off regardless of the TV state, if both overrides
  above are off.
- Living TV Guard turns off only if `media_player.living_room_tv_77`, the native
  webOS entity, explicitly reports `off`. A DLNA entity reporting `idle` is not
  proof that the TV is off. Living Sticky must also be off.

If the TV is switched off later, its state transition immediately rechecks the
same inactivity condition. `unknown`, `unavailable`, or missing sensor states
never count as inactivity. An unknown or unavailable TV protects its outlet
without preventing Dining Media guard from shutting down.

## Reload, recovery and manual control

The automation uses a ten-minute state trigger and repeats the elapsed-state
check once per minute. This catches a deadline whose pending trigger was lost
when automations reloaded, with at most one extra minute of delay. A full HA
restart begins a fresh observed inactivity interval; downtime is not evidence
that rooms were empty. See Home Assistant's [state conditions](https://www.home-assistant.io/conditions/state/)
and [automation triggers](https://www.home-assistant.io/docs/automation/trigger/).

Startup, automation reload and an outlet recovering from `unknown`/`unavailable`
to `off` restore power if one of the four sensors is active and its room overrides
are off. A regular manual
`on` to `off` transition does not itself switch an outlet back on: the next
activity event or explicit reconciliation can restore it. Commands are sent only
when an outlet actually needs to change state. A failure of one outlet does not
block the other, and inactivity is checked again before cutting TV power.

Turning Sticky off does not itself restore power; the next activity or explicit
reconciliation does. If the room is already vacant, the periodic inactivity check
can shut down an outlet after Sticky is released. Manual control of an outlet
does not disable occupancy management; enable its Sticky override to hold it in
the chosen state across future activity, reloads and inactivity checks.

## Verification and troubleshooting

`tests/test_dining_media_evening.py` runs the actual automations against simulated
entities in an isolated Home Assistant instance. It covers each activity source,
continuous shared inactivity, the last sensor's deadline, new movement, offline
sensors, TV states, late TV shutdown, manual off, outlet recovery, startup/reload,
one failed outlet, activity arriving between commands, room override isolation,
unknown overrides, and Sticky changes during a wait or service call. Only the test copy
shortens the ten-minute durations; physical loads are not switched by the tests.

Inspect the traces for **Media guards: Restore power on occupancy** and
**Media guards: Turn off after shared inactivity**. The latter retains its stable
entity `automation.dining_media_guard_evening_power_off`. For a blocked shutdown,
check the state and last-change time of every sensor, the applicable Sticky
overrides, then the native LG state.
Do not treat a missing motion report as proof of an empty room.

Validate the full configuration before `automation.reload`; no Core restart is
required. Preserve the independent `switch.dining_guard` curtain controller and
all lighting Sticky definitions.

The source reconciliation for this package is tested offline. Merging it does
not prove a live deployment or physical outlet response; those are separate
operational checks.

Matter exposure is a separate step on the existing bridge. Preserve all prior
endpoints and controller fabrics; publish only the canonical relay. Keep
addresses, MACs, registry IDs, credentials and operational receipts outside
this repository.
