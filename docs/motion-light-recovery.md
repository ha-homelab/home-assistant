# Motion-light timeout recovery

Room overrides also cover activation and dimming. See
[Motion lighting overrides](motion-light-sticky.md) for shared-light ownership,
action-time checks and the existing morning reset schedule.

The shared `config/blueprints/automation/ha_homelab/motion_light_off.yaml`
blueprint controls 11 motion-timeout rules covering 14 distinct lights and
lighting switches. Instances in `dependencies/automations` supply their motion
triggers, targets and existing conditions. The same protection for manual
switching applies to every instance, including Tea table and LED Under Cabinet.

## Manual switching and genuine recovery

An ordinary `off -> on` transition is a manual override of an older inactivity
deadline. The light stays on until a new motion cycle clears and its configured
timeout expires, or someone turns it off. There is no separate manual-on expiry.
An already pending timer, the once-per-minute check, HA startup and automation
reload cannot use motion that cleared before this new on-state to turn it off.

The quick recovery check accepts only `unknown -> on` or `unavailable -> on`,
after three seconds. These transitions indicate restored availability, rather
than an ordinary turn-on. `unavailable -> off -> on` is an ordinary turn-on for
this purpose: the immediately preceding state is `off`.

Eligibility belongs to each target individually. Recovery of one dining-room
light does not authorize shutdown of another light that was just turned on
manually. A recovery run remembers the recovered entity and that on-state's
`last_changed` timestamp. An intervening off/on cycle, loss of availability or
other new state invalidates that run. Attribute-only changes do not start a new
on-state.

## Timeouts, guards and retries

Any active configured motion sensor blocks shutdown. The most recent valid
motion-clear event determines the applicable inactivity deadline; newer motion
supersedes an older timer. Unknown or unavailable sensors cannot establish
inactivity, although another working configured sensor can do so.

Every attempt rechecks inactivity and all existing sticky, sun, time and other
conditions immediately before the device command. Only targets currently `on`
are commanded. The dining dimmer retains its two-second transition. Light and
switch targets use their own domain's `turn_off` service, and a failed device
call does not prevent attempts for other eligible targets.

If a recovered target remains in the same on-state after a failed shutdown,
its recovery run retries every 60 seconds, with the same guards on every
attempt. A `wait_template` cancels the old retry loop promptly when that state
ends; it does not wait a full minute before noticing an off/on cycle. Recovery
entitlement is never inferred from the automation's shared `last_triggered`
timestamp. The blueprint uses `mode: parallel` with `max: 20`, allowing another
target's trigger to proceed while a recovered device waits for its next retry.

The periodic check also retries ordinary motion-driven shutdowns when the
current motion-clear event belongs to the target's current on-state. It cannot
revive an older deadline after a new manual turn-on. The former counter-only
workaround is folded into this shared behavior; rule 051 retains its seven-minute
timeout and Kitchen sticky condition.

## Restart and reload boundary

An HA restart or a reload that rebuilds a changed automation cancels its
recovery runs. HA preserves unchanged automation instances during selective
reload, including their valid in-memory recovery provenance and pending runs.
After a run is lost, an `on` state alone is not enough to reconstruct whether a device recovered
from a disconnection or was turned on manually. A fresh motion cycle or a newly
observed genuine availability recovery establishes eligibility again.

Sensor timestamps can still support ordinary timeout checks when they prove a
motion-clear event followed the current on-state. A full HA restart generally
resets observed state timestamps; the blueprint does not assume the house
stayed empty while HA was stopped. This deliberately avoids replaying an old
shutdown against a newer manual turn-on.

No cloud service, new helper entity, snapshot or persistent pending-command
store is required. Existing sticky helpers continue to block shutdown wherever
the instance configures them.

## Current rules

The following rule numbers refer to filenames in `dependencies/automations/config`.
Targets, durations and existing instance guards are preserved.

- **013 Bathroom:** mirror light, 5 minutes; Bathroom sticky.
- **017 Bathroom two:** `switch.bath2`, 20 minutes; Bathroom sticky.
- **020 Bedroom:** Bedroom Lamp, 3 minutes; sun elevation below 0.60°, 18:00–23:10
  in HA's local time, and Bedroom sticky.
- **031 Dining room:** four lights/switches, 5 minutes; sun below 0.10° and
  Dining room sticky.
- **038 Hallway:** two lights, 5 minutes; sun below 1.95° and Hallway sticky.
- **047 Kitchen table lamp:** 35 minutes; sun below 0.60° and Kitchen sticky.
- **048 Kitchen table lamp prolonged inactivity:** 40 minutes; sun below 0.10°
  and Kitchen sticky. This is a second rule for the same lamp.
- **051 LED Under Cabinet:** 7 minutes; Kitchen sticky.
- **054 Tea table:** 3 minutes; sun below 0.60° and Kitchen sticky.
- **063 Lobby:** `switch.dining_wall_light_2`, 5 minutes; sun below 0.20° and
  Lobby sticky. This target also belongs to the dining-room rule.
- **082 Porch:** two lights, 5 minutes; sun below 0.20° and Porch sticky.

## Validation and deployment

`tests/test_motion_light_off.py` exercises the actual blueprint in isolated HA
instances with fake lighting services. The regression checks for this change
must cover manual turn-on past old deadlines, fresh motion, both availability
states, failed recovery retries, sibling isolation, off/on cancellation,
attribute-only updates, restart/reload boundaries, and unchanged instance
guards. Test results are recorded separately; this document does not certify
that a test run or physical device check has completed.

Validate the installed HA configuration and compare fresh live file hashes
before applying the blueprint and matching automation instances together.
Reload automations after the check succeeds; neither an HA restart nor a script
reload is needed. Preserve unrelated live configuration. Tests with fake
services verify the logic without switching household devices, but cannot prove
that an offline physical device receives a command.

Reference: [HA automation triggers](https://www.home-assistant.io/docs/automation/trigger/)
and [blueprint schema](https://www.home-assistant.io/docs/blueprint/schema/).
