# Tuya Studio Curtain Motor — local ZHA support

This local adapter supports the exact Zigbee fingerprint **`_TZE204_r0jdjrvi` / `TS0601`**. A generic `TS0601` model name alone is not sufficient: other Tuya products use incompatible datapoints under the same name.

The device pairs with ZHA without this adapter, but the tested Home Assistant 2026.10.0 / zha-quirks 2.3.0 combination initially exposed only a firmware entity. [`tuya_studio_curtain.py`](../config/custom_zha_quirks/tuya_studio_curtain.py) adds a standard cover, motor direction, working mode and motor-fault status.

## Zigbee pairing

1. In Home Assistant, open **Settings → Devices & services → ZHA → Add device**.
2. On the **motor itself**, press and release the setup button **three times briefly**.
3. Press the same button a **fourth time**, and hold it for **about two seconds**, until the indicator **flashes rapidly**.
4. Release the button and leave the motor powered while ZHA completes discovery.
5. Verify the manufacturer/model fingerprint above before installing the adapter.

**Three short presses, then one long press: short → short → short → hold ~2 s → release at rapid flashing.**

This exact sequence successfully joined the motor. A simple long press alone produced only brief flashing and did not join it during our attempts.

The supplier's [BX82-TYZ1 manual](https://ae01.alicdn.com/kf/Sb324104250e74532a4c859eed06c3794h.pdf) documents that sequence. The motor has no readable external model label, so BX82-TYZ1 is a matching manual, not a verified hardware model designation. Do not confuse pairing with the separate factory-reset or travel-learning sequences.

## Motor button and remote commands

Reference: the same supplier manual, English page 2, sections 03 and 05–11. These are operating instructions, not additional features implemented by the ZHA quirk.

`SET` is the motor button; `P2` is on the remote's back. Arrows mean separate presses; `+` means simultaneous. The manual lists **2.4G/BT**, not generic 433 MHz remote compatibility.

### Pair a compatible remote

1. Hold **SET 2 s**, release: LED steady.
2. Press remote **OPEN**: LED flashes once.
3. Press remote **P2**: LED off; paired.

### Settings through an already paired remote

Prefix every command below with **P2 → P2**: LED flashes, then stays on. Completion: LED off, motor jog.

- Reverse direction: **STOP**.
- Save travel across power loss: **CLOSE**.
- Custom opening limit: position the curtain before the prefix; finish with **OPEN**. Repeat to cancel; applies to remote, hand-pull and app opening.
- Faster: **OPEN + STOP**; slower: **CLOSE + STOP**. Three speeds; default middle.
- Toggle hand-pull starting: **OPEN + CLOSE**.

### Motor-only alternatives and reset

