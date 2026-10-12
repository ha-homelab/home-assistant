# Dining Media guard

The converted JH-G01U outlet is **Dining Media guard**, controlled through
`switch.dining_media_guard`. It restores the former Dining guard 2 role: power
for the dining-room speakers, printer and associated equipment. The separate
`switch.dining_guard` remains the curtain motor supply.

## Identity and adoption

Match the loader and encrypted native API MAC to the privately recorded old
outlet identity before adoption. Do not infer identity from a DHCP hostname:
the reservation retained an unrelated historical lamp name. The old LocalTuya
device was already removed during the earlier three-outlet cleanup; do not
remove another device or the working curtain controller.

The installed profile uses ESPHome 2026.9.1, a GPIO4 relay, a GPIO5 physical
button, and an inverted GPIO12 indicator. Same-model physical and restart
checks were waived by the owner, so they are not reported as new test passes.
Keep native API and OTA credentials private.

Adopt the verified encrypted ESPHome API, name the device and relay, and add a
separate Dining Media guard row beside the existing Dining guard in Lovelace.
Retain the existing curtain row and every manual override control. A Home
Assistant restart is not required.

## Motion turns media power on

Automation 108 retains both RF dining motion triggers and the existing
`input_boolean.living_room_sticky` condition. Its first action now turns on
`switch.dining_media_guard` with `continue_on_error: true`.

Placing the new action first means failures from the later fireplace or Living
guard actions cannot prevent media power from being restored. Continuing after
a media action failure preserves the existing devices' opportunity to run. The
legacy actions, their order relative to each other, and the automation's guards
are unchanged. Motion does not enable the curtain supply.

No existing script still referenced the old media outlet. The migration does
not add this power strip to generic lights-off scripts, which could interrupt
speakers or a printer at an unrelated time.

## Evening power-off follows Living lamp

The owner selected **Living lamp**, the living-room floor lamp, as the evening
shutdown signal. The package `dining_media_guard_evening.yaml` defines the new
`automation.dining_media_guard_evening_power_off` with these conditions:

- `switch.living_lamp` has changed to off and stayed off for 15 minutes.
- Living lamp is still off when the rule runs.
- The sun elevation is below -2 degrees; an unknown elevation blocks shutdown.
- `input_boolean.living_room_sticky` is off.

Its only action is `switch.turn_off` for `switch.dining_media_guard`. It does not
control the fireplace, Living guard, curtains, or Dining Arc lamp. The former
rule 107 stays retired, and its unavailable fireplace-on guard is not inherited.
The separate Matter `light.arc_lamp_m` and ESPHome Dining Arc lamp remain distinct
from the selected Living lamp.

This retains the original state-trigger timing: a lamp that was already off
does not start a new timer merely because the sun crosses -2 degrees. Reloading
automations or restarting HA resets an in-progress 15-minute state timer.

## Verification and troubleshooting

Validate the complete HA configuration, reload automations, and check that the
canonical relay is available and linked to the loaded motion automation and evening-off rule. Read
back the dashboard and ensure it contains one separate media row. Verify that
curtain automation files, sticky definitions, Office override controls and
their notification rules are unchanged.

If motion does not enable power, inspect the two RF motion sensors and the
living-room sticky state first. Review the new first action separately from
errors raised by the later legacy devices. Do not change the sticky state or
cycle the connected load merely to test the migration.

Matter exposure is a separate step on the existing bridge. Preserve all prior
endpoints and controller fabrics; publish only the canonical relay. Keep
addresses, MACs, registry IDs, credentials and operational receipts outside
this repository.
