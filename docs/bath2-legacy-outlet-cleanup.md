# Bath2 and the retired heater outlet

The owner repurposed the physical outlet formerly called Playpen, Heat500w,
or Dining chandelier as Bath2 on ESPHome. The live LocalTuya identity matched
that ESPHome device's hardware identity. Only the obsolete Playpen record was
present; no separate active Heat500w or Dining chandelier records were found.
Hardware identifiers, addresses, credentials, and private backup contents are
intentionally omitted here.

The canonical control is now `light.bath_2`, backed by `switch.bath_2`;
see [the light migration](bath-2-light.md). The separate legacy bathroom light
`light.bath2_old` remains unchanged. It is a different device.

## Retired behavior

- Remove the obsolete `switch.playpen` LocalTuya device, entity, customization,
  and the Lovelace row labelled Heater 500W (Playpen).
- Retire small-heater rules 090, 092, 097, and 099. Rule 090 transferred power
  from other loads to the heater, so the complete transfer is retired instead
  of leaving source-load shutdown actions without a destination load.
- Remove only the 450 W Playpen candidate from shared selector rule 085.
- Remove only the obsolete Playpen-off prerequisite from charger rule 098.
  Its remaining guards, threshold, delay, and charger action are preserved.
- Keep Bath2 out of the old heating and self-consumption controls.

No active script directly referenced the retired outlet. Generic load-selection
scripts remain unchanged and consume the reduced candidate map. The migration
manifest retains the retired automation identities and reasons. Historical
backups and the unused root `automations.yaml` remain archival evidence; the
running configuration includes only `automations/`.

## Deployment and verification

Keep private snapshots of the affected YAML, entity/device metadata, LocalTuya
configuration, and dashboard before deleting the obsolete records. Validate the
complete HA configuration, reload automations when no actions are running, and
remove the resulting restored-only automation registry entries by exact ID.
Reload core customization without restarting HA.

Verify that the retired device and four automation entities are absent, Bath2
still belongs to ESPHome, Bath2_old retains its original device identity, and
all other LocalTuya device dictionaries are unchanged. No physical load needs
to be toggled for this cleanup. Source validation must account for all 130
original automation identities, with 102 remaining active after this cleanup.

The private recovery snapshot contains former device credentials. Restore only
selected records if required; never publish or blindly restore the full HA
storage directory. Reintroducing the old heating rules would assign heating
behavior to a plug that is now used for a different purpose.
