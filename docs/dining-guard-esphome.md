# Dining guard consolidation

The three numbered LocalTuya Dining guard outlets are retired. Their replacement
is one verified ESPHome relay named **Dining guard**, with the canonical entity
`switch.dining_guard`.

## Curtain behavior

The morning and evening curtain automations use the replacement for dining-room
motor power. Their schedules, sun and manual-override conditions, 90-second
startup delay, cover commands and existing power-off delays are preserved.
This migration does not add RF control or shorten the dining curtain warm-up.

Both dining curtain profiles in the 3D floorplan use the same replacement.
The main Lovelace dashboard shows one Dining guard row.

## Motion is a separate role

The old Dining guard 2 outlet was also a target of the mixed dining-motion
automation. That one obsolete action is removed. The fireplace and Living guard 2
actions remain. Motion does not turn on the new curtain power outlet.

## Deployment and recovery

Before retiring the old devices, verify the replacement's physical button and
relay, encrypted API/OTA, and default-off behavior after restart. Keep private
backups of the old LocalTuya device configurations, HA registry and dashboard
records, and the Matter bridge including identity data.

Rename the verified ESPHome relay to the canonical entity, update the managed
configuration and dashboard, validate HA configuration, and remove only the
three matching old devices through the device registry API. Preserve all other
LocalTuya device configurations.

The installed floorplan loads curtain profiles at process startup. Restart HA
after applying the profile file, then verify the loaded profiles as well as the
files on disk. Do not test by moving curtains or switching a connected load.

Export only the replacement relay through the existing Matter bridge. Preserve
the bridge identity, existing filters, endpoints and controller fabrics. Manual
Google Home and Alexa acceptance tests remain deferred at the owner's request.

After deployment, check that the relay is available and off, all old entity IDs
are absent from active configuration and registries, and previously available
lights and switches recover. Historical backups and recorder history are not
active configuration and should remain available for recovery.
