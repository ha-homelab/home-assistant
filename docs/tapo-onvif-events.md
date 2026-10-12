# Tapo ONVIF events in Home Assistant

This configuration uses the seven Tapo cameras' own detection events without
requiring a continuous HA video consumer. Camera addresses, MAC identities and
room mappings stay in the private h3 and HA configuration; the
[reservation guide](tapo-dhcp-reservations.md) covers router recovery.

All seven ONVIF entries are configured and loaded. Five missing entries were
added, the existing C225 entry was configured for events only, and Front's
existing configuration was retained. This HA onboarding step did not restart HA
or reboot cameras. A two-minute passive check found no direct HA RTSP connections
to any of the seven cameras. Motion entities have now been discovered for all
seven cameras, including Bedroom person detection. The distinction between
entity discovery and observed transitions is recorded below.

## Camera names and entity IDs

The six renamed devices and 54 model-based entities were migrated through the
supported HA registry API on September 27, 2026. Existing event suffixes were
preserved. Actual device identities and their location-to-entity mappings are
kept in the private HA registry rather than a second inventory in Git. Use the
current registry when identifying or replacing a camera.

Device display names, ONVIF entry titles, internal names and entity labels now
agree. Registry unique identities, event enablement, disabled video/control flags,
credentials and addresses were preserved. All six renamed entries remained loaded.
HA 3D uses the same map for its motion/person bindings, including Bedroom person
detection, while retaining other room sensors and installation points. Native HA backups preserve
the registry; for a clean installation use the private h3 inventory and HA registry.

The dated fleet observations below predate this ID migration. The Living Room phone video path
is documented separately in [ONVIF phone video](onvif-phone-video.md). The later
[desktop MQTT URL publisher](tapo-desktop-mqtt.md) enables five hidden low-resolution
camera entities for viewing only on request; Front and Living Room reuse their relays.

## Entry and entity settings

Use the built-in ONVIF integration with each camera's reserved IP, port `2020`, and
its private local Camera Account. This is the camera account configured in Tapo,
not the TP-Link cloud login. Do not place its username or password in Git.

The fleet configuration uses these settings:

- `enable_webhooks: false`: use ONVIF PullPoint event subscriptions across the
  existing routed network. HA does not need an inbound callback from each camera.
- Keep discovered event sensors enabled. Set the entry preference
  `pref_disable_new_entities: false` so sensors first discovered from later event
  messages can be added automatically.
- For events only, disable both ONVIF video profiles. The desktop feature is an
  explicit exception: enable and hide only `minorStream` for Dining Room, Kitchen,
  Bedroom, Studio and Mishka, following [its settings](tapo-desktop-mqtt.md).
  Front and Living Room retain both native video profiles disabled. Merely
  turning off stream preloading does not rule out traffic from preview requests.
- Disable ONVIF reboot and clock-setting buttons and imaging-control entities;
  this setup needs event sensors only. After firmware or integration updates,
  review any newly discovered non-event entities and keep them disabled.
- RTSP transport can remain TCP with the existing video options. These options do
  not cause a stream to open while the camera entities are disabled.

An event sensor may remain `unknown` until its first usable camera message.
Missing event variants can appear later when the camera emits them for the first
time. No notification or household automation should be inferred from entity
creation; those are separate configuration steps.

## Advertised capabilities

On September 26, 2026, read-only `GetDeviceInformation`, `GetProfiles`, and
`GetEventProperties` calls authenticated against all seven cameras. No stream URI
was requested and no video stream was opened by this probe.

All seven advertise these topics:

- `RuleEngine/CellMotionDetector/Motion`
- `RuleEngine/PeopleDetector/People`
- `RuleEngine/TamperDetector/Tamper`
- `RuleEngine/LineCrossDetector/LineCross`
- `RuleEngine/TPSmartEventDetector/TPSmartEvent`

