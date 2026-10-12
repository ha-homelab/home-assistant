# HACS maintenance deployment — September 15, 2026

The daily HACS maintenance coordinator is enabled in the existing Home Assistant
2026.9.1 installation on h7, at **05:00 America/Los_Angeles**. The policy and
recovery behavior are documented in [HACS maintenance](../hacs-maintenance.md).

## Deployed configuration

- Source revision: `6a6f22cc1c4e09a90425a0d6c1f616c91f09fd3a`.
- Package SHA-256: `03363f182b7d1e2ebff062441e5685bf96fb813339ae3f91ed0c927a0cb1d5ce`.
- Only the new `packages/hacs_maintenance.yaml` and `release.json` differ from
  the previous running managed configuration. Both pinned libraries are unchanged.
- Two new automations are enabled, two worker scripts are idle, and both status
  helpers are off. The coordinator entity is
  `automation.hacs_maintenance_update_repositories_and_restart_once`.
- The automatic backup destination/retention remain the existing Synology DSM
  configuration with three retained copies and no retained local copy.

## Evidence

- YAML/include/credential validation passed; both component contracts passed.
- All 38 ordinary repository tests passed. The 15 HA runtime tests were also run
  separately inside the installed HA 2026.9.1 Python environment, using isolated
  state and mocked services; all passed. They cover success, worker timeouts,
  failed uploads, failures after the version is written, delayed completion,
  numeric version strings, restart deferral and startup reset.
- The installed HA configuration checker accepted both the staged and promoted
  configurations. The staged report contained zero errors and zero warnings.
- Promotion checked for file/pod drift and kept rollback material at
  `/config/.ha-homelab-backup-0oh6la3u`.
- Activation reloaded `input_boolean`, `script`, and `automation`, each preceded
  by a fresh export and passing idle check. An initial busy notification action
  delayed activation; it was allowed to finish naturally.
- Runtime verification preserved all 130 library automation identities, modes
  and enabled states, all 60 pre-existing scripts, and existing helper states.
  The resulting inventory has 132 automations and 62 scripts.
- All managed live file hashes match the staged manifest. The running HA
  process identity is unchanged, and no maintenance errors appeared in the
  inspected post-deployment log window.
- A guarded live trigger with conditions enabled exercised the no-update path:
  neither worker ran, the backup success timestamp was unchanged, and no restart
  was requested. There were no available HACS updates at deployment time.

The deployment did not perform a real HACS update, create a fresh production
backup, or restart HA. The scheduled success path still depends on the live
repository downloads and Synology service at run time; the coordinator verifies
their outcomes before proceeding. Private state exports, checker logs, manifests,
and the isolated runtime-test receipt are retained in the local task evidence
directory, outside Git.
