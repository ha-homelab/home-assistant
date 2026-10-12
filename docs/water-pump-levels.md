# Water pump level thresholds

The owner-approved operating thresholds are **below 26 cm** to stop the pump and
**above 27 cm** to restart it. The shutdown rule turns `switch.pump_power_enable` off,
then requests `switch.shutoff_valve` on (open). The startup rule turns the pump
on, then requests the valve off (closed). The 1 cm gap and strict comparisons
avoid repeated switching near the threshold: exactly 26 or 27 cm, and the interval between them, cause no transition.

The automation library keeps its existing pump-state conditions and lower-reading
guard (`sensor.water_cm > 1`). Missing or nonnumeric source readings now mark
the level and derived volume unavailable instead of exposing a zero fallback.
The water-level guards and notification destinations are unchanged.
This changes operating cutoffs only, not the tank geometry or volume calculation.

## KMC pump control and shared power protection

Pump control now uses the first KMC's `switch.pump_power_enable` for rules 101,
102, 128 and 129. The bounded valve helper also checks this entity when waiting
for acknowledgement and validating the original request. The former Zigbee
pump relay is no longer part of these control paths; it can be renamed for
reuse independently. The real valve remains `switch.shutoff_valve`.

Both power protections remain enabled and watch
`sensor.kmc_water_and_laundry_power` above **700 W**: rule 101 for **3 minutes**,
rule 102 for **5 minutes**. This is the **shared total of all three KMC outputs**,
including Moen monitor power and Laundry, and is **not yet calibrated**. It is
not an individual pump-consumption measurement. Other connected loads can
therefore contribute to the threshold; the owner explicitly selected this
shared signal. No scaling, pump-only estimate or threshold change is applied.

Rule 101 retains its historical one-minute alias and stable ID, but its actual
configured duration is three minutes. Existing water-level guards, the
ten-second valve-request delay and notification actions are preserved.

Before deploying these references, record all automation enabled states and
wait for the four water automations and `script.water_valve_after_pump` to become
idle naturally. Validate the installed configuration, reload scripts and
automations, then verify compiled references and restore no state blindly.
Compare the enabled-state inventory after reload; both protections must remain
enabled. Configuration verification does not require operating a relay or valve.

The stable entity IDs `automation.water_level_less_than_18_centimeters` and
`automation.water_level_more_than_19_centimeters` retain their historical numbers
to preserve references. Their active thresholds are defined by rules 128 and 129
in the pinned automation library; their notification text now says 26 and 27 cm.

Deploy the reviewed library pin, validate with the installed HA configuration
checker, and reload automations at an idle action boundary. A full HA restart is
not required. Numeric-state triggers fire when entering the configured range;
changing the YAML alone does not force an immediate physical transition. Verify
both switch states separately: a successful configuration check does not prove
that an unavailable valve accepted a command.

## Bounded valve recovery

Rules 101, 102, 128 and 129 dispatch their explicit valve command through
`script.water_valve_after_pump`. This asynchronous helper leaves the pump
automation free to handle a new threshold crossing while Flo is unavailable.
All four callers share the helper, and a newer request cancels the older one.
The high-power rules retain their original 19/23 cm guards and ten-second delay;
this change does not alter their protection cutoffs or notifications.

The helper allows up to 15 seconds for the pump's state acknowledgement, then
waits at most five minutes for the valve to become available. Both waits are
state-driven. The request is discarded when its original water range becomes
invalid; after pump acknowledgement, any pump state change also cancels it.
Current pump state and water level are checked again immediately before the
single valve command. A valve already in the requested state receives no call.

There is no periodic valve synchronization, repeated pump start, or replay after
completion, timeout, script reload or HA restart. A subsequent manual or Flo
safety closure is therefore preserved. A service error after the valve becomes
available ends the request; no blind retry can override an intervening closure.
Notifications still describe the water event, not confirmed physical valve
movement. Check the valve state separately when physical confirmation matters.

`tests/test_water_valve_recovery.py` executes the real helper in isolated HA with
mock switch services. It covers recovery at four minutes (using scaled timers),
expiration, invalid/boundary readings, changed intent, delayed pump acknowledgement,
a newer opposite command, manual closures and a second emergency pump shutdown
while Flo is offline. Tests requiring actual library callers run during deployment
with the bundled automation library present. Deploy the helper before its four callers;
reload scripts and then automations at a verified idle boundary. No HA restart.

## Water fill speed source

`sensor.water_fill_speed` displays the positive part of the existing native
Derivative helper `sensor.water_speed`, rounded to two decimal places in cm/h.
A real zero or falling water level displays zero; a missing or nonnumeric helper
reading displays unavailable. The old `sensor.water_level_derivative` reference
was an unfilled placeholder, not a configured entity. Neither pump control nor
its 26/27 cm thresholds depend on this display.

The existing helper is named **Water speed** and uses these options:

```yaml
name: Water speed
source: sensor.water_level_2_water_level
round: 2
unit_time: h
time_window:
  hours: 0
  minutes: 10
  seconds: 0
```

No unit prefix or maximum sub-interval is configured. The raw source already
reports centimetres, so the derivative produces cm/h without a conversion.
These are the current options of the built-in HA Derivative integration
(configuration version 1, minor version 4 in HA 2026.9.1).

Restore the existing helper from the native HA backup. For a new installation
without that helper, create one Derivative helper with the options above and
ensure its entity ID is `sensor.water_speed`; do not create a second helper when
the restored one exists. The helper settings and registry identity are unchanged
by this repair. The display retains `sensor.water_fill_speed`.

Only the template source reference changes. A controlled `template.reload`
applies it without reloading Derivative or restarting HA. Reloading the template
integration also briefly recreates water-level entities: preserve enabled states
and temporarily disable the two level-crossing rules (128/129) during that reload,
then restore them after the level sensors are stable. The two high-power rules
(101/102) trigger on shared KMC power and only test water level as a condition; this
source-only template reload does not require disabling them. Do not trigger pump/valve automations
just to verify a display. The isolated HA tests exercise availability, positive
and negative rates, real zero, rounding and recovery.
