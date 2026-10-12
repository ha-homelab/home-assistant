# Approving Home Assistant Core updates

Home Assistant runs as a container in k3s. The independent Core updater discovers
stable releases, publishes status to Home Assistant, and performs an update only
after an explicit approval. The HA package is
[`config/packages/core_updates.yaml`](../config/packages/core_updates.yaml).

This workflow is separate from the scheduled HACS maintenance package. It does
not update the SMLIGHT operating system, coordinator radio firmware, or Zigbee
end devices. ZHA updates as part of the chosen Home Assistant Core release.

## Everyday use

1. A new candidate produces a persistent HA notification and an actionable
   notification on the configured phone, currently Vitaly iPhone Air. The
   registered notify service retains its original identifier,
   `notify.mobile_app_als_iphone_89310`.
2. Review the exact version and release notes. **Install VERSION** approves that
   version and its candidate ID. Unlocking the phone is required for that action.
   The Core Updates dashboard provides the same explicit approval flow.
3. **Later**, swiping away the notification, and closing HA do not install
   anything. Later hides the notification; the candidate remains available on
   the update dashboard. It is not a timed snooze.
4. The independent updater performs its backup, preflight, deployment and health
   checks. HA may disconnect during its restart. The updater does not depend on
   HA remaining online to complete the operation.
5. HA reports the retained result when it reconnects. A success message means the
   worker's health checks passed; a failed or recovery-required message does not
   claim that installation completed.

The notifications use `script.notify_optional`, so an absent phone service does
not prevent the persistent notification or change the approval requirements.
The last notified candidate and result are restored `input_text` helpers. HA
restarts and ordinary MQTT attribute updates do not resend the same notification.
To deliberately resend the current offer, clear
`input_text.core_update_notified_candidate`, then reload the notification
automation or wait for the next update-entity state change.

## Status and approval contract

The read-only MQTT update entity is `update.home_assistant_core`. Its attributes
are `candidate_id` (32 lowercase hexadecimal characters), `target_version`,
`stage`, `last_error`, plus the normal update attributes `installed_version`,
`latest_version`, and `in_progress`.

Stages are `idle`, `available`, `preparing`, `backup`, `preflight`, `deploying`,
`verifying`, `succeeded`, `failed`, and `recovery_required`. Notifications are sent
for a new `available` candidate and terminal results. Progress updates do not
create repeated success or failure notifications.

MQTT conveys status only. There is no installation command topic: a client able
to publish MQTT messages must not thereby gain permission to deploy HA.
`script.core_update_approve` requires both the displayed `target_version` and
`candidate_id`. It sends this JSON through `rest_command.core_update_approve`:

```json
{
  "action": "install",
  "target_version": "2026.10.0",
  "candidate_id": "0123456789abcdef0123456789abcdef"
}
```

The destination is the cluster-only `/approve` endpoint on
`ha-core-updater.homeassistant.svc.cluster.local:8099`. The authorization header
comes from the local `ha_core_updater_authorization` secret. The external worker
independently authenticates the request, verifies the exact active candidate and
version, and accepts it at most once. An accepted request returns HTTP 202.

Phone action identifiers embed the captured candidate and version:
`HA_CORE:INSTALL:CANDIDATE:VERSION`. The event handler compares both with the
current offer, and the script checks again immediately before sending. An old
notification cannot approve a replacement candidate, even when it has the same
version. A second check in the worker closes the race between those local checks
and the HTTP request.

HTTP 403, 409, and 422 responses are reported as unaccepted requests. A timeout or
lost response is reported as **approval not confirmed**, because the worker may
already have accepted it. There is no automatic retry from HA. Check the current
stage first. Duplicate requests are also rejected by the worker.

## Dashboard integration

The bundled `custom:core-update-card` is a dependency-free browser component in
[`config/www/core-update-card.js`](../config/www/core-update-card.js). It displays
the installed and offered versions, progress stage, sanitized worker error and
release notes. Its Install button is disabled when the offer is unavailable,
inconsistent, or already running. It captures the displayed candidate and
version before opening a confirmation dialog; it never substitutes a new
candidate while that dialog is open.

Register `/local/core-update-card.js?v=1` as a **JavaScript module** Lovelace
resource. Create a storage dashboard with URL path `core-updates`, and initialize
its raw configuration from
[`config/dashboards/core-updates.yaml`](../config/dashboards/core-updates.yaml).
Its view URL is `/core-updates/overview`, used by the phone and persistent
notifications. The source files are included automatically by the tracked-file
configuration build. Deploying the YAML file alone does not register a dashboard
or resource; those storage registrations are a separate setup step. Increment
the resource query version after a card change if browser caches retain old code.

The shipped dashboard uses:

```yaml
type: custom:core-update-card
entity: update.home_assistant_core
title: Core updates
```

The standard update entity provides version and release information. Its native
Install action is intentionally unavailable because MQTT is not the approval
transport. An approval card must call `script.core_update_approve` with **the same
version and candidate shown in its confirmation prompt**.

Any replacement approval card must preserve the shipped card’s behavior: capture
both values before opening its confirmation dialog, retain that snapshot while
the dialog is open, and submit the captured pair only after the user confirms. If the candidate changes in the meantime, the
request is rejected; it must not silently substitute the newest candidate. The
card must not contain the updater secret or call the cluster endpoint directly;
it calls HA's authenticated script service.

For a manually maintained native card, literal captured fields work without any
custom integration. This example is deliberately not a dynamic “install latest”
button; replace both example values together with an actual candidate:

