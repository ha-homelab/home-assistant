# Room Sticky: automatic lighting and curtains

Room Sticky pauses automatic lighting and curtain commands for its room. It does
not issue a device command. While ON, motion, presence, schedules and automatic
solar-surplus lighting leave the room alone in both directions. Manual light
controls remain usable. The existing curtain helper scripts also honor Sticky.

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
- Fixed-time light shutdowns and solar-surplus lighting commands use the same
  room ownership, including shared lights.
- Scheduled curtain opening/closing, motor power, RF transmissions and delayed
  Wi-Fi fallbacks require both the global Curtains Sticky and the room Sticky
  to be OFF. A blocked room does not stop other rooms from completing their run.

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
Studio Sticky still protects automatic Studio curtain closing and motor power.
Studio opening remains manual only. See
[the migration record](dining-arc-lamp.md#remove-the-old-lighting-role).

## Persistent overrides and command boundaries

The old `automation.morning_sticky_reset` is retired. Room Sticky stays ON until
the owner changes it; 06:15 no longer silently resumes automation. Room helpers
continue to restore their state after an ordinary Home Assistant restart.

Manual light buttons, notification action buttons and explicit household
shutdown scripts retain their direct-control behavior. Sticky is an automatic
control override, not a lock that prevents an owner from switching a light.

Curtains check the override again after warm-up, before each movement and before
delayed motor power-off. Enabling Sticky while a run waits prevents later
commands; it cannot recall an RF packet or stop a movement already sent. When
updating from the old rules, cancel their pending runs before reloading so an old
one-hour delayed power-off cannot finish under the former policy.

## Diagnosing an apparent bypass

Inspect the automation trace at the command time, not only the current helper
state. A helper enabled after a command cannot prevent that command. Check every
caller, including fixed schedules and energy rules, and compare the loaded
automation with the maintained source. A stale deployed file or a background
helper reset can otherwise look like a broken condition.

## Verification and deployment

Regression suites run the actual YAML with Home Assistant's condition and
script engine and fake device services. They cover blocked and allowed commands,
shared-light isolation, changes during an awaited command, absence and recovery,
the backdoor fade, scheduled and energy-driven commands, delayed curtains, and
preservation of manual light state.

```sh
python tools/validate.py
python dependencies/automations/tools/validate.py
python dependencies/scripts/tools/validate.py
REQUIRE_HA_RUNTIME=1 python -m unittest discover -s tests -p 'test_living_room_presence.py'
REQUIRE_HA_RUNTIME=1 python -m unittest discover -s tests -p 'test_motion_light_off.py'
REQUIRE_HA_RUNTIME=1 python -m unittest discover -s tests -p 'test_sticky_lighting.py'
REQUIRE_HA_RUNTIME=1 python -m unittest discover -s tests -p 'test_living_curtain_morning.py'
```

Deploy changed automation definitions together with the updated shutdown
blueprint, presence package and backdoor script. Preserve installation-specific
metadata and unrelated private overrides. Check the complete HA configuration,
then reload changed automations and the script when they are idle. No device
reset, re-pairing or Home Assistant restart is required.
