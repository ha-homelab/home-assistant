# Dining Media guard

> **Living bookshelf is temporarily excluded from occupancy control.** Its
> recovery trigger and both action blocks are commented out while it supplies
> a Zigbee router. Leave the outlet on. Resume only after that router has a
> separate power supply; there is no automatic next-day reactivation. The
> bookshelf policy below is retained for that later restoration.

To resume, uncomment both marked bookshelf action blocks and its recovery entry,
re-enable `BookshelfOccupancyTest`, restore its duration-count expectation, and
validate before reloading automations.

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

The package `config/packages/dining_media_guard_evening.yaml` owns
`switch.dining_media_guard`, `switch.living_bookshelf`, and `switch.living_tv_guard`.
Living bookshelf follows the same occupancy and inactivity policy as Dining
Media guard; it has no separate sensor, daylight, or television-state condition.
The filename and original
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
- Dining Media guard and Living bookshelf require both `input_boolean.living_room_sticky` and
  `input_boolean.dining_room_sticky` to be `off`. This keeps the original Living
  override and also honors the outlet's Dining room ownership.
- An override that is `on`, `unknown`, `unavailable`, or absent blocks its outlet.
  Dining Sticky does not prevent an otherwise permitted TV outlet command.

These guards are checked immediately before each outlet command. Enabling an
override while the first command runs prevents a later protected command. The
global Curtains Sticky controls curtains only; it is not a media-power override.

After **all four sensors have individually stayed off for ten minutes**:

- Dining Media guard and Living bookshelf turn off regardless of the TV state, if both overrides
  above are off.
- Living TV Guard turns off only if `media_player.living_room_tv_77`, the native
  webOS entity, has continuously reported `off` for **two hours**. A DLNA entity
  reporting `idle` is not proof that the TV is off. Living Sticky must also be off. The outlet must have
  continuously reported `on` for **two minutes**, and
  `timer.living_room_tv_wake_grace` must be `idle`.

The outlet-age check protects power restored by occupancy or a physical button.
The timer protects an explicit [LG power-on request](lg-tv-wake-on-lan.md), even
when the outlet was already on and the TV still reports `off` while waking. It
lasts two minutes, is not restored after a Core restart, and duplicate in-flight
wake requests do not extend it. Missing or unknown timer state blocks automatic
TV power-off. Dining Media guard and Living bookshelf do not depend on either
TV startup protection.

If the TV is switched off later, its two-hour off interval must finish before
the same inactivity condition is checked again. Returning to any other state
restarts that interval. The periodic check cannot bypass it. `unknown`,
`unavailable`, or missing sensor states never count as inactivity. An unknown or unavailable TV protects its outlet
without preventing Dining Media guard from shutting down.

The two-hour standby allowance is a conservative power policy, not a signal
that panel maintenance has completed. LG says OLED care can take up to 1.5 hours
on some models and must not be interrupted by unplugging the TV; see the
[LG OLED care guide](https://kr.eguide.lgappstv.com/manual/w24_mr2/global/Contents/settings/oledcare_k_u_b_e_c_a_t_j/enga/w24__settings__oledcare_k_u_b_e_c_a_t_j__enga.html).
Manual outlet controls are unchanged. Keep Living Sticky enabled when power
must remain uninterrupted beyond this interval, including manually scheduled care.

## Reload, recovery and manual control

The automation uses a ten-minute state trigger and repeats the elapsed-state
check once per minute. This catches a deadline whose pending trigger was lost
when automations reloaded, with at most one extra minute of delay. A full HA
restart begins fresh observed inactivity and TV-off intervals; downtime is not evidence
that rooms were empty. See Home Assistant's [state conditions](https://www.home-assistant.io/conditions/state/)
and [automation triggers](https://www.home-assistant.io/docs/automation/trigger/).

Startup, automation reload and an outlet recovering from `unknown`/`unavailable`
to `off` restore power if one of the four sensors is active and its room overrides
are off. A regular manual
`on` to `off` transition does not itself switch an outlet back on: the next
activity event or explicit reconciliation can restore it. Commands are sent only
when an outlet actually needs to change state. A failure of one outlet does not
block the others. Occupancy is rechecked before a later outlet command, so
returning activity protects the bookshelf as well as TV power.

Turning Sticky off does not itself restore power; the next activity or explicit
reconciliation does. If the room is already vacant, the periodic inactivity check
can shut down an outlet after Sticky is released. Manual control of an outlet
does not disable occupancy management; enable its Sticky override to hold it in
the chosen state across future activity, reloads and inactivity checks.

An explicit TV power-on request may restore `switch.living_tv_guard` while
lighting Sticky is on; this is direct user control, not occupancy control. It
leaves Sticky unchanged. After the bounded startup grace, all normal inactivity,
TV-state and room-override checks still apply.

## Verification and troubleshooting

`tests/test_dining_media_evening.py` runs the actual automations against simulated
entities in an isolated Home Assistant instance. The same behavioral suite runs
for both Dining Media guard and Living bookshelf. It covers each activity source,
continuous shared inactivity, the last sensor's deadline, new movement, offline
sensors, TV states, late TV shutdown, manual off, outlet recovery, startup/reload,
one failed outlet, activity arriving between commands, room override isolation,
unknown overrides, Sticky changes during a wait or service call, newly restored
outlet power and missing/active wake timers. `tests/test_lg_tv_wake.py` also runs
both packages together for manual cold/warm wake during inactivity and shutdown
after grace. Only test copies shorten durations; physical loads are not switched.

Inspect the traces for **Media guards: Restore power on occupancy** and
**Media guards: Turn off after shared inactivity**. The latter retains its stable
entity `automation.dining_media_guard_evening_power_off`. For a blocked shutdown,
check the state and last-change time of every sensor, the applicable Sticky
overrides, then the native LG state.
Do not treat a missing motion report as proof of an empty room.

Validate the full configuration before `automation.reload`; no Core restart is
required. Install the LG wake package's timer and helper, reload timer and script
configuration, then reload both packages' automations together. Preserve the independent `switch.dining_guard` curtain controller and
all lighting Sticky definitions.

The deployed rules must enforce the same Sticky policy for Dining Media guard
and Living bookshelf: both Living and Dining Sticky must explicitly be `off`
before either outlet changes automatically. A runtime configuration that ignores
Sticky is stale and must be corrected in both restore and shutdown actions,
including startup, reload and recovery paths. Preserve unrelated timers and TV
power checks when reconciling this drift. Inspect the deployed configuration;
a source test pass alone cannot establish which policy is currently running.

The source reconciliation for this package is tested offline. Merging it does
not prove a live deployment or physical outlet response; those are separate
operational checks.

Matter exposure is a separate step on the existing bridge. Preserve all prior
endpoints and controller fabrics; publish only the canonical relay. Keep
addresses, MACs, registry IDs, credentials and operational receipts outside
this repository.
