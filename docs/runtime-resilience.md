# Automation and script resilience

[Deployment evidence and rollback](releases/2026-09-22-runtime-resilience.md).

The September 22 audit examined 133 loaded automations (130 folder, three package)
and 68 scripts (54 folder, 14 package), their entity/service references, execution
modes, delays, repeated sequences, templates and recent runtime errors. The
[follow-up inventory](runtime-audit-2026-09-22.json) records missing static references
without credentials, message contents or runtime state attributes.

## Changes

- A shared `script.notify_optional` replaces 62 direct notify calls. Its small
  Python-script dependency checks the **current service registry on every call**;
  a provider returning later is used automatically. Missing services log only
  their names. Delivery errors remain in HA logs and subsequent independent
  actions continue. Original recipients, payloads and ordering are retained;
  schema and template failures still surface as configuration errors.
- The same helper checks power/availability before calling the two confirmed
  webOS notifiers (`notify.lg2` and `notify.lg_webos_tv_oled77c5pua_dusqljr`).
  Their media-player IDs are explicitly mapped because the living-room entity
  was renamed. Off, unavailable, unknown or missing TVs are quietly skipped;
  active/idle/paused TVs receive the unchanged payload. Each call reads current
  state, so delivery resumes without a reload. Chrome copies and subsequent
  household actions still run, and errors from attempted deliveries remain
  visible. Skipped deliveries do not wake the TV or replay on power-on.
- Five invalid `notify.send_message` calls targeting the LG media-player entity
  now use that same TV's registered webOS notification service. The device
  registry confirms the exact destination. Missing legacy phone/browser/TV
  services are not redirected to another recipient.
- Calls to the existing notification/logging scripts cannot abort subsequent
  household actions on a runtime delivery failure. Pump protection still turns
  the pump off, attempts notifications, waits ten seconds and closes its valve.
- MQTT notification scripts use queues (maximum 100) so concurrent calls are not
  silently dropped by single mode. The JSON message uses `to_json`, preserving
  decoded fields, topics and retain flags while escaping arbitrary text.
- Confirmed entity corrections cover the Dinner Two motion sensor (five rules),
  Kitchen presence sensor (one rule), and irrigation timer's switch state trigger.
  Existing timeout durations and conditions remain unchanged. The irrigation
  switch and Kitchen sensor were registered but unavailable at the snapshot;
  fixing an ID does not reconnect their hardware.
- Heating cooldown accepts the first run when `last_triggered` is `None`.
- Nine-player shutdown uses one loop and continues after an individual failure.
  Household shutdown continues from lights to switches and host shutdown after
  independent service failures. Targets and order are preserved.
- Repeated porch fades, Cree reset cycles and mailbox flashes use loops with the
  exact original command order and delays, verified against the original sequence.
- Kodi supplied IDs no longer contain a literal inline comment. Selected-channel
  playback reads the selector state and requires one matching catalogue entry.
  Missing/malformed/ambiguous catalogues stop before requesting playback.

The existing [motion timeout recovery blueprint](motion-light-recovery.md) remains
in use for 14 shutdown rules. Broader automation modes, power thresholds, household
schedules and device assignments are preserved. Power-control and safety routines
were not combined into a generic blueprint: their guards and ordering differ.

## Source and runtime consistency

The root IGW package is synchronized with the already deployed local Cast service
configuration, including its existing `igw_google_flow` script. This is source drift
repair, not a change to the live IGW package. Its authorization remains a local
`!secret`; the repository contains only the secret name and an example placeholder.
The runtime verifier now accepts user display-name overrides only when registry
platform and original configured name match. This preserves the user's `Energy`
name for `script.igw_google_status` without weakening entity-ID checks.

The immutable script import remains in `contracts/source-baseline.json`; reviewed
changes are recorded separately in `contracts/reviewed-runtime.json`. Automation
contracts retain the original import fingerprint alongside the reviewed behavior.

## Validation and deployment

`tests/test_runtime_resilience.py` runs 22 isolated scenarios in the installed
Home Assistant 2026.9.1 runtime, using the actual script engine, Python-script
sandbox, template renderer and MQTT schema. Device and notification services are
mocked. The scenarios include missing/returning/failed providers, schema errors,
complete package merging/service registration, JSON escaping, queued messages, preserved timing, Kodi selection, heating first
run, the irrigation trigger and pump protection continuing to the valve.

Root CI runs the helper scenarios in the pinned HA image with networking disabled.
Tests needing private library files skip in public checkout CI; **all 22 must run
without skips for deployment**. The existing lighting scenarios also validate all
14 current blueprint instances. Repository validators enforce all original IDs.

Deploy both library revisions together with this root package and Python script.
Stage changed files against the actual live configuration, verify their previous
hashes, run HA `check_config`, keep a rollback copy, and validate the installed
configuration again. Check fresh runtime state for active work before each reload.
Reload `python_script`, then `script`; verify both new services and the helper
entity are registered **before** reloading caller automations. No HA restart is needed.
Verify all IDs/enabled states and deployed hashes afterward. Reloads reset pending
in-memory `for` timers; the motion blueprint reconciles elapsed lighting timeouts.

No real notification, reset sequence, pump, heater or media action is invoked as a
smoke test. Passing isolated scenarios establishes code behavior, not live hardware
or provider availability.

## Remaining operational dependencies

The audit retains 30 distinct static entity IDs absent from both state and entity
registries. They include legacy Tuya switch IDs, old speakers/TVs, cameras, motion
sensors and the Kodi player/catalogue. The inventory gives each source location.
They are not automatically removed or remapped: identical room names do not prove
that two devices are interchangeable. Registered-but-unavailable devices are a
separate integration/hardware issue.

The four notification dependencies from the initial audit have since been resolved
in the [owner-directed notification repair](notification-repair.md): the old
phone and Pushbullet destinations were removed, Chrome HTML5 delivery was restored,
and the old TV reference now uses the confirmed working LG service. The 30 remaining missing
static device/entity IDs remain a separate follow-up. Dynamic templates and
device-ID actions cannot be fully validated by the static inventory.

The owner-approved [retirement cleanup](retired-entities.md) removed 22 of the
original missing dependencies and their obsolete callers.

The shared helper also mirrors Chrome deliveries to [Vitaly iPhone Air](iphone-camera-notifications.md), including on-demand live camera attachments.
