# Bathroom warmer on ESPHome

The converted YM-WS-1 outlet uses `switch.bathroom_warmer`, displayed as
**Bathroom warmer**. It replaces `switch.bathroom_warmer_l` on LocalTuya.
The converted device was matched to the old outlet using its private hardware
identity and encrypted ESPHome API before removing the obsolete device.

## Preserve the existing behavior

Automation 019 still waits for one minute continuously off. It turns the warmer
back on only while `input_boolean.bath_warmer_sticky` is off. Automation 112
keeps the existing switch-state notification actions and other targets.
Returning from unavailable to off can therefore start the normal restoration
timer. An automatic restoration is not a commissioning load test.

The active Away Devices On and Away Devices Off scenes both use the new relay.
Their obsolete hardware-ID alias was verified as belonging to this exact outlet;
the other outlet in each scene is preserved. The existing Lovelace entity row
uses the canonical relay and display name, retaining its position and
`last-changed` secondary information.

No curtain profile or furniture binding references this outlet. Validate the
configuration, reload automations and scenes, and read back the loaded references.
A Home Assistant restart is not required for this migration.

## Verification and limits

The known YM-WS-1 profile was reused with owner authorization: GPIO15 relay,
GPIO13 inverted pull-up button, and GPIO12 inverted internal indicator. The relay
has an `ALWAYS_OFF` startup policy. Firmware/API identity, HA availability,
automation state, loaded scene targets, Lovelace, and removal of old active
references were checked. Repeated physical tests, deliberate load cycles and
outlet restart tests were waived and were not performed.

Only the obsolete LocalTuya device and its sole entity were removed. No new
backup or snapshot was created. Private keys, addresses, hardware identifiers,
and operational receipts belong in the private workbench, not this repository.

## Matter exposure

Expose only the canonical relay through the existing bridge when its API is
available. Preserve all existing endpoint identities and controller fabrics,
then verify the new endpoint type, reachability and identity readback.

At HA handoff the existing Matter bridge API timed out from both the HA host and
the Mac, although its Kubernetes pod reported Ready. No filter change or new
endpoint was claimed. HA and Desktop adoption can complete independently;
Matter exposure remains pending until those checks succeed. Do not reset or
recommission the bridge to work around an unrelated API timeout.
