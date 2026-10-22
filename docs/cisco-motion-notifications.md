# Motion snapshots on Cisco phones

The optional Cisco branch sends one image from the same notification-camera
entity used by the existing iPhone/Watch alert. The Cisco helper opens the
authenticated HA MJPEG endpoint, accepts its first complete JPEG, and closes
that connection. This is the first frame available to this new subscriber;
it is not a recording of the exact instant motion began or necessarily the
identical frame the iPhone displayed.

The existing mobile notification is sent first. A subsequent internal
`cisco_motion_snapshot_requested` event starts a separate automation without
waiting for its camera or phone work. The receiver admits at most four parallel
events and drops overflow. It does not queue old camera images. Cisco errors
cannot retract or delay the preceding mobile delivery.

## Install

First deploy a Cisco gateway revision that supports the guarded `motion_image`
action and the image API's `idle_close_seconds` field, then install or update
the helper below. Older gateways ignore the idle-close field: updating only
the helper will leave snapshot pages open. Do not substitute the generic image
action when a gateway lacks guarded motion delivery. Use the matching gateway
and helper described in the
[Cisco motion-notification guide](https://github.com/4alvit/cisco-home-telephony/blob/main/docs/motion-notifications.md).

1. Install the reviewed `scripts/cisco_motion_snapshot.py` from
   [cisco-home-telephony](https://github.com/4alvit/cisco-home-telephony) as
   `/config/housekeeping/cisco_motion_snapshot.py` in Home Assistant. Keep its
   source revision and checksum with the deployment record. The helper is
   separately maintained; the portable notification-frame-cache wheel does
   not contain it.
2. Create `/config/.storage/cisco_motion/` with mode `0700`. Store its JSON
   configuration and token files with mode `0600`, readable by the HA process.
   Do not put these files or camera images in `/config/www`, Git, or public
   release assets. `.storage/` is ignored by this repository.
3. Map the approved keys `garage`, `porch`, `ring`, and `living_room_onvif` to
   their existing HA notification-camera entities in the private JSON. Include
   only the sources and destination extensions you want to enable. Use the
   helper's example configuration and validation from the same reviewed Cisco
   revision. An empty destination list sends nothing.
4. Deploy `config/packages/cisco_motion_notifications.yaml` plus the appended
   dispatch actions in `camera_person_notifications.yaml` and
   `onvif_video_notifications.yaml` through the normal configuration workflow.
   Preserve locally mapped entity IDs and the existing notification policy.
5. Check HA configuration, reload `shell_command`, then reload automations. A
   restart of Asterisk or the phone firmware is not required. Confirm the
   receiver automation and shell-command service are registered before testing.

Example private configuration, using placeholder endpoints and one destination:

```json
{
  "version": 1,
  "gateway": {
    "base_url": "http://gateway.example.invalid:8080",
    "token_file": "gateway-token.txt"
  },
  "home_assistant": {
    "base_url": "http://127.0.0.1:8123",
    "token_file": "ha-token.txt"
  },
  "cameras": {
    "garage": {
      "entity_id": "camera.example_notifications",
      "label": "Driveway motion"
    }
  },
  "destinations": ["201"],
  "state_directory": "/config/.storage/cisco_motion/state",
  "cooldown_seconds": 60,
  "max_event_age_seconds": 90
}
```

To include every configured physical phone, use `"destinations": ["*"]`.
This retains powered-off phones in the configured scope, but only phones that
are online and eligible at delivery time can receive the image. A reconnected
phone is considered on the next new event; reconnecting does not replay missed
events or old images. An explicit extension list instead limits that scope.

The private HA credential needs access to the approved camera stream; the
gateway credential needs the existing phone/image API. Token filenames are
resolved relative to the configuration. Do not send HA credentials or original
camera URLs to the Cisco handset. The helper uses the gateway's guarded
`motion_image` action and selects idle, registered phones. A configured voice
profile does not by itself exclude a phone: the gateway must confirm that
hands-free is disabled and any finite voice session is quiescent before
allowing motion delivery. Enabled hands-free, an active voice session or an
unknown state still prevents delivery; an idle gap between assistant sessions
does not establish eligibility. The helper does not answer, hang up, or
interrupt a voice-assistant session to show an image.

## Event contract

The existing automations dispatch this shape after their mobile action:

```yaml
event: cisco_motion_snapshot_requested
event_data:
  camera_key: garage
  event_id: "{{ trigger.to_state.context.id ~ '_garage' }}"
  event_at: "{{ as_timestamp(trigger.to_state.last_changed, 0) | int(0) }}"
continue_on_error: true
```

The receiver automation rechecks `input_boolean.notifications_off`. It accepts only
the four approved source keys, an 8–96-character identifier containing letters,
digits, underscores or hyphens, and whole Unix seconds. Events older than
90 seconds or more than five seconds in the future are dropped. The helper
independently validates and deduplicates events, applies its configured age and
per-phone cooldown limits, and enforces a 50-second watchdog with up to two
additional seconds for child cleanup, within HA's 60-second shell-command limit.
The shell command is foreground work inside the separate HA automation; it
does not leave a detached camera subscriber running.

Each snapshot requests `idle_close_seconds: 45` through the gateway. This uses
the phone's native idle-close action, not a fixed 45-second wall-clock expiry;
interaction with the phone can delay or cancel that action. The minimum
per-phone cooldown is 60 seconds. Events arriving during that cooldown are
dropped, not queued for display when it ends.

Use the original trigger time rather than `now()` at delivery time, so the
existing bounded Ring/ONVIF preparation cannot turn a stale event into a fresh
one. Each camera suffix keeps source events distinct. The event ID correlates
the automation dispatch; it does not establish the camera sensor's exposure
time.

The earlier notification-readiness helper and the private ONVIF frame cache
remain separate. This branch makes one short-lived HA subscriber and may share
the relay's existing producer. It does not claim zero extra stream traffic or
reuse a stale motion-thumbnail file.

## Verify and troubleshoot

- First run the Cisco helper's `--dry-run` with the private configuration and a
  fresh event identifier/time. Check its selected destinations before allowing
  a controlled image test. A successful HTTP request alone does not establish
  that a person saw the phone screen.
- If the mobile alert arrives but no Cisco image appears, inspect the
  `Cisco: show a motion snapshot` automation trace and bounded helper result. Check global
  mute, event age, destination selection, registration, an active call or voice
  session, cooldown, and availability of the approved notification camera.
- A static image page already open before the upgrade has no retroactive idle
  timer. Press **Exit** once to close that old page, then test a fresh event.
  New snapshot pages request the native idle-close action described above.
- Missing configuration, an unavailable helper, a failed camera, or a busy
  phone must leave the existing mobile notification intact. Never fall back to
  an unapproved camera, old cached image, or force-ending a call.
- More than four simultaneous events are intentionally dropped rather than
  replayed. Repeated or stale identifiers do not request automatic retries.

To disable only Cisco delivery, set the private destination list to empty.
For rollback, remove the three appended event actions and the
`cisco_motion_notifications` package, then reload automations and
`shell_command`. Keep the original mobile actions, Ring/ONVIF preparation,
camera entries and relay configuration in place. Remove the separate helper
and private state only after any admitted bounded runs have ended.

The isolated tests validate HA automation registration, event routing, mobile-first
ordering, nonblocking dispatch, concurrency overflow, mute/staleness handling
and safe shell arguments. They perform no real camera, phone or mobile I/O.