- Reverse: **SET short → SET hold 2 s**; LED flashes, motor jogs.
- Save travel: **SET short twice → SET hold 2 s**; same feedback.
- Learn travel: complete one full opening and closing against the track ends. Abnormal blockage clears travel; power cycling may require relearning unless saved.
- **Factory reset:** hold **SET 2 s** (steady LED), release, then hold **SET 5 s** (flashing). Clears remotes, travel and other settings. No individual remote-removal sequence is documented.
- Zigbee leave/rejoin: use [Zigbee pairing](#zigbee-pairing); this also removes the previous network association.

### Verification and integration boundaries

As of 2026-10-12, the Zigbee joining sequence and installed travel have been verified. **Remote pairing has been explained but not yet confirmed by the user.** The remote shortcuts, motor-button reversal, travel-memory setting, speed selection, custom opening limit, hand-pull toggle and factory reset remain untested on this unit. Do not treat this reference as a record that those settings were applied.

The installed direction is **Back**, verified through ZHA. Reversing again by remote or SET would change that working setup; verify actual movement and the reported direction before updating the commissioning record. Preserve the distinction between remote pairing, Zigbee joining and factory reset: adding a remote does not call for the other two procedures.

The current quirk exposes open/close/stop, target position, direction, working mode and motor fault. It does **not** expose remote registration, speed, travel-memory or hand-pull controls. The working-mode setting has not been physically verified and must not be presented as speed selection. Do not invent Tuya datapoint writes for the manual's button sequences.

The manual's Tuya gateway, account sharing and voice-assistant sections describe an alternative ecosystem. This installation uses ZHA directly; no Tuya gateway or cloud-account linking is needed for its HA controls. Refer to the original manual for that alternative setup rather than moving the commissioned motor to another network.

## Installation

1. Check `zha.custom_quirks_path` in Home Assistant's active configuration. This repository already sets `/config/custom_zha_quirks/` in `config/configuration.yaml`.
2. Copy only `tuya_studio_curtain.py` into that directory. Keep existing quirks.
3. Reload the ZHA integration. Other ZHA devices briefly reconnect during the reload.
4. Verify that the motor has a cover entity and that its custom quirk is applied.

The quirk is tracked under `config/` and is included by `tools/build.py` in assembled releases. The deployed path is `/config/custom_zha_quirks/tuya_studio_curtain.py`, on the persistent Home Assistant configuration volume. Removing this file and reloading ZHA removes this adapter without resetting the motor or Zigbee network. Remove the local adapter when an installed upstream release supports this exact fingerprint correctly; do not assume a firmware update entity means an update is available.

## Protocol and checks

The mapping comes from the exact device in [zigbee-herdsman-converters](https://github.com/Koenkk/zigbee-herdsman-converters/blob/master/src/devices/tuya.ts), documented as [TS0601_cover_8](https://www.zigbee2mqtt.io/devices/TS0601_cover_8.html).

- DP 1: enum, open `0`, stop `1`, close `2`.
- DP 2: target position and position reports.
- DP 3: position reports only.
- DP 5: direction, forward `0`, back `1`.
- DP 12: motor fault.
- DP 106: continuous `0`, intermittent `1`.

Raw position is `0=open, 100=closed`, matching ZCL. Home Assistant presents the opposite percentage convention (`100=open`), which its cover implementation converts. The adapter deliberately uses `invert=False` and suppresses outbound writes to report-only DP 3. Position reports outside 0–100 are ignored rather than creating an invalid cover state.

[`validate_studio_curtain_quirk.py`](../tools/validate_studio_curtain_quirk.py) runs in an isolated Python process using Home Assistant's installed packages. It creates a mocked device, never opens the radio, and checks the exact fingerprint, preserved Green Power endpoint, both report datapoints, invalid position handling, open/close/stop encoding, target writes to DP 2 only, and the additional status/configuration datapoints.

```sh
# From the repository root, using Python with the tested HA packages installed:
python3 tools/validate_studio_curtain_quirk.py
# Optionally validate another candidate:
QUIRK_FILE=/path/to/tuya_studio_curtain.py python3 tools/validate_studio_curtain_quirk.py
```

These checks passed with the versions above. They verify protocol translation, not physical travel, direction, end stops or the final installed curtain.

## Live verification

On 2026-10-11 the adapter loaded successfully and created `cover.studio_curtains` plus the direction, mode and fault entities. The device remained available in ZHA. A real `cover.stop_cover` call sent DP 1 enum `1`: the motor returned a successful Zigbee default response and echoed the same Tuya datapoint about 0.1 seconds after transmission. No open/close motion or travel calibration was performed while the motor was detached from the track.

The cover was added to the existing **Lighting** Lovelace view, beside the other curtain cards. This view is storage-managed; its full private storage record is not exported to Git. To recreate just this card in the dashboard editor:

```yaml
type: tile
entity: cover.studio_curtains
name: Studio Curtains
icon: mdi:curtains
features:
  - type: cover-open-close
  - type: cover-position
```

At initial pairing, its position remained unknown because the motor had not supplied a valid position. This was separate from network availability. The earlier Office Curtains entity was not replaced during pairing.

## On-track commissioning on 2026-10-12

The user installed this motor on the track previously driven by **Office Curtains R**, initially fully open. The original direction was reversed for this installation: an `open_cover` command physically closed the curtain halfway. Setting **Motor direction** to **Back** (DP 5 enum `1`) made `close_cover` close it fully, as confirmed by the user. This is an installation-specific direction setting, not a new default for every matching motor.

A subsequent full opening took approximately 9.3 seconds and produced a real DP 3 position report of `0`, shown by Home Assistant as **100% open**. The radio acknowledged and echoed the movement and direction commands. Command acknowledgements alone were not treated as proof of physical movement.

A `set_cover_position` command to **50%** was acknowledged and echoed on DP 2; the user confirmed that the curtain stopped approximately halfway open. The curtain was then commanded back to fully open. No factory reset, pairing change or speculative limit-datapoint write was used. Power-loss retention of the learned limits has not been tested. The existing Office Curtains entity and dashboard references were not migrated as part of calibration. The subsequent automation migration is recorded below.

## Replacing the previous Office Curtains R motor

The installed motor has demonstrated correct full travel and midpoint positioning. Its direct ZHA connection removes the previous device's Wi-Fi/LocalTuya connection path, but **fast command acknowledgement while already connected does not establish recovery time after a power cut**. The user reported that the old LocalTuya opener needed roughly a minute after power restoration; no comparable cold-start measurement has been made for this motor. ZHA still depends on the coordinator and Zigbee network.

Before claiming that replacement solves the delay, record the time from restored power to the first command that actually moves the curtain, then verify direction, endpoints and a physical 50% stop. Separately record whether travel memory was enabled and survived the power cycle. The manual's memory shortcut alone is not evidence that this unit retained calibration.

At calibration time, the automation migration was still pending:

- The new working target is `cover.studio_curtains`.
- The old `cover.office_curtains_r` template wraps `cover.office_curtains_office_curtains` with inverted commands/position in [`config/covers.yaml`](../config/covers.yaml). Do not carry that inversion over to the new cover: its installed direction is already corrected.
- [`027_curtains_close_in_the_evening.yaml`](../dependencies/automations/config/027_curtains_close_in_the_evening.yaml) still targets the old template. Dashboard references and other automation/script references need a fresh inventory when migration is requested.

## Commissioning and troubleshooting

The motor was paired while powered separately from the curtain track. Install it on the intended track before learning travel limits or verifying full open/close movement. Follow the supplier's mechanical installation and travel-learning instructions. Direction and accurate percentages require verification on the installed curtain. Do not add timed automations until that check is complete.

- **Only firmware entity appears:** confirm the exact fingerprint, custom path and successful ZHA reload; inspect logs for custom-quirk import errors.
- **Commands work but position is unknown:** the motor may not have learned travel limits or sent a position report yet. Unknown is not proof of lost connectivity.
- **Wrong physical direction:** check the motor direction setting after installation. Do not compensate by applying an extra percentage inversion in an automation.
- **No response:** check power and ZHA availability, then inspect Tuya cluster (`0xEF00`) responses. A service returning success alone is not evidence that the motor moved.
- **Future upstream support:** [zha-device-handlers PR 4943](https://github.com/zigpy/zha-device-handlers/pull/4943) includes this fingerprint, but was unmerged when this adapter was prepared. Its broad proposed mapping was not copied wholesale.

No factory reset, firmware flash or travel calibration is required to install the adapter.

## Automation migration on 2026-10-12

This is the historical migration record. The manual-opening policy below
supersedes its morning behavior; do not restore the morning Studio actions.

The owner confirmed that the new Zigbee motor is powered through
`switch.studio_guard`. Both existing automation identities, schedules,
`input_boolean.curtains_sticky` conditions and power sequences are retained.

- Morning rule **078** explicitly sends `cover.open_cover` to
  `cover.studio_curtains` after the existing 90-second shared warm-up. Previously
  it only powered Studio guard; it had no Studio opening command.
- Evening rule **027** sends `cover.close_cover` to `cover.studio_curtains`.
  The exact former `cover.office_curtains_r` action remains commented beside it.
  The existing 90-second warm-up and one-hour delay before guard power-off remain.
- Only the new Studio movement calls use `continue_on_error: true`, so an
  unavailable motor does not prevent the remaining room commands or shutdown.
  This does not silently retry an unsuccessful Studio movement.

The old LocalTuya entity and inverted template remain available for manual
rollback. No active automation or script targets them. Their inversion is not
applied to the new cover, whose direction was already calibrated as **Back**.
No registry identities or dashboard controls are changed by this migration.
For rollback, restore the commented evening action and remove the newly added
morning Studio open action; retain the shared guard power actions.

Validate both rules in an isolated HA instance with recorded services, including
Studio failure cases and daylight/manual-override checks. Deploy only the two
changed automation files, run the installed HA configuration checker, then reload
each by its stable automation ID. Verify loaded configuration, enabled state and
unchanged motor state without firing the household schedules. These checks do not
constitute a new physical movement or cold-start recovery test.

## Manual opening policy (2026-10-23)

Studio must not open automatically in the morning. Rule **078** now operates
only the kitchen and dining curtains: both `switch.studio_guard` power-on and
`cover.studio_curtains` opening have been removed from that schedule. This policy
does not depend on the shared `input_boolean.curtains_sticky` being enabled.
Manual controls and the existing evening close rule **027** remain available.
The motor still needs power for manual commands.

The incident was traced to rule 078's sunrise trigger, followed by its existing
90-second warm-up and explicit Studio open action. It was not an unsolicited
Zigbee command. Removing only the open command would leave unnecessary scheduled
power changes, so the entire Studio branch was removed. Kitchen and dining
retain their daylight check, earliest time, warm-up and power sequence in
independent branches. Each branch requires both its room Sticky and Curtains
Sticky to be off, rechecking before movement and any delayed power-off.

Validation uses an isolated Home Assistant instance with recorded service calls.
The morning tests require that neither Studio power nor Studio movement is
called, while permitted kitchen/dining opening and evening Studio closing still
work. To verify this policy in an existing installation, compare rule 078 with
the current source and preserve its room/global Sticky checks. After any
required update, run the installed configuration checker and reload only the
changed automation by its immutable ID. Confirm its loaded actions and enabled
state without triggering it. No physical movement is needed to test this policy,
and a source-pin rollback must not restore the old morning actions.
