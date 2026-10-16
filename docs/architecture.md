# Configuration ownership

## Runtime

Home Assistant Container 2026.9.1 runs as `homeassistant/home-assistant-0`, a StatefulSet on `h7` in the `k3s-heaven` context. Its existing persistent `/config`, `/share`, host networking, recorder database, MQTT connection and Zigbee radio remain in place.

This repository owns the human-maintained YAML configuration and its two bundled libraries. Separately maintained deployment configuration owns cluster manifests, companion services and recovery settings. Do not create a second HA Core or MQTT bridge when consuming this configuration.

## Boundaries

- Automation IDs are stable registry identities. Their English aliases are presentation metadata. Existing `automation.*` entity IDs are preserved by the two-stage migration.
- Script object keys are both their stable identities and the basis for `script.*` service calls. They remain unchanged, including historical short keys used by dashboards.
- Helper IDs, MQTT topics, device IDs, notification payloads, speech text, thresholds, delays and action ordering remain the same as the source installation.
- Cerbo/Venus supplies energy telemetry. HA consumes it and hosts household automations; changing descriptions must not silently alter energy control policy.
- The existing IGW voice package remains in the root repository because its scripts and REST command share a blueprint and transport contract.
- UI integration entries, entity/device registries, credentials, voice exposure and storage-mode dashboards remain runtime data. Back them up privately; do not commit `.storage`.
- HACS/custom integration source remains installed in `/config/custom_components`; staging links to the installed code for the real schema check. Review custom component updates separately.
- `home_floorplan: {}` enables the existing authenticated 3D floorplan panel. Its custom integration, static assets and floorplan data are provided by a separately deployed floorplan integration; this overlay preserves them and does not provision them. Keep the root declaration when rebuilding a release.
- Existing helper commands `/config/kodi` and `/config/comcast.py`, media and camera snapshot directories are external runtime dependencies. A configuration bundle does not provision or execute them.

## Known inherited behavior

The child repositories record exact inherited behavior and unresolved dependencies. Some notification services are absent in the source service inventory; some historical script names do not match the action they perform. Names and descriptions now explain those actions, while targets and payloads remain unchanged pending evidence for a replacement.

The storage dashboard `lovelace.zero_grid` contains a pre-existing reference to `automation.zero_grid___smart_battery_management`, which is not active in the source configuration. There is no verified one-to-one replacement, so the migration must not connect that control to a different energy automation. Existing valid dashboard automation and script references retain their entity IDs.

Three mapping-shaped automation files and two comment-only files were inactive under HA's merge-list loader. They are archived outside the active library rather than accidentally enabled. The source's duplicate guest-return rules and intentional no-op actions are documented by the automation repository.
