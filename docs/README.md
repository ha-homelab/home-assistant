# Home Assistant configuration — documentation index

This index covers the public configuration in this repository: the managed Home
Assistant package, device migrations, dashboards, notification and recorder
tooling, and the dated deployment records behind them. Start with the visual
[process and evidence guide](process-and-evidence.md) if you want the boundaries
before the details.

## Get started

- [Public source and private runtime](public-source.md): what is published here
  versus what stays on the live installation.
- [Process and evidence](process-and-evidence.md): the illustrated workflow from
  configuration to deployment and its verification limits.
- [Architecture: configuration ownership](architecture.md): the k3s-hosted
  container, its persistent storage and who owns each file.
- [Deployment and rollback](deployment.md): installing the configuration and
  restoring the previous revision.
- [Installation device bindings](site-device-bindings.md): replacing the
  nonfunctional example IDs with your own.

## Configure devices and rooms

- [Air Purifier Living and Switch07](air-purifier-living.md) and
  [Bath2 legacy outlet cleanup](bath2-legacy-outlet-cleanup.md).
- [Bath 2 light](bath-2-light.md), [Bathroom warmer](bathroom-warmer-esphome.md)
  and [Bedroom guard](bedroom-guard-esphome.md).
- [Bedroom lamp motion and shutdown](bedroom-matter-lamp.md) and
  [Living lamp migration](living-lamp-esphome.md).
- [Kitchen ESPHome outlets](kitchen-esphome-outlets.md), [Kitchen lamp](kitchen-lamp.md)
  and [Mishka and Kitchen curtain power](mishka-kitchen-esphome.md).
- [Dining Arc lamp](dining-arc-lamp.md), [Dining guard consolidation](dining-guard-esphome.md)
  and [Dining Media guard](dining-media-guard.md).
- [Fireplace two outlet retirement](fireplace-two-retirement.md) and
  [MPPT fan](mppt-fan.md).
- [Garage lighting](garage-lighting.md), [Garage power outlets](garage-power-outlets.md)
  and [Garage button binding](garage-button-binding.md).
- [Studio guard migration](studio-guard-esphome.md),
  [Studio curtains on ZHA](studio-curtains-zha.md) and
  [Living-room RF curtains](living-curtains-rf.md).
- [Switch06 ESPHome maintenance](s6-esphome-maintenance.md),
  [Switch08 and Switch09](switch08-switch09.md),
  [Switch10](switch10.md), [Switch11](switch11.md), [Switch12](switch12.md),
  [Switch15](switch15.md), [Switch16](switch16.md), [Switch20](switch20.md) and
  [Switch21](switch21.md).
- [KMC Switch17–Switch19](kmc-switch17-19.md) and
  [KMC and Supernight outlet roles](outlet-role-reassignment.md).
- [Ping outlets](ping-outlets.md): network-reachability switches added in October.
- [RF Airbridge](rf-airbridge.md): MQTT reception, RCSwitch transmission and
  Dooya curtain control.
- [Bluetooth lighting](bluetooth-lighting.md): the CC1101 RF node and the
  living-room chandelier.

## Lighting, presence and dashboards

- [Living-room presence lighting](living-room-presence.md).
- [Motion-light timeout recovery](motion-light-recovery.md) and
  [Room Sticky](motion-light-sticky.md): pausing automatic lighting and curtains.
- [Lovelace input contrast](lovelace-input-contrast.md): readable dark-theme inputs.
- [Phones, Media and Cerbo GX](phones-and-cerbo-dashboards.md): the endpoint
  inventory dashboards.
- [Radio and speaker console](radio-console.md): the compact station selector card.
- [Vacuum maps](vacuum-maps.md): the interactive Roborock map view.

## Energy, batteries and water

- [Victron Off-grid mode](victron-black-start.md): the persistent island-mode
  operator choice and battery shutdown behavior.
- [Victron MQTT keepalive](victron-mqtt-keepalive.md): telemetry refresh automation.
- [Self-consumption device actions](self-consumption-device-actions.md).
- [BatteryLife SoC limit](mqtt-number-diagnosis.md) and
  [JBD MQTT availability](jbd-mqtt-availability.md).
- [Water pump level thresholds](water-pump-levels.md).

## Media, voice and displays

- [Echo Dot music from Plex](echo-plex-music.md) and
  [Homeway voice](homeway-voice.md) for Echo devices.
- [EPG voice playback](epg-voice.md) and [OTT d1 navigation with RM433](ott-d1-rm433.md).
- [Matter voice exposure](matter-voice-exposure.md): what the Matter bridge exports.
- [LG remote volume safety](lg-remote-volume-safety.md) and
  [LG TV Wake-on-LAN](lg-tv-wake-on-lan.md).
