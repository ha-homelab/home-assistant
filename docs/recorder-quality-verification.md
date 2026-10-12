# Recorder quality verification

Use these tools to verify recording and retained statistics against an explicit
contract. A recent global Recorder row or statistics that advanced since an old
snapshot does not establish that every protected sensor is healthy.

## Policy and scope

The checked-in [base policy](recorder-quality-policy.json) fixes the expected
entities, raw-history requirements, reporting cadences and statistics types.
Runtime discovery may add configured Energy sources; it cannot remove an absent
base entity or weaken its expectations. Change that contract only through a
reviewed policy change, never to make a failed snapshot pass.

Current storage policy remains **28 days globally** and **seven days of raw
history for the exact 32 JBD cell entities**. No additional signal has a shorter
retention period. Both physical monitors, including the `_2` identities, remain
protected. The optimization exclusion cohort contains **23 exact entities**:
13 Emporia L1 aliases, eight heater diagnostics and two Tasmota solar L1 aliases.
This count excludes the older unrelated exclusions already in the configuration.
Canonical power, Energy counters and JBD safety measurements remain recorded.

`auto_repack: false` disables automatic table rebuilding; it does not disable
automatic purging. The separate daily cell cleanup retains its backup-idle gate.
These verification tools never invoke purge, repack or configuration changes.
See [Recorder retention](recorder-retention.md) for cleanup semantics.

## Private input and identity handling

Keep runtime exports, generated policies and database snapshots outside Git in a
private directory, with restrictive permissions such as `umask 077`. The inputs
can contain personal entity IDs, readings and runtime attributes. Do not include
tokens, connection strings or unredacted exports in PRs or logs.

Capture a coherent runtime JSON object using an existing authenticated HA client:

- `checked_at`: the actual timezone-aware capture time.
- `config`: the REST `/api/config` response, including `state`.
- `states`: the complete REST `/api/states` response, retaining `entity_id`,
  `state`, `attributes`, `last_changed` and `last_reported`.
- `energy`: the WebSocket `energy/get_prefs` result.

`prepare_recorder_quality.py` reads `stat_energy_from`, `stat_energy_to` and
`stat_consumption`, including device and water consumption. It ignores prices,
cost statistics and compensation fields. Each source must exist in the runtime
export with `state_class: total` or `total_increasing`. Missing sources,
conflicting base rules, duplicate runtime IDs and unsupported external statistic
IDs fail preparation; investigate them instead of dropping them.

Use the exact IDs returned by HA. For example, `sensor.water_main_total` below is
a synthetic placeholder, not an alias to resolve automatically. A display
pseudonym must never be passed to an API or SQL query. An anonymized inventory is
not suitable as the source of a production quality policy.

## Capture and evaluate

Run preparation from this repository with fresh private runtime evidence:

```sh
umask 077
python3 tools/prepare_recorder_quality.py \
  --runtime /private/audit/runtime.private.json \
  > /private/audit/policy.private.json
```

The default base is `docs/recorder-quality-policy.json`; `--base` can select a
reviewed version for a historical replay. Preserve that base version with the
evidence. The generated file contains exact live Energy identities.

Run collection inside the installed HA environment, where PyYAML, SQLAlchemy,
the database driver and the active `/config` are available. Make the collector,
its `verify_recorder.py` dependency and generated policy available in a private
audit directory; the example paths are placeholders:

```sh
python3 /private/audit/tools/collect_recorder_snapshot.py \
  --policy /private/audit/policy.private.json \
  --config-root /config \
  > /private/audit/snapshot.private.json
```

Credentials are resolved from active YAML and secrets inside the container.
The collector queries only explicitly selected IDs, with a maximum scope of 500.
Raw and aggregate lookups use indexed `LIMIT 1` queries and a per-session
three-second query timeout. EXPLAIN must select the expected bounded index
access; a full `index` or `ALL` scan is rejected. There is no full-table COUNT,
DDL or maintenance operation. Driver errors are reported by type without their
potentially sensitive text. Treat any query error as incomplete evidence.

Copy the private results back through the approved transport, then evaluate
locally without a database connection:

```sh
python3 tools/verify_recorder.py \
  --policy /private/audit/policy.private.json \
  --runtime /private/audit/runtime.private.json \
  --snapshot /private/audit/snapshot.private.json \
  --baseline /private/audit/before.private.json \
  > /private/audit/quality.private.json
```

`--baseline` is optional. It reports advancement separately and cannot turn stale
data into a pass. `--now` accepts a fixed evaluation time for historical replay;
do not use an old evaluation time to make a current health check pass. The
verifier exits 0 for a pass, 1 for quality failures and 2 for invalid input.

The verifier checks fresh runtime/database captures, running HA, global Recorder
freshness, required runtime values and per-entity reporting cadences. Numeric
values must be finite; `unknown`, `unavailable`, NaN and infinity do not pass.
Static states may legitimately retain an old raw row when their value has not
changed. A changed value that settled at least 120 seconds before both captures
must not still have a different raw value predating that change. Recent
transitions allow for Recorder commit and capture timing; this check does not
prove every intermediate change was recorded. A fresh `last_reported` proves HA received an update, not that the
physical source sampled a new value.

Required five-minute and hourly statistics must cover a recent completed bucket
within the policy's grace period, with aligned `start_ts` and valid `created_ts`.
Measurement rows require finite, consistent mean/min/max; cumulative counters
require finite state/sum. Recovery cutoffs can additionally require newly created
statistics. A valid bucket alone does not prove that every transient within it
was retained.

## Before/after boundaries

Capture a baseline before changing policy. Prepare the post-change policy with
the exact reviewed ID lists and fixed observed cutoffs:

```sh
python3 tools/prepare_recorder_quality.py \
  --runtime /private/audit/after-runtime.private.json \
  --exclusion-entities /private/audit/excluded-ids.private.json \
  --exclusion-cutoff '2026-10-02T14:30:00Z' \
  --retention-entities /private/audit/retained-cell-ids.private.json \
  --retention-cutoff '2026-09-25T14:30:00Z' \
  > /private/audit/after-policy.private.json
```

The dates illustrate syntax only. Exclusion cutoff means the time the deployed
filter was effective: there must be no rows at or after it. Retention cutoff
means the recorded purge request time minus seven days: there must be no rows
strictly before it. Retention IDs must also be protected raw-history entities.
For exclusions activated at different times, use the appropriate fixed cutoff
for each separately evaluated cohort. Never silently replace an original cutoff
with the current time.

Both the collector and generated policy normalize timezone-aware ISO timestamps
to numeric epochs before binding SQL parameters. MySQL must never compare a
numeric timestamp column with an ISO date string. The verifier requires snapshot
cutoffs to match policy cutoffs exactly and every scoped boundary query to have
completed. A boundary pass proves the queried condition; separately check the
automation trace, trigger time and backup gate to establish that the scheduled
cleanup ran. The purge service returns before backend cleanup completes.

## Known legacy dependency

`sensor.solar` is a pre-existing missing source of the unused YAML integral
`sensor.sensor_net_solar_production_integral` (`unique_id: total_solar_kwh`).
It is not the configured Energy solar path. Energy uses `sensor.pv1_kwh`, whose
confirmed source is `sensor.current_solar_production`. Report the legacy defect
separately; do not invent an identity mapping or repoint a cumulative counter
because names appear related. Its absence must not hide a missing actual Energy
source or justify weakening the checked-in quality contract.
