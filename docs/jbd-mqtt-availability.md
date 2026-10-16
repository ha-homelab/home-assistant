# JBD MQTT availability recovery

The 32 `sensor.jbd_chain2_monitor_voltage_cell{1..4}_bms{1..4}` entities,
including the corresponding `_2` entities, belong to two physical monitors.
Their similar names do not make them duplicates. Preserve their entity IDs,
unique IDs, device ownership and history.

## Diagnose the source before changing Recorder

The path is ESPHome monitor -> Cerbo FlashMQ -> HA Mosquitto bridge -> MQTT
integration -> Recorder. Check each boundary separately:

1. Save the two devices' registry entries and retained discovery documents.
   Chain 1 uses topic prefix `battery` and legacy discovery IDs; Chain 2 uses
   `battery2` and MAC-based discovery IDs. Confirm actual device MACs and MQTT
   client IDs from the registry and broker logs; do not infer ownership from the
   entity's display name.
2. Observe cell state topics on both brokers for at least 30 seconds. Count
   non-retained messages separately from initial retained deliveries. An old
   retained numeric value does not prove the monitor is publishing now.
3. Inspect `battery/status` and `battery2/status`. The discovery documents use
   these topics for availability. Fresh measurements together with retained
   `offline` explain why all the associated HA entities can remain unavailable.
4. Check that the bridge carries both chains' sensor/binary-sensor state topics,
   status topics and discovery documents inbound. Preserve the existing command
   boundaries; diagnosis does not require adding any battery control routes.
5. Correlate broker connection logs with the last numeric states and statistics.
   A later HA restart can update `unavailable` timestamps and obscure the original
   failure time. Verify global Recorder freshness independently.

Do not respond to this condition by deleting entities, changing retention,
purging/repacking the database, disabling availability, or publishing a synthetic
`online`. Values from the separate Victron integration need their own physical
mapping and retention review before being considered replacements.

## Publisher-side recovery after reconnects

