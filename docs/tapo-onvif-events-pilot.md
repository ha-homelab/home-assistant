# Front Tapo ONVIF event pilot

The pilot used a TP-Link Tapo C120 with firmware
`1.9.3 Build 260521 Rel.66417n`. The September 26, 2026 pilot adds native camera
events to Home Assistant without creating another video consumer.

The existing Frigate and Kerberos processing is intentionally retained for this
camera. Frigate still reads `/stream1` for recording and `/stream2` for detection;
Kerberos and HA's existing camera entities still share the Oracle go2rtc relay.
The pilot therefore does **not** eliminate Front's existing Wi-Fi video traffic.
It tests whether the same camera can independently provide useful event sensors.

## Home Assistant configuration

The built-in ONVIF integration was added through its supported configuration
flow with the name **Front Tapo**, port **2020**, and the camera's existing local
Camera Account. Credentials remain in private HA configuration and native
backups; they are not repository configuration.

Options:

- `enable_webhooks: false`: use ONVIF PullPoint subscriptions across the existing
  routed network, without requiring the camera to reach an HA webhook.
- RTSP transport: TCP; extra FFmpeg arguments: `-pred 1`; wallclock timestamps off.
  These video options are inert while the ONVIF camera entities are disabled.
- Both `camera.front_tapo_mainstream` and `camera.front_tapo_minorstream` are
  explicitly disabled in the entity registry. This also prevents a dashboard
  thumbnail from opening a direct RTSP connection through this integration.
- The new reboot, clock-setting and imaging-control entities are disabled.
- Event sensors remain enabled. New event entities may appear when the camera
  first publishes their topic, so automatic addition of new entities is allowed.

The currently discovered sensors are:

- `binary_sensor.front_tapo_cell_motion_detection`
- `binary_sensor.front_tapo_person_detection`
- `binary_sensor.front_tapo_vehicle_detection`

The camera advertises motion, tamper, line crossing, people and TP-Link smart-event
topics. An advertised topic alone is not proof that the configured camera will
emit it, or that HA will expose every variant as a sensor. In particular, an event
sensor can remain `unknown` until its first usable message after setup/reload.

No notification, recording, lighting or other automation is attached to these new
sensors. Existing Front notification suppression and dashboard video entities are
unchanged. HA itself was not restarted; only the new ONVIF entry was reloaded.

## Verification and next cameras

The subsequent [fleet rollout](tapo-onvif-events.md) records the configuration
and verification status of all seven Tapo cameras.

The direct ONVIF probe authenticated successfully and read device information,
media profiles and advertised event topics without requesting video. The camera
provides H.264 profiles at 2560×1440 and 640×360, plus a JPEG profile.

The integration loaded successfully. Real camera events were observed on
September 26, 2026 (America/Los_Angeles): motion became active at 17:05:50 and
cleared at 17:06:40; person detection was active at 17:05:52 and cleared at 17:05:57;
vehicle detection activated at 17:06:23 and cleared at 17:06:25. The vehicle entity
was discovered automatically from that event. These validate event transport and
state updates, not detection accuracy or latency against a visual ground truth.

During a 60-second observation covering active events, sampling HA's IPv4 and IPv6
TCP connection tables found zero established direct RTSP connections to Front on
port 554. Both ONVIF camera entities remained explicitly disabled. Existing
Frigate/Kerberos video consumption and Front notification suppression were retained.

Before adding another camera, confirm its stable reservation in the
[Tapo DHCP inventory and migration guide](tapo-dhcp-reservations.md). That guide
covers the seven discovered cameras; address reservation does not add them to HA.

For another Tapo camera, first enable its local Camera Account, add ONVIF, disable
its ONVIF video entities, and verify actual motion/person state transitions. Watch
for new direct RTSP connections from HA while idle and during events. A separate
on-demand video route can then reuse the Oracle relay; do not infer that adding
ONVIF stops other recorders or detectors from reading the camera continuously.

For rollback, remove only the **Front Tapo** ONVIF entry through Devices & services.
Do not remove the existing Generic/MJPEG camera entries or change the Frigate,
Kerberos or go2rtc source configuration. The entry and registry settings are
included in normal native HA backups; no extra backup schedule was introduced.

References: [HA ONVIF integration](https://www.home-assistant.io/integrations/onvif/),
[TP-Link local camera access](https://www.tp-link.com/us/support/faq/2680/).
