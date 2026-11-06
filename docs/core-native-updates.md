# Home Assistant Core in the native Updates screen

`core_update_bridge` exposes the external k3s Core updater as
`update.home_assistant_core`. The normal Home Assistant Updates screen provides
Install, release notes, installed/offered versions and in-progress status. The
existing Core Updates dashboard and mobile notification actions still work.

## User flow

1. An hourly workflow checks official **stable** Core releases and prepares one
   pull request with immutable runtime and backup image pins.
2. The updater verifies that proposal and announces an available update. An
   installed beta is never downgraded to an older stable version.
3. Review the release notes and PR link, then press **Install** in Home Assistant.
4. The independent updater checks maintenance is idle, makes a fresh backup,
   checks the target image against the configuration, requests the exact PR merge,
   verifies main, then deploys and checks Core health.
5. HA may disconnect during its restart. The external updater continues and
   publishes the outcome when HA returns. In-progress is intentionally
   indeterminate: backup/merge/restart cannot supply an honest shared percentage.

Discovery and PR creation do not install anything. A merge by itself does not
install anything either. The install approval is bound to one version, candidate
and reviewed proposal head. A stale dialog or changed PR needs a fresh review.
The server also rejects requests while repository maintenance is busy.

## Configuration

Copy `config/custom_components/core_update_bridge` to HA's `custom_components/`.
The existing package now includes:

```yaml
core_update_bridge:
  url: http://ha-core-updater.homeassistant.svc.cluster.local:8099
  authorization: !secret ha_core_updater_authorization
```

Use the existing authorization secret; do not commit its value. The configured
base URL must have no embedded credentials, path or query. Authenticated HTTP
requests never follow redirects. The integration also supports manual setup in
Devices & services. It creates one config entry for this updater.

The upstream worker and workflow are documented in
[k3s-self-healing](https://github.com/ha-homelab/k3s-self-healing/blob/main/docs/core-update-proposals.md).
Enable `proposal_workflow` only after that workflow is installed. When migrating
from MQTT discovery, set the worker's `native_update_entity` to true, retire the
old MQTT entity, then load the new integration with the same entity ID. Do not
leave two competing update entities. All status topics remain read-only.

The site uses configuration-only pre-upgrade backups, including HA settings,
keys and device registries. Oracle Recorder history is not part of that gate.
The generic worker defaults to full backups unless configured explicitly.

## Troubleshooting

- **No available update after installing a beta:** expected when the latest
  stable release is older. The next newer stable release will be offered.
- **A new release exists but no offer:** inspect the proposal workflow and PR;
  the worker requires a valid proposal before offering it.
- **Install unavailable or rejected:** refresh status, check maintenance and the
  candidate expiry. Do not replay captured approval payloads.
- **Timeout after pressing Install:** inspect Core Updates before trying again.
  Approval requests are not automatically retried.
- **PR merge or preflight failed:** Core remains unchanged until source merge is
  verified. Review the external worker's private logs. Backup compatibility
  profiles remain mandatory and may need review for a new release.
- **Recovery required:** determine whether a source merge or deployment occurred
  before using the existing recovery/reoffer procedure. Do not blindly downgrade
  a database that may already have been migrated.

The integration's runtime tests execute native `update.install` against a mocked
external updater. They verify explicit version forwarding, progress, duplicate
click rejection, stale candidates and no automatic install on startup.
