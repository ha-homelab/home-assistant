# Camera snapshot recovery — 2026-09-23

The Kerberos migration left the old localhost MJPEG servers and recording MQTT
subscription behind. Porch/Ring history files were missing, Garage files were
empty, and Garage callers referred to a missing entity name.

## Runtime contract

All existing snapshot callers use `script.capture_camera_alert(camera_key)`.
The queue serializes capture and rotation, including the two Ring consumers and
manual notification scripts. Capture goes to a hidden pending file. The shared
Python helper decodes the JPEG before publishing it with atomic replacement.
Failed, empty or truncated captures leave all four last-good files intact.
Identical retained Ring frames do not rotate history twice. On initial recovery,
missing or corrupt history slots are seeded with the new real frame; these are
bootstrap copies, not reconstructed historical motion events.

Successful captures still refresh file modification times. When a validated JPEG
already matches a destination slot, only its timestamp is updated: the helper
avoids replacing and fsyncing identical image data. Validation is shared for
identical frames within one commit, without persisting a cache across captures.
When every slot contains the same retained frame, one JPEG decode is sufficient.
Distinct historical frames are each validated once. A repeated latest frame
with valid history requires no image rewrites; missing or corrupt history is
still repaired, and changed images use atomic replacement in the same order.

The native Kerberos bridge reads `payload.action` and `payload.device_id` from
`kerberos/hub/home-assistant`. Four independent, restorable 30-second timers
prevent repeated per-frame events from flooding existing notifications. Unknown
agents, malformed messages and non-motion events are ignored. Ring uses the
current MQTT binary sensor's off-to-on transition. Existing notification windows,
mute conditions, messages and destinations remain unchanged.

## Integration settings outside Git

The September 24 [dashboard recovery](camera-dashboard-recovery.md) supersedes
the direct Front/Backdoor live URLs below with shared Oracle go2rtc sources.
Snapshot helpers and motion-history behavior remain unchanged.

Keep live credentials and `.storage` out of this repository. Front and Backdoor
now use Generic Camera with their current Kerberos camera RTSP sources and TCP,
preserving `camera.front_camera` and `camera.backdoor_camera`. Garage's generic
camera was renamed from `camera.172_30_32_1` to `camera.garage_camera`, including
the existing overview card. Porch snapshots use the native 1920×1080 stream through go2rtc (TCP, video-only).
Garage and Backdoor motion capture use the authenticated snapshot API on
`agent-garagecamera.kerberos.svc.cluster.local` and
`agent-tenantscamera.kerberos.svc.cluster.local`. Repeated HA/RTSP startup failed
with camera `453 Not Enough Bandwidth`; preloading did not fix it and is disabled.
The API reuses the agent's established camera connection and returned valid
1920×1080 Garage JPEGs repeatedly. Backdoor can need over 10 seconds to return
a fresh keyframe (13.23 seconds observed), exceeding HA camera capture’s limit;
the Agent JPEG request allows 20 seconds and preserves its 1280×720 image. Front
still uses native HA camera capture (2560×1440); Porch uses its 1920×1080 stream. No
reduced-resolution Frigate detection preview is used for saved snapshots.
Kerberos recording configuration is unchanged.

The shared Agent fetch helper reads `/config/kerberos-snapshot-auth.json` (mode 0600),
containing the existing agent `username`/`password` from Kubernetes
`kerberos/agent-shared`. Provision this privately, never in Git or command-line
arguments. It authenticates only against fixed in-cluster agent service names,
uses a short-lived response token in an HTTP header, and never persists or logs
that token. Login is bounded to 10 seconds and JPEG capture to 20 seconds; failures
preserve previous images when the agent is unavailable. Update this private file if the agent credentials are rotated.

Ring captures the working MQTT `camera.front_door_snapshot`, avoiding
the abandoned HLS bridge. If its cached image is older than 15 seconds, request
a new snapshot and wait up to 20 seconds for its timestamp to change; on timeout
leave saved files intact. Browser clicks open the same-origin saved Ring image.

On 2026-09-24 the owner retired Backyard. Its MJPEG entry, four Local File
entries, two motion rules, dashboard snapshot stack and legacy copy command
are removed. The shared capture helper no longer accepts its camera key.
Other Backyard-named devices are independent of the retired camera.

## Validation and rollout

Run the repository validators and `tests/test_camera_snapshots.py` in the deployed
HA image, with bundled libraries for the native-motion bridge cases. The suite
covers missing/zero-byte history, invalid/truncated JPEGs, duplicate frames,
concurrent captures, camera failure, invalid keys and per-camera motion gating.
The notification regression suite independently verifies existing recipients,
Chrome images, light actions and delays.

Deploy the root helper/package and both pinned caller libraries together after
HA's installed configuration check. Reload shell commands and timers, then scripts
and automations only after a fresh idle check. Do not reset disabled automations
or running timers. Call the capture helper directly to verify images without
sending test notifications; reload failed Local File entries after files exist.
Rollback restores the preceding root/component revisions and the private config
entry/dashboard backup. Do not delete last-good snapshot files during rollback.
