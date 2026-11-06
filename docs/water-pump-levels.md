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

Rule 102 now watches `sensor.kmc_water_and_laundry_power` above **700 W** for
**two continuous minutes while pump power is enabled**. It stops the pump and
requests Flo fallback even when the tank-level sensor is unavailable. Starting
the pump while the meter is already above the threshold starts the timer;
turning it off or dropping to 700 W or lower cancels the timer. This is the
**shared total of all three KMC outputs**, including Moen monitor power and
Laundry, not a dedicated pump meter. The owner selected this signal because
other loads on the strip do not reach that threshold. Calibration and the
700 W threshold are unchanged.

Rule 101 remains an enabled three-minute backup with its existing low-level
guards. It now requires the pump still to be on and uses the same guarded
fallback; normally rule 102 has already stopped it. Historical IDs and file
names remain stable, while rule 102's display name says two minutes. Optional
notifications follow fallback dispatch, so a failed notification does not delay
the water command. The old ten-second delay is removed from these protections.

## Low-pressure fallback

`packages/water_flo_failover.yaml` also watches `sensor.water_pressure_psi` below
**20 psi (about 138 kPa)** for 30 seconds. This matches the lower normal limit in
the supplied Flo warning. Invalid/negative pressure is not treated as zero.
The native Flo integration polls cloud data approximately once per minute;
this is not a local pressure switch or an email trigger. Its generic alert
sensor reports counts, not the specific warning type, so it cannot identify
low pressure on its own. Startup checks the current pressure after 30 seconds.

`script.water_flo_failover` cancels an older pending valve request, requests pump
off, and allows 15 seconds for acknowledgement. It then allows at most five
minutes for Flo and its alert status to become available. The alert sensor is
resolved from the valve's HA device registry; exactly one binary sensor is
required. A pending critical alert blocks automatic valve opening. Ordinary
warning counts alone do not. Missing or ambiguous alert information also
blocks opening. The pump stays off and a persistent notification describes
the unresolved condition.

Both waits require `wait.completed`: a pump acknowledgement or Flo recovery
arriving after the timeout cannot revive the expired request, even if the state
changes before the next action evaluates its guard.

Opening is attempted once, only while pump-off is still confirmed. A manual
pump restart cancels a pending opening; a later manual/safety valve closure is
not repeatedly undone. Level-based pump startup yields while fallback runs or
pressure is below 20 psi. Both the pressure rule and power protection work
without `sensor.water_cm`. The existing 26/27 cm level policy otherwise remains.

Flo's `switch.shutoff_valve` means **on = valve open**. It is distinct from
`switch.moen_flo_water_monitor_power`, which supplies power to the monitor and
is not switched by this fallback. Flo reports optimistic command state before
the next cloud poll; a successful service call is not physical flow confirmation.

`tests/test_water_flo_failover.py` uses isolated HA with mocked switches and a
synthetic Flo registry. It covers shutdown acknowledgement, cloud recovery and
expiry, critical alerts, cancellation, pressure boundaries, power spikes, and
starting under an already-high load. No real water commands are used in tests.

Before deploying these references, record all automation enabled states and
wait for the water automations and both water scripts to become idle naturally.
Validate the installed configuration, reload scripts and
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

Level rules 128 and 129 dispatch their explicit valve command through
`script.water_valve_after_pump`. This asynchronous helper leaves the pump
automation free to handle a new threshold crossing while Flo is unavailable.
Both level rules share the helper, and a newer request cancels the older one.
The independent protection rules use the guarded fallback described above.

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
with the bundled automation library present. Deploy the helper before its callers;
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
(101/102) trigger on shared KMC power, while only the backup rule 101 tests water level as a condition; this
source-only template reload does not require disabling them. Do not trigger pump/valve automations
just to verify a display. The isolated HA tests exercise availability, positive
and negative rates, real zero, rounding and recovery.
