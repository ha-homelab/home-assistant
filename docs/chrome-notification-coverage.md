# Chrome coverage for household notifications · 2026-09-22

The owner requested that the repaired Chrome destination receive the other
existing household notifications, including general motion sensors.

`script.notify_optional` now accepts an explicit `also_chrome: true` flag on one
delivery per notification flow. It preserves the original recipient and payload,
then attempts a Chrome copy independently through `html5.send_message`. Missing
or failing providers do not prevent the other delivery or later household actions.
The default remains false; existing HTML5 deliveries are never copied again.

The copy includes title/message and a same-origin navigation URL. An optional
`chrome_image` supplies the image, icon and click URL for camera snapshots.
Provider-specific fields such as Kodi display duration, Alexa target lists and
webOS filesystem paths are not forwarded to the browser.

## Enabled coverage

- Thirteen notification automations now opt in once: camera MQTT notifications
  for backdoor, backyard, front, garage and porch; general RF motion sensors;
  access-point connectivity; switch states; covers opening/closing; both pump
  protection thresholds; and the five-minute irrigation timeout.
- The shared `script.notify` and `script.notifymax` now copy their messages once.
  This also covers their 24 automation callers for energy loads, heating,
  Victron/solar operation and water-level pump control: **37 automation paths**
  gain Chrome coverage in total.
- The manual TV front-camera snapshot script also sends Chrome a browser image.
- Existing direct browser delivery for camera scripts, Ring and mailbox remains.
  The generic motion rule excludes the mailbox from its Chrome copy because its
  dedicated browser rule already handles it. Ring retains its existing dedicated
  browser schedule and notification guard. Porch RF announcements are covered by
  the general motion rule, without another copy from Alexa's announcement rule.

Original triggers, conditions, schedules, enabled states and device actions remain
unchanged. This expands the desktop/TV household notification stream; retained
MQTT diagnostics, TV confirmation dialogs and HA-only maintenance records remain
in their existing destinations. It does not introduce a global event-bus listener
that copies arbitrary services or HTML5 events.

## Verification

All **63** isolated HA 2026.9.1 scenarios pass without skips: 32 notification and
runtime resilience cases, 16 lighting cases and 15 maintenance cases. New checks
execute the actual 13 automation action sequences and common notification scripts,
validate rich image payloads against HA's HTML5 schema, check original/Chrome
provider failures, preserve remaining physical actions, and verify motion mute and
mailbox duplicate prevention through the automation engine. Full package merging
and script-service registration are tested with the new copy flag as well.

Real device and notification providers are mocked in these regression tests.

## Installed release

Deployed root executable revision `511e040`, automation revision `ff500b8` and
script revision `55b2e3e`. Staged and installed HA configuration checks returned
zero errors and warnings. All 17 installed file hashes and their original rollback
copies were verified. The backup is `/config/.chrome-coverage-backup-jvpcmrwf`.

Scripts and automations were reloaded after fresh idle checks. Runtime verification
confirmed all 130 folder automations, three package automations, 54 folder scripts
and 15 package scripts, with identities and automation enabled states preserved.
There are still no deprecated HTML5 event-bus listeners. HA was not restarted.

To roll back, restore the 17 files listed in the backup's receipt, validate the
configuration, and reload scripts and automations while idle. Browser registration
and previously working direct Chrome delivery are independent of this expansion.