The four C201 cameras additionally advertise
`RuleEngine/IntrusionDetector/Intrusion`. The C225 and C120 responses do not include
that topic. These responses describe available event types, not whether every
detection feature is enabled or whether HA can translate every proprietary event.
In particular, person recognition must be validated with actual state transitions
on each camera where it will drive an automation.

Profiles were read as metadata only: C120 advertises H.264 at 2560×1440 and
640×360; C225 at 2688×1520 and 1280×720; C201 at 1920×1080 and 1280×720. Every model
also advertises a 640×360 JPEG profile. Their presence does not mean HA consumes
any of those streams.

## Verification and operating limits

At `2026-09-27T00:41:00Z`, the final diagnostics check showed all seven entries loaded, all seven
PullPoint managers started, and all webhook managers stopped. All 14 ONVIF camera
entities and all discovered controls were disabled by the user; every entry
allowed later event-entity discovery.

During passive observation from `2026-09-27T00:37:58.360576Z` to
`2026-09-27T00:39:58.520223Z`:

- Both C225 cameras and one C201 delivered
  real motion and person `off` → `on` → `off` transitions.
- Front C120 continued to deliver motion and vehicle transitions. Its person
  detection did not activate in this window; person activation and clearing were
  already observed in the earlier Front pilot.
- The other three C201 cameras produced
  no event sensors during this initial window. Their HA integrations and PullPoint
  subscriptions were healthy; event discovery happened later as described below.
- Across 116 samples of HA's IPv4 and IPv6 TCP tables, there were zero established
  direct RTSP connections to any of the seven camera addresses on port `554`,
  including during the observed events.

By the camera-name verification at `2026-09-27T01:15:08.668951Z`, motion entities
had appeared for all four C201 cameras. Kitchen, Studio, and Mishka also had
person-detection entities; Bedroom had only motion. This supersedes the initial
observation's missing-sensor result, but does not by itself prove activation and
clearing for every newly discovered sensor. All seven ONVIF entries remained
loaded and their 14 video entities remained disabled.

Read-only analytics queries found the same motion rule, active-cell configuration,
and sensitivity of `60` on all four C201 cameras. ONVIF did not expose a detector
enabled flag in those responses. For the outstanding Bedroom person test, walk
through its configured detection area and check for person activation and clearing
in HA. If a real walk produces no person events, check person-detection enablement,
detection areas, and schedules in Tapo before investigating the ONVIF event path
further. Missing events alone do not establish that detection is disabled.

These checks validate received events and sampled network connections, not
detection accuracy, visual identity of a moving subject, or camera-to-HA latency.
A finite sample cannot exclude a connection between samples or after a future
configuration change. Recheck entity settings and direct RTSP connections after
enabling entities or adding dashboard cards; keep event validation separate from
topic advertisements or an initial `off` state.

Front's existing Frigate, Kerberos, and Oracle go2rtc video consumers remain in
place. Event-only ONVIF onboarding does not stop those consumers or eliminate
their existing Wi-Fi traffic. Living Room has a separate bounded, event-triggered
phone video path. The later desktop feature adds viewing on request as described
above; the dated onboarding observations remain a record of the events-only setup.

## Restore and rollback

The supported ONVIF configuration flow stores entries and their credentials in
private HA configuration; the entity registry stores disabled entities. Normal
native HA backups include these settings. Continue the existing backup schedule;
no additional recurring backup is required for ONVIF onboarding.

After restoring a native HA backup, confirm the router reservations, loaded ONVIF
entries, event sensors, and disabled video/control entities. For a clean HA setup,
add each missing ONVIF entry through Devices & services using its reserved IP,
port `2020`, and the private Camera Account; apply the settings above and repeat
the event and connection checks. Reuse an existing entry instead of creating a
duplicate for the same camera.

For rollback, remove only newly added ONVIF entries and restore any changed
settings on previously existing entries from the recorded pre-change state or a
native backup. Do not remove DHCP reservations or unrelated Generic/MJPEG camera
entries, and do not change the existing Frigate, Kerberos, or go2rtc sources.
