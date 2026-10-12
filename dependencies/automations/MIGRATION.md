# Preserve identities during the first deployment

## Why the migration has two stages

On Home Assistant 2026.9.1, an automation's YAML `id` becomes its registry `unique_id`. A previously unregistered automation obtains its initial entity ID from its alias. Once registered, the same unique ID resolves to the stored entity ID even if the alias changes.

The live source confirms that automation reload removes changed entities before adding their replacements. The initial source configuration contains 130 active automations and only four registered identities. All 130 original aliases match exactly one live entity in the captured baseline.

The source paths used to verify this behavior are `homeassistant/components/automation/__init__.py` (`_async_process_config`, `_create_automation_entities`) and `homeassistant/helpers/entity_platform.py` (registry creation and assignment).

## Preparation

1. Preserve a private off-box snapshot of the current automation directory, relevant root YAML, entity registry, dashboards, and an API state export. Keep credentials and registries out of git.
2. Compare the fresh live files with the source hashes recorded during preparation. Stop if another editor changed them.
3. Read a fresh state export and ensure no automation action is running:

   ```bash
   umask 077
   hass-cli -o json raw get /api/states > before-states.json
   python tools/verify_runtime.py before-states.json --phase before
   ```

4. Render both the seed and final assembled Home Assistant configuration in staging and run the Home Assistant 2026.9.1 configuration checker against each. Offline checks do not replace the installed Home Assistant validator:

   ```bash
   python tools/render_seed.py /private/staging/automation-seed
   python tools/validate.py --baseline /private/snapshot/config
   ```

The seed is generated from the final files and the migration record. Independent baseline validation proves it differs from the source **only by adding the 126 missing IDs**; existing identities, aliases, descriptions, and implicit defaults remain as before.

## Stage 1: Register stable identities

Install the seed directory as `/config/automations` using the root deployment workflow. Validate the complete configuration and call `automation.reload` once. Do not trigger any automation as part of validation.

Export fresh states and verify the exact original entity IDs, aliases, states, and new identities:

```bash
hass-cli -o json raw get /api/states > seeded-states.json
python tools/verify_runtime.py seeded-states.json --phase seed --before before-states.json
```

Do not proceed if an entity is missing, unavailable, suffixed, or has an unexpected ID or enabled state. Preserve the new registry entries in the next private rollback snapshot.

## Stage 2: Apply readable metadata

Install the final `config/` directory, validate the complete configuration, and reload automations once more. Existing registry entries preserve the old entity IDs while the English aliases become their display names.

```bash
hass-cli -o json raw get /api/states > final-states.json
python tools/verify_runtime.py final-states.json --phase final --before before-states.json
```

Recheck errors, entity availability, representative natural events, and downstream telemetry. The migration preserves entity IDs, so existing dashboard and cross-automation references require no string replacement. The migration map is the authoritative list for verifying that claim.

## Reload behavior and rollback

Reloading changed automations reattaches triggers and can reset pending `for` timers. The validator checks for currently running actions before migration; it cannot report all pending trigger timers. Use two controlled reloads, preserve action ordering, and observe the water, energy, and heating rules afterward.

The family-away automation explicitly has `initial_state: off`; retain that setting. The other source `initial_state` values and all execution modes are also preserved.

After stage 1 succeeds, the seed configuration is the preferred rollback target: it restores the original behavior and aliases while retaining the new registry identities. Restoring the original ID-less files against a registry containing the new IDs can create suffixed entity IDs. Keep both configuration and registry recovery material private, and do not edit a live `.storage/core.entity_registry` file.

## Later deployments

Once all expected identities exist, deploy the final files directly through the root repository. Keep IDs immutable. Validate the full assembled configuration before reloading, and compare states afterward.