The maintained firmware now imports one shared
[`mqtt-availability.yaml` package](https://github.com/victron-venus/esphome-jbd-bms-mqtt/blob/main/packages/mqtt-availability.yaml).
Each connected monitor repeats its real retained `online` message at QoS 1 every
30 seconds, on its own existing status topic. The birth message also uses QoS 1.
The native offline last will and shutdown message remain enabled. The refresh
runs only while the monitor's MQTT client is connected.

This prevents the status from remaining permanently offline after an older
connection's will arrives late. A transient false offline can still last until
the next successful refresh, normally up to 30 seconds. The firmware change
does not modify FlashMQ's internal ordering. It sends no battery commands and
does not force sensor updates. Cerbo's battery collector checks measurement
freshness separately from these two-segment status topics.

For diagnosis, allow two refresh intervals before considering a manual recovery.
If status remains offline, check the deployed package, real connection state,
source publications and bridge delivery instead of assuming the timer ran.

## Recovery for the confirmed stale-status condition

When all 16 cells of a monitor are publishing fresh values but its status is
`offline`, recover one MQTT session at a time:

1. Keep a separate observer connected with a unique diagnostic client ID.
2. Recheck the monitor's exact MQTT client ID and authentication context against
   current broker evidence. A one-shot connection using that same client ID can
   replace its stale broker session. Immediately disconnect the diagnostic
   connection gracefully, preserving its persistent session (`clean_session=false`),
   with automatic reconnect disabled, no diagnostic will, and no publishes.
   This briefly interrupts only that monitor's MQTT connection.
3. Allow the real ESPHome monitor to reconnect. Require a **non-retained**
   `online` birth message from the publisher and fresh values for all 16 cells.
   Stop if either is missing; repeated session takeovers are not a recovery loop.
4. Verify the same results through HA's broker, then observe beyond the monitor's
   keepalive interval. Re-subscribe to verify the retained status is now `online`.
   Preserve the other chain until the first has passed these checks.

This procedure changes connection state, not configuration or firmware, and has
no configuration rollback. If the publisher fails to reconnect, inspect device
and network connectivity rather than retaining the diagnostic connection or
fabricating availability. It requires no HA, Cerbo, broker or ESP32 reboot and
sends no restart, charging, discharge or protection commands.

ESPHome's [birth and last-will messages](https://esphome.io/components/mqtt/#last-will-and-birth-messages)
explain the availability contract. The [firmware repository](https://github.com/victron-venus/esphome-jbd-bms-mqtt#readme)
documents discovery identities; cluster configuration owns the bridge routes.

## Acceptance checks

Use the exact 32 cell IDs and a fixed recovery timestamp. Require all of the
following, rather than merely checking that a timestamp differs from yesterday:

- Both retained status topics are `online`; all 32 state topics have fresh,
  finite numeric measurements and all 32 HA states are numeric.
- Entity/device identities and identity/state/availability routing in all 138
  discovery documents remain unchanged. An OTA update changes the configuration
  hash in ESPHome's firmware metadata; verify its version separately.
- Each cell has a new numeric raw Recorder row after recovery.
- Each cell has finite five-minute and hourly statistics whose interval covers
  post-recovery measurements. Check both `start_ts` and `created_ts`: an hourly
  bucket starts before recovery when service resumes midway through the hour.
  Wait for the relevant aggregation boundaries before claiming completion.
- Use indexed metadata lookups and per-entity timestamp queries with `LIMIT 1`;
  no full history scans are necessary.

The [Recorder policy](recorder-retention.md) remains independent: global retention
is 28 days, the exact 32 cell entities have seven-day raw history, and the
21 exclusions and 12 protection/extrema includes remain unchanged. Recovery
resumes future history; it does not recreate the missing interval.

## September 30, 2026 incident

All 136 measurement/binary-sensor entities were unavailable even though both
monitors were publishing. The two restart-button entities account for the rest
of the 138 registry entries. The MQTT integration was loaded, discovery was
present, and the six bridge state/status routes were intact.

FlashMQ 1.23.2 logged new monitor connections at **2026-09-30 00:16:43 and
00:16:53 UTC**, then removed their older sessions at **00:16:55 UTC** with
`SessionTakenOver` and keepalive-expiry reasons. The last five-minute cell
statistics started at **00:15 UTC**. This sequence, together with continuing
measurements and retained `offline`, is consistent with a late old-session will
overwriting the new connection's birth message. The original individual MQTT
publications were not captured, so that ordering remains an inference.

The real publishers emitted `online` after one session recovery each at
**2026-10-01 03:50:36 UTC** (Chain 1) and **03:51:15 UTC** (Chain 2), or
September 30 at 20:50/20:51 Pacific. No firmware, bridge, Recorder, registry or
BMS settings changed.

The initial recovery above changed connection state only. The subsequent
publisher-side fix is tracked in
[firmware PR 69](https://github.com/victron-venus/esphome-jbd-bms-mqtt/pull/69).
An isolated FlashMQ 1.23.2 instance reproduced the ordering in eight out of eight
pipelined same-client-ID reconnects. Replaying the package's refresh restored
retained online after 30 seconds; closing the real test connection kept it
offline across the next refresh interval.

Both physical monitors received the package on October 1 UTC, one at a time,
while keeping their installed ESPHome versions. Each then passed a real MQTT
session-takeover test: native offline delivery, the actual publisher's online
birth, subsequent QoS 1 refreshes about 30 seconds apart, retained online after
a 90-second observation window, and fresh finite values for all 16 cells.
The diagnostic clients sent no publications. Telemetry freshness was checked
within 30 seconds, stricter than the battery collector's 60-second stale limit.
The subsequent HA check found all 136 measurement states available and all 32
cell topics fresh and finite. All 138 registry and discovery identities/routes
were preserved; only the expected firmware configuration hashes changed.

For future OTA changes, preserve the installed BLE scan/polling settings and
ESPHome version, keep one rollback image per monitor, and verify fresh telemetry
after each device separately. The deployed Chain 1 YAML is historically named
`jbd-all-batteries.yaml`; it contains four BMS devices and must not be replaced
with the repository's legacy eight-BMS template of the same filename.

The October 1 rollback bundle is stored privately on the ESPHome persistent
volume at `/config/.codex-jbd-reconnect-20261001`. It contains the original live
YAML, per-monitor baseline and patched OTA images, the shared package and a
SHA-256 artifact manifest. Baseline images use the previously installed
ESPHome versions (2026.6.5 for Chain 1, 2026.7.4 for Chain 2) and the same verified
BMS component revision. These binaries and live YAML contain credentials and
must not be committed to Git. Roll back one monitor with its own baseline image
and original YAML, then repeat the source/HA freshness and identity checks.

Build in a private persistent workspace or a dedicated builder with an explicit
disk budget. The ESPHome dashboard pod's `/tmp` volume has a 1 GiB limit: keeping
both compiler environments there exceeded it and caused that pod to be evicted
after these OTA uploads. Its replacement was ready, and all four persistent
images and both live configuration hashes were rechecked. MQTT telemetry and
the monitor firmware run independently of the dashboard. Do not use its limited
temporary volume for future multi-version builds.
