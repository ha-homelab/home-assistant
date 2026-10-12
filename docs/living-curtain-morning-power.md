# Living-room morning power repair — 2026-09-25

Historical repair record. The subsequent
[RF start with Wi-Fi fallback](living-curtains-rf.md) retains power-on and the
manual override while replacing the living-room 90-second delay with a
three-second RF start and independent Wi-Fi fallbacks.

The 06:30 living-room curtain automation contained only a 90-second delay and
two `cover.open_cover` calls. It never powered `switch.living_guard_1`, which
supplies both living-room motors. The same omission exists in the original
15 September import. The 25 September trace confirms that the time trigger and
manual-override condition passed, followed by the delay and both service calls;
an apparently finished trace did not prove motor movement.

Enable `switch.living_guard_1` first, preserve the 90-second warm-up, and then
wait up to three minutes independently for each original motor entity. One
unavailable motor or failed open command must not block the other. Recheck
`input_boolean.curtains_sticky` immediately before each open command, including
when the user enables the override during warm-up. If the relay telemetry is
unavailable but the motors are already available, still allow the scheduled
open commands. Leave power on afterward; do not change motor calibration,
direction, position wrappers, or the 06:30 schedule.

The isolated HA tests in `tests/test_living_curtain_morning.py` use the pinned
automation and fake switch/cover services. They cover power-before-movement,
the initial manual override and a later override, one unavailable motor,
delayed reconnection, one failed command, and unavailable relay telemetry with
working motors. Tests shorten delays only in their private copies.

Deploy after installed configuration validation and an idle-checked automation
reload. A power-only live check can verify motor reconnection without issuing
an open or close command. Physical opening at the next scheduled run remains
separate from this configuration/runtime verification.

Live power-only check: at 2026-09-25 15:09:36 UTC, `switch.living_guard_1`
changed from off to on after the switch service call. The main curtain returned
at 15:09:50 UTC and the sheer at 15:10:01 UTC (about 14 and 25 seconds). Both
motor endpoints and the relay answered on their configured Tuya TCP ports.
No open, close or position command was issued during this check. Their reported
50% positions after boot are not treated as fresh physical position verification.
