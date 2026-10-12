# Garage Zigbee lighting

All five CREE bulbs use the local ZHA coordinator. The four bulbs migrated from
SmartThings retain their physical device identities; only their light entity
IDs are renamed. Their disabled SmartThings records remain disabled.

The 2026-10-07 entity rename is:

- `light.bedroom_one` → `light.garage_bulb_one` (Garage One).
- `light.bedroom_two` → `light.garage_bulb_two` (Garage Two).
- `light.bedroom_three` → `light.garage_bulb_three` (Garage Three).
- `light.bedroom_four` → `light.garage_bulb_four` (Garage Four).
- `light.cree_connected_a_19_60w_equivalent_light` → `light.garage_bulb_five` (Garage Five).

The `garage_bulb_*` names avoid the existing `light.garage_one`,
`light.garage_two` and `light.garage_three` entities, which identify other lights.
Do not repurpose those existing IDs or `light.bedroom_five`.

## Controls and shutdown

`light.garage` retains its identity and includes the five renamed entities.
The controllable-load automation and dashboard continue to use that HA group.
The converted TS0041-TB garage button runs experimental firmware and controls
the same five bulbs through its On/Off binding to the separate native Zigbee
group `Garage Direct` (`0x4701`), independently of the legacy HA button automation.
See the [button runbook](garage-button-binding.md) for commissioning evidence,
settings, and physical acceptance checks.

### Legacy button automation after firmware conversion

The converted button no longer advertises the stock
`remote_button_short_press` / `button_1` device trigger. Retaining that trigger
caused an automation setup repair after HA restarted on 2026-10-09.
Rule 022 now keeps `automation.audio_button_toggle_audio_switch` as a disabled,
empty compatibility entry: `initial_state: false`, no triggers and no actions.
Its stable ID is preserved, and accidental enable/manual execution cannot
duplicate the button's direct Toggle command. The native Zigbee binding,
button firmware/settings, `light.garage`, and household shutdown scripts do not
need changes for this repair.

Apply only the reviewed rule 022 file to a live overlay deployment, preserving
a private backup and checking its prior hash. Validate with the installed HA
version, then reload automations while actions are idle. Verify the same entity
is `off`, the trigger repair is gone, and other automation states are unchanged.
Do not restore the stock trigger unless the button is deliberately returned to
stock firmware and duplicate direct control has first been disabled.

The household shutdown script (`script.turn_off_living_room`) and morning
shutdown automations (`automation.off_lights` at 05:35 and
`automation.off_lights_except_living_room` at 05:45) explicitly list all five
bulbs. Garage Five was previously omitted and is now included. These controls
retain their other light/switch targets, schedules, parallelism, and error
handling. The household script still invokes the iNew shutdown helper.

## Deployment and verification

1. Save private exports of the entity/device registries, states, affected YAML,
   and affected Lovelace configuration. Confirm new IDs are unoccupied and
   every old ID belongs to the expected ZHA device.
2. Validate the four changed YAML files against the running HA installation.
   Rename through the entity registry API; do not edit live registry storage
   files. Set the five display names and their Garage area.
3. Install the script, two automations and group configuration together. Update
   Lovelace references through its API. Preserve unrelated live configuration.
4. Reload groups, scripts and automations at an idle point. Verify all five new
   IDs are available, map to the original ZHA devices, and are the exact members
   of `light.garage`. Confirm automation/script identities and disabled states
   are preserved and active configuration has no old light references.
5. Check action targeting using isolated Home Assistant service mocks. Do not
   execute household shutdown as a smoke test: it affects other rooms and a host.

Repository updates alone do not rename live registry entries or storage-mode
Lovelace dashboards. Coordinate both operations. Historical import contracts,
backups and recorder data may correctly retain the old IDs.

For rollback, reverse the registry rename through the API, restore the saved
YAML and dashboard configuration, validate, and reload at an idle point. Keep
ZHA device identities and the disabled SmartThings records intact. No Zigbee
reset, pairing, firmware update, or Home Assistant restart is required.

The local Kodi helper's `wa` shortcut toggles Garage Five. Its command manifest
must be updated both in `tools/kodi_ha_commands.json` and beside the resolved
`~/k` script. Validate with `kodi_ha.py wa --dry-run`; this only reads the new
entity state. Other Kodi targets, including `gaon`/`gaoff`, retain their existing
meaning. Preserve the private helper connection file and media script.

Commissioning checks passed on 2026-10-07: all three shutdown sequences included
five distinct garage bulbs in isolated HA execution, and the household failure
case still reached switch and host shutdown. Staged and installed HA checks
reported zero errors. Group/script/automation reloads preserved 215 script and
automation IDs and all automation enabled states. All five renamed lights were
available; no obsolete IDs remained in active YAML or Lovelace configuration.

The experimental button firmware conversion and native Zigbee group setup are
tracked in [Garage button: firmware and direct control](garage-button-binding.md).
That runbook records commissioning separately from the existing HA group.
