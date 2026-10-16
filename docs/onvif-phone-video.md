# Living Room ONVIF video notifications

The Living Room camera sends its native ONVIF detection
messages to HA. `binary_sensor.living_room_camera_cell_motion_detection` changing
from a known `off` to `on` prepares a live attachment and sends **Living Room
ONVIF: motion detected** to **Vitaly iPhone Air**. The service name remains
`notify.mobile_app_als_iphone_89310`. Dining Room and the other Tapo cameras keep
event sensors only; this change does not enable their phone video alerts.

`config/packages/onvif_video_notifications.yaml` implements the trigger and a
60-second cooldown. Unknown/unavailable recovery and HA startup do not replay
motion. The global `input_boolean.notifications_off` mute is checked before and
after video preparation. This alert has no additional quiet hours. Router category
`camera_onvif` permits only this camera and phone and excludes Chrome. Existing
Front, Kerberos, Frigate-generic and RF suppression remains in force; Garage/Porch
person alerts and Ring Front Door retain their existing policy.

## Video lifetime and traffic

1. ONVIF PullPoint receives detection events without reading RTSP video. All
   Living Room native ONVIF video and camera-control entities remain disabled.
   Other rooms' later desktop viewing exception is documented in
   [Tapo desktop MQTT](tapo-desktop-mqtt.md).
2. `shell_command.onvif_notification_video_ready` invokes the shared
   `housekeeping/notification_video_ready.py living_room_onvif`. It subscribes to
   the private Oracle `go2rtc-onvif` relay and waits for a complete JPEG, with a
   total startup/retry limit of 35 seconds.
3. Readiness returns immediately after that frame. A detached subscriber holds
   the stream for at most 30 more seconds to let the iPhone/Watch attach. HA sends
   `data.entity_id: camera.living_room_onvif_notifications` and
   `push.category: camera`; a tap targets this camera. Expand the iPhone alert to
   view live video. Device playback still requires a check on the actual device.
4. The subscriber closes its own connection when the hold expires. An active
   viewer can continue; after the last viewer disconnects, the relay releases
   the encoder and camera connection. A later viewer can initiate a new cold start.

The relay runs on **Oracle h7**, not Synology. It opens the camera's H.264
`stream2` only on demand and converts it to 640-pixel-wide MJPEG at about one frame
per second with one encoder/filter thread. Multiple viewers share one upstream
RTSP camera connection. The warm interval itself carries video from home to Oracle;
phone viewing also consumes Oracle outbound traffic. This is bounded event-driven
traffic, not zero camera traffic. Frequent motion can cause repeated warm intervals.
There is no preload, recorder or permanent consumer in this relay.

The relay is a separate deployment so adding it requires no restart of the
existing Front/Ring/Porch/Garage/Backdoor relay. Their capture/recording pipelines
are unchanged. Manifest and private Secret template live in
cluster configuration.

## HA camera entry

Create an **MJPEG IP Camera** entry through Devices & services:

- Name: `Living Room ONVIF Notifications`.
- Entity: `camera.living_room_onvif_notifications`.
- MJPEG URL: `http://go2rtc-onvif.kerberos.svc.cluster.local:1984/api/stream.mjpeg?src=living_room_onvif_notifications`.
- No still-image URL or camera credentials in the HA URL. No indoor snapshot is
  saved under public `/local/` for this flow.
- Set the entity registry's **hidden** flag (`hidden_by: user`) and do not add it
  to automatically refreshing dashboard previews. A preview, snapshot request or
  explicit viewer can start this on-demand stream even without a motion event.
- Keep stream preloading disabled. The ONVIF camera entities remain disabled;
  the dedicated MJPEG camera is enabled and hidden.

The internal service is not published outside the cluster. The camera account is
held in the private Kubernetes Secret. HA's authenticated camera proxy supplies
the phone's attachment. Preparation failure still sends the motion alert with
an explicit video-unavailable message; a missing camera or notification provider
must not interrupt other household actions.

## Validation, recovery and rollback

