# Tuya Studio Curtain Motor — local ZHA support

This local adapter supports the exact Zigbee fingerprint **`_TZE204_r0jdjrvi` / `TS0601`**. A generic `TS0601` model name alone is not sufficient: other Tuya products use incompatible datapoints under the same name.

The device pairs with ZHA without this adapter, but the tested Home Assistant 2026.10.0 / zha-quirks 2.3.0 combination initially exposed only a firmware entity. [`tuya_studio_curtain.py`](../config/custom_zha_quirks/tuya_studio_curtain.py) adds a standard cover, motor direction, working mode and motor-fault status.

## Pairing

1. In Home Assistant, open **Settings → Devices & services → ZHA → Add device**.
2. On the **motor itself**, press and release the setup button **three times briefly**.
3. Press the same button a **fourth time**, and hold it for **about two seconds**, until the indicator **flashes rapidly**.
4. Release the button and leave the motor powered while ZHA completes discovery.
5. Verify the manufacturer/model fingerprint above before installing the adapter.

**Three short presses, then one long press: short → short → short → hold ~2 s → release at rapid flashing.**

This exact sequence successfully joined the motor. A simple long press alone produced only brief flashing and did not join it during our attempts.

The supplier's [BX82-TYZ1 manual](https://ae01.alicdn.com/kf/Sb324104250e74532a4c859eed06c3794h.pdf) documents that sequence. The motor has no readable external model label, so BX82-TYZ1 is a matching manual, not a verified hardware model designation. Do not confuse pairing with the separate factory-reset or travel-learning sequences.

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

Its position remains unknown because the motor has not supplied a valid position. This is separate from network availability. The earlier Office Curtains entity was not replaced: its relationship to the intended Studio installation has not yet been confirmed.

## Commissioning and troubleshooting

The motor was paired while powered separately from the curtain track. Install it on the intended track before learning travel limits or verifying full open/close movement. Follow the supplier's mechanical installation and travel-learning instructions. Direction and accurate percentages require verification on the installed curtain. Do not add timed automations until that check is complete.

- **Only firmware entity appears:** confirm the exact fingerprint, custom path and successful ZHA reload; inspect logs for custom-quirk import errors.
- **Commands work but position is unknown:** the motor may not have learned travel limits or sent a position report yet. Unknown is not proof of lost connectivity.
- **Wrong physical direction:** check the motor direction setting after installation. Do not compensate by applying an extra percentage inversion in an automation.
- **No response:** check power and ZHA availability, then inspect Tuya cluster (`0xEF00`) responses. A service returning success alone is not evidence that the motor moved.
- **Future upstream support:** [zha-device-handlers PR 4943](https://github.com/zigpy/zha-device-handlers/pull/4943) includes this fingerprint, but was unmerged when this adapter was prepared. Its broad proposed mapping was not copied wholesale.

No factory reset, firmware flash or travel calibration is required to install the adapter.
