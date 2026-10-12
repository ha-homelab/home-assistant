# SmartThings cooktop notifications

The Samsung Range already exposes `custom.cooktopOperatingState` through the
official SmartThings integration. `binary_sensor.range_operating_state` is its
aggregate cooktop sensor (`off`/`on`); `sensor.range_operating_state` reports the
same capability as `ready`/`run`. These are separate from the oven's machine and
job states. Recorded history confirms both directions of the cooktop transition.

`config/packages/cooktop_notifications.yaml` sends **Kitchen: cooktop on** with
**At least one cooktop burner is on.** on a known `off` to `on` transition. It
uses `script.notify_optional` once with Chrome as the destination. The existing
router creates exactly one Companion copy for Vitaly iPhone Air
(`notify.mobile_app_als_iphone_89310`); Maria and other destinations are not added.

The household `input_boolean.notifications_off` mute applies. There is no time
of day restriction or critical-alert override. A 60-second cooldown from the
automation's last accepted run suppresses short off/on bounce observed in the
source history. This can also suppress a genuine second start within that
minute. Cooldown checks do not keep a script running or create a pending timer.
Leaving out `initial_state` preserves a user's later manual disable on reload.

There are no notifications for switching off, repeated `on` updates, oven
changes, or recovery from `unknown`/`unavailable` directly into `on`. The sensor
does not identify a particular burner: turning on another burner while the
aggregate state is already `on` cannot produce a separate notification. A start
while HA or the SmartThings connection is unavailable can be missed; this is an
informational cloud notification, not an independent stove safety alarm.

## Validation and deployment

Run the repository validator and `tests/test_cooktop_notifications.py` in the
installed HA version. The isolated test uses real HA state triggers, conditions
and the shared notification router, with notification providers mocked. It must
not connect to SmartThings or operate a real appliance.

Deploy only the new package after comparing the live router with the tested
version and checking the assembled configuration in the installed HA image.
Preserve live files and existing automation enabled states. Reload automations
once during an idle window; a full HA restart is not required. Confirm the new
automation is enabled and existing identities/states remain unchanged. Verify
real delivery on the next ordinary cooktop start, without remotely switching on
the appliance for a test.

Rollback: disable this automation immediately, or remove only its package file
and reload automations during an idle window. No SmartThings integration code,
appliance configuration, helpers or credentials are changed.

Reference: [official Home Assistant SmartThings integration](https://www.home-assistant.io/integrations/smartthings/).
