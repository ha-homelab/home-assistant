# Home Assistant scripts

The second KMC strip's former Audio output now serves **Living lamp**. Household
shutdown follows it through `switch.living_lamp`; the retired `switch.audio_l`
ID is absent from active scripts. The first KMC's former Fireplace and Stage LED
targets are removed because that strip now supplies water equipment and
Laundry. Neither their old IDs nor replacement power controls belong in the
household lighting shutdown. Other targets, error continuation and the final
iNew shutdown call remain unchanged. The former standalone Living lamp
plug is retained as Switch02 and is not substituted into this logical role.

Bath 2 is controlled through `light.bath_2`, backed by the hidden ESPHome
relay `switch.bath_2`. The household shutdown script includes the light in its
domain-neutral shutdown action. The retained Tuya
light `light.bath2_old` is excluded from routine shutdown targets; other lights,
media power targets, and the final host shutdown action are unchanged.

Reviewed, versioned YAML scripts for the `ha-homelab` Home Assistant installation. The initial migration preserves the 54 scripts loaded from `/config/scripts` on Home Assistant 2026.9.1.

There are now **50 active folder scripts**. The owner retired the two unsupported
Kodi channel scripts and the Cree power-cycle script on 2026-09-22. Their IDs
remain in the immutable import and registry, with explicit reasons in the
`retired_scripts` contract; they are absent from the deployable `config/` tree.

Every script has an English display name, a description, an icon, an explicit execution mode, and its original object key. Six scripts expose their existing parameters as documented UI fields. Templates, service payloads, action order, delays, targets, and execution behavior are checked against the immutable source baseline and explicitly reviewed runtime overrides.

## Layout

- `config/`: deployable YAML, grouped by purpose. Each file defines one script.
- `contracts/script-registry.json`: stable entity identifiers, file locations, and display metadata.
- `contracts/source-baseline.json`: credential-reviewed original source with deployment URLs replaced by example.invalid.
- `contracts/reviewed-runtime.json`: reviewed execution changes, with stable identifiers still enforced.
- [Script catalog](docs/catalog.md): purpose, parameters, source file, and review findings for every script.
- [Operations guide](docs/operations.md): validation, integration, deployment, and rollback boundaries.
- [Source audit](docs/source-audit.json): service availability at the source snapshot, without credentials.

Only `config/` is copied to `/config/scripts`. Keep repository tools, contracts, and documentation outside the Home Assistant include directory.

## Use with Home Assistant

The parent configuration repository owns deployment and includes the deployed folder:

```yaml
script manual: !include_dir_merge_named scripts
```

Keep any existing UI-managed `script: !include scripts.yaml` and package scripts alongside this include. The folder's 50 scripts are only part of the live script inventory. Avoid defining any of their object keys a second time in another source.

`script.backdoormotion`, `script.kk`, and all other existing identifiers remain unchanged. Friendly aliases describe actual behavior; they do not rename script calls. Do not add automation-style `id` or unsupported `unique_id` options to these script definitions. Home Assistant uses each script's mapping key as its identifier. See the official [script configuration](https://www.home-assistant.io/integrations/script/) and [directory includes](https://www.home-assistant.io/docs/configuration/splitting_configuration/) documentation.

## Runtime resilience

The parent configuration must deploy `packages/runtime_resilience.yaml` and
`python_scripts/notification_service_available.py` before these callers are reloaded.
Chrome uses `html5.send_message` with the registered `notify.chrome` entity,
including same-origin picture/click paths. The old iPhone and Pushbullet targets
are retired. The shared `script.notify_optional` checks the current provider registration on
**each call**, preserves the original payload, and allows subsequent actions after
missing providers or delivery failures. It selects no substitute recipients and
still exposes schema/template errors. MQTT notification scripts queue up to 100
calls; retained topics and payload fields are unchanged. The JSON message now
escapes quotes, slashes and newlines correctly.

Media-off continues to the next player after a runtime failure. Household-off
continues from lights to switches and host shutdown after an independent service
failure. The retained backdoor fade preserves command order and exact delays.
The front-porch script keeps its Chrome notification after removal of obsolete
cloud Tuya switch pulses. The volume preset and media-off script omit the retired
Al Mini, iMac and bedroom Google Home targets. The unsupported Kodi channel
selection chain and Cree reset sequence are retired instead of redirected to
devices that have since been repurposed.

The parent repository runs these sequences in isolated HA with mocked device and
notification services, including equivalence against the original sequences.

## Validate locally

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python tools/validate.py
.venv/bin/python -m unittest discover -s tests -v
```

CI runs the same checks with read-only repository permissions. It rejects duplicate YAML keys, duplicate script IDs across files, ignored `.yml` files, missing metadata, unsupported script options, identifier drift, executable changes, and common credential patterns. Tests verify the guards catch real migration mistakes.

This validator establishes repository and behavior-contract consistency. It does not run scripts or prove device, provider, custom integration, or complete Home Assistant configuration behavior. The parent configuration must pass Home Assistant's own check before deployment.

## Change policy

For a metadata cleanup, keep the executable baseline unchanged. A behavior change needs a focused review covering the actual caller, action target, expected before/after result, failure behavior, and rollback. Record approved execution changes in `contracts/reviewed-runtime.json`; preserve the original import baseline. Never regenerate either contract merely to make CI pass.

These scripts are bundled in the public Home Assistant source repository.
Deployment credentials belong in the installation's private `secrets.yaml` or
existing secret store and are referenced with `!secret`. Keep runtime exports and
private configuration outside Git; see [public source and private runtime](../../docs/public-source.md).

## Camera snapshot recovery

Camera callers now delegate to the root `script.capture_camera_alert` helper,
which validates a fresh JPEG before replacing the saved image and rotating
history. Deploy the matching root package/helper with these callers. Existing
notification guards, destinations and stable entity IDs are retained. See the
[root runbook](https://github.com/ha-homelab/home-assistant/blob/main/docs/camera-snapshot-recovery.md)
for bootstrap history, source migration, tests and rollback.

On 2026-09-25 the owner retired the arc/black lamps: `script.flash` is removed,
and the household shutdown list omits only the retired light targets.

## Dining Arc lamp role cleanup

The owner moved the ESPHome Studio wall-lamp controller to Dining Arc lamp and
retired its previous automation role. The household shutdown script removes
only `switch.studiowalllamp_studio_wall_lamp`; it does not assign that old
shutdown behavior to `switch.dining_arc_lamp`. All remaining lighting targets,
media power controls, error handling, and the iNew shutdown call are preserved.
