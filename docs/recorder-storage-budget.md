# Recorder storage operating budget

## Scope and acceptance

Keep Home Assistant Recorder in its existing MySQL schema, with **one day of raw
states/events and five-minute statistics**. Keep hourly long-term statistics,
Energy counters, device identities and configuration. Any k3s datastore on the
same MySQL instance must use a separate schema and account, outside every
Recorder query and cleanup operation.

Use decimal units: budget **5,000,000,000 bytes**, operating target
**4,000,000,000 bytes**, early cleanup threshold **3,500,000,000 bytes**.
This is an operating budget with measured cleanup, not a MySQL hard quota.
Native HA retention has no size limit. Arbitrary bursts, delayed cleanup and
indefinitely retained hourly statistics can exceed the budget; report this
explicitly rather than silently deleting protected statistics.

The November 11 audit measured 43,708,252,160 bytes of data/index allocation:
32,175,980,544 states; 9,005,137,920 state attributes; 1,230,503,936 events;
866,254,848 short-term statistics; 145,522,688 long-term statistics. The oldest
indexed raw state was approximately 29.16 days old. A recent 20,000-state sample
covered 495 seconds, about 3.49 million rows/day. One day should be substantially
smaller, but only post-cleanup measurements establish its actual size.

## Initial cleanup

1. Capture Recorder freshness, current hourly statistic metadata and an exact
   UTC request time. Verify that another purge/rebuild is not already running.
2. Call the supported `recorder.purge` action once with `keep_days: 1`,
   `repack: false`, `apply_filter: false`. Persist the request cutoff and outcome.
   Do not treat the HTTP response as completion.
3. Follow the same cutoff using indexed existence/oldest-row checks on `states`,
   `events`, `statistics_short_term` and `statistics_runs`; also check newly
   written raw rows and newly completed hourly buckets. Do not repeatedly enqueue
   another purge merely because allocated bytes remain high.
4. If a purge raises a foreign-key or other database error, do not claim cleanup
   completed or enqueue repeated retries. Preserve foreign-key enforcement and
   diagnose the failed cycle before adding periodic cleanup. Shorter retention
   alone does not repair a failing purge.
5. HA 2026.11.0 uses a default 4,000-ID batch. Each cycle can process up to 20
   state batches and 15 event batches, then requeues unfinished work. Roughly
   92 million old states imply over a thousand cycles. Measure the first 5–10
   minutes before estimating duration; database latency and attribute cleanup
   dominate, so there is no reliable fixed completion time.
6. Once the old rows are gone, evaluate physical reclamation separately.
   `recorder.purge` with `repack: true` runs `OPTIMIZE TABLE` across **all** HA
   Recorder tables in this version. Keep automatic repack disabled. Verify
   tablespace type, managed-instance free storage, temporary rebuild headroom,
   expected locking and both HA/k3s health before a deliberate maintenance run.
   Never run a schema-wide rebuild during k3s migration or an existing rebuild.

The configuration change requires a coordinated HA restart to become the daily
default. The explicit purge action does not require that restart. The dishwasher
`history_stats` source remains recorded, but its current-day calculation can lose
the earliest hour on a 25-hour daylight saving transition day. Longer raw-history
cards, including a five-day thermostat chart, lose older raw detail;
hourly-statistic charts retain their long-term history. Daily purging alone can
retain nearly 48 hours before the next run; `keep_days: 1` is a cutoff per run,
not continuous expiration.

## Deployed follow-up and historical monitoring proposal