The HA runtime tests cover real off/on trigger semantics, cooldown, reconnect
suppression, both mute checks, camera/phone routing, and preparation failure.
Loopback MJPEG tests cover complete-frame readiness, timeouts and bounded cleanup.
The shared Ring/ONVIF readiness parser scans incoming chunks once and retains
only one byte between reads, including when a JPEG marker spans two reads. It
does not repeatedly copy or rescan the growing first frame. Startup accepts at
most 1 MiB through the first JPEG end marker, including multipart headers; an
oversized completed frame is rejected even if its last chunk also contains that
end marker. Bytes after a valid first frame do not count against its budget.
Startup timeout and cancellation explicitly close the owned HTTP response as
well as the session; cancellation does not signal readiness. Tests also reject
event-loop resource-leak diagnostics, not just failed readiness assertions.
For live verification, observe zero active relay producers/consumers at idle,
prepare the stream, retrieve multiple distinct JPEG frames through authenticated
`/api/camera_proxy_stream/camera.living_room_onvif_notifications`, and confirm one
upstream producer during viewing and zero again after viewers and the hold end.
The HA pod should not open a direct RTSP connection to the Living Room camera.

A live check on September 27, 2026 started the stream in 2.12 seconds, received
three distinct JPEG frames through HA, and observed one upstream producer during
viewing and zero producers/consumers before and after. The HA pod had zero direct
Living Room RTSP connections in these samples. Frigate had no direct Living Room
input. These samples validate stream behavior, not actual iPhone/Watch playback.

Native HA backups include the MJPEG entry, ONVIF entries and renamed entity
registry. YAML and helper code are in the root repository. For a fresh cluster,
restore the private `go2rtc-onvif` Secret using the infrastructure template, apply
its Deployment/Service, then restore HA or recreate the entry above. Consult
the private h3 inventory and HA registry for device identities and their room
mappings.
Keep the existing weekly backup schedule.

To stop new phone alerts, disable the Living Room ONVIF automation. To remove the
feature, remove its package and scoped router exception, reload idle scripts,
automations and shell commands, and remove the MJPEG entry and dedicated relay.
Keep the shared helper and Ring compatibility wrapper while Ring uses them. This
rollback does not require deleting ONVIF event entries, reverting room names, or
restarting HA or the existing camera relay.
# Optional private floorplan frame reuse

The readiness worker now feeds the JPEG bytes it already receives into
`housekeeping/notification_frame_cache.py` for `living_room_onvif` only. This adds
no subscriber, camera connection or video encoder, and does not extend the
existing startup/hold deadlines. Ring and other notification sources are unchanged.

The optional sink publishes at most one frame per second to
`/config/.storage/notification_frames/living_room_onvif.json`, outside public
`www`/`local`. It uses a 0700 directory, atomic 0600 temporary files, a random
event ID, capture timestamp and bounded base64 JPEG. A nonblocking file lock
ensures overlapping workers cannot overwrite/delete the owner's frame. Disk
errors disable caching while allowing the notification to continue. Normal exit
removes the frame; a killed worker may leave one file, which the floorplan reader
rejects after five seconds. This is a transient private frame, not an MP4 archive.

Home Floorplan 0.5.14 reads the file via its administrator-only WebSocket command,
validates/downsizes the JPEG, and displays it by the saved Living Room Camera
placement. Native HA and the Access-protected standalone plan share that host.
The map cannot ask this helper to capture or keep video alive. Muting or cooling
down the existing notification automation also means there is no new map video.
Other rooms are not implicitly enabled.

Install `notification_video_ready.py` and `notification_frame_cache.py` together;
the next worker uses them without a HA restart. No automation/relay change is
required. Keep these two files together during restores and future upgrades.
Run `test_ring_video_ready.py` and `test_notification_frame_cache.py`: the latter
uses a loopback stream to prove one connection, readiness and cleanup at the
original deadline, plus chunk, size, permissions and overlapping-worker checks.
To roll back, restore the previous readiness helper when no worker is active.
Do not publish the cache directory or commit real image bytes.