```yaml
type: button
name: Install Home Assistant 2026.10.0
icon: mdi:update
tap_action:
  action: perform-action
  perform_action: script.core_update_approve
  data:
    target_version: "2026.10.0"
    candidate_id: "0123456789abcdef0123456789abcdef"
  confirmation:
    text: >-
      Install Home Assistant 2026.10.0 after backup and configuration checks?
      Home Assistant will restart.
```

Home Assistant's native button card does not render Jinja in action data. Do not
put templates into these fields or implement an approval script that silently
reads whichever release is latest after the user confirms.

## Deployment requirements

- Deploy the worker and its durable state, credentials, RBAC and network policy
  before enabling approval in HA. The endpoint is not an internet webhook.
- Provision `ha_core_updater_authorization` in local `secrets.yaml` with the full
  `Bearer ...` value matching the worker. Commit only the example placeholder.
- Load the HA package, its `input_text` helpers and existing
  `script.notify_optional`. Reload the appropriate YAML integrations or perform
  a normal configuration rollout after validation.
- Keep `homeassistant.components.rest_command` logging at `warning` or higher.
  The existing `igw_google_voice` package owns this setting; declaring it twice
  causes a package merge warning. DEBUG logs can expose authorization headers.
- Treat the endpoint's durable response and subsequent worker status as the
  authority. A successful HA script call alone is not proof of an installed
  release, completed backup, or healthy ZHA connection.

## Coordination with scheduled HACS maintenance

The Sunday HACS job and Core update worker must not modify the installation at
the same time. HACS checks Core status before its backup, every installation,
and its final restart; its individual backup/install workers also check again.
Any Core progress, active stage, `recovery_required`, unknown stage or unavailable
status defers HACS. It leaves an already running installer to finish and retains
its pending restart request.

A missing Core entity is allowed only on installations without the Core package
marker (`input_text.core_update_notified_candidate`). When that helper exists,
missing Core discovery/status fails closed. This preserves standalone HACS use
while preventing a disconnected updater from being mistaken for an idle one.

Conversely, the Core approval script rejects requests while the HACS coordinator
or either HACS worker is running/unavailable. It identifies the coordinator by
its stable automation ID, so renaming the entity does not bypass this guard.
The external Core worker also validates HACS inactivity after acquiring its own
operation lock; the YAML checks alone are not a distributed atomic lock. These
guards do not intercept manual `update.install` calls outside the maintenance
package.

## Troubleshooting

**No phone notification:** check the registered notify service and the
`script.notify_optional` trace/logs. The persistent HA notification and dashboard
remain available. A restored notified-candidate helper intentionally prevents
repeated delivery of the same offer.

**An old Install button does nothing:** it no longer matches the current
candidate, the worker is busy, or the entity is unavailable. Review the current
offer. Stale rejection is intentional; neither HA nor the worker upgrades the
request to a newer version.

**HTTP 403:** verify the locally provisioned authorization value and worker
secret. Do not print either in traces, commands or issue reports.

**HTTP 409:** the offer changed or an operation is already in progress. Read the
current stage before submitting another request.

**Approval not confirmed:** the request timed out or its response was unusable.
The worker may already be running. Wait for state updates or inspect the worker;
do not assume it is safe to launch a second deployment manually.

**HA is offline during deployment:** use the worker's k3s logs and durable status.
Do not rely on an HA automation to recover HA itself. Follow the worker runbook
for restoring the saved configuration/database and matching old image when its
health checks fail. Do not downgrade a possibly migrated database by only
changing an image tag.

**Recovery required:** stop submitting new requests and follow the worker's
recovery instructions. This state is distinct from a preflight failure where
no production deployment started.

## Validation

`tests/core_update_card.cjs` executes the actual browser component against a
small DOM boundary and fake HA transport. Its ten scenarios cover initial
unavailability, exact service arguments, changed candidates during confirmation,
old rendered callbacks, cancellation, duplicate clicks, invalid/busy states,
text-only rendering of untrusted strings, ambiguous transport failure and safe
release links. Run it with
`node tests/core_update_card.cjs config/www/core-update-card.js`.
The CI workflow runs this check directly, so a missing Node runtime cannot turn
it into a skipped passing check. `tests/test_core_update_card.py` also includes it
in normal Python test discovery. This is behavioral coverage, not a screenshot
or physical phone acceptance test.

`tests/test_core_updates.py` executes the shipped action sequences in an isolated
Home Assistant runtime with HTTP, notification, helper and script service
boundaries stubbed. It covers exact-version approval, stale same-version
candidates, candidate replacement between handler and script, Later/dismiss
behavior, malformed events, busy/unavailable states, unaccepted HTTP responses,
lost responses, restored notification deduplication and terminal results. It
never starts an update or contacts production devices.

Run with the deployed HA image, read-only source and no network, as done for other
runtime tests in this repository:

```sh
python -m unittest discover -s tests -p test_core_updates.py -v
```

Set `REQUIRE_HA_RUNTIME=1` in CI so a missing HA dependency cannot silently skip
runtime coverage. Ordinary local Python runs only the static boundary checks
when HA is absent. Live acceptance also requires checking the delivered phone
notification and dashboard, then observing a deliberately approved update and
its backup and health-check evidence. Unit tests do not establish those physical
or deployment outcomes.

References: [actionable phone notifications](https://companion.home-assistant.io/docs/notifications/actionable-notifications/),
[REST command responses](https://www.home-assistant.io/integrations/rest_command/),
and [MQTT update entities](https://www.home-assistant.io/integrations/update.mqtt/).
