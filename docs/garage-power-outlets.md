# Garage power outlets

The garage's GREFIC CZ-U201 uses these two ESPHome entities:

- `switch.garage_door_power` — **Garage Door Power**, the left outlet viewed
  from the front, native Outlet 2 / GPIO14. This supplies the garage-door motor.
  It is not an open/close command; the separate garage remote operates the door.
- `switch.garage_floodlight` — **Garage Floodlight**, the right outlet, native
  Outlet 1 / GPIO15. This supplies the ceiling LED floodlight.

## Consumer migration

Active consumer references to `switch.garage_opener_l` now use
`switch.garage_door_power`. References to `switch.garage_beam`, including its
historical alias `light.garage_beam_light`, now use `switch.garage_floodlight`.

The self-consumption selector retains the floodlight's **108 W configured
estimate**. That value is not a new power measurement. Its existing domain-aware
dispatch uses the switch branch. Door power is not added to that load map.
Switch-state notifications and the three existing Lovelace references use the
new entities. The live script, group, template and floorplan audit found no
remaining garage consumer references requiring changes.

## Retained originals

The owner explicitly requested retaining both originals for a later decision:

- `switch.garage_opener_l`, still named **Garage opener**, with its LocalTuya
  device and integration entry.
- `switch.garage_beam`, still named **Garage Beam**, with its Matter device and
  integration entry.

Do not rename, disable or delete them as part of this migration. The old
`switch.garage_opener_l` block in `config/customize.yaml` is deliberately retained
to preserve its name; it is not an actuator binding. Archived configuration and
dated audits retain their original identifiers. In particular, this migration
supersedes the unresolved floodlight classification in
[the September audit](missing-reference-runtime.md) without rewriting that
historical evidence.

## Validation and operating boundary

The live audit verified loaded automation targets, the floodlight estimate,
Lovelace bindings, and unchanged original registry entities/devices. It scanned
active configuration and found only the intentional old customization block.
Local source changes were compared semantically with the current live rules;
no old checkout was deployed over the running configuration.

The owner paused physical testing. This reference cleanup sends no load or
garage-door commands and does not restart or flash the outlet. The last observed
software state was floodlight ON and door power OFF; visual load confirmation
remains outside this cleanup. Configuration validation is not a physical test.

Source changes also carry forward the already completed
[kitchen outlet migrations](kitchen-esphome-outlets.md), so releasing this source
stack does not restore their old light-domain references.
