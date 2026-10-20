# Motion lighting overrides

Room Sticky pauses automatic motion lighting. It does not issue a light command.
When it is ON, motion and presence leave the room's lights alone in both
directions. Manual controls remain usable.

Every lighting command requires the relevant helper to be explicitly OFF.
Missing, unknown and unavailable helpers block the command too. Checks run
immediately before each command: notifications, previous device calls and delays
can take time while the owner changes Sticky. A command already sent to a device
cannot be recalled.

## Covered paths

- RF motion activation in the bathrooms, bedroom, dining room, hallway, kitchen,
  lobby, second room and porch.
- Living-room Zigbee presence, including lamp-state reconciliation, startup,
  reload, the minute check, the 20-minute absence timer and the morning boundary.
- Motion-clear dimming and the shared shutdown blueprint, including genuine
  unknown/unavailable recovery and later retries.
- The retained backdoor camera motion script's light pulse, each fade step and
  final shutdown. Camera capture and notifications remain independent.
- The existing living-room override in the fireplace/media motion rule is
  checked before each controlled switch.

Other current camera/MQTT motion paths capture images or send notifications.
Sensor reporting continues while Sticky is ON; non-lighting consumers continue
to receive events.

## Room ownership and shared lights

The existing room helper remains the owner of each ordinary lighting rule.
Bathroom Sticky also owns Bathroom 2; its `rf_studio_motion` entity has a legacy
name and does not transfer ownership to Studio Sticky.

Two lights have consumers in more than one room:

- `switch.dining_wall_light_2` requires **both Dining and Lobby Sticky OFF**,
  whichever room's motion rule requests the change.
- `light.hall_2_m` requires **both Hallway and Mishka Sticky OFF**, including
  hallway dimming and inactivity shutdown.

These extra checks apply to the shared light only. Lobby Sticky does not pause
the other dining lamps, and Mishka Sticky does not pause Hallway 1.

The shutdown blueprint accepts `target_sticky_helpers`, mapping a light entity
to a list of Sticky helpers. It checks this mapping on every attempt alongside
the existing room guards and motion timing rules. Manual OFF-to-ON protection
is unchanged: a stale absence timer cannot switch off a newer manual ON.
Genuine availability recovery remains separate.

Studio's previous wall-lamp motion rules were retired when that lamp moved to
the dining room. Studio Sticky and its UI controls are intentionally retained;
they currently have no active Studio lighting rule to pause. See
[the migration record](dining-arc-lamp.md#remove-the-old-lighting-role).

## Existing schedules and explicit controls

This override concerns motion/presence lighting. Explicit user actions and
separate scheduled household shutdowns keep their existing behavior.

The existing `automation.morning_sticky_reset` clears nine room Sticky helpers
at **06:15 Home Assistant local time**. It is a separate schedule and is
unchanged here. After a helper is OFF again, automatic lighting can resume.
Studio, curtain and warmer overrides are not added to that reset. Room helpers
continue to restore their state after an ordinary Home Assistant restart.

## Verification and deployment

Regression suites run the actual YAML with Home Assistant's condition and
script engine and fake device services. They cover blocked and allowed commands,
shared-light isolation, changes during an awaited command, absence and recovery,
the backdoor fade, and preservation of manual light state.

```sh
python tools/validate.py
python dependencies/automations/tools/validate.py
python dependencies/scripts/tools/validate.py
REQUIRE_HA_RUNTIME=1 python -m unittest discover -s tests -p 'test_living_room_presence.py'
REQUIRE_HA_RUNTIME=1 python -m unittest discover -s tests -p 'test_motion_light_off.py'
REQUIRE_HA_RUNTIME=1 python -m unittest discover -s tests -p 'test_sticky_lighting.py'
```

Deploy changed automation definitions together with the updated shutdown
blueprint, presence package and backdoor script. Preserve installation-specific
metadata and unrelated private overrides. Check the complete HA configuration,
then reload changed automations and the script when they are idle. No device
reset, re-pairing or Home Assistant restart is required.