The retention change itself did not install a controller. The later
[shared runtime PR #65](https://github.com/ha-homelab/k3s-self-healing/pull/65)
added the MySQL budget worker to the existing Core updater. On November 11, 2026,
the installed settings enable that worker with qualified purge. It measures every
five minutes and latches a Recorder pause at 4.5 GB; it never automatically resumes
recording. This remains backpressure, not a hard storage quota. The implementation
and recovery procedure live in the private deployment runbook; see also
[database switching and backup boundaries](recorder-heatwave-local.md).

The following is the **earlier design proposal**, retained to explain its intent;
it is not an inventory of deployed services. The selected implementation reuses
the updater inside k3s, rather than adding the host timer proposed below. For a
separate host-based implementation, run one controller outside k3s so a datastore
failure does not disable its own monitor. Use a timer
every five minutes, a process lock and private persistent request state.
Keep SQL credentials schema-scoped and never place credentials in command-line
values or public YAML.

- Confirm `SELECT DATABASE()` equals the explicitly configured HA schema before
  any query. Reject a schema containing `kine`. The controller sends no SQL DELETE,
  ALTER, OPTIMIZE, DROP, TRUNCATE or privilege changes.
- Read fresh data/index estimates with session `information_schema_stats_expiry=0`
  and a bounded SELECT timeout. Poll size/freshness every five minutes.
- Request native one-day cleanup hourly, or earlier at 3.5 GB after a 15-minute
  cooldown. Keep native daily `auto_purge: true` as the fallback. Do not interpret
  HA automation `mode: single` as a backend purge lock.
- Write the fixed cutoff and `dispatching` state durably **before** the HTTP call.
  A timeout/crash after dispatch is an unknown outcome: keep the request pending,
  verify its cutoff and never blindly replay it. A request nonce is an audit
  identity, not an HA service idempotency key.
- While pending, verify progress against that fixed cutoff. No new request is
  allowed until old rows are absent. After 30 minutes without observable progress,
  alert; do not kill HA or create a request storm. If a pending request survives an
  HA restart and has stopped progressing, an operator may explicitly reconcile it.
- If the raw cutoff is satisfied but measured size remains above 4 GB, report
  reclamation/capacity work needed. Purging again cannot shrink retained files.
  At 5 GB, raise a critical budget breach with measured bytes and metric type.
  Do not change retention to zero or delete hourly statistics automatically.
- `recorder.disable` is not a hard write fence: it gates state/event recording,
  while statistics/import tasks can still write. Its flag also resets at startup.
  Do not use it as evidence that a hard size cap has been enforced.

Do not deploy a second controller from this historical proposal alongside the
installed worker. Its actual scheduling, private settings and durable receipts
are the operational source of truth; documentation alone is not enforcement.

## Distinguish the storage measurements

`SUM(DATA_LENGTH + INDEX_LENGTH)` estimates allocated clustered/secondary-index
pages for the exact HA schema. It is not a sum of live payload bytes or a physical
disk measurement. `TABLE_ROWS` is approximate. `DATA_FREE` identifies reusable
tablespace extents; it must not be subtracted and labelled physical savings.
In shared tablespaces it can be repeated on multiple table rows.

For actual HA files, inspect `INFORMATION_SCHEMA.INNODB_TABLESPACES` using an
authorized administrative collector: require `SPACE_TYPE = 'Single'`, match
actual schema/table identity, sum `ALLOCATED_SIZE` once per distinct tablespace,
and retain `FILE_SIZE` separately. The current HA account cannot query these
tables; `innodb_file_per_table=1` alone does not prove the type of every existing
table. Missing permission produces **physical size unknown**, never a zero.

Managed-instance storage additionally includes other schemas, binary/redo/undo
logs and temporary files. Measure those through OCI/server telemetry separately.
Deleting HA rows does not authorize deleting logs, k3s rows or any other schema.
After reclamation require a fresh physical result below 5 GB, a healthy HA
Recorder, preserved hourly statistics and healthy k3s. Continue monitoring over
at least a full operating day before claiming a stable storage plateau.

## Primary sources

- [HA Recorder configuration](https://www.home-assistant.io/integrations/recorder/)
  and [supported purge action](https://www.home-assistant.io/actions/recorder.purge/).
- Exact HA 2026.11.0 [purge implementation](https://github.com/home-assistant/core/blob/2026.11.0/homeassistant/components/recorder/purge.py),
  [queued tasks](https://github.com/home-assistant/core/blob/2026.11.0/homeassistant/components/recorder/tasks.py),
  [batch limit](https://github.com/home-assistant/core/blob/2026.11.0/homeassistant/components/recorder/const.py),
  [repack implementation](https://github.com/home-assistant/core/blob/2026.11.0/homeassistant/components/recorder/repack.py)
  and [recording/statistics paths](https://github.com/home-assistant/core/blob/2026.11.0/homeassistant/components/recorder/core.py).
- MySQL [table estimates](https://dev.mysql.com/doc/refman/8.4/en/information-schema-tables-table.html),
  [physical tablespace metadata](https://dev.mysql.com/doc/refman/8.4/en/information-schema-innodb-tablespaces-table.html)
  and [OPTIMIZE behavior](https://dev.mysql.com/doc/refman/8.4/en/optimize-table.html).
