# Motion-light recovery deployment — September 22, 2026

Deployed to `home-assistant-0` in namespace `homeassistant`, context
`k3s-heaven`, running HA 2026.9.1. The pod restart count stayed at zero.

- Configuration source: `e48589994fb151097abde49f6aa8546ee07b07d7`.
- Automation source: `bbd6d9e8ed3b43a5e9aa56836b5a698fdf5dbf11`.
- Scope: one shared blueprint and 15 existing automation files; 14 rules now
  use the blueprint and the redundant counter recovery rule is disabled.
- Staging: `/config/.motion-light-stage-oo09kpsh`.
- Rollback copies: `/config/.motion-light-backup-j4cteh_1`.

The patch was staged against the current live configuration after comparing each
changed file with its expected Git baseline. Unrelated live files were preserved.
Both staged and installed HA checks reported zero errors and zero warnings.
After a fresh successful idle check, one `automation.reload` activated the
change. No script reload, HA restart, synthetic production sensor state or manual
device test was used.

Validation passed:

- 16 isolated HA runtime tests, including schema validation of all 14 instances.
- Root suite: 38 ordinary tooling tests passed; 31 HA-dependent tests skipped in
  the local Python runtime. The 16 lighting runtime tests ran separately in the
  installed HA image and passed.
- Child contract validation, identity-seed rendering, root YAML checks,
  reproducible bundle assembly and Gitleaks scans of both change sets.
- All 16 installed file hashes matched the committed source.
- The library runtime verifier passed for all 130 automation identities.
- Direct before/after comparison preserved all automation/script entity IDs,
  display names and execution modes. Only the intentionally retired counter rule
  changed enabled state. At 15:59 UTC, all 14 rules had fresh minute-trigger traces
  ending normally at their conditions, with no lighting-template errors.

The broader root verifier reached the package-script check and reported an
existing unrelated display-name discrepancy: `script.igw_google_status` is named
`Energy` in live HA. Its name was `Energy` both before and after this patch. The
script and its metadata were not changed, and the verifier was not weakened to
hide this discrepancy.

Offline physical lights were not disconnected or forced on for testing. Their
future successful device response depends on integration/device connectivity;
the installed blueprint continues reconciling while shutdown is due. Existing
missing entity references and restart semantics are documented in the
[runbook](../motion-light-recovery.md).

To roll back this patch, restore the 15 automation files from the backup, remove
the newly added `blueprints/automation/ha_homelab/motion_light_off.yaml`, validate
the configuration, require another fresh idle check and reload automations.
Re-enable the old counter recovery automation, whose pre-patch state was `on`.
Keep its existing ID; do not restore older ID-less automation definitions.