- [Entity display names](entity-display-names.md): device labels and the local
  Kodi remote.

## Cameras and notifications

- [Tapo ONVIF events](tapo-onvif-events.md), the [front Tapo pilot](tapo-onvif-events-pilot.md)
  and [Tapo live URLs over MQTT](tapo-desktop-mqtt.md).
- [Tapo DHCP reservations](tapo-dhcp-reservations.md).
- [Camera dashboard recovery](camera-dashboard-recovery.md),
  [Camera snapshot recovery](camera-snapshot-recovery.md) and
  [Living Room ONVIF video notifications](onvif-phone-video.md).
- [Cisco motion notifications](cisco-motion-notifications.md) and
  [iPhone notifications](iphone-camera-notifications.md).
- [Chrome notification coverage](chrome-notification-coverage.md) and
  [Chrome and TV notification repair](notification-repair.md).
- [Notification frame cache](notification-frame-cache.md): the portable
  frame-validation library.
- [SmartThings cooktop notifications](cooktop-notifications.md) and
  [RuView notifications in OTTPlayer](ruview-ott-notifications.md).
- [Home Feed Card compatibility](home-feed-card-hotfix.md) and
  [Vehicle Info Card hotfixes](vehicle-info-card-hotfix.md).

## Operate and maintain

- [ESPHome build isolation](esphome-build-isolation.md): separate outlet build
  directories, pinned-builder boundaries and explicit firmware selection.
- [Approving Core updates](core-updates.md) and
  [Core in the native Updates screen](core-native-updates.md).
- [Automatic HACS maintenance](hacs-maintenance.md).
- [Recorder retention policy](recorder-retention.md),
  [Recorder storage budget](recorder-storage-budget.md),
  [Recorder HeatWave and local storage](recorder-heatwave-local.md) and
  [Recorder quality verification](recorder-quality-verification.md).
- [Roomba controls, maps and telemetry](roomba-experience.md),
  [Roomba Insights](roomba-insights.md) and
  [Roomba connection recovery](roomba-network-recovery.md).
- [Local Samsung appliances](local-samsung-appliances.md) and
  [Email in Home Assistant](mail.md).
- [Automation and script resilience](runtime-resilience.md) and
  [display templates during startup](template-startup-resilience.md).
- [Authoring automations: live debugging first, GitHub second](automation-authoring-workflow.md):
  the YAML-mode edit loop, the migration inventory gate, the pull request and the
  reviewed deployment that follows.
- [LocalTuya cover hotfix](localtuya-cover-hotfix.md) and
  [managed go2rtc startup recovery](go2rtc-startup-recovery.md).

## Reference

- [Missing entity references: runtime classification](missing-reference-runtime.md)
  and [Retired entities](retired-entities.md).
- [Site device bindings](site-device-bindings.md) list the example entity and
  device IDs that must be replaced.
- Machine-readable contracts live beside this index: `reference-contract.json`,
  `runtime-dependencies.json`, `recorder-quality-policy.json` and
  `matter-household-exposure.json`.
- Lovelace views from this repository are under `dashboards/`; their YAML is
  reference material rather than a runbook.

## Development and release

- [Portable library releases and acceptance](release-packaging.md): the
  notification frame-cache wheel and its beta/RC deliverable.

## Evidence and dated records

- [Initial managed-configuration release — 2026-09-15](releases/2026-09-15.md) and
  [HACS maintenance deployment](releases/2026-09-15-hacs-maintenance.md).
- [Motion-light recovery deployment — 2026-09-22](releases/2026-09-22-motion-light-recovery.md),
  [SoC limit correction](releases/2026-09-22-mqtt-soc-limit.md) and
  [runtime resilience deployment](releases/2026-09-22-runtime-resilience.md).
- [Runtime reliability audit — 2026-09-28](releases/2026-09-28-reliability.md) and
  [battery cell numbering](releases/2026-10-01-battery-cell-numbering.md).
- [Curtain commissioning — 24 September 2026](curtain-live-verification-2026-09-24.md) and
  [Living-room morning power repair](living-curtain-morning-power.md).
- [Porch lamp migration — 2026-11-22](porch-lamp-migration-2026-11-22.md): the
  backdoor-lamp entity rename, the Porch Light helper member removal and the
  voice-alias cleanup, with the references still open in source.

Shared repository policy (`release-workflow.md`, `quality.md`, `fuzzing.md`,
`rc-fuzzing.md`, `runner-preflight.md`, `release-read-safety.md`,
`VERSIONING.md`) is repeated from the shared release toolkit and is summarized
rather than repeated here.

Dated records keep their original versions and measurements. They are evidence
for that deployment, not a live status report of the current installation.
