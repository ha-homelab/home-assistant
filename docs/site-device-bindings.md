# Installation device bindings

The all-zero portal ID and ZHA device ID in the example configuration are
synthetic placeholders. They do not identify a working installation. Binding
them is required before deployment; publishing these examples does not update
a running system.

Before upgrading an existing installation, preserve its reviewed files in
private storage outside Git. In an assembled Home Assistant configuration the
paths are:

- `automations/023_media_start_the_plex_hub_playlist_from_the_sailor_button.yaml`
- `automations/118_victron_keep_mqtt_telemetry_active.yaml`
- `mqtt.yaml` from the root configuration, with matching portal IDs in all topics

Keep the complete known-good files, compare their SHA-256 hashes, and select them
explicitly through the deployment composition wrapper's `--overrides` directory.
That wrapper replaces existing files and records their hashes in `release.json`.
The standalone public builder does not apply external overrides itself.
Review the assembled output before deployment; never copy synthetic IDs over
working bindings by assuming the example is ready to run.

Existing automation IDs, script references, trigger timing, queue behavior and
MQTT read-request behavior remain the same. Real device IDs and account-specific
configuration belong in installation inputs, not source fixtures. The example
change does not remove older Git history or update a deployment's source pin.
