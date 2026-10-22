# Automatic HACS maintenance

[Deployment evidence](releases/2026-09-15-hacs-maintenance.md) records the enabled
installation, source revision, validation and the remaining live execution boundary.

The `hacs_maintenance` package updates installed HACS repositories daily at
**06:00 America/Los_Angeles**, using Home Assistant's configured timezone. Disable
the automation named **HACS maintenance: update repositories and restart once** to
pause future runs. The package does not update Home Assistant Core, container
images, Supervisor, or device firmware.

## Operation

1. Snapshot available (`on`) HACS update entities. Install ordinary repositories
   sequentially and `update.hacs_update` last. When there are no updates and no
   pending restart, do nothing, including no backup.
2. Reject a busy/unavailable backup manager, a running installer, or unavailable
   worker/latch entities before beginning.
3. Reuse a successful automatic backup completed within the preceding four hours.
   On Sundays this can use the 03:30 recorder/native backup and avoid another
   Oracle-to-Synology upload. Invalid, future or older timestamps require a new
   `backup.create_automatic` with the existing automatic backup configuration.
   The current installation uploads to Synology DSM, retains three copies, and
   does not retain local copies. This maintenance run uses the same retention
   policy; it does not change the existing backup schedule or destinations.
   HACS does not run a new MySQL export. A fallback native archive includes the
   latest completed export already staged in `/config/recorder_backup`; its
   manifest records the SQL export time independently of the archive time. See
   the [weekly backup schedule](../README.md#weekly-backups-and-maintenance) and
   the installation's recorder recovery instructions.
4. When creating a new backup, wait up to 60 minutes for the backup worker to finish, the manager to become
   idle, and `sensor.backup_last_successful_automatic_backup` to contain a fresh
   timestamp from this attempt. A service return alone is insufficient: remote
   upload failures can complete without raising a service exception.
5. For each repository, capture the latest version, start the installation worker,
   and wait up to 15 minutes. Require a valid update state, `in_progress: false`,
   an installed version matching the captured target, and the worker's per-attempt
   success acknowledgment. The acknowledgment is cleared before each install and
   set only after its post-install actions finish. Installation uses the
   ordinary latest-version action; if a different release appears during the
   call, verification stops the batch instead of pinning or downgrading a version.
6. The installation worker latches a restart request when an integration/HACS
   installation returns, including when it finishes after the coordinator's
   timeout. The coordinator must still verify every selected version before
   proceeding to restart. Also respect
   HACS's existing `Restart of Home Assistant required` release summary. Dashboard
   and theme updates alone do not request a restart.
7. After all selected updates succeed, wait up to 30 minutes for other automation
   and script actions, update operations, and backups to finish. Restart once if
   needed. Otherwise retain the restart request for the next daily run. The
   startup automation clears the restored latch after a real HA startup.

Failures create a persistent notification and stop the batch before remaining
updates or restart. A timeout **does not cancel** the underlying backup or
installer, to avoid interrupting file writes. A later run refuses to start while
either worker remains active. Results are visible in Home Assistant notifications
and the coordinator's five stored automation traces.

The idle check covers currently executing actions, not pending trigger timers or
future events. Like any Home Assistant restart, maintenance interrupts pending
in-memory timers. Unavailable HACS entities without a known available update are
not treated as update candidates. HACS discovers releases on its own polling
schedule; this package does not force an unsupported repository refresh.

## Slow uploads and unused repositories

The backup wait is **60 minutes**. A successful remote upload was observed taking
31 minutes 27 seconds: the former 30-minute limit stopped maintenance before any
installation, even though the backup finished shortly afterward. The worker must
still finish, the manager must be idle, and the success timestamp must belong to
the new attempt. A slow or failed upload never authorizes an unprotected update.
A timed-out worker is left running; the next daily run can retry safely.

For an update that stays available, inspect the coordinator trace and the
`hacs_maintenance_result` notification before changing HACS. An update prompt can
mean a backup timed out rather than an installer failed. The repository package
now matches the installation's existing daily 06:00 schedule.

Unused repositories should be uninstalled through HACS after checking integration
entries and dashboard references. The retired **iCloud3 Apple Device Tracker**
(`gcobb321/icloud3`) and **Sankey Chart Card** (`MindFreeze/ha-sankey-chart`) are not
runtime dependencies. **Energy Sankey Card** (`davet2001/energy-sankey`) is a
separate project and remains in use. Remove orphan Lovelace resources and the
retired integration's own leftover data, without deleting other integrations or
historical backup archives.

## Deployment and verification

Build and stage a clean committed root checkout as described in `deployment.md`.
Promote with `--scope overlay`, then reload `input_boolean`, `script`, and
`automation`, taking a fresh state export and passing `tools/verify_idle.py`
immediately before each reload. Installing this package does not require a HA
restart or a real HACS update. Existing library identities and enabled states are
checked by `tools/verify_release.py`; the package adds two automations, two worker
scripts, and two status helpers.

The behavioral tests in `tests/test_hacs_maintenance.py` run the actual Home
Assistant script engine against isolated state and mocked services. Run them
with Python from the installed HA image; local CI skips that module when Home
Assistant is unavailable. A separate CI job runs all maintenance scenarios in
the deployed HA image, pinned by digest, with networking disabled and a read-only
source mount. They never contact the production HA API or devices.
The installed HA configuration checker must also accept the assembled bundle.

For rollback, turn off the coordinator first and let any active worker finish.
Preserve a pending restart request until installed integrations have been loaded
by a HA restart. Restore the previous managed package/configuration only after
the idle check passes; reload the affected domains and verify the previous
automation and script identities. Do not stop an active installer to roll back
the maintenance policy.

## Implementation references

- [HACS update entities](https://www.hacs.xyz/docs/use/entities/update/)
- [HACS restart requirements](https://www.hacs.xyz/docs/use/update/)
- [HA backup service implementation](https://github.com/home-assistant/core/blob/2026.9.1/homeassistant/components/backup/services.py)
- [HA backup completion and upload errors](https://github.com/home-assistant/core/blob/2026.9.1/homeassistant/components/backup/manager.py)

The restart-summary contract and backup success fence were checked against the
installed HACS and Home Assistant 2026.9.1 source. Revalidate these contracts when
upgrading the HA image or changing backup destinations.
