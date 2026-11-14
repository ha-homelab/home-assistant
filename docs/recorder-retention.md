# Recorder retention policy

The September 2026 audit found about 3.49 million state IDs added per day and
1.12 GiB/day of observed OCI storage growth over the preceding week. Three
bounded samples of 100,000 state rows showed that frequent changing telemetry,
rather than repeated identical values or large attributes, dominates recording.

## Recorded measurements

Global raw history and short-term statistics retention is **one day**.
Hourly long-term statistics remain preserved. See the [5 GB operating
budget](recorder-storage-budget.md) for monitoring, extra purge requests and
physical reclamation. The budget is not a hard quota. Exact `include.entities`
entries restore 12 JBD extrema and voltage-fault entities previously caught by the
existing `sensor.*_voltage` exclusion. Other exclusion domains and globs remain
unchanged. Exact includes preserve the default recording behavior for unrelated
entities; do not convert them to include domains or globs.

Thirteen reviewed Emporia Vue AC Load L1 aliases are excluded. Their canonical
`*_power` entities retain raw history and statistics. The Emporia producer writes
the same value to `/Ac/Power` and `/Ac/L1/Power`; all 13,647 matched observations
in the audit agreed. This does not justify excluding real phase measurements
from other devices. Consumers of the alias's historical ID must use the canonical
ID instead.

Eight heater diagnostics (current, power factor, apparent and reactive power)
are also excluded. Their live values remain available, but their future raw
history and native statistics stop. Heater power, energy counters, Energy
sources, battery protections, and historical automation inputs remain recorded.

Two Tasmota solar aliases, `sensor.solar_tasmota_tasmota_120_power_l1` and
`sensor.solar_tasmota_tasmota_121_power_l1`, are also excluded. The installed
producer publishes the identical value to `Power` and `Ac/L1/Power` for these
devices. Their canonical `*_power_total` entities feed `solar_total_power` and
retain history and statistics. This makes 23 exact optimization exclusions;
older unrelated exclusions are unchanged.

## Live RuView algorithm diagnostics

Two additional globs exclude the raw server-module catalog and the floorplan's
derived diagnostic text from future Recorder writes:

```yaml
sensor.ruview_node*_server_modules
sensor.home_floorplan_ruview_node*_modules
```

The producer publishes bounded algorithm status and experimental outputs, which
can change about once a second when module diagnostics are enabled. The floorplan projects a complete status catalog
and a few current events into receiver details. These live diagnostics remain
visible through HA and the plan; they are not qualified room presence, person
counts or coordinates. `entity_category: diagnostic` alone does not prevent
Recorder writes, so both raw and derived entities need explicit exclusions.

Presence, motion, fall, classification and room-activity history keep their
existing policy. The new filters do not delete historical rows, change the
database connection, alter retention, or trigger a purge. The regression boundary
cases cover both current and future receiver numbers against HA's actual filter
when run inside its pinned runtime.

On 2026-10-05, read-only verification of the proposed filters using the installed
HA filter passed all 160 boundary cases. Live include entries and unrelated
exclusions matched the repository baseline. This check neither applied the
configuration nor restarted HA; activation still requires the rollout below.

Roll out the producer with `publish_server_modules=false`. Apply these additive
filters and the reviewed floorplan backend together, check the full installed HA
configuration and live-file drift, then coordinate one HA restart. Recorder has
no filter reload service; global `disable`/`enable` is not a substitute. Verify
the effective filters before enabling MQTT module publication. Keep ordinary
presence/fall publication active throughout. For rollback, disable only module
publication first, then restore the changed files from their private backups,
validate and restart; unrelated history must remain intact.

## Raw history and storage budget

The former daily seven-day JBD cell purge is retired because one-day global
retention now supersedes it. Both physical monitors, including the `_2` IDs,
remain recorded. The entity filters and canonical Energy sources are unchanged.

The November audit measured approximately 43.71 GB of data/index allocation,
including 32.18 GB of states, 9.01 GB of state attributes and 145.5 MB of hourly
long-term statistics. A bounded recent sample contained about 40 state rows per
second. These measurements explain why 28 days cannot fit a 5 GB operating
budget; they do not predict the exact post-purge physical file size.

The dishwasher's current-day runtime input remains recorded. Calculations and
raw history charts have only the retained window available; a 25-hour daylight
saving transition day can exceed the rolling 24-hour cutoff.
Energy charts backed by hourly statistics retain their long-term data.

Native `auto_purge: true` supplies daily cleanup. This policy does not deploy
an external controller. Any future hourly or size-triggered controller must
persist and verify each fixed cutoff before sending another request.
`recorder.purge` returns after enqueueing work, not after finishing deletion.

`auto_repack: false` keeps automatic table rebuilding disabled. Deletion makes
pages reusable; it does not guarantee that MySQL files shrink. Physical
reclamation is a separate capacity-checked maintenance operation. No indexes,
hourly statistics or unrelated database schemas are removed.

## Deployment and verification

Use the current live files as the deployment baseline and retain a private backup.
Stage the changed YAML files against the installed HA version, validate the full
configuration, and reject live-file drift before promotion. Recorder filters
require a Home Assistant restart. The first authorized backlog purge is an explicit
separate action after checking Recorder freshness, backup idleness, and current
cell statistics; configuration deployment alone does not trigger it.

Before and after deployment, verify Energy configuration and existing automation
identities, continued canonical and cell statistics, restored battery history,
and absence of new rows for the 23 exclusions after their respective activations. Check the fixed
one-day cutoff across raw state/event and short-term statistic tables after cleanup. Measure net recording and OCI
growth over a full operating cycle, rather than extrapolating one short sample.

Use the [Recorder quality verification runbook](recorder-quality-verification.md)
for explicit expected coverage, real Energy IDs, finite numeric values, recent
completed statistic buckets and bounded indexed queries. Advancement since an
old snapshot is reported separately from present health.

The focused regression suite preserves the filter boundaries for canonical
Energy, safety and live motion data, enforces nonzero one-day retention and
verifies that the superseded selective purge cannot enqueue extra tasks.
Run the optional HA filter checks inside the installed HA runtime.

If cell history stops while the global Recorder remains fresh, follow the
[JBD MQTT availability runbook](jbd-mqtt-availability.md) before changing filters
or retention. A retained `offline` status can hide actively publishing cells.

## Rollback

Restore only the files changed by the release being rolled back, validate and
restart Home Assistant. Do not reactivate the retired seven-day cell cleanup when rolling
back a later filter-only change. Do not restore an old whole-configuration bundle over
unrelated changes. Rollback resumes future recording; it cannot recreate history
that was excluded or purged. Keep the private deployment backup and database
backup until the release has been accepted.

References: [Recorder](https://www.home-assistant.io/integrations/recorder/),
[selective purge](https://www.home-assistant.io/actions/recorder.purge_entities/),
[statistics](https://data.home-assistant.io/docs/statistics/).
