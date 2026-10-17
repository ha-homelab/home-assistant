# Operations and migration notes

## Deployment contract

The public `home-assistant` repository tracks this component under
`dependencies/scripts` and assembles its `config/` directory into the existing
`/config/scripts` path. The release receipt identifies the root commit and each
component's Git tree hash; there is no separate submodule commit to update. See
[public source and private runtime](../../../docs/public-source.md#one-source-tree).
Deploy the full tree as one reviewed unit. Preserve separate UI-managed scripts
and package scripts.

Before deployment:

1. Validate this repository and inspect the commit difference.
2. Compare the running configuration with the backup used for the migration, so a newer local edit is not overwritten.
3. Back up the live scripts folder and retain the previous root commit and release receipt.
4. Assemble the parent configuration and run Home Assistant's complete configuration check with its real integrations and secret references.
5. Inspect running scripts before reloading; a reload can interrupt active sequences and delays. A stopped reset or power sequence can leave devices in an intermediate state.
6. Reload scripts only when the runtime check and deployment plan permit it. Verify all 50 active folder-script IDs from the registry remain present, the four reviewed retirements remain absent, and inspect logs.

Do not run all scripts as a smoke test: some shut down hosts, change television settings, reset a bulb, or switch household circuits. Validate a requested device action with its owner and a specific expected outcome.

Rollback restores the prior assembled release from its recorded root commit,
repeats the configuration check, and reloads at a safe point. The registry makes identifier comparison explicit.

## Reviewed behavior and remaining boundaries

The original source snapshot is retained in the contracts for comparison. The
following notes distinguish changes already completed from behavior deliberately
retained; they do not claim every physical device was exercised.

- `backdoormotion`, `frontmotion`, and `garagemotion` send desktop notifications before their time conditions. Moving those conditions to the top would suppress notifications that currently run at all hours.
- Optional notifications now go through the root `script.notify_optional` router, which checks provider availability and isolates delivery failures. Chrome uses `html5.send_message`; the old iPhone and Pushbullet targets are retired. The current root router owns the browser/phone suppression policy, so a historical notification action in a folder script does not imply that every destination receives it.
- `notify_mqtt` now serializes its payload with `to_json`, preserving quotes and line breaks. Both MQTT notification scripts use bounded queues and retain their existing topics and retained-message flags.
- `play_kodi_channel`, `your_kodi_script`, `resetcreebulb`, and `flash` are reviewed retirements. They must not be restored to satisfy the original 54-script inventory.
- `tv_pic` builds its snapshot URL from `input_text.base_url`, populated by the
  installation's private `home_assistant_external_url` setting. Verify that
  origin and the image endpoint before deploying an origin change; see
  [deployment values](../../../docs/public-source.md#deployment-values). `tv_pic2` uses the registered LG notifier and the local image path. The root router applies the owner's Front-camera browser/phone suppression.
- Camera-motion scripts stop when the shared capture helper cannot obtain and validate a fresh image. Keep this failure boundary: continuing blindly would present a previous snapshot as the current event. The helper preserves the previous image/history on a failed capture.
- `kk` intentionally preserves the crossed `pla`/`sta` selector mapping. Inspect the shell command implementation before renaming or swapping its data.
- `tv_random_channel2` keeps its original exclusive range limits: the first digit is always `1`, the second is `0..3`, and the last two are `0..8`.
- `turn_off_living_room` affects several rooms and invokes a host shutdown. Its lighting and switch phases isolate runtime service failures so later phases can still run; it remains unsuitable for a general smoke test.

## Metadata and naming decisions

Display names identify the actual destination and result. Historical object keys remain stable to preserve dashboards, automations, templates, and external callers. Examples include the old `playplexplaylist` key now described as Amazon Music album playback, and `cast_porch_to_chromecast` now described as the garage-camera stream.

UI fields document only variables already referenced by actions: `message`, `energy_saving`, and `channelid`. Their selectors do not provide new runtime defaults or add validation behavior. The TV value remains free text because supported values depend on firmware.

The initial metadata migration wrote implicit single-run modes explicitly as
`mode: single`. Subsequent execution changes are recorded separately in
`contracts/reviewed-runtime.json`; the immutable source contract remains intact.

## Garage light rename (2026-10-07)

Household shutdown now explicitly includes `light.garage_bulb_one` through
`light.garage_bulb_five`. The first four replace the migrated `light.bedroom_*`
IDs; the fifth adds the formerly omitted, already-local ZHA bulb. All unrelated
targets and the later switch/host shutdown actions remain unchanged. Deploy
with the matching parent group, entity registry rename, dashboard references,
and automation dependency. See the [garage lighting runbook](https://github.com/ha-homelab/home-assistant/blob/main/docs/garage-lighting.md)
for the mapping, verification and rollback.
