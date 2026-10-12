# Vitaly iPhone Air notifications

`script.notify_optional` sends one Companion copy of each eligible Chrome delivery to
`notify.mobile_app_als_iphone_89310`. The service retains the phone's original app
registration name; the verified device/config entry is **Vitaly iPhone Air**.
The delivery policy is centralized in this helper:

- Frigate **active-person activity in Garage and Porch** is explicitly enabled on
  Vitaly iPhone Air only. The shared `camera_person_notifications` package watches
  `sensor.garage_person_active_count_2` and `sensor.porch_person_active_count_2` for
  a known `0` becoming positive. It sends once per active scene, not on every count
  update, generic motion or recovery from `unknown`/`unavailable`. The existing
  `input_boolean.notifications_off` mute still applies. A `camera_person` category
  permits only direct phone deliveries with the Garage/Porch live camera entity;
  it does not enable Chrome copies or alerts from other cameras.
- **Living Room ONVIF** uses native camera cell-motion events and sends live
  video only to Vitaly iPhone Air, with `ONVIF` in the title. A 60-second cooldown
  and global mute apply. Its separate Oracle relay opens one camera substream
  during preparation/viewing and releases it afterward. The `camera_onvif`
  exception accepts only this camera and phone; it never enables Chrome copies.
  See [ONVIF phone video](onvif-phone-video.md) for transport and recovery.
- Front, Garage, Porch and Backdoor camera motion (the Kerberos camera channels),
  plus other messages identifying Kerberos or Frigate, remain suppressed on both
  Chrome and Vitaly iPhone Air. Camera capture/recording, TV and desktop destinations
  continue. Known snapshot paths and notification camera entity IDs are also
  recognized, so title-less legacy calls cannot bypass the camera policy.
- RF motion reports are suppressed on both Chrome and Vitaly iPhone Air. Matching
  is case-insensitive and recognizes titles such as `Motion RF Dinner Motion`
  and title-less messages such as `RF Counter Motion on`. Existing TV and desktop
  destinations continue; the sensors and their household automations stay active.
  Motion automation 070 formats MQTT/display text as the sensor name alone:
  `RF Counter Motion turned on` becomes `Counter Motion`. Its explicit `rf_motion`
  category is based on the source entity ID, so removing the visible prefix cannot
  re-enable Chrome or phone deliveries. Sensor names/IDs, triggers and mute are unchanged.
- Routine light/switch state reports are suppressed on Vitaly iPhone Air;
  Chrome and existing destinations continue. The state-report
  automation passes `notification_category: light_switch_state`, so cover reports
  are not accidentally suppressed merely because their legacy title says Switch.
- **Ring Front Door** uses `binary_sensor.front_door_motion_2` (Ring MQTT), on a
  known `off` → `on` transition. Its dedicated phone automation preserves the
  existing 09:05–23:20 notification hours and global mute, then prepares the live
  stream before sending `camera.ring_camera_notifications`. Snapshot capture and
  browser delivery cannot block this phone alert. The legacy Ring snapshot message
  stays in Chrome, but is excluded from phone mirroring to prevent duplicates.
  Other eligible Chrome messages retain their phone copy.

`notify.alair` is an unrelated Kodi destination. Maria's phones are unchanged.
Existing motion filters, quiet periods, cooldowns and optional-provider error
handling still apply. Browser-specific action buttons and TV icons are not sent
to iOS. A failed phone delivery cannot stop the household action that follows it.

