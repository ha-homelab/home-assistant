# Home Assistant automations

The existing iNewSwitch outlet is now **Switch06** after its ESPHome 2026.9.1 update.
Rules 085/087/091/093/095/100 use `switch.switch06`, and rule 112 uses
`sensor.switch06_signal`. Only entity references changed; the 750 W estimate,
schedules, guards, delays, actions and stable automation IDs are preserved.

The second KMC strip's first physical output now has the logical Recliner role.
Rule 112 follows `switch.recliner` instead of the old third-datapoint/Tablet
alias. The first KMC now supplies **Moen Flo Water Monitor Power**, **Pump
Power Enable** and **Laundry**. Rule 112 follows their new entity IDs for
notifications only. Rules 074 and 091 omit that strip's former Fireplace and
Stage LED targets, so lighting and surplus-power routines cannot control the
new loads. Other targets, schedules and conditions are preserved.
Existing Living lamp and Studio Guard rules keep their logical IDs
and therefore follow their replacement outlets. The retained standalone plugs
Switch01–03 do not inherit those automation roles.

Water rules 101/102/128/129 now control the first KMC's
`switch.pump_power_enable`. Both power protections stay enabled and use
`sensor.kmc_water_and_laundry_power` above 700 W for 3 and 5 minutes respectively.
The owner selected this uncalibrated total for all three KMC outputs; it is not
pump-only consumption. Water-level guards, delays, valve requests and
notification actions are unchanged. The former Zigbee pump relay can be reused
without carrying these control references with it.

The bundled automation library for **ha-homelab**, running on the `h7` Home Assistant container in k3s. It contains **98 active automations** from the original 130-rule import, with readable English names, stable identities, descriptions, explicit execution modes, and five stored traces per automation.

The owner retired 11 obsolete rules on 2026-09-22: five guest-indicator rules,
five legacy Tuya device/quiet-mode rules, and the unused battery-discharge capture.
Their original identities and reasons remain in `retired_automations` in the
migration manifest. The validator requires the complete original inventory to
be accounted for and rejects undeclared deletion or identity reuse. Four retired
motion sensors are removed from the remaining bathroom and notification rules.
On 2026-09-23 the owner also retired `switch.tv_l`: five lighting rules now run
independently of TV power, retaining their motion triggers, timeouts, solar checks
and manual overrides. Switch notifications no longer watch the retired TV.

The initial migration preserves every trigger, condition, action, delay, template, target, execution limit, and configured initial state. Existing notification text is retained because it is part of the running behavior.

On 2026-09-24 the owner retired the unused Backyard camera. Its two motion
snapshot/notification rules are removed; their identities and retirement reason
remain in the migration inventory.

On 2026-09-24 the owner also retired the Blink-based early curtain-closing
exception. The ordinary evening solar thresholds, morning schedules, and
`input_boolean.curtains_sticky` manual override remain unchanged.

On 2026-09-24 the owner retired Postbox and Presence Sensor 1. The two mailbox
notification/indicator rules are removed. Kitchen lighting keeps its RF motion
triggers, 35/7/3-minute inactivity timers, availability retries, and existing
guards. Motion notifications retain their destinations and one Chrome copy.

## Layout

The garage button rule 022 is a disabled, empty compatibility entry after the
TS0041-TB firmware conversion. Its stable entity ID is preserved, but it no
longer attaches the stock `remote_button_short_press` / `button_1` trigger or
sends `light.toggle`. The button controls its native Zigbee group directly.
This prevents trigger setup errors after HA reloads and duplicate light commands
if the legacy automation is accidentally enabled or manually triggered.

