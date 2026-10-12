# Living lamp migration

The former LocalTuya outlet `switch.bedroom_lamp_l` now uses the ESPHome entity
`switch.living_lamp`, named **Living lamp**. It is an on/off relay; it does not
provide brightness or color controls.

## Dashboard and placement

The existing Lovelace position for `light.arc_lamp_m` now contains a button for
Living lamp. A tap toggles the relay, its state is displayed, and a hold opens
more information. The old bedroom button is removed, so there is only one
Living lamp card.

The Matter entity `light.arc_lamp_m` and its **Smart RGBTW Bulb** device remain
registered. Replacing a dashboard card does not retire that separate device.

The obsolete `bedroom_table_lamp` object and binding are removed from the bedroom
floorplan. Other placements are preserved; no new living-room coordinates are
inferred. The model, viewer, and downloadable model exports are regenerated.

## Automation behavior

Rules 020 and 021 are retired because their sole target was the former bedroom
lamp. Living lamp is not controlled by bedroom motion. Rule 074 retains its
existing global morning shutdown schedule, and rule 112 retains its existing
state-change notifications, with their target changed to `switch.living_lamp`.
Other devices, schedules, conditions, and actions are preserved.

## Identity and verification

The encrypted ESPHome device identity was checked against the converted outlet
before adoption. The owner had already verified that the physical button
switches the actual load. The migration used passive state verification and
did not add another load cycle. The old LocalTuya device was removed only after
the canonical replacement was reachable.

The indicator GPIO polarity was corrected in firmware and the new firmware was
verified through the encrypted API. Its physical appearance after correction
has not been re-observed; software verification is not a visual confirmation.

Only the canonical relay is exported through the existing Matter bridge as an
on/off plug-in unit. All previous endpoint identities and the three controller
fabrics were verified unchanged. Controller-app acceptance remains deferred by
the owner.

The live configuration check passed. Readback verified the switch card, removed
bedroom bindings, active global automations, and absence of the obsolete entity
from active configuration. No Home Assistant restart or new snapshot was needed.
Private addresses, keys, hardware identifiers, and execution records remain
outside this repository.