Dedicated phone camera alerts attach their approved camera entity. iOS receives
`data.entity_id` and `push.category: camera`. Existing outdoor alerts open
`/lovelace/2` on a tap; Living Room targets its camera with
`entityId:camera.living_room_onvif_notifications`.
Expanding the notification requests HA's authenticated MJPEG stream. Apple Watch
presentation and delivery depend on the paired phone's notification mirroring,
lock state and Focus settings; a successful server stream does not prove watch
playback. See the [Companion camera notification documentation](https://companion.home-assistant.io/docs/notifications/dynamic-content/).

Front live video was confirmed on the user's Apple Watch (automatic playback) and
iPhone (long-press the notification) on September 26, 2026. Garage has separately
shown upstream RTSP interruptions: a successful thumbnail or a few initial frames
does not prove continuous video. A person alert still depends on Frigate receiving
camera frames; opening its live attachment depends on the source staying available.

## Camera transport

The five existing outdoor notification cameras use the built-in **MJPEG IP Camera** integration:

- URL: `http://go2rtc-cameras.kerberos.svc.cluster.local:1984/api/stream.mjpeg?src=<name>_notifications`
- Names: Front / Garage / Porch / Backdoor / Ring Camera Notifications.
- The still-image URL uses the existing motion snapshot at
  `http://127.0.0.1:8123/local/<name>_camera_alert.jpg`, so delivering a thumbnail
  does not start a video encoder. Expanding the notification requests live video.
- No camera credentials are exposed in these URLs; the internal service is not
  published to the internet. HA provides the authenticated external proxy.
- Entries are created through the supported configuration flow and included in
  the native HA backup, not checked into Git as `.storage` files.

The matching go2rtc configuration is documented in
[the Kerberos Secret template](https://github.com/4alvit/k3s-self-healing/blob/main/docs/templates/kerberos-secrets.example.yaml).
MJPEG encoding runs on Oracle h7 at 640 pixels wide, approximately one frame per
second and one encoder/filter thread. All five encoders start on demand. Front/Backdoor
reuse their existing local producers; Garage/Porch read their Oracle relays;
Ring reads its existing Ring MQTT RTSP service. No additional direct Wi-Fi camera
connection or Synology transcoder is introduced. Viewing still consumes Oracle
outbound bandwidth.

### Ring cloud startup

Ring's on-demand cloud stream has taken 12–20 seconds to start; HA's MJPEG proxy
waits only 10 seconds for response headers. `shell_command.ring_notification_video_ready`
keeps its `housekeeping/ring_video_ready.py` compatibility entry point, which
runs the shared `housekeeping/notification_video_ready.py` helper to subscribe to the existing Oracle relay
before sending the push. Startup, including retries if the relay rejects its first
request while Ring is starting, is capped at 35 seconds. Once a complete JPEG
arrives, the command returns and a detached subscriber holds that same stream for
at most 30 more seconds, giving the phone/Watch time to attach. It closes only its
own connection; other viewers can continue. There is no permanent stream, no new
camera credential, and no extra direct Wi-Fi camera feed.

If preparation fails, the motion push still sends and says live video may be
unavailable. Muting notifications during preparation cancels the pending push.
Opening much later can encounter another cold start. Ring motion detection may
pause while live streaming, so the bounded subscriber is deliberately short;
see [Ring-MQTT video streaming](https://github.com/tsightler/ring-mqtt/wiki/Video-Streaming).

Generic cameras remain the dashboard's full-resolution RTSP/WebRTC sources.
Their original still-image options and full-resolution snapshots are retained.
A bare Generic RTSP source can provide a dashboard stream but produce an empty
MJPEG response for iOS; single-frame conversion also proved intermittent. The
dedicated notification streams preserve dashboard/snapshot quality and avoid
starting a conversion for every notification video frame. The relays use buffered
RTSP input, as documented in
[the infrastructure configuration](https://github.com/4alvit/k3s-self-healing/blob/main/docs/templates/kerberos-secrets.example.yaml).
Porch has also shown upstream camera connection timeouts and packet loss. Its
notification video can time out while the source is unavailable; this is separate
from successful delivery of the phone notification.

## Validation and rollback

The HA runtime suite and loopback stream tests check bounded stream startup/cleanup,
Living Room native state transitions, cooldown, reconnect suppression, global mute
(including during preparation), strict phone/camera routing and failure fallback,
Ring state transitions, quiet hours, snapshot independence, and suppression by source/snapshot, light/switch categories, Ring camera delivery,
separation from other browser targets, provider failures and continuation of
household actions. Probe `/api/camera_proxy_stream/<entity>` with an authenticated
client and verify multiple **distinct** JPEG frames, not just HTTP 200.
To roll back Ring phone delivery, revert the dedicated Ring automation, its
shell command/helper and the Ring browser-mirroring exclusion together. Reload
`shell_command`, idle scripts and automations; no HA restart is needed. Reverting
only the exclusion would create duplicate phone alerts. The existing five MJPEG
camera entries and full-resolution dashboard camera identities can remain.
