# Studio guard migration

The converted WP5 outlet uses the ESPHome entity `switch.studio_guard`, named
**Studio guard**. It replaces the exact LocalTuya entity `switch.studio_guard_1`.
The canonical entity has no numeric suffix.

## References and behavior

Automation 027 retains its existing evening curtain sequence, conditions,
delays, and other targets. Automation 078 retains its morning sequence. Only
the three references to the old Studio guard outlet change.

The power guard for both `cover.office_curtains_office_curtains` and
`cover.office_curtains_r` becomes `switch.studio_guard`. The existing Lovelace
row uses the new entity and display name while preserving the surrounding
layout and controls. No floorplan furniture placement is moved or replaced.

The installed floorplan integration loads curtain profiles when its Python
module is imported and has no profile reload service. Activating these changes
therefore requires one controlled Home Assistant restart after configuration
validation and checking for active control work. This is not an outlet restart
test. Verify the loaded profiles through the authenticated curtain-state API
after Home Assistant returns.

The old `_power` timestamp in persisted curtain observations is historical.
Do not copy it to the new relay as evidence of a new power-on event; live
curtain profiles must refer only to the canonical new entity.

## Verification limits

The loader and encrypted ESPHome API identities were matched to the old
outlet before adoption. The known WP5 profile exposed the expected relay,
physical button, and red indicator entities.

The owner waived repeated physical checks, load cycles, and outlet restart
tests for this known profile. Those checks were not performed and must not be
reported as passed. HA availability and the configured references are verified
by readback; they do not constitute a new physical load test.

Remove only the exact obsolete LocalTuya device after the canonical replacement
is reachable. Export only its relay through the existing Matter bridge and
verify preservation of all existing endpoint identities and three controller
fabrics. Keep firmware keys, addresses, hardware identifiers, and execution
records in the private workbench rather than this repository.
