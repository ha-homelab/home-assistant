# Chrome and TV notification repair · 2026-09-22

The owner confirmed that `notify.mobile_app_als_iphone2` and `notify.pushbullet`
are retired, Chrome HTML5 push should work, and living-room TV motion messages
are still in use.

## Findings and changes

- Removed six active delivery actions for the two retired destinations across
  two automations and four scripts. Physical actions, delays, schedules and
  existing entity IDs remain unchanged.
- The HTML5 integration was configured and retained its old browser registrations,
  but callers used the absent legacy **service** `notify.chrome`. The current
  Chrome profile at the configured HTTPS origin also had notifications disabled.
  Enabled the subscription through HA's profile page and Chrome's permission
  prompt, registered it as `chrome`, and reloaded only the HTML5 integration.
- Chrome now has a notification **entity** `notify.chrome` and event entity
  `event.chrome`. Seven caller actions use `html5.send_message` with
  `entity_id: notify.chrome`, through the shared optional-delivery boundary.
  `notify.chrome` is an entity here, not an old-style callable service. HTML5's
  current action retains images, icons and custom click data without relying on
  deprecated legacy notification services.
- Notification pictures and click URLs now use same-origin paths (`/local/...`
  and `/api/camera_proxy_stream/...`) instead of hardcoded old-server URLs.
  Image/icon fields use the modern action's top-level schema; navigation URLs
  remain in `data.url`. Existing message text and camera selection are preserved.
- Living-room motion notifications already used the working service
  `notify.lg_webos_tv_oled77c5pua_dusqljr`. They remain intact. The one separate
  `script.tv_pic2` reference to the absent `notify.living_room_tv` service now
  uses that same registered LG destination. Its camera icon uses webOS's
  supported `data.icon` field instead of an ignored nested attachment mapping.
- The shared helper and Python registry query accept the exact additional action
  `html5.send_message`. Their validation still rejects unrelated service domains.
  Old browser registrations and credentials were not removed or rotated.

## Verification

The newly registered Chrome subscription accepted a real, non-sensitive test
notification and HA received its `received` browser callback. This verifies the
push service, browser subscription and return callback route; a service-call
success alone would not establish browser receipt.

The installed HA runtime passes 22 resilience scenarios, 16 motion-light scenarios
and 15 maintenance scenarios. The new cases validate the actual modern HTML5
service schema, current Chrome caller payloads/URLs, preserved physical sequences
and the registered LG service with its supported icon field. TV delivery is
validated against the confirmed existing destination; no unsolicited television
message is sent as a test.

The retired-service removal is limited to active configuration. Immutable import
baselines and dated audit evidence retain original source references for history.
The earlier list of four missing notification destinations is therefore resolved:
two were retired, Chrome was repaired, and the old TV reference was replaced with
the confirmed working destination. The separate missing-device inventory is unchanged.

