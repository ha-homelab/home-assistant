# Runtime reliability audit — September 28, 2026

The live audit at 02:37 UTC on September 29 found no HA Repairs issues. Flo had
recovered independently at 02:01 UTC; all seven Flo entities were available.
No device reset, water actuation or notification was used as a smoke test.

## Configuration and code fixes

- Four water rules now dispatch a bounded, asynchronous valve request. The
  [water runbook](../water-pump-levels.md) describes its 15-second pump-state
  acknowledgement wait, five-minute availability window, cancellation guards
  and single-command limit. A completed request does not enforce a standing
  valve state, and the helper never retries starting the pump.
- Water usage, cost, pressure, level, volume and fill-rate templates become
  unavailable when their numeric source is missing or invalid. Restoring a valid
  source restores the sensor, including the level-to-volume dependency. Actual
  zero readings remain valid. Units, conversions, level truncation and its
  existing 100 cm cap are retained. Fill rate keeps `cm/h` without the incompatible
  `speed` device class.
- The second/fourth-Friday calendar uses direct date arithmetic instead of
  constructing every possible day of the month. This fixes errors in February
  and 30-day months and reduces each update to at most three candidate dates.
  The existing schedule and same-day result of zero are unchanged.
- Snapshot rotation avoids replacing and fsyncing identical JPEGs while refreshing
  successful-capture timestamps. Equal payloads share one decode per commit;
  distinct historical frames are still validated. Missing/corrupt history and
  atomic replacement behavior are covered by regression tests.

## Validation and deployment

The installed HA 2026.9.1 runtime passed **109 isolated scenarios**, without
failures or skips: camera history, notification routing, Ring/ONVIF readiness,
motion recovery, valve cancellation/timeouts, and water/calendar templates.
Calendar results were independently compared for every day in 2024–2028.
Real template entities additionally verified cascading availability recovery.
The root YAML validator and all 106 automation contracts passed.

Stage against fresh live hashes, run HA's installed configuration checker, and
retain an on-volume rollback copy. After promotion, reload scripts at an idle
boundary and confirm the valve helper is registered before reloading automation
callers. Temporarily suspend only the two level-crossing rules while reloading
templates, then reload automations and restore their previous enabled states.
This prevents recreating the level sensor from manufacturing a water event during
deployment. Verify unchanged execution timestamps for those rules and the resulting
numeric sensors/calendar. The snapshot helper is loaded afresh by each shell invocation. No HA
restart or change to recurring backup schedules is required by this root release.

The audit also found Homeway websocket-reader blocking and failed weekly backup
jobs. Their source fixes and deployment evidence belong to the infrastructure
repositories. Intentionally disconnected Mikrotik1/Eero Shed devices and Roomba
i7's intermittent Wi-Fi are not retired by this audit.
