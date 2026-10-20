# Victron Off-grid mode and battery shutdown

`input_boolean.off_grid_mode` is the operator's persistent choice of island
operation. It replaces `input_boolean.victron_automatic_shutdown_enabled`.
The Home view exposes **Off-grid mode** immediately after **Winter**.
No `initial` value is configured: Home Assistant restores either ON or OFF on
restart. A new helper without any saved state starts OFF. Migration explicitly
sets OFF as requested, restoring the normal Winter schedule; it does not invert
the former disabled shutdown interlock into Off-grid ON.

## Operating policy

- **Off-grid ON:** the 00:01 overnight rule and the fifteen-minute grid-import
  shutdown rule send no inverter or charging commands. The overnight rule
  still records why it skipped the shutdown. The low-battery exception remains active.
- **Off-grid OFF + Winter ON:** at **00:01 America/Los_Angeles**, turn off an
  enabled Quattro, then enable `inverter_do_not_supply_ev` and
  `inverter_only_charging`. Winter takes precedence if Summer is also ON.
  This explicit operator policy does not require grid or battery telemetry.
- **Off-grid OFF + Winter OFF:** retain the overnight shutdown when Summer is
  OFF and valid available battery voltage is below 52 V.
- **Low battery:** below **50 V for five minutes**, with voltage still valid
  and below 50 V at execution, turn off the inverter in either mode. In Off-grid
  mode this exception also applies if the charge-only flag remains ON. Outside
  Off-grid mode, preserve the existing charge-only exemption.
- The economic grid-import rule still requires accepted AC input for two minutes,
  current import above 300 W and solar below 10 W. Off-grid must explicitly be OFF.
  Unknown or missing mode blocks economic and overnight shutdowns.

Off-grid is a manual policy choice, not an automatic grid-loss detector. Set it
ON when running the house without mains. It does not change physical BMS/inverter
protections, manually commanded switching, or the existing automatic start rules.
The 50 V threshold is a software reserve threshold, not a measured BMS state of
charge. A skipped midnight schedule is not replayed after restart or a mode change.
`binary_sensor.victron_battery_low` is ON only for finite positive voltage below
50 V. Invalid/unavailable readings turn it OFF and reset the confirmation period.
The reserve rule requires this sensor continuously ON for five minutes. It also
rechecks once a minute and when HA starts, the inverter returns, Off-grid is
selected, or charge-only ends. This recovers an already-low battery without
requiring a new voltage crossing. Automation reload preserves the sensor's
continuous-low age; a full HA/template restart conservatively starts a new interval.
A recheck never bypasses the five-minute guard.

## Visible status and decision history

The existing inverter card exposes **Night shutdown**, **Last midnight check**,
and **Battery below 50 V** after the mode switches. The policy entity explains Off-grid, season, disabled
night automation and missing voltage states. Its detail panel includes the next
00:01 check, current inverter/mode values and low-battery protection status.
This is a live policy summary, not a promise that the inverter is currently ON.

`input_text.victron_last_overnight_decision` retains the last midnight decision
and its timestamp/mode/voltage context across HA restarts. It is recorded even
when Off-grid blocks the run. A run says **attempting** before control services,
then **requested** only after all three service calls return. Neither wording
claims a physical acknowledgement. Diagnostic writes are best-effort and cannot
block a valid shutdown. Before the first new midnight run, the UI explicitly
says no decision has been recorded; it does not fabricate a prior result.
The helper is also recorded by the current recorder settings, unlike the
excluded input_boolean entities. No external notifications are added.

To reproduce the dashboard change, add these rows to the existing inverter
entities card, keeping its other controls:

```yaml
- entity: input_boolean.winter
- entity: input_boolean.off_grid_mode
- entity: sensor.victron_overnight_policy
  name: Night shutdown
- type: attribute
  entity: sensor.victron_overnight_policy
  attribute: last_overnight_decision
  name: Last midnight check
  icon: mdi:clipboard-text-clock-outline
- entity: binary_sensor.victron_battery_low
  name: Battery below 50 V
  secondary_info: last-changed
```

Avoid duplicating the existing Winter and Off-grid rows. Open **Night shutdown**
for the full decision text and protection details if the card truncates a value.

## Measurement contract

`sensor.battery_voltage` accepts only finite positive values up to 70 V. Missing,
zero, malformed and non-finite values become unavailable, never synthetic 0 V.
Its MQTT `expire_after: 90` makes a silent source unavailable. The grid binary
sensor has the same expiry. The keepalive issues exact reads every five seconds.

The minimum and maximum cell-voltage sensors for both batteries are unavailable
when none of their 16 cells has a finite numeric reading. When some cells are
available, extrema use those readings and continue to ignore missing or
non-finite cells. Their state templates return `none` for an empty input set
instead of sending the text `unavailable` through HA's numeric sensor handling.

Neither grid nor battery `last_reported` is a receipt clock. HA MQTT entities
can renew expiry on an identical message without writing a new state. Therefore
these shutdown rules use availability and validated values, not a 90-second
`last_reported` test for those sensors. The separate import/solar receipt checks
remain part of the economic rule.

## Verification and deployment

`tests/test_victron_black_start.py` in the automation library executes the actual
rules inside isolated HA with recorded switch services. Cases include Off-grid
blocking, Winter without telemetry, Summer precedence, unchanged live readings,
invalid/recovered voltage and the low-battery exception. The root
`tests/test_victron_battery_telemetry.py` checks invalid MQTT data, expiry and
restoration of both helper states across isolated HA instances.
`tests/test_victron_cell_extrema.py` checks missing, non-finite and partial cell
readings, including an actual template sensor becoming unavailable and recovering.
The dedicated
`test_victron_low_battery_triggers.py` suite attaches real HA triggers, including
an actual automation reload, and verifies startup, lost telemetry, mode changes,
and restored inverter availability. It shortens a copy of the five-minute window
after asserting the production threshold; it never calls live device services.
`test_victron_policy.py` verifies real template state changes and durable history.

Deploy `packages/victron_policy.yaml`, the mode helper and all three rules together. Back up and compare live
files before replacing them; validate using the installed HA. Reload input_boolean, input_text and template first, verify the low-battery
sensor exists, then reload automations while actions are idle. This migration needs no HA restart.
Check the new helper state, automation identities/enabled states, and the updated
Home dashboard. Remove the obsolete helper registry entry after confirming no
remaining runtime references. Do not trigger real inverter services to test.

If the recorder excludes input_boolean, its historical mode changes are not
available in the recorder even though RestoreEntity still persists the setting.
Keep private deployment receipts and snapshots separately from source control.

## Rollback

Restore only the backed-up files for this change after comparing current hashes;
do not overwrite concurrent unrelated edits or the full dashboard. Validate before
reloading affected domains. Restore the previous inverter-card rows from the
private dashboard snapshot. The previous interlock version defaults to blocking
shutdown, so do not enable it as a generic rollback step. Record that rollback
restores the old numeric-state re-arm limitation; hardware BMS/inverter protection
remains independent.
