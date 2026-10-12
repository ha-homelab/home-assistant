# Mishka and Kitchen curtain power on ESPHome

The two former LocalTuya power outlets now use stable ESPHome names:

- `switch.laser_l` becomes `switch.mishka_guard`, displayed as **Mishka guard**.
- `switch.kitchen_guard_1` becomes `switch.kitchen_guard`, displayed as **Kitchen guard**.

The old LocalTuya records are removed only after confirming their hardware
identity and the corresponding replacement integration. The Lovelace controls
and automation targets follow the new IDs. The shared notification rule also
watches Mishka guard under its new ID. Existing automation identities,
thresholds, time schedules, manual overrides, delays, and unrelated targets
are preserved.

Both rear-bedroom curtain profiles use `switch.mishka_guard`; the kitchen
curtain profile uses `switch.kitchen_guard`. These profiles are loaded when
the floorplan integration starts. A single HA restart activates both changes;
reloading automations alone does not reload the profile module.

## Device acceptance

The KMC 30137 used for Mishka guard passed the physical button, relay, lamp,
and indicator checks. A subsequent HA command problem was resolved by removing
and re-adding only its new ESPHome integration entry. The registry identity,
address, MAC, entity command key, and protocol encoding had matched the device.
A plain entry reload did not fix it. A fresh HA on/off command was then confirmed
through an independent ESPHome state subscription, followed by a successful
HA restart-off test. This establishes recovery; it does not establish the
underlying cause of the previous connection failure.

Kitchen guard reuses the established WP5 firmware profile. The owner explicitly
waived repeated per-device button, load, indicator, and restart testing.
Firmware upload, encrypted API identity, and passive availability were verified.
Unperformed physical tests remain recorded as unverified rather than passed.
No load toggling is part of its HA migration.

## Matter and recovery

Only each relay is exported through the existing Matter bridge. Diagnostic
entities, restart buttons, physical-button sensors, and the WP5 red indicator
are excluded. Stable bridge identity, existing endpoint identities, and all
three controller fabrics are preserved. No controller re-pairing is required.
Controller acceptance after migration remains deferred by the owner.

Before changes, keep private snapshots of the affected YAML, registry metadata,
LocalTuya entries, dashboard, and the Matter backup including identities. Restore
only the affected records when recovering; avoid overwriting concurrent HA
changes. Never publish credentials, hardware identifiers, addresses, or Matter
identity backups. Local validation covers the complete configuration, automation
contracts, daylight timing, and curtain memory/profile behavior.
