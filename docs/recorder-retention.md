# Recorder retention policy

The September 2026 audit found about 3.49 million state IDs added per day and
1.12 GiB/day of observed OCI storage growth over the preceding week. Three
bounded samples of 100,000 state rows showed that frequent changing telemetry,
rather than repeated identical values or large attributes, dominates recording.

## Recorded measurements

Global history retention remains **28 days**. Exact `include.entities` entries
restore 12 JBD extrema and voltage-fault entities previously caught by the
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

## Selective cell history

The `recorder_retention` package runs at **07:30 America/Los_Angeles**. It requires
the backup manager to report `idle`, then calls `recorder.purge_entities` with
exactly 32 reviewed JBD cell IDs and `keep_days: 7`. The unsuffixed and `_2` IDs
belong to different devices and both remain recorded.

This deletes old raw state detail and unused attributes while retaining generated
statistics. Global 28-day retention still governs short-term statistics; hourly
statistics remain subject to Home Assistant's normal long-term policy. Daily
execution normally leaves between seven and eight days of raw detail. Busy or
unavailable backup status skips that day's run, extending the retained window.

There is no startup trigger. The service queues cleanup and returns before it
finishes; `mode: single` prevents simultaneous automation actions, not multiple
backend purge requests. Avoid manually triggering repeated cleanup while a prior
request is pending. Completion requires indexed checks that all 32 entities have
no raw rows before the fixed requested cutoff. A successful service response or
completed trace alone is insufficient.

## Expected effect and limits

The exact exclusions account for **3.5–15.4% of state rows** in the three samples.
Restoring battery summaries adds an unmeasured amount of recording, so these are
gross reductions, not guaranteed net daily savings. The seven-day cell policy
reduces retained history without reducing incoming writes. A constant-row-cost
model for all changes gives **15.7–30.1% less table allocation at steady state**;
it is not a forecast of immediate filesystem space reclaimed.

No indexes are removed and no `OPTIMIZE TABLE`/repack is requested. Do not confuse
OCI disk usage with table allocation. MySQL can reuse freed pages without an
immediate reduction in its allocated files.

`auto_repack: false` also prevents the default periodic table rebuild. Automatic
purging remains enabled. Any future rebuild needs a separate capacity and
maintenance-window assessment; it is not a remedy for a high incoming write rate.

The October 2 follow-up found that the database still had less than 28 days of
raw history. A second physical JBD monitor started recording on September 24,
and a later MQTT outage temporarily reduced incoming data. Compare equivalent
hardware and availability periods before attributing storage changes to this
policy. The first global expiration is not necessarily a storage plateau, and
selective deletion can free reusable pages without shrinking files.

## Deployment and verification

Use the current live files as the deployment baseline and retain a private backup.
Stage both changed YAML files against the installed HA version, validate the full
configuration, and reject live-file drift before promotion. Recorder filters
require a Home Assistant restart. The first authorized backlog purge is an explicit
separate action after checking Recorder freshness, backup idleness, and current
cell statistics; restarts do not trigger it.

Before and after deployment, verify Energy configuration and existing automation
identities, continued canonical and cell statistics, restored battery history,
and absence of new rows for the 23 exclusions after their respective activations. Check the fixed
seven-day cutoff for all 32 cells after cleanup. Measure net recording and OCI
growth over a full operating cycle, rather than extrapolating one short sample.

Use the [Recorder quality verification runbook](recorder-quality-verification.md)
for explicit expected coverage, real Energy IDs, finite numeric values, recent
completed statistic buckets and bounded indexed queries. Advancement since an
old snapshot is reported separately from present health.

The focused regression suite exercises the actual HA filter and purge schema in
the pinned HA 2026.9.1 runtime, including protected historical inputs, exact purge
scope, the mandatory nonzero retention period, and the fail-closed backup gate.

If cell history stops while the global Recorder remains fresh, follow the
[JBD MQTT availability runbook](jbd-mqtt-availability.md) before changing filters
or retention. A retained `offline` status can hide actively publishing cells.

## Rollback

Restore only the files changed by the release being rolled back, validate and
restart Home Assistant. Keep the existing cell-retention package when rolling
back a later filter-only change. Do not restore an old whole-configuration bundle over
unrelated changes. Rollback resumes future recording; it cannot recreate history
that was excluded or purged. Keep the private deployment backup and database
backup until the release has been accepted.

References: [Recorder](https://www.home-assistant.io/integrations/recorder/),
[selective purge](https://www.home-assistant.io/actions/recorder.purge_entities/),
[statistics](https://data.home-assistant.io/docs/statistics/).
