# OTT d1 navigation with Sonoff RM433

`config/packages/ott_d1_remote.yaml` uses the existing MQTT discovery triggers
for the RM433 remote. Buttons are numbered left to right, top to bottom:

- First row: button 1 sends Up; button 2 sends Left.
- Second row: button 3 sends Down; button 4 sends Right.
- Third row: buttons 5 and 6 remain unassigned.
- Bottom row: button 7 sends Back/Cancel; button 8 sends OK/Enter.

These are ordinary navigation keys, so their effect follows the player's current
screen (live playback, channel list, or another menu). This
requires no receiver firmware, Debian service, or player code change.

The trigger's registered device ID is `8ac1a57250698f6b441439e5a6e9c5a0`.
Its MQTT identifier is `sonoff_rm433_462be`; discovery validates source `rf`,
radio origin, RM433 format, bit count, and each learned code. The receiver already
suppresses repetitions until a 350 ms quiet interval. The automation ID is
`ott_d1_rm433_channels`.

Each press first reads controller presence. It sends one
`input` request with the selected named key only when the target
`dev_c0b414dd92b2b5a36fffde703a6968f5` has exactly one valid presence entry,
a last-seen age from zero to three seconds, and no pending commands. Each HTTP
request has a three-second timeout. Home Assistant keeps at most four runs,
including the active one, in arrival order. Each press gets an absolute
two-second deadline in the automation's top-level variables, before joining
the action queue. A queued press whose deadline has passed is discarded without
making an HTTP request.

If the presence check does not permit sending, the active run waits 150 ms
before another GET, only within the original deadline. It clears the previous
response before each attempt. Immediately after GET it rechecks the deadline,
so even a successful response arriving late cannot cause a POST. A valid idle
response permits exactly one POST; POST timeouts and failures are never retried.
Thus a brief pending command no longer loses the next nearby press, while a
long outage does not build up a queue of stale navigation commands. A slow
in-flight HTTP request may finish after two seconds; the deadline limits when
new requests can begin, not how long an already started request can take.

The controller currently retains an accepted request for up to 60 seconds.
The presence check reduces stale delivery but cannot make the check and send
atomic: a player that disconnects between them may receive the command later.
A POST timeout also does not prove the request was rejected. Do not add automatic
retries. HTTP 202 means accepted by the controller, not verified navigation.
The player's input response also precedes dispatch: `accepted: true`,
`dispatched: false`, `effect: input-after-ack` is the normal acknowledgement.
Use the operation record and observed UI state to verify the later effect.

The existing controller requires `User-Agent: ottplay-cli/1.0` on this route.
Set `ott_control_authorization` in private `/config/secrets.yaml` to the existing
controller authorization value (`Bearer` plus its administrator token). Do not
commit its value or expose it in command output. The URL and target are fixed,
and the public package contains only the secret reference. The existing
`igw_google_voice.yaml` package keeps REST command logging at warning level.

## Scoped deployment

1. Review the package and this runbook. Record the source revision and package
   SHA-256. Confirm that the live RM433 MQTT device ID and d1 ID still match.
2. Make private copies of the existing secret file and package, if present.
   Compare fresh hashes before editing to detect concurrent changes. Add only
   the new secret key, preserve all other keys, and retain restrictive modes.
3. Atomically install only `/config/packages/ott_d1_remote.yaml`. Do not promote
   a complete overlay or replace `/config/release.json`; unrelated live changes
   may differ from the assembled repository release.
4. Run the installed Home Assistant checker (`python -m homeassistant --script
   check_config --config /config --json`) and keep output private. If it fails,
   restore this package and secret change before rechecking; do not reload.
5. Save a fresh `/api/states` snapshot and pass `tools/verify_idle.py` immediately
   before each reload. Once idle, call `rest_command.reload`, then repeat the
   idle check and call `automation.reload`. No HA restart is required. Preserve
   disabled automations, and record before/after states and pod restart count.
6. Confirm both REST actions and automation registration. Verify rejected
   presence responses cannot cause a POST, then test one physical press of
   each chosen button. Compare the RF event, HA trace, controller request
   result, operation record, and player UI state. A synthetic trigger verifies only the
   downstream path and must be recorded separately from physical RF evidence.

For rollback, restore or remove only this package and its newly added secret
key, run the installed checker, and repeat the guarded REST/automation reloads.
Retain the private rollback copies and scoped deployment receipt.

## Deployment verification, 2026-10-11

The package was installed with the existing controller credential kept in HA's
private secrets file. The installed configuration check passed. Both targeted
reloads passed their idle guards; existing automation enabled states were
preserved and the HA pod did not restart. The registered automation is
`automation.ott_d1_rm433_channel_buttons`.

The user's physical Button 3 press reached HA as
`rf:e25ece990e1d2b94:2003`; it did not match the original two-button automation.
The six-button navigation mapping above replaces that incomplete assignment.
Physical single-press reception was also verified during RM433 commissioning.
Synthetic downstream verification and physical navigation checks are recorded
separately; an acknowledgement alone does not prove what appeared on the TV.

All six labelled synthetic MQTT events subsequently reached the input handler;
each corresponding operation record reported `invoked` and `handler_completed`.
UI snapshots confirmed that OK opened the channel list and Back closed it. The
snapshots do not expose the highlighted row, so they do not independently verify
the visible arrow movement. Seven regression tests passed using the installed
HA runtime in an isolated temporary configuration.

During the later physical calibration, Up, Down, Right and Back all reached
their input handlers. Left reached Home Assistant but the original immediate
presence gate discarded it because the preceding command was still pending.
This directly motivated the bounded wait above. A subsequent physical OK press
also reached its input handler, and the next UI snapshot showed the channel
list. Actual arrow movement still requires observation on the display.

The regression tests run the actual automation in isolated HA instances, with
local event triggers and fake REST services. They exercise brief busy recovery,
FIFO order, the four-run bound, expiration while queued, a GET completing after
the deadline, and an uncertain POST that must not be repeated. No test connects
to the live player or publishes RF events. Thirteen tests passed against the
installed HA 2026.10.0 runtime. The bounded-queue revision is not yet deployed.

The commissioned MQTT discovery entries are tracked in
[Home Assistant PR 105](https://github.com/ha-homelab/home-assistant/pull/105).
They must already exist before enabling this package on another installation.
