# Porch lamp migration — 2026-11-22

The Philips Hue lamp that had been the **Backdoor Porch Light** left the
installation when its SmartThings cloud entry was removed. The owner replaced it
with the spare front-porch CREE **Connected A-19 60 W Equivalent**
(`e2:0d:b9:ff:fe:09:fa:a7`, ZHA, 5000 K white) that was previously paired as
`light.porch_one` and had no fixture. This record covers the runtime registry
changes and what is still open in source.

## Why this is a registry change, not a YAML change

`light.porch_one` was a ZHA entity, and the Hue lamp was a SmartThings entity.
Neither entity definition lives in this repository: they exist in
`.storage/core.entity_registry` and are created by integrations. Nothing in
`dependencies/` could rename, re-point or delete them, so the live installation
was changed first through supported Home Assistant APIs and this document
records that state. See
[automation authoring and GitHub workflow](automation-authoring-workflow.md) for
where the boundary sits.

## Applied runtime changes

1. **Entity rename.** `config/entity_registry/update` renamed the ZHA light entry
   `001d1358d625f5a186dcf12130345b1d` from `light.porch_one` to
   `light.backdoor_porch`, the identity the retired Hue lamp used.
2. **Friendly name.** ZHA composes display names as "device name + entity name",
   so a bare entity rename produced `Porch One Backdoor Porch Light`. The device
   `760af3c577269cac2807c97987611387` was renamed to `Backdoor Porch Light` and
   the entity's own name was cleared. The entity's own area had to move to the
   device to satisfy the same registry rule; the device now carries the **Porch**
   area that the entity previously held. Result: `light.backdoor_porch`,
   `friendly_name: Backdoor Porch Light`.
3. **Porch Light helper.** The helper config entry `01M5KDM0VX6RXZYRN83HX36VMJ`
   still listed `light.porch_one`, which no longer existed, and the group stayed
   `unavailable` on that dangling member. Its options were updated through the
   supported options flow (`POST /api/config/config_entries/options/flow`, then
   the same endpoint with the flow ID, `{"entities": ["light.porch_two"],
   "all": false, "hide_members": false}`). Stored options now contain only
   `light.porch_two`, so the change survives a restart; a `group.set` service call
   would only have changed the in-memory group and reverted on restart.
4. **Voice aliases.** The renamed entity carried the Matter/Assist aliases
   `Porch One` and `Porch Light One`. They were removed with
   `config/entity_registry/update` (`"aliases": []`) because the bulb is no longer
   a front-porch light and the aliases would otherwise keep steering voice
   requests to the backdoor lamp.

## Repository updates in this change

- `docs/matter-household-exposure.json`: the porch group lists only
  `light.porch_two`, and the `light.porch_one` endpoint is removed. The manifest
  keeps 45 controls, still includes `light.backdoor_porch`, and its names remain
  unique. Removing the endpoint is required, not cosmetic: the publisher rejects a
  manifest entity that is absent from the bridge preview.
- `docs/matter-voice-exposure.md`: the canonical porch list now describes the
  current entities, and the 2026-10-22 counts stay as history.
- `docs/automation-authoring-workflow.md`: the live-first authoring runbook this
  migration follows.

## Evidence

- `light.porch_one` returned `404` after the rename; `light.backdoor_porch`
  reports `state: off`, `supported_color_modes: ["brightness"]`.
- `.storage/core.config_entries` for the helper reads
  `{"entities": ["light.porch_two"], "all": false, "hide_members": false,
  "group_type": "light", "name": "Porch Light"}`.
- `.storage/core.entity_registry` for `light.backdoor_porch` reads `name: null`,
  `aliases: []`, `device_id: 760af3c577269cac2807c97987611387`.
- `homeassistant.reload_config_entry` on `light.porch_light` returned `200`; the
  group is `unavailable` because its only remaining member `light.porch_two` is an
  empty fixture, not because of a stale reference.
- Not checked: the bulb was not switched on, so brightness and the 5000 K
  appearance are the owner's observation rather than a measured result. Alexa,
  Google Home and the Matter bridge were not re-tested.

## Still open in source

These files still reference the retired `light.porch_one` and therefore act on a
missing entity until the owner decides what the porch should do:

- `dependencies/automations/config/074_lighting_turn_off_scheduled_lights_in_the_morning.yaml`
- `dependencies/automations/config/075_lighting_turn_off_scheduled_lights_except_the_living_room.yaml`
- `dependencies/automations/config/080_porch_turn_on_the_light_from_a_notification.yaml`
- `dependencies/automations/config/082_porch_turn_off_lights_after_motion_clears.yaml`
- `dependencies/automations/config/083_porch_turn_on_lights_after_motion.yaml`
- `dependencies/scripts/config/lighting/household_lights_and_media_off.yaml`
- `dependencies/scripts/contracts/source-baseline.json`,
  `dependencies/scripts/contracts/reviewed-runtime.json` and
  `tools/kodi_ha_commands.json`, which record the same reference

The live `/config/automations/` and `/config/scripts/` copies match these files
(verified with `grep -rln light.porch_one /config/automations /config/scripts`),
so motion on the front porch currently turns on nothing. The front-porch fixtures
hold no bulbs: `light.porch_two` is an empty socket. Options are to retire the
porch rules with a `retired_automations` entry, or to point them at a fixture that
exists again; both are behaviour decisions that need an owner choice and a
separate PR. Do not silently redirect them to `light.backdoor_porch`: the
backdoor lamp already has its own motion and notification rules
(`script.backdoormotion`) and would double-trigger.

## Rollback

Re-running the reverse registry operations restores the previous shape:
`light.backdoor_porch` → `light.porch_one` with name `Porch Light 1`, the device
renamed back to `Porch One`, and the helper options restored to
`["light.porch_one", "light.porch_two"]`. The aliases are intentionally not
restored; add them back through the entity dialog only if voice control should
follow the old porch name again. Do not edit `.storage` files by hand while Home
Assistant is running.
