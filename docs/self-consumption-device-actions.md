# Self-consumption device actions

Automation `automation.power` uses the existing grid/battery load selector. Its
light shutdown branch previously sent `brightness: 100` to `light.turn_off`.
Home Assistant 2026.9.1 rejects that field for shutdown, so selecting a light
could abort the remaining actions.

The payload now includes brightness only for `light.turn_on`. Each independently
selected light or switch call continues after a recoverable device error, allowing
later selected loads to receive their commands. HA still records the failed call;
the existing MQTT message describes the attempted command, not confirmation that
the device changed state.

The load map, selection algorithm, 200 W decision offset, selector tolerance,
action order, two-second trigger, five-second delay and `single` execution mode
are unchanged. The `input_boolean.modern_self_consuming` enable guard is retained.
It was off during the review and must remain off during deployment. No physical
device action or enable-helper change is needed to validate this repair.

Six scenarios execute the actual HA script engine, light schemas and unchanged
root `select_devices.py` in an isolated HA instance, with device and notification
services replaced by recorders. They verify valid shutdown payloads, retained
turn-on brightness, failures in both light/switch ordering combinations, skipped
missing/unknown/unavailable targets, and the existing timing/guard contract.
The deployment receipt separately checks live configuration, control identities,
the unchanged enable helper and the absence of a deployment-triggered run.

This does not resolve unidentified hardware. The [runtime classification of
missing references](missing-reference-runtime.md) explains why the missing garage
light is already excluded by the selector and why no guessed replacement was
introduced.
