# Roomba Insights: passive local telemetry

Roomba Insights adds one diagnostic sensor to each robot already configured by
Home Assistant's native `roomba` integration, plus an experimental relative-path
image for robots that advertise or report a pose. It reuses that integration's
in-memory connection. It does not request credentials, create a second MQTT
client, send commands, or enable disabled robots.

This matters because older Wi-Fi Roombas generally allow only one local MQTT
connection. Running another map collector against the same robot can interfere
with Home Assistant. See the [native integration documentation](https://www.home-assistant.io/integrations/roomba/).

## Install

Install from the tracked source tree or a repository source archive. The
repository's Python wheel and sdist package **ha-notification-frame-cache**;
they are not installers for Roomba Insights and do not contain this component.

1. Deploy the tracked `config/custom_components/roomba_insights` directory as
   `/config/custom_components/roomba_insights` in Home Assistant.
2. Restart Home Assistant at a coordinated maintenance point so it discovers
   the new custom integration.
3. Add **Roomba Insights** from **Settings → Devices & services**. Confirm the
   empty form once. No robot password or cloud account is required.
4. Each existing iRobot device gains a **Local telemetry** diagnostic sensor.
   Robots in `setup_retry` remain visible as disconnected diagnostics. They do
   not prevent a connected robot from working.
5. A robot with pose support also gains a **Relative cleaning path** image.
   It remains unavailable until actual cleaning messages supply enough valid
   points. An unavailable image at startup is not an installation failure.

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

## Experimental relative cleaning path

The optional image draws sampled native `pose.point` reports on a plain
background. It is a trace of relative odometry, not an extracted iRobot map,
measured coverage, walls, room boundaries, or a calibrated 3D position. Device
units are not labelled as meters. This implementation has not yet passed a
physical cleaning-path acceptance test on the target robot.

Collection requires all of the following:

- A new message contains a complete, finite `x`, `y` and `theta` pose. Initial
  cached poses and battery-only messages never become path points.
- The reported mission has `cycle: clean` and `phase: run`.
- A valid explicit mission identity is available: `nMssn` and/or a positive
  `mssnStrtTm`. The component does not invent a session or map identity when
  these fields are missing. A malformed or partial identity update clears the
  previous trace before any new points can be connected.
- At least two accepted points form one continuous segment. One point or
  disconnected single points do not produce a placeholder map.

The trace retains at most **2,048 points**, with at least **one second** between
accepted points in a continuous segment. Repeated positions are not appended.
Invalid poses, non-cleaning phases, receipt gaps over **30 seconds**, reversed
receipt times and jumps over **500 native units** break the line. These are
conservative plotting guards, not a claim about physical speed or distance.
A new mission clears the trace. A disconnection hides the image; the next
observed connection starts a new trace instead of joining old coordinates.
Replacing the native client also starts empty.

Rendering uses a fixed **640 × 480 PNG**, capped at **1 MiB**, in an executor.
Updates are coalesced to at most one render every **five seconds**. A result
from an obsolete snapshot cannot replace the newer desired image. Removing
the integration cancels pending image updates and prevents in-flight renders
from publishing, without closing the native robot connection.

`last_point_received_at` is local receipt time. The image's own timestamp is
its publication time; neither is the robot's observation time. `observed_at`
remains null, `coordinate_frame` is `relative_uncalibrated`, and
`is_house_map` is false. Only summary counts/status are exposed as image
attributes; the complete point list is not published in recorder attributes.
The in-memory trace is not restored after a restart. HA serves the image
through its normal authenticated or token-authorized image endpoint, not a
public `/local/` file. Treat image URLs and captures as private.

If no image appears, first inspect the telemetry's actual mission fields and
pose receipts during a supervised clean. Supported pose telemetry alone does
not prove that the required mission identity is reported by a given firmware.
Do not weaken the identity checks or manufacture a map merely to show an image.

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

Run both focused suites:

```sh
python -m unittest discover -s tests -p test_roomba_insights.py -v
python -m unittest discover -s tests -p test_roomba_trail.py -v
```

Pure telemetry tests run without HA. Lifecycle and setup tests additionally
require the deployed Home Assistant runtime; they use synthetic native entries
and a fake connection in a temporary configuration directory. They do not
connect to a physical robot.

The trail suite checks mission and disconnect boundaries, invalid/partial
poses, bounded retention, concurrent snapshots, PNG pixels across a deliberate
gap, render throttling, obsolete-worker rejection and image removal. Run with
`REQUIRE_HA_RUNTIME=1` in the target runtime to require the HA and Pillow checks
instead of accepting skipped tests.

On 2026-10-22, the combined **46 tests passed with no skips in HA 2026.10.0**:
23 insights tests and 23 trail tests. This includes sensor/image platform setup
and unload, single-entry configuration, and image lifecycle behavior. The
fixtures use synthetic robots and do not establish physical cleaning-path
accuracy or deployment status.
