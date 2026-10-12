# Bedroom guard migration

The former LocalTuya relay `switch.bedroom_guard_3_bedroom_guard_3` is replaced
by the ESPHome relay `switch.bedroom_guard`, displayed as **Bedroom guard**.
The other two Bedroom guard devices are separate outlets and must be retained.

## References and behavior

- Automation 028 closes bedroom curtains in the evening. Its sun elevation
  threshold of 0.1, `curtains_sticky` override, cover commands, 90-second startup
  delay and one-hour shutdown delay remain unchanged. Only the two outlet
  targets change.
- Automation 076 retains its 07:08 schedule, override and Mishka guard action.
  Only its Bedroom guard target changes.
- The left and right bedroom curtain profiles use `switch.bedroom_guard` as
  their power guard. The profiles are loaded at integration startup, so the
  runtime must be restarted after deploying the updated profile file.
- The existing Lovelace row keeps its last-changed secondary information and
  uses the new entity ID and display name.

No script, group or scene required an outlet reference change in the live
preflight. Recheck references before repeating this procedure on another
installation; an old inventory is not proof that a current reference is absent.

## Safe replacement procedure

1. Verify the physical outlet identity privately and confirm the ESPHome API
   encryption, relay, physical button and indicator before retiring LocalTuya.
2. Back up the selected integration configuration, registries, dashboard,
   affected files and Matter bridge data including its identity material.
3. Verify HA on/off control and restart behavior with a suitable load. Avoid
   repeated cycling of installed equipment. This deployment used one on/off
   cycle followed by a software restart while the relay was already off;
   it did not exercise an on-to-restart transition. Firmware uses `ALWAYS_OFF`.
4. Assign the canonical relay and device names using the HA registry API.
   Update the identified references without changing automation behavior.
5. Remove only the verified old LocalTuya device through the supported device
   removal API. Preserve all other devices in the shared LocalTuya entry.
6. Validate HA configuration, restart once when appropriate, and check both
   loaded curtain profiles and the dashboard. Search active configuration for
   stale references; historical backups intentionally retain old IDs.
7. Export only the canonical relay through the existing Matter bridge. Keep
   diagnostic/button entities out of the export and verify that all previous
   endpoint identities and controller fabrics remain unchanged.

Private addresses, hardware identifiers, encryption keys, backups and execution
logs are deliberately excluded from this document and the repository.

## Verification caveat

A missing event in an additional ESPHome observer is inconclusive by itself.
The HA relay in this deployment is not an assumed-state entity: its displayed
state comes from an ESPHome `SwitchState` response. Distinguish command delivery,
observed state changes and a physical load test instead of treating a successful
service call alone as proof of operation.