Reference: [Home Assistant HTML5 push notifications](https://www.home-assistant.io/integrations/html5/).

## Installed release

Deployed root executable revision `293258b`, automations `b30a91d`, and scripts
`eb8aa2d` to the existing HA instance. Both staged and installed configuration
checks reported zero errors and zero warnings. All nine deployed file hashes and
all nine original rollback copies were verified. The backup is
`/config/.notification-repair-backup-temq1hc5`; the staged copy is
`/config/.notification-repair-stage-mcjm0wxy`.

Python-script, script and automation reloads passed fresh idle checks. Runtime
verification confirmed all 130 folder automations, three package automations,
54 folder scripts and 15 package scripts, with zero script additions and all
existing identities/enabled states preserved. No HA process restart was needed.
A scan of the active automation/script/package YAML found no retired destinations.

At **2026-09-22 17:28:14 UTC**, Chrome returned the `html5_notification.received`
callback for the final test routed through the installed `script.notify_optional`
and `html5.send_message`. The HA browser tab was closed before this test, so receipt
also verifies background push delivery. Only the newly registered Chrome profile
was targeted; existing browser registrations were preserved.

Rollback the nine YAML/Python files from the backup, validate, then reload Python
scripts, scripts and automations while idle. The newly enabled Chrome subscription
is independent browser/runtime state and can remain; no credentials were replaced.

## HTML5 event-entity migration

The final delivery diagnostic above temporarily subscribed to the legacy
`html5_notification.received` bus event. That diagnostic caused the repair warning
at **2026-09-22 17:28:14 UTC**; its WebSocket had already closed when the warning
was investigated, and the live event bus had no remaining `received` listeners.
Future delivery checks must observe `event.chrome` and match its `event_type` and
`tag` attributes instead of subscribing to any `html5_notification.*` bus event.

Three permanent notification-button automations still listened to the deprecated
`html5_notification.clicked` event. Their triggers now use `event.received` with
`options.event_type: [clicked]` and an exact match on
`trigger.to_state.attributes.action`. They retain the studio override on/off and
porch light actions, IDs, modes and enabled states. Targets cover all currently
registered browsers: `event.chrome`, `event.g011825` and `event.f011826`. Add any
future browser's event entity to these three target lists if its buttons should
control the same actions.

Three additional isolated HA runtime tests load these actual automation files.
They verify first/repeated clicks from all three browsers, ignore receipt/close
callbacks and unrelated buttons/entities, and prevent replay of old clicks on
attribute changes or recovery. All **56** runtime scenarios pass without skips
(25 resilience, 16 lighting and 15 maintenance). No live light/override action or
outgoing notification is needed for this regression check.

Deployed automation revision `0b36578` with root validation revision `d198fc4`.
Staged and installed configuration checks returned zero errors and warnings;
all three installed hashes and original backup hashes match. The backup is
`/config/.html5-events-backup-w4ezs3io`. After an idle-checked automation-only
reload, all existing identities/enabled states were retained and the live event
bus reported **zero** `html5_notification.*` listeners. HA did not restart.

HA retains this diagnostic repair even after its listener disconnects. Once the
zero-listener check passed, the one historical `received` warning was dismissed
through the normal Repairs API (`dismissed_version: 2026.9.1`); no other repair
was hidden, and no active HTML5 repair remained. This is a dismissal of the stale
diagnostic record, not deletion from HA's repair history.

To roll back, restore the three automation YAML files from that backup, validate
and reload automations while idle. This would reinstate deprecated listeners.

References: [event received trigger](https://www.home-assistant.io/triggers/event.received/)
and [event entities](https://www.home-assistant.io/integrations/event/).

## Retired browser subscriptions — 2026-10-03

The owner retired the unused `g011825` and `f011826` HTML5 registrations.
The active subscription is `h7_mac`, registered at the configured external HA origin,
with the stable entities `notify.chrome` and `event.chrome`. The separately
disabled `chrome_legacy_h2` entities remain disabled.

The three studio/porch notification-button automations now listen only to
`event.chrome`. Their IDs, click-action filters, device actions and enabled
states are unchanged. Existing runtime regression scenarios also verify that
callbacks from either retired browser cannot trigger a physical action.

The installed configuration was backed up, staged and checked with zero errors
and warnings. After a fresh idle check, only the three automation files were
promoted and automations were reloaded. Both registrations were then removed
through `DELETE /api/notify.html5`, the HTML5 integration was reloaded, and the
four retired notify/event entities were removed through the entity-registry API.
No runtime storage file was edited directly and Home Assistant did not restart.
All 117 existing automation identities and enabled states were preserved.

Only `h7_mac` remains in `html5_push_registrations.conf`; its subscription data
and keys were preserved byte-for-byte at the JSON-value level. A notification
sent directly to `notify.chrome` received the matching browser callback at
**2026-10-03 16:58:53 UTC**. The three button scenarios passed in the installed
Home Assistant 2026.9.1 runtime without real device I/O.

Private rollback data is retained in `/config/.html5-retirement-backup-xoy17xfq`.
If the retired browsers are needed again, register them from their HA profile
at the h7 HTTPS origin. To undo this retirement exactly, restore the three YAML
files from that backup, validate and reload automations while idle, then POST
each saved subscription/browser pair with its original `name` to
`/api/notify.html5` and reload only the HTML5 integration. Verify the restored
entity names through the normal registry API; do not overwrite live `.storage`
files with registry backups.
