# Deployment and rollback

## Installation bindings are required

The public configuration contains nonfunctional example device IDs. Before any
installation or source-pin update, follow [installation device bindings](site-device-bindings.md):
keep the two automation files and matching `mqtt.yaml` in the operator's reviewed
private override directory. A saved audit copy is not proof that the operator's
build command uses those files.

The build commands below use `/private/path/assembly/tools/build.py` to denote the
installation's separately maintained composition wrapper, which accepts explicit
`--overrides`, validates its committed public-source pin and records override
hashes in `release.json`. This is **not** this repository's standalone
`tools/build.py`: the standalone builder deliberately assembles public examples
and does not apply private overrides. Do not stage that uncustomized output on an
existing installation. Verify all three binding-file hashes in the assembled
receipt against the selected private files before staging or promotion; preserve
any other existing overrides as well.

## Before the first migration

1. Keep an off-box, private backup of the complete running `/config`, including `.storage`, secrets and installed integration code. The selective task snapshot is useful for comparison but does not replace a full disaster-recovery backup.
2. Confirm the target pod is healthy on h7 and remains on Home Assistant 2026.9.1. Do not change the image, mounts, network, recorder or MQTT service during configuration migration.
3. Run the root and child validators. Compare both libraries with the private original snapshot using their baseline options. Check source hashes against fresh live YAML so another editor's changes are not overwritten.
4. Export fresh HA states. The command `hass-cli info` in the installed 0.9.6 CLI calls a retired discovery endpoint; use `hass-cli -o json raw get /api/config` and `/api/states` instead.
5. Check that no automation or script action is running. A reload reattaches triggers and resets pending `for` timers; the state API cannot enumerate those pending timers. Use the minimum two controlled automation reloads for initial registration and monitor afterward.

## Build and stage the identity seed

Run the command blocks as Bash scripts with the shown fail-fast option. A failed check must stop the sequence before a reload.

```bash
set -euo pipefail
umask 077
hass-cli -o json raw get /api/states > /private/path/before-states.json
python dependencies/automations/tools/verify_runtime.py /private/path/before-states.json --phase before
python /private/path/assembly/tools/build.py /private/path/ha-seed --seed \
  --overrides /private/path/ha-overrides --secrets /private/path/secrets.yaml
python tools/stage.py /private/path/ha-seed /private/path/seed-receipt.json
```

The local secret file must include `recorder_db_url` with the exact existing recorder connection string, plus every other current secret. Preserve the current secrets; do not replace them with example placeholders.

Staging copies the bundle into a private directory on the existing `/config` volume, uses the installed custom integrations and runs the installed HA configuration checker. It neither starts another HA instance nor calls any device action. The receipt records source revisions, pod identity, exact staged file hashes and pre-installation live hashes. Validation logs and receipts are private.

## Promote and reload the seed

```bash
set -euo pipefail
umask 077
python tools/promote.py /private/path/seed-receipt.json --scope overlay
hass-cli -o json raw get /api/states > /private/path/before-script-reload.json && \
  python tools/verify_idle.py /private/path/before-script-reload.json && \
  hass-cli --timeout 60 service call script.reload || exit $?
hass-cli -o json raw get /api/states > /private/path/before-seed-reload.json && \
  python tools/verify_idle.py /private/path/before-seed-reload.json && \
  hass-cli --timeout 60 service call automation.reload || exit $?
hass-cli -o json raw get /api/states > /private/path/seeded-states.json
python tools/verify_release.py /private/path/seeded-states.json --phase seed --before /private/path/before-states.json
```

Promotion rejects a changed pod, modified staged files or live file drift. It keeps a private on-volume rollback copy, replaces only the two managed library directories, overlays explicitly managed root files and writes `configuration.yaml` last. It preserves `.storage`, custom integrations, databases, media and unrelated files. It checks the installed configuration before any reload and automatically restores the previous files if installation or validation fails.

The initial root configuration cleanup resolves to the same effective configuration, apart from extracting the recorder secret and removing an ignored recorder setting. It does not require a HA restart. A script reload also reloads the unchanged IGW package scripts.

## Apply final names

After verifying all 130 automation identities, build and **stage again**. The seed promotion intentionally invalidates any older live hashes.

```bash
set -euo pipefail
umask 077
python /private/path/assembly/tools/build.py /private/path/ha-final \
  --overrides /private/path/ha-overrides --secrets /private/path/secrets.yaml
python tools/stage.py /private/path/ha-final /private/path/final-receipt.json
python tools/promote.py /private/path/final-receipt.json --scope automations
hass-cli -o json raw get /api/states > /private/path/before-final-reload.json && \
  python tools/verify_idle.py /private/path/before-final-reload.json && \
  hass-cli --timeout 60 service call automation.reload || exit $?
hass-cli --timeout 60 service call frontend.reload_themes
hass-cli -o json raw get /api/states > /private/path/final-states.json
python tools/verify_release.py /private/path/final-states.json --phase final --before /private/path/before-states.json
```

The idle check returns `1` when an action is running and `2` for an invalid or unreadable export. Any nonzero exit must block reload. Let active actions finish or correct the export error, then take a fresh export before retrying. Never reuse an old idle result. The export, check and corresponding reload are also chained with `&&` and an explicit failure exit so the script stops before any later phase.

Verify the 54 folder scripts and six package scripts retain their entity IDs and states. Compare valid dashboard/cross-automation references, inspect new log errors and observe naturally occurring events without manually firing lighting, water, heat or energy actions. Check HA API availability, pod restarts and representative telemetry. Record exact commits and checks in a release receipt.

## Rollback

If promotion fails before reload, the tool restores the previous files automatically and leaves its private backup for diagnosis. If a runtime verification fails after IDs were registered, build and stage the **seed** again, promote its automation scope and reload once. The seed restores the original behavior and aliases while retaining the new identities.

Do not restore the original ID-less automation files against the newly populated entity registry: that can create suffixed entity IDs. Do not edit the live `.storage/core.entity_registry` file. A complete disaster-recovery restore must coordinate configuration and registry snapshots while HA is stopped.

Private backups are deliberately retained; do not prune them until the release has been accepted and an independent recovery copy exists.

## Later releases

Edit the bundled library in `dependencies/` through a root PR, review and commit that exact source pin in the installation assembly, then build with its reviewed private override directory, stage, promote and verify. IDs remain immutable. Use `--scope automations` for automation-only changes and `--scope overlay` when both libraries and root configuration are intentionally part of the reviewed release. Changes to non-reloadable integration settings require a separately planned HA restart; do not assume a domain reload applies every possible root change.

The [Victron MQTT keepalive runbook](victron-mqtt-keepalive.md) documents its
suppressed periodic keepalive, exact freshness reads, bundled source and guarded
single-file runtime update. A targeted repair has its own receipt and does not
claim that the complete root release recorded in Git is deployed.