Living-room curtain rules 027, 029, and 077 delegate to the root
`script.living_curtains_move` helper: power the shared socket, begin learned RF
commands after three seconds, then independently repeat the same target over
Wi-Fi when each motor returns. Existing schedules and manual overrides remain;
the evening kitchen/office/dining branch retains its delays and power-off order.
Deploy the root `living_curtains_rf` package and its private secret values before
reloading these callers. See the root
[RF curtain runbook](https://github.com/ha-homelab/home-assistant/blob/main/docs/living-curtains-rf.md).

Victron rules use the persistent `input_boolean.off_grid_mode`. When it is ON,
rule 121's economic shutdown and every action in rule 125's midnight sequence
are blocked. When it is OFF, Winter turns off the inverter at 00:01 independently
of grid/battery telemetry (and takes precedence over Summer). Without Winter,
the non-Summer below-52-V condition remains. Rule 122 retains the 50 V / five-minute
low-battery exception in both modes, including Off-grid with a leftover charge-only
flag. Missing/invalid voltage never qualifies as low battery. The root-provided
`binary_sensor.victron_battery_low` must stay ON for five minutes; startup,
mode/inverter changes and minute rechecks recover an already-low battery after
reload without bypassing that duration. The midnight rule also records its
skipped/attempting/requested decision in a persistent root-provided text helper;
these best-effort diagnostics are not physical acknowledgements. Battery/grid MQTT
expiry, not `last_reported`, detects their missing messages; identical valid
messages can refresh expiry without changing that timestamp. The economic rule
retains its stable-grid and current import/solar guards. Deploy with the companion
root helper replacement. Tests execute real HA conditions with mocked device I/O.

- `config/` — one automation per YAML file. Numeric filename prefixes preserve the original include order.
- `migration/automations.json` — original names, persistent entity IDs, new display names, and behavior fingerprints.
- `archive/` — five definitions that were already inactive; `.yaml.disabled` files are excluded from Home Assistant's YAML loader.
- `tools/` — offline validation, identity seed generation, and runtime verification.

The [home-assistant repository](https://github.com/ha-homelab/home-assistant) bundles this directory and assembles its `config/` contents into the runtime `/config/automations/` directory. Home Assistant uses:

```yaml
automation: !include_dir_merge_list automations/
```

## Validate locally

### Victron telemetry keepalive

Rule 118 sends the legacy Serial read every five seconds with
`{"keepalive-options":["suppress-republish"]}`. An unsuppressed payload (`{}` or empty) on that topic
also requests the entire Venus item tree; repeating it can build up subscriber
queues and delay MQTT keepalive responses. Suppression retains the streaming
lease and exact Serial response without the periodic tree replay.

The rule also reads `vebus/290/Ac/ActiveIn/Connected` and
`system/0/Dc/Battery/Voltage` explicitly. These two Home Assistant inputs expire
after 90 seconds and must receive real observations even when values stay
constant. The enabled MQTT birth message, `homeassistant/status = online`,
requests one complete tree when HA reconnects, bootstrapping the other sensors.
A two-run queue lets this connection event wait for an in-flight heartbeat;
overlapping periodic ticks are skipped to reserve that queue slot.
The stable automation ID is unchanged; all publications use read (`R/`) topics.

Deploy the corresponding root repository commit, validate HA's complete
configuration, and reload automations only when existing actions are idle.
Verify the loaded rule, advancing sensor reports, and Venus MQTT stability.
The source protocol is documented in
[dbus-flashmq](https://github.com/victronenergy/dbus-flashmq#keep-alive).

### Local commands

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python tools/validate.py
```

For independent comparison with the original private snapshot:

```bash
.venv/bin/python tools/validate.py --baseline /path/to/original/config
```

Validation rejects duplicate YAML keys, duplicate identities, missing files, changed registration order, and unrecorded runtime behavior changes. CI runs these checks and a Gitleaks scan. Deliberate behavior changes update the fingerprint while retaining the imported fingerprint for independent baseline comparison.

## Water pump level thresholds

The water-level rules stop `switch.pump_switch` and turn on
`switch.shutoff_valve` below **26 cm**, then start the pump and turn off the valve
above **27 cm**. At exactly 26 or 27 cm, and between those values, neither
threshold fires. This retains a 1 cm gap to avoid repeated switching.
The existing lower-reading guard (`above: 1`), pump-state conditions, high-power
protections and notification routing are preserved. Notification text uses the
new thresholds. The historical automation entity IDs containing `18` and `19`
remain stable; their names do not define the active thresholds.

## Motion-light recovery

Twelve lighting shutdown rules use the shared `ha_homelab/motion_light_off.yaml`
blueprint supplied by the root configuration repository. Original motion triggers
are the single source of sensor IDs and timeouts. The blueprint retries after a
light returns and once a minute, rechecks current motion and existing guards, and
isolates failures per lighting target. Newer motion supersedes stale timers.
The old standalone counter recovery rule remains registered but disabled and
empty. Deploy these instances together with the root blueprint; see the root
[runbook](https://github.com/ha-homelab/home-assistant/blob/main/docs/motion-light-recovery.md).
The migration map records these 15 deliberate changes and the expected disabled
state of the retired rule. All other identities, enabled states and rules remain
under the original contract. The identity seed tool retains legacy aliases but
is not a rollback to historical behavior; use the previous release for rollback.

## First deployment

Follow [MIGRATION.md](MIGRATION.md). **Seed identities using the original aliases before deploying the renamed configuration.** Of the 130 automations, 126 previously had no registry identity; assigning an ID and renaming one in the same first reload can change its entity ID and break dashboard references.

Deploying these files does not require restarting the Home Assistant pod. Configuration validation and controlled automation reloads are handled through the root repository's deployment workflow.

## Editing rules

Bath 2 uses `light.bath_2`, backed by the enabled but hidden ESPHome relay
`switch.bath_2`. Motion rules and scheduled shutdowns use light services.
Both entities are excluded from rule 112 screen notifications.
The original Tuya light remains available as `light.bath2_old` for explicit
manual use. Motion timing, the bathroom manual override, and automation
identities are unchanged.

1. Keep the `id` stable for the lifetime of an automation. Never regenerate it when changing a name or moving a file.
2. Keep existing `automation.*` entity IDs stable. Dashboard and integration references use those identifiers.
3. Explain the purpose and relevant timing in English. Treat thresholds, service targets, templates, and trigger IDs as runtime behavior.
4. Preserve execution modes and limits unless a separately reviewed behavior change requires otherwise.
5. Never commit tokens, passwords, `secrets.yaml`, `.storage`, or raw backups.

See [KNOWN-BASELINE.md](KNOWN-BASELINE.md) for inherited behavior and the boundary of the initial migration.

## Camera snapshot recovery

Camera callers now delegate to the root `script.capture_camera_alert` helper,
which validates a fresh JPEG before replacing the saved image and rotating
history. Deploy the matching root package/helper with these callers. Existing
notification guards, destinations and stable entity IDs are retained. See the
[root runbook](https://github.com/ha-homelab/home-assistant/blob/main/docs/camera-snapshot-recovery.md)
for bootstrap history, source migration, tests and rollback.

On 2026-09-25 the owner retired 28 light entities. Eight dependent arc-lamp rules
are retired without broadening their guards; shared morning shutdown rules only
drop the retired targets. The living-room curtain schedule now enables Living
guard 1 before its existing 90-second warm-up, then waits for and opens each
motor independently while rechecking the manual override.

## Concise motion notifications

Rule 070 sends the sensor name alone to MQTT and display destinations, for example
`Counter Motion` instead of `RF Counter Motion turned on`. It removes the leading
RF prefix and uses one shared label for every destination. Entity identities,
triggers, mute and destination selection remain unchanged. The explicit
`rf_motion` category identifies RF source entities independently of their display
text; deploy the matching root notification router before reloading this rule so
Chrome/phone suppression stays effective. Non-RF motion keeps its existing routing.
The root HA runtime suite checks the actual rule and notification router together.

## Cabinet LED 1 manual use and recovery

Rule 051 treats only `unknown`/`unavailable` to `on` as quick availability
recovery. An ordinary `off` to `on` leaves Cabinet LED 1 on until another motion
cycle or a manual turn-off. There is no new seven-minute timer just because the
light was turned on. The existing seven-minute motion timer starts when the new
motion clears. `input_boolean.kitchen_sticky` blocks every shutdown attempt.

Minute/startup/reload checks also respect manual use: an old motion-clear time
cannot authorize shutting down a newer light-on state. An off attempt already
authorized by genuine recovery or a newer motion cycle can still retry after a
device failure. A new off/on cycle cancels that older intent. The shared blueprint
accepts an optional `recovery_from_states` filter; its default retains other
instances' existing behavior. Deploy the matching root blueprint before this
instance.

## Bounded water-valve recovery

Rules 101/102/128/129 send their explicit Flo valve request to the root
`script.water_valve_after_pump` helper using `script.turn_on`. The pump automation
therefore remains available for new level crossings while Flo is offline. A
request waits at most five minutes for Flo, rechecks its original water range and
pump state, and makes at most one valve service call. A newer request supersedes
an older one; completed requests never undo subsequent manual or safety closures.
The helper sends no pump commands and adds no periodic state enforcement. Deploy
the root helper before reloading these callers. High-power cutoffs, ten-second
delays, notifications and stable identities remain unchanged.

## Independent device recovery

Dining, hallway and porch motion-on rules attempt each existing lighting target
even if another device reports a runtime service failure. Their action order,
brightness, transitions, time and manual-override guards remain unchanged.
Failures remain visible in Home Assistant logs.

`tests/test_device_recovery.py` runs the retained motion-light rules in an
isolated Home Assistant state machine with mocked services. It checks that one
failed device does not prevent commands to the other targets. The required CI
job uses the pinned HA image with networking disabled; no real devices are used.

## Retired Man at work control

On 2026-10-11 the owner retired rule 106 (`automation.solar_on`) and rule 098
(`automation.power_above_three_hundreds`). HA no longer forces Heater One and
Heater Two back on or applies the legacy Solar S2000 grid-import cutoff through
these rules. Their identities and reasons remain in the retirement inventory.
The root configuration removes `input_boolean.man_at_work`; remove its row from
the storage-mode Lovelace dashboard when deploying this retirement. This does
not change the relays' current states or their local Tasmota Wi-Fi recovery rules.

## Daylight-aware morning curtains

Rule 077 opens the main and sheer living-room curtains at **sunrise or 06:30,
whichever is later**, using Home Assistant's configured location and local time.
Both events are triggers; the conditions require daylight, the 06:30–12:00 morning
window, and the existing manual override to be off. An early summer sunrise
therefore waits until 06:30, while a dark winter morning waits for sunrise.
The sun condition uses calculated event times so it does not race the update of
`sun.sun` at sunrise. Reloading the automation does not itself open the curtains.

The RF start three seconds after power-on and independent Wi-Fi fallbacks remain
in the existing root helper.

Rule 078 applies the same daylight rule to kitchen and dining curtains, keeping
its earliest start at **06:35**. It starts at sunrise or 06:35, whichever is later,
with the same manual override and noon cutoff. When sunrise is later than 06:35,
both room schedules start at sunrise. Kitchen/dining retain their existing
90-second motor warm-up before the Wi-Fi open commands, followed by the original
60-second delay and dining socket power-off. Their actual movement need not be
simultaneous with the living-room RF commands. Bedroom and evening schedules are
unchanged.
The isolated runtime tests in `tests/test_living_curtain_daylight.py` simulate
both seasonal event orders and the manual override without commanding devices.

## Garage lighting identities

The 05:35 and 05:45 shutdown automations explicitly include all five local ZHA
lights, `light.garage_bulb_one` through `light.garage_bulb_five`. This replaces
the four migrated `light.bedroom_*` references and adds the previously omitted
fifth garage bulb. Schedules, unrelated targets and parallel actions remain
unchanged. Deploy with the parent configuration's coordinated registry rename,
Garage group and household script update; see the [garage lighting runbook](https://github.com/ha-homelab/home-assistant/blob/main/docs/garage-lighting.md).

Dining guard consolidation replaces the three retired LocalTuya outlets with
`switch.dining_guard`. Morning and evening curtain rules keep their existing
schedules, conditions, delays and cover commands. The mixed dining-motion rule
keeps its fireplace and Living guard 2 actions; its retired Dining guard 2 action
is removed rather than redirected to curtain power.

## Retired Playpen heater

On 2026-10-10 the owner repurposed the former Playpen / Heat500w outlet as
Bath2 on ESPHome. The four small-heater rules 090, 092, 097, and 099 are retired,
with their identities retained in the migration inventory. Rule 090 also stopped
its source loads when transferring surplus to that heater, so the whole transfer
is retired. Rule 085 drops only the 450 W heater candidate; rule 098 drops only
its obsolete heater-off condition. All other load controls are preserved.
The new bathroom outlet is deliberately absent from these energy rules.

Room guard and Kitchen guard use the canonical ESPHome entities
`switch.mishka_guard` and `switch.kitchen_guard`. Rules 024, 025, 076, and 112
replace the old Laser target; rules 027 and 078 replace Kitchen guard 1.
The existing schedules, overrides, action order, and delays are retained.

Bedroom guard uses `switch.bedroom_guard` (ESPHome). Rules 028 and 076 retain
their existing evening/morning triggers, sticky override, delays and all other
targets; only the retired Bedroom guard 3 entity reference changes.

### Living lamp

The former bedroom lamp outlet is now the ESPHome relay `switch.living_lamp`.
Rules 020 and 021 were initially retired when this outlet moved. They are now
restored for the separate Matter `light.bedroom_lamp`, preserving the original
RF sensor, evening/sun guards, three-minute inactivity timeout and Bedroom sticky
override. The Living lamp outlet stays independent. Both household shutdown
automations include the new Bedroom Lamp; rule 112 uses the Living lamp relay.

### Studio guard

The converted WP5 outlet uses `switch.studio_guard` / Studio guard. Rules 027
and 078 retain their existing curtain schedules, overrides, delays, and all
other targets; only the former `switch.studio_guard_1` target changes.

### Bathroom warmer

The converted YM-WS-1 outlet uses `switch.bathroom_warmer` / Bathroom warmer.
Rule 019 retains the one-minute off timer and restores power only while
`input_boolean.bath_warmer_sticky` is off. Rule 112 retains its existing
state-change notifications. Only the retired `switch.bathroom_warmer_l`
references change. The root configuration owns the Away Devices scenes and
the Lovelace row, which use the same canonical relay.

### Dining Arc lamp

The former Studio wall-lamp controller is now `switch.dining_arc_lamp`.
Its old motion rules 110 and 111 are retired. Rules 074 and 075 drop only
the old lamp shutdown action; rule 085 drops only its former 35 W load-map
entry. The old Studio motion behavior is not carried to the new room. Dining rules
031 and 033 additionally control the new relay alongside the wall lights,
using the existing two Dining motion sensors, sun guards, Dining sticky
override, five-minute off delay, and recovery behavior.
The owner explicitly retained `input_boolean.studio_sticky`, its Office
button, and notification rules 041 and 042. Other lighting targets and
shared-rule behavior are unchanged.

## Dining Media guard

`switch.dining_media_guard` restores the former Dining guard 2 media/printer
power role. Rule 108 turns it on before the unchanged fireplace and Living guard
actions. Its action uses `continue_on_error`, so a failed media outlet does not
block the existing devices; failures from those later devices cannot block the
media outlet. Both RF dining motion triggers and `input_boolean.living_room_sticky`
remain unchanged. The separate `switch.dining_guard` still powers only the curtains.

The historical evening-off rule 107 remains retired. The root HA package
`dining_media_guard_evening.yaml` now provides a separate media-only replacement,
using the owner-selected `switch.living_lamp`: off for 15 minutes, still off, sun
below -2 degrees, and `input_boolean.living_room_sticky` off. It turns off only
`switch.dining_media_guard`, with no fireplace dependency. Dining Arc lamp and
the Matter Bedroom Lamp (formerly `light.arc_lamp_m`) are distinct devices and
do not trigger this rule. The
existing fireplace and Living guard behavior remains unchanged.

## Air purifier living

The former `switch.workdesk` is now the ESPHome relay
`switch.air_purifier_living`, displayed as **Air purifier living**. Rules 085,
087, 088, 091, 096 and 098 use its new entity ID. This is an identity rename:
the existing 235 W assumption, grid-power thresholds, priority conditions,
10-second state checks, other timers and all manual overrides are unchanged.
The original role in retired automation history remains historical evidence.

## MPPT fan

The former `switch.old_lamp` outlet is now `switch.mppt_fan`. Rules 123 and
124 retain their existing individual solar/power thresholds, five-minute
timers, relay-state guards, Heater Three actions, and notifications. This is
an entity migration, not a new aggregate-power or temperature control policy.

## Manual switching and motion timeouts

All 11 motion-timeout blueprint instances protect ordinary manual OFF-to-ON
use until a new motion cycle. Quick recovery accepts only unknown/unavailable
to ON and tracks each recovered device separately. Existing timeouts and
solar, schedule and sticky conditions remain in force. The root configuration
provides the matching blueprint and its isolated regression tests; deploy these
pinned changes together. Rules 110 and 111 remain retired.
