# Kitchen lamp entity migration

The kitchen Matter light is named **Kitchen lamp** and uses
`light.kitchen_lamp`. It replaces `light.kitchen_lamp_m`; the existing entity
registry identity, Matter device and pairing are retained.

The motion, dimming, inactivity and morning rules, the kitchen group and the
household lights-off script use the new entity ID. This rename does not change
their timing, brightness, Kitchen Sticky or manual-control behavior.

For an existing installation, rename the entity through Home Assistant's entity
registry and update the stored Lovelace dashboard, private EchoMuse allowlist and
Home Studio binding. Home Studio's saved inventory must be edited through its
revision-checked API, preserving every other placement. Update the source
inventory too so a subsequent build retains the binding.

The additive Matter exposure manifest uses the new ID. On an already published
bridge, preserve its existing endpoint: with the existing `stableIdentity`
feature enabled, admit the new exact entity filter, rename the HA entity, refresh
the registry, then remove the old filter. Verify the mapping moved to the new ID
and all endpoint identities and controller fabrics stayed unchanged. The old ID
may remain inside the immutable Matter serial number; it is identity data, not
an active HA entity reference. Do not recreate the bridge or re-pair the lamp.

Historical import baselines and old traces intentionally retain the old ID.
Active scripts are checked against the updated reviewed-runtime contract.
