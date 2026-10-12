# Sockets behind fireplace two retirement

On 2026-10-11, the owner retired the unavailable LocalTuya device
**Sockets behind fireplace two** and all three of its relays:

- `switch.50w_ll`
- `switch.tiny_garland_l`
- `switch.mini_tv`

The associated switch-as-light helpers `light.50w_l` and
`light.tiny_garland_ll` were removed through their configuration entries.
The device was then removed through Home Assistant's device registry.
The shared LocalTuya entry now contains 32 devices instead of 33; all other
device configurations and entity identities were verified unchanged.

The two Lovelace rows were removed. References were removed from the morning
lighting shutdown, shutdown except the living room, switch notifications, and
the household lights/media shutdown script. Other targets, schedules, script
error handling and the host shutdown helper were retained. The existing
automation and script identities were preserved.

The complete HA configuration check passed, the three changed automations were
reloaded by ID, and scripts were reloaded through the normal service. Readback
of the loaded configurations confirmed that the five retired entity IDs were
absent. The cleanup sent no relay commands and required no HA restart.

Existing recorder history and archival backups were not changed. The separate
`switch.tiny_garland_ll` spelling and other fireplace entities were not part of
this device and were not removed by a substring match.
