# Roomba Insights: passive local telemetry

Roomba Insights adds one diagnostic sensor to each robot already configured by
Home Assistant's native `roomba` integration. It reuses that integration's
in-memory connection. It does not request credentials, create a second MQTT
client, send commands, or enable disabled robots.

This matters because older Wi-Fi Roombas generally allow only one local MQTT
connection. Running another map collector against the same robot can interfere
with Home Assistant. See the [native integration documentation](https://www.home-assistant.io/integrations/roomba/).

## Install

1. Deploy the tracked `config/custom_components/roomba_insights` directory as
   `/config/custom_components/roomba_insights` in Home Assistant.
2. Restart Home Assistant at a coordinated maintenance point so it discovers
   the new custom integration.
3. Add **Roomba Insights** from **Settings → Devices & services**. Confirm the
   empty form once. No robot password or cloud account is required.
4. Each existing iRobot device gains a **Local telemetry** diagnostic sensor.
   Robots in `setup_retry` remain visible as disconnected diagnostics. They do
   not prevent a connected robot from working.

The normal configuration build includes these tracked files. A source update
alone does not deploy them or create the integration entry. Removing Roomba
Insights detaches only its own observers and leaves the native connection
running.

## What the sensor means

The state is the reported mission phase when connected, or the native entry's
setup/disconnection status. Attributes include the source vacuum entity,
connection state, last nonempty message receipt, selected mission statistics, map ID/version references, and
selected fields from the last room-cleaning command.

`position` is diagnostic native `pose.point` data. These coordinates are not
swapped to the library's separate `co_ords` convention. No conversion to a
floorplan is assumed. Coordinates are validated as finite numbers; boolean,
string, missing, partial and implausibly large values are rejected.

- `observed_at` is always null: the local payload does not supply a verified
  device observation timestamp.
- `received_at` is set only when a complete pose arrives in a new message.
- A cached pose present at setup has no known receipt time.
- Battery, signal and mission-only messages do not refresh a pose timestamp.
- An incomplete new pose invalidates the current report, while preserving the
  previous complete position as explicitly last-known diagnostic information.
- `cache_read_at` describes a local inspection, not a fresh physical position.
- `frame_quality` remains `uncalibrated`, even if map IDs are known.
- `position_current` remains false. This sensor must not be used directly as a
  live marker source for a calibrated 3D floorplan.

Roomba 960-class devices can expose relative position suitable for building a
cleaning trail. A trail is not a saved floor map with walls or room polygons.
Some newer firmware does not expose local position at all. The existence of
an iRobot app map does not imply that the local protocol provides its image.

## Room metadata is evidence, not a replay service

`room_request_observed` means an actual complete `start` message contained a
map ID, map version and a nonempty valid region list. The native library deeply
merges its cache, which can retain an old command's room fields after a generic
command. For this reason, cached `lastCommand` at startup is diagnostic only;
new commands are captured from the original message delta.

`room_request_matches_current_map` compares the observed request with the
reported map catalog. It requires a complete, bounded, recognized catalog and
an unambiguous matching version. A truncated or malformed catalog cannot
confirm a room request. It does not
establish which floor is active, validate physical room boundaries, or prove a
coordinate transformation. Invalid, duplicate or oversized region lists never
become valid by silently dropping entries. No room-cleaning service is provided
by this passive component.

The upstream [dorita980 room command documentation](https://github.com/koalazak/dorita980#cleanroomargs)
explains how room IDs are normally learned from an app-initiated cleaning and
`lastCommand`. If an actual room request has not been received, do not invent
IDs or substitute a whole-home cleaning command.

## Reliability and privacy

The observer takes bounded, allowlisted snapshots inside the existing MQTT
callback, then schedules HA state updates on its event loop. Native entry
reloads are detected by a lightweight local scan every 30 seconds. A queued
callback from an old connection cannot update its replacement. Unload removes
only this component's callbacks.

Passwords, BLIDs, addresses, SSIDs, serials and the unrestricted native cache
are not exposed as sensor attributes. Map IDs, room names and relative
coordinates are private household data even though they are not credentials.
Keep live state exports and floorplan geometry out of public repositories.

If a robot is disconnected, check power and Wi-Fi coverage first. This
integration cannot fix a dock in a Wi-Fi dead spot and does not repeatedly
reload the native integration or alter credentials.

## Validation

Run `python -m unittest discover -s tests -p test_roomba_insights.py -v`.
Pure telemetry tests run without HA. Lifecycle and setup tests additionally
require the deployed Home Assistant runtime; they use synthetic native entries
and a fake connection in a temporary configuration directory. They do not
connect to a physical robot.
