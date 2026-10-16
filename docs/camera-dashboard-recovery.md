# Camera dashboard recovery — 2026-09-24

The Cameras view (`/lovelace/2`) uses the existing Generic Camera entities for
Garage, Backdoor, Front, Porch and Ring. Each camera opens through Home
Assistant's authenticated video path. The four IP cameras share their original
Oracle ingress with their Kerberos Agent; opening HA does not open another
connection over home Wi-Fi. Frigate's Synology configuration is unchanged.

## Sources and retained identities

- `camera.front_camera`: `go2rtc-cameras.kerberos.svc.cluster.local:8556/front`
- `camera.backdoor_camera`: `go2rtc-cameras.kerberos.svc.cluster.local:8556/backdoor`
- `camera.garage_camera`: `go2rtc-garage.kerberos.svc.cluster.local:8556/garage`
- `camera.porch_camera`: `go2rtc-porch.kerberos.svc.cluster.local:8556/porch?video=h264`
- `camera.03cabcc9_ring_mqtt`: `ring-mqtt.homeassistant.svc.cluster.local:8554/54e019cac69d_live`

All use RTSP over TCP. The Ring migration replaces an obsolete Docker DNS name;
its existing authentication is retained privately. Camera credentials and HA
configuration entries remain outside Git. Source changes use the Generic Camera
options flow, including its validation/confirmation step; no live `.storage`
editing or HA restart is needed. Existing camera entity IDs and automation
callers are preserved. Friendly names now identify the camera instead of an old
IP address.

The deployment operator maintains the Kubernetes manifests and Secret examples.
All three go2rtc Deployments select Oracle node h7; they are not public services.
Front, Garage and Backdoor use native RTSP without video encoding. Porch retains
its FFmpeg copy/remux because the camera's SDP is invalid for the native Agent
client. Agents read the same internal streams as HA. Recreate rollouts release
the original direct camera session before starting its replacement. Frigate
retains its existing local camera inputs; it does not pull video back from Oracle.

## Dashboard configuration

Storage-mode dashboard configuration is backed up privately, not committed as
`.storage`. The camera and Frigate archive views were updated through the
Lovelace WebSocket API, preserving the other four views and checking for
concurrent changes before saving.

The installed Advanced Camera Card 8.1.0 (shown as Iris in the UI) uses
`custom:advanced-camera-card`. Each of the four IP camera cards has the retained
Generic `camera_entity`, `live_provider: ha`, `engine: frigate`, and an explicit
`frigate.client_id: frigate` plus the matching `camera_name`. Thus live video uses
the Oracle relay and existing Frigate recordings remain available from the same
card. Ring uses `engine: generic`.

- Five working live cards replace broken/duplicate Porch, disabled Lux Pro and
  unavailable legacy camera cards. The unrelated camera integrations remain
  installed where ownership or other usage is not established.
- The four person images reference the current Frigate integration's `_2`
  entities. All twenty saved motion-history images are retained.
- The separate Frigate view contains four archive galleries, using
  `view.default: gallery` and `media: {type: events, events_type: clips}`. The
  obsolete duplicate Foscam archive is removed.
- The old `frigate-hass-card.js` resource is removed after migrating every card
  that used it. The current resource is retained; no package update is required.
- `live.preload: false`, `lazy_load: true`, `lazy_unload: [hidden, unselected]`,
  and matching `auto_pause` stop background loading when the card becomes hidden.
  Archive `media_viewer.auto_play: []` requires the viewer to start a clip.
  Video viewed by a browser still consumes Oracle outbound traffic; internal
  sharing does not eliminate that necessary viewer traffic.

The unreferenced `camera.ring` Generic entry was the abandoned
`192.168.160.1:3000/public/stream.m3u8` bridge and is removed. Working Ring MQTT,
cloud integration and snapshot history are retained. The old `camera.in_camera`
MJPEG entry is still referenced by the separate legacy `camera.combined` YAML
platform, so it is not deleted as part of this dashboard change.

## Verification and rollback

All four Agents remained connected with increasing `packagesProcessed`, fresh
`lastPacketAt` and the original live resolutions: Front 2560x1440, Porch
1920x1080, Garage and Backdoor 1280x720. Each relay reported exactly one connected
camera producer with both Agent and HA consumers. Chrome decoded all five live
videos, including Ring at 1920x1080, with advancing playback clocks. The archive
galleries loaded the existing clips without configuration/legacy-resource errors.
HA was not restarted. The Kubernetes local CI and source security checks passed.

Restore a dashboard view/resource through the supported Lovelace API from the
private backup, preserving subsequent changes to other views. Camera source
rollback uses each Generic Camera options flow. Agent source rollback removes
only the three explicit RTSP environment overrides, restoring the retained
original Secret values. Relay Secret backups retain the previous configurations.
Do not route HA or Kerberos through Synology to roll back this repair.

## Front native-event pilot

The [Front Tapo ONVIF pilot](tapo-onvif-events-pilot.md) adds camera-generated
motion/person sensors with both new ONVIF video entities disabled. The existing
Front dashboard camera, Frigate inputs and Kerberos relay consumers remain as
configured above.
