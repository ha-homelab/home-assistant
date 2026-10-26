# Bath 2: a light backed by an ESPHome relay

The public control is `light.bath_2`, named **Bath 2**. It uses Home Assistant's
native [Change device type of a switch](https://www.home-assistant.io/integrations/switch_as_x/)
helper with `switch.bath_2` as its source and `invert: false`.
The underlying ESPHome entity keeps its original unique ID; its display name is
also Bath 2. The helper is stored in Home Assistant's private config entries,
not duplicated by a YAML template light.

The source switch is hidden, **not disabled**. Disabling it would break the light:
the helper must continue to receive relay states and forward on/off commands.
No firmware change or device pairing is involved. The light supports on/off only.
The unrelated `light.bath2_old` remains a legacy device.

## Recreate the helper

1. Rename the ESPHome entity from `switch.bath2` to `switch.bath_2` and name it Bath 2.
2. In Settings → Devices & services → Helpers, create **Change device type of a switch**.
3. Select `switch.bath_2`, target type **Light**, and leave inversion off.
4. Set the resulting entity ID to `light.bath_2` and name it Bath 2.
5. Keep the source enabled but hidden. Confirm the light follows its on/off and
   unavailable states before loading the migrated consumers.

## Consumers and screen notifications

Motion rules 017/018, morning schedules 074/075 and the household-off script use
`light.bath_2` with the correct light service or domain-neutral shutdown action.
Bathroom Sticky, motion timeouts and manual-ON protection are unchanged.
Lovelace and the private EchoMuse control allowlist also use the light.

Rule 112's screen-notification trigger excludes both the source switch and the
light. Renaming alone or merely hiding the source is not sufficient to silence
an explicit automation trigger. Other device notifications remain enabled.
Do not add the source or facade to that notification trigger when rebuilding.

## Validation

`tests/test_bath_2_light.py` creates the native helper in an isolated Home Assistant
instance. It verifies on/off forwarding, state and unavailable propagation, an
enabled hidden source, and that neither old/new relay nor facade changes trigger
screen notifications while a different eligible switch still does.
The existing Sticky and motion-timeout suites cover the migrated light target.
A live idempotent command can check routing without deliberately cycling a light
that someone may currently be using.
