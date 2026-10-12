# Tapo live camera URLs over MQTT

Home Assistant publishes a single UTF-8 URL on
`homelab/cameras/live/<camera_id>` whenever the corresponding ONVIF cell-motion
sensor changes from a known `off` to `on`. This is implemented by one automation
and one seven-camera mapping in
[`config/packages/tapo_desktop_mqtt.yaml`](../config/packages/tapo_desktop_mqtt.yaml).
No video or image bytes travel through MQTT.

The payload has this form (the domain below is an example):

```text
https://ha.example.invalid/api/camera_proxy_stream/<camera_entity>?token=<current-camera-token>
```

The origin is read from the local `home_assistant_external_url` secret.

Camera IDs and stream entities are:

- `c225` (Living Room): `camera.living_room_onvif_notifications`.
- `front`: `camera.front_camera_notifications`.
- `c225-2` (Dining Room): `camera.dining_room_camera_minorstream`.
- `kitchen`: `camera.kitchen_camera_minorstream`.
- `bedroom`: `camera.bedroom_camera_minorstream`.
- `studio`: `camera.studio_camera_minorstream`.
- `mishka`: `camera.mishka_camera_minorstream`.

Messages use QoS 0 and `retain: false`: they are immediate viewing opportunities,
not a replay queue. The consumer must use a clean MQTT session, discard retained
messages and allow only the seven topic/path pairs above. Person/vehicle sensors
do not publish additional events for the same motion. Startup, state attribute
changes and recovery from `unknown` or `unavailable` do not publish events.
Unavailable cameras or missing camera tokens suppress publication.

The token is HA's **camera-scoped access token**, read from the current camera
state at publication time; it is not the HA account token or camera password.
Treat complete payloads as private credentials: do not display or log them,
retain them, or copy them into Git. This automation stores no traces. A consumer
must subscribe to the authenticated HA MQTT broker and open the current URL,
not cache a URL from an earlier event.

## Video and consumer behavior

Publishing a URL does not open the stream. Desktop host API 1.9 and Kerberos
0.2.0 introduced the URL-topic consumer. Configure the seven token-free endpoints
above in **MQTT live camera endpoints** (`mqtt_live_endpoints`); the worker adds
the exact subscriptions to its existing MQTT connection. Its preview closes
after 15 seconds and uses a cooldown per camera, independent of token changes.
It does not emit a second OS notification. The HA change does not send phone
or browser alerts. Desktop 2.5.43-beta.2 with this configuration was verified
running and connected on September 27, 2026.

### Front uses the same ONVIF event path

Front uses `binary_sensor.front_tapo_cell_motion_detection` and
`homelab/cameras/live/front`, just like the other six Tapo cameras. Its video URL
uses `camera.front_camera_notifications`, which reuses the existing Oracle
relay. A direct native ONVIF video profile would add another camera connection
while the recorders are running; event consistency does not require that change.

To make this the only Front preview source, install desktop plugin builds with
per-camera exclusions and save these public settings:

- Frigate **excluded_cameras**: `["front"]`.
- Kerberos **excluded_legacy_cameras**: `["front_camera"]`.
- Keep Kerberos **mqtt_live_endpoints.front** set to the token-free Front
  endpoint above.

These are exact, case-sensitive identities. Frigate's live configuration names
the camera `front`; the Kerberos Hub topic `kerberos/hub/home-assistant` carries
`front_camera` in its event payload. The Hub topic suffix identifies the hub,
not the camera. Kerberos exclusions must apply only to Agent/Hub events, never
to the separate HA URL consumer. Do not disable an entire plugin or remove its
shared MQTT subscription to suppress one camera. Garage, Porch, Backdoor and
Tenants keep their existing desktop behavior. Recorder/detection services and
the HA publisher do not need to change for this cutover.

The HTTPS endpoint serves MJPEG directly. Front and Living Room reuse their
existing Oracle go2rtc/MJPEG cameras, including Living Room's independent phone
notification path. For Dining Room, Kitchen, Bedroom, Studio and Mishka:

- Enable only the native ONVIF `minorStream` camera entity and set
  `hidden_by: user`. Keep `mainStream` and camera controls disabled.
- Keep stream preloading off and do not place these entities on refreshing
  dashboard cards. A snapshot/preview request also counts as a video request.
- Set ONVIF Extra FFmpeg arguments to `-pred 1 -vf scale=-2:360 -r 2`, keeping
  existing PullPoint, TCP and timestamp settings. The direct MJPEG handler opens
  FFmpeg on request, scales to 360 pixels high at 2 fps, and closes it when the
  viewer disconnects. This output limit does not reduce the camera's encoded
  input bitrate.

Those five streams run in HA on Oracle h7 and need no additional relay or
Synology workload. They open a camera connection per active viewer; desktop
should keep at most one preview per camera. No new permanent stream or recorder
is created. Viewing still consumes home Wi-Fi and Oracle outbound traffic for
the duration of the preview. The 15-second limit belongs to the desktop consumer;
the HA endpoint itself remains open while its client keeps reading.

## Validation and recovery

The HA runtime test checks real state-trigger behavior, no startup/recovery or
person-event replay, current-token rotation, camera availability and MQTT service
payloads without real camera/notification I/O. HA `check_config` validates the
deployed package. Live checks on September 27, 2026 returned HTTP 200 and three
JPEG frames from each of the seven HTTPS URLs, with no redirect. First-three-frame
latency was 2.76–6.20 seconds including cold starts. Each direct ONVIF stream had
one RTSP connection during viewing and zero within three seconds of client
disconnect. Front and Living Room had no direct HA-to-camera RTSP connections;
they used their existing relays. No FFmpeg worker remained after these checks.
These are endpoint checks, not a claim that a desktop release already contains
the new consumer.

Native HA backups preserve the five entity enable/hidden flags and ONVIF options;
the YAML mapping is versioned here. On a clean install, restore the camera entries
and room entity IDs before enabling the publisher. For rollback, disable this
automation and the five minor-stream entities, restore their previous FFmpeg
arguments (`-pred 1`), and reload the affected ONVIF entries. Preserve Front and
Living Room's existing camera entries and phone notification settings. No full
HA restart or new backup schedule is required.
