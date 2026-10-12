# Runtime resilience deployment · 2026-09-22

Installed on the existing Home Assistant **2026.9.1** instance, pod
`home-assistant-0`, namespace `homeassistant`, Kubernetes context `k3s-heaven`.
The HA process was not restarted (container restart count remained zero).

## Reviewed sources

- Root executable revision: `2b57b29`.
- Automations: `2ffe44497b3f52b23982a91bbef123cfcc53bbd4`.
- Scripts: `717d71e68ab22c901c0659b02084f4610481570a`.
- The earlier shared lighting recovery blueprint remains installed and validated.

The audit covered 133 loaded automations and 68 scripts before adding the helper.
The selective deployment changed 55 automation files, 14 script files, one root
package and one Python script. Other live configuration files were preserved.
The already-live IGW Cast package was synchronized into source only.

## Validation evidence

- Automation contracts: all 130 stable identities and reviewed behavior hashes pass.
- Script contracts: all 54 stable object keys pass; 15 validator tests pass.
- Root tooling: 39 tests pass locally; HA-dependent scenarios run separately below.
- Installed HA runtime: 19 resilience, 16 lighting and 15 HACS-maintenance scenarios
  pass, without skips. Real hardware, notifications and update services are mocked.
- Clean, pinned configuration overlay builds successfully with 130 folder
  automations and 54 folder scripts; package definitions remain included.
- Staged and final installed HA configuration checks: **zero errors, zero warnings**.
- All **71** final deployed file hashes match reviewed source.
- Runtime verifier passes for 130 folder automations, three package automations,
  54 folder scripts and 15 package scripts. Existing entity IDs, friendly names,
  available entities and automation enabled states are preserved. The only new
  script is `script.notify_optional`.
- The `Energy` user display name is checked against registry platform, unique
  entity identity and original configured name, then preserved.

## Activation and correction

Fresh idle checks preceded reloads of Python scripts, scripts and automations.
The first script reload exposed a package-merge behavior: empty selector mappings
were discarded and HA disabled the new helper, despite `check_config` passing.
Some naturally occurring notification automations logged missing-helper errors
until the package fields were corrected. Explicit selector options now survive
merging; a new regression scenario loads the **complete package and script
integration** and verifies registration and delivery to a mocked service.

The failed initial registration also created an alias-derived entity ID for the
new helper. Only that new registry entry was normalized to `script.notify_optional`;
its unique/service key remained `notify_optional`. No pre-existing entity was renamed.
The corrected script reload, final configuration check and strict identity verifier
all passed. Natural motion events subsequently invoked the helper successfully.
A two-minute post-correction log sample contained no helper-registration,
helper-execution or template-rendering errors. Existing unrelated MQTT-number
range errors remain covered by the [prior diagnosis](../mqtt-number-diagnosis.md).

No live device action, notification message, bulb reset, update or HA restart was
invoked as a test. Script/automation reloads reset in-memory pending `for` timers;
the lighting recovery blueprint independently reconciles overdue lights.

## Recovery copies

- Staging directory: `/config/.runtime-resilience-stage-c0k1_zl8`.
- Original-file backup: `/config/.runtime-resilience-backup-_z93yb_u`.
- The backup contains the first deployment receipt and the pre-correction helper
  copy (`helper-before-selector-fix.yaml.disabled`) for diagnosis. The corrected
  helper hash differs from the first staged hash; use root revision `2b57b29` as
  the final source of truth.
- Private off-host snapshots and final hash receipt are retained outside Git.

For rollback, restore the 69 changed pre-existing library files from the backup
and remove only the two newly added helper files. Validate the resulting complete
configuration, wait for idle execution, then reload caller automations and scripts
and Python-script service registration. Retain or remove the unused new helper's
registry entry deliberately; it is not an original entity. The earlier lighting
recovery deployment is independent and should not be rolled back with this patch.

The [audit and operation notes](../runtime-resilience.md) document the remaining
52 static entity IDs and four optional notification providers needing known
replacement/retirement decisions. No uncertain device was reassigned.
