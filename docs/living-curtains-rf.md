# Living-room curtains: fast RF start with Wi-Fi fallback

The living-room main and sheer curtain schedules dispatch learned Dooya requests
three seconds after powering their shared socket. Each requested
motor still receives the same Open or Close command over Wi-Fi when its existing
Home Assistant cover entity becomes available. An RF completion event is not an
acknowledgement from the motor, so it never suppresses this fallback.

This replaces the living-room morning flow's 90-second warm-up. It also removes
the main living-room curtain from the other rooms' evening warm-up sequence and
adds power-on before the evening sheer command. Automation identities, execution
modes, and unrelated rooms are preserved. The 2026-10-07 morning correction below
adds daylight and local-time guards to the living-room opening schedule.

## Installed revision and deployment

The historical root and automation revision records remain with the deployment
operator. The public bundle contains the [current helper source](https://github.com/ha-homelab/home-assistant/blob/b10fa9a87a356f8942aef383042c6a23e6cebcbd/config/packages/living_curtains_rf.yaml).
In that historical deployment, the merged root tree was identical to the staged and checked revision
`2253c31232875c62c1a17325a3bcf0bbf2856bf8`. The installed package
`/config/packages/living_curtains_rf.yaml` has SHA-256
`c6fe18d19cc8d2c85df5ea77efe1a577d01da4e812561f7cd62642cb2bd19413`.

Deployment replaced only the three automation files, the new package, and the
required private secret additions. Both staged and live installed-HA checks
reported zero errors. Fresh idle guards passed before script and automation
reloads. After reload, all three new scripts were available and idle; the three
existing schedule automations were enabled. The four previously disabled automations
remained disabled. Unrelated live configuration and `/config/release.json`
were preserved because the whole live configuration differs from the assembled
root release. Private backups, checks, and installation receipts are retained
under `work/rf-dooya-upgrade-private` outside Git.

The RF node runs reviewed public firmware
[`d33918a39135f07aafbd76e92f60470abf9c945b`](https://github.com/ha-homelab/rf-airbridge/commit/d33918a39135f07aafbd76e92f60470abf9c945b).
OTA completed successfully, all 15 legacy RF sensor entities remained present,
and Home Assistant exposes both the RCSwitch and Dooya native actions. See the
[RF Airbridge runbook](rf-airbridge.md) for the build identity and firmware
validation history.

## Live Close-both verification

A live `script.living_curtains_move` request with `curtain: both` and
`command: close` completed successfully after installation. Timing below is
measured from completion of the shared socket's `switch.turn_on` service call,
not from independent measurement of voltage at either motor:

- The main RF request was dispatched at **3.008 seconds** and the sheer request
  at **5.015 seconds**. This exercised the three-second warm-up and two-second
  serialized dispatch gap.
- Both Dooya transmissions reported `send_finished` with `button: 3`,
  `check: 3`, `repeats: 3`, `receiver_resumed: true`, and
  `delivery_confirmed: false`.
- The sheer Wi-Fi fallback was called at **9.980 seconds** and the main fallback
  at **18.360 seconds**. Both independent waits reported completion and the
  parent script trace finished.
- A real received RF frame appeared **13.904 seconds after the second transmit**,
  on the same post-OTA boot. This confirms reception resumed after
  the transmissions in the observed session.

The private evidence is retained in `live-close-summary.json`,
`move-trace-final.json`, and `live-events.jsonl` under
`work/rf-dooya-upgrade-private`. The shared socket remains powered, matching the
helper's existing power policy.

This verifies the live power/dispatch/fallback sequence, not physical curtain
movement or RF delivery to a motor. The reported `closing` state and position
50 were not accepted as movement evidence because boot-time position telemetry
can be stale. No visual observer confirmation has been recorded. Physical Open
and Close acceptance for both motors remains outstanding, including separating
RF operation from the later Wi-Fi fallback.

## Schedule changes

- **Sunrise or 06:30, whichever is later, both living-room curtains:** automation 077 calls
  `script.living_curtains_move` with `curtain: both`, `command: open`.
- **Descending sun between 0 and 0.6 degrees, sheer:** automation 029 calls the
  same helper with `curtain: sheer`, `command: close`. Its descending-sun and
  manual-override conditions are retained.
- **Sun below 0.2 degrees, main:** automation 027 runs a living-room helper
  branch alongside its existing other-room branch. Kitchen, office, and dining
  retain their socket commands, 90-second delay, Wi-Fi close commands, one-hour
  delay, and original power-off sequence. Only the old living-room Wi-Fi close
  call is removed from that branch; its fallback now belongs to the helper.

Kitchen/dining rule 078 starts at **sunrise or 06:35, whichever is later** and
retains its 90-second Wi-Fi motor warm-up. Bedroom schedules are unchanged.
Both living-room motors use `switch.living_guard`. These flows leave that
socket on, as before; they add no new living-room power-off policy.

### Morning daylight correction — 2026-10-07

The former fixed 06:30 trigger opened both curtains before daylight. The trace
confirmed a scheduled run at 06:30 on 7 October, when the configured sunrise was
approximately 07:10 local time. Rule 077 now has both a 06:30 time trigger and a
sunrise trigger, guarded by the 06:30–12:00 local morning window and the sun
condition `after: sunrise`, `before: sunset`. This makes the later event win
without a long-running wait or an additional helper. HA calculates sunrise from
its configured location; local time follows the configured time zone and DST.

An early summer sunrise cannot open the curtains before 06:30. In autumn and
winter, 06:30 cannot open them before sunrise. The astronomical condition avoids
a race with `sun.sun` changing state at sunrise. It estimates daylight; it is not
an outdoor illuminance measurement. Existing manual override, RF commands and
Wi-Fi fallback remain in effect. There is no new startup, reload or catch-up
trigger, and no movement command is part of deployment.

Deploy only automation 077 after checking for live-file drift, retaining its
previous file privately, and running the installed HA configuration check.
Reload automations only after a fresh idle check; preserve existing enabled and
disabled states. Rollback restores the previous 077 file and uses the same check
and reload. Runtime tests live in the automation library; the root caller
contract checks this schedule while preserving the evening contracts.

The correction was applied on 2026-10-07. Staged and installed configuration
checks both returned zero errors. A fresh idle guard preceded the automation
reload; all 123 registered automation identities and the four disabled states
were preserved. The living-room morning automation remained enabled and idle,
with its last-triggered timestamp unchanged by the reload. The six isolated
daylight runtime scenarios passed locally in the installed HA runtime and in CI.
The installed 077 file has SHA-256
`ee5c445ee24ba94bbae4e15d1db4743f96ea3c7c0ad95df35255164167027e0f`.
Private pre-change files and deployment receipts are retained outside Git.

### Kitchen and dining daylight correction — 2026-10-07

Rule 078 previously started every day at 06:35 even when it was still dark. It
now follows the same daylight rule as the living room: time and sunrise triggers,
the existing manual override, a local morning window ending at noon, and the
astronomical condition `after: sunrise`, `before: sunset`. Its earliest time
remains 06:35, while the living room retains 06:30. On mornings with sunrise later
than 06:35, both automations start at sunrise.

Only the schedule and conditions change. The existing studio, dining and kitchen
socket commands, 90-second warm-up, kitchen/dining Wi-Fi open commands, and
60-second delay before switching off the dining socket are preserved. Kitchen
and dining therefore receive their opening commands about 90 seconds after the
shared sunrise trigger; this is not a simultaneous RF movement command. Evening
and bedroom schedules are unchanged.

The automation library's daylight tests exercise both morning schedules against
early, late and winter sunrises, a sunrise between their earliest times, manual
override changes, and the noon cutoff. They substitute service handlers and
shorten only the private test copy's delays, so testing sends no device commands.
The kitchen/dining action sequence and production delays are checked explicitly.

Deploy only rule 078 after checking live-file drift, saving a private backup,
and passing staged and installed HA configuration checks. Reload after a fresh
idle check and compare automation identities and disabled states. Rollback uses
the saved 078 file followed by the same check and reload. There is no startup or
reload trigger and deployment does not request curtain movement.

Applied on 2026-10-07. All 14 isolated daylight scenarios passed in the installed
HA 2026.9.1 runtime. Staged and installed configuration checks returned zero
errors; the idle-guarded reload returned HTTP 200. All 123 automation identities
and four disabled states were preserved. Rule 078 remained enabled and idle,
with its last-triggered timestamp unchanged. The deployed file has SHA-256
`b35c4de60f52fdaf97b17da8ffd6b53ac9e40139242f5f8cd30cdaf94da8026b`.
Private backups and verification receipts are retained outside Git. The next
natural morning run has not yet been observed.

## Execution and manual override

`script.living_curtains_move` validates the requested target and action, checks
`input_boolean.curtains_sticky`, powers the shared socket, and waits three
seconds. It dispatches all selected RF requests before starting either Wi-Fi wait.
The main command precedes the sheer command when both are requested.

`script.living_curtain_send_rf` is a short queued wrapper. It checks the manual
override again when a queued request starts, launches
`script.living_curtain_rf_transport` with `script.turn_on`, and leaves a
two-second gap between dispatches. The transport rechecks the override and asks
`esphome.rf_send_dooya_code` to send three repeats. The gap accommodates the
normal three-repeat transmit duration and the firmware's shared cooldown.

Transport errors remain in that background script and do not prevent the
caller's Wi-Fi fallback. This isolation is necessary even with
`continue_on_error`: Home Assistant 2026.9.1 does not suppress a missing-service
error with that flag and does not expose a `has_service` template function.
The queue serializes dispatches, not physical acknowledgements. A missing or
failing native service remains visible in the transport trace/log.

After the RF attempts, each selected motor gets an independent, parallel wait
of at most 180 seconds for its original cover entity to become available.
The wait also exits if the manual override is enabled. A final override check
precedes each Wi-Fi command. A timed-out or failing main motor does not block the
sheer motor, or vice versa. The helper itself allows parallel invocations, so a
long Wi-Fi wait cannot occupy the shared RF queue and block another scheduled
curtain command.

Fallback always repeats the same target command, including when an entity
already reports the target position. Boot-time position values are known to be
stale and do not confirm physical movement. No boot-time calibration, opposite
movement, or inferred position is introduced. If power relay telemetry fails,
the existing policy of still attempting movement is retained for motors that
may already have power.

## Private learned identities

The package `config/packages/living_curtains_rf.yaml` reads four integer secrets:

- `living_main_curtain_rf_remote_id`
- `living_main_curtain_rf_channel`
- `living_sheer_curtain_rf_remote_id`
- `living_sheer_curtain_rf_channel`

Populate these from the privately retained, observed Dooya frames, not from the
placeholder zeroes in `secrets.yaml.example`. The selected command variants are
Open `button: 1`, `check: 1`, and Close `button: 3`, `check: 3`, each observed for
both profiles. Alternative observed check nibbles are not cycled or guessed.
The remote identifier and channel select the target profile; private captures,
actual identifiers, and secrets must not be copied into the public RF project.

Capturing a remote's code establishes a candidate command, not successful motor
operation from the ESPHome transmitter. Verify physical Open and Close for
each motor during commissioning and record the result separately.

## Validation and deployment

`tests/test_living_curtain_morning.py` loads the real package through Home
Assistant's YAML include and package-merge path with synthetic secrets and
mocked device services. It checks power-to-RF order, serialized RF before Wi-Fi,
missing/failed RF service fallback, stale-position handling, independent
timeouts/reconnection, manual override during warm-up/queue/waits, and concurrent
fallbacks. Delays are shortened only in the test copy. Caller contract tests
compare the three edited automations with immutable pre-change automation
revision `692d615a32bdafd9f26ab3b56d2ed3cc1dc0dc64`.

All 14 isolated runtime scenarios passed in the installed Home Assistant
2026.9.1 runtime on 2026-10-06, using mocked device services and synthetic
identities. All three caller contract tests and both repository validators also
passed. These checks verify orchestration, not RF reception by either motor.

The automation library owns files 027, 029, and 077. Review and merge that
component first, then pin its reviewed commit in this root repository alongside
the package. Deploy the package and private secrets before reloading its callers.
Keep the existing four manually disabled automations disabled.

Use scoped deployment: back up and atomically replace only these three
automation files, the new package, and the required private secret additions.
Do not replace unrelated live configuration or assert that the entire running
configuration matches a root release. Run the installed Home Assistant
configuration checker and take a fresh idle check before each script/automation
reload. Preserve an earlier copy of every changed file for rollback.

The configuration is installed. Physical curtain acceptance is recorded
separately from configuration validation and API dispatch. On rollback,
restore the three previous automation files, reload them after a fresh idle
check, then remove the helper package only when no running caller depends on
it. Retain the private learned captures and original firmware recovery copies.
