# Garage button: firmware and direct Zigbee control

The garage button is a battery-powered Tuya **TS0041**, originally identified
as **`_TZ3000_mrpevh8p`**, with a Telink TLSR8258 radio. The experimental
**1.1.3-holdoff1 EndDevice firmware** was installed on 2026-10-08, after the
initial upstream conversion. It reports **`TS0041-TB` / `mrpevh8p`** and actual OTA
version **`0x11033001`**. The new transfer reached 100%, Home Assistant reported
success, and an uncached device read confirmed the installed version.

All five lamps remain in the native group. During initial upstream commissioning,
the button acknowledged its On/Off group bind with `Status.SUCCESS`, and the owner
confirmed immediate physical on/off operation. The new hold-to-off settings have
now been read back successfully; their physical acceptance test is pending. The
HA toggle automation remains disabled. The existing `light.garage` HA group still contains
all five bulbs for dashboard and household-script use.

During the earlier upstream conversion, transfers stopped near 7% and 10%, and
a later attempt failed before sending image bytes. Its successful transfer followed battery replacement,
securing its contact, and a ZHA integration reload; these changes do not isolate
a single root cause. It took approximately eight and a half minutes. After
100%, allow time for the version query and fresh device interview. In this run
the new identity was read successfully, followed by a leave/rejoin and further
configuration. ZHA then loaded `tuya_binding_switch:(mrpevh8p / TS0041-TB)` and
restored the existing firmware entity with installed/latest `0x11033000` and
`in_progress: false`. A briefly unavailable update entity or cached stock
identity alone is not evidence that the flash failed.

## Hold-to-off extension (installed 2026-10-08)

The source, tests, build instructions, and generic English recovery guide live in
[ha-homelab/zigbee-direct-button](https://github.com/ha-homelab/zigbee-direct-button).
Its experimental `1.1.3-holdoff1` image (`0x11033001`) is now installed. The actual
transfer took approximately 29 minutes 52 seconds. An uncached OTA-cluster read
returned `285421569` (`0x11033001`); uncached configuration reads confirmed:

- Momentary / 1 (`0xff00`), ToggleSimple / 2 (`0x0010`).
- Long-press duration 1000 ms (`0xff03`).
- ShortPressLongOff / 4 (`0xff05`).

A short release sends Toggle. A one-second hold sends one absolute Off command
to the same native group, without an initial Toggle, dimming, or a release Toggle.
Physical hold-to-off acceptance is pending. The five-member native group and
five-member `light.garage` helper are present; the old HA toggle automation is off.

Ordinary key presses did not make the converted firmware responsive to OTA setup:
the firmware returns to a 120-second poll interval and only starts with a short
fast-poll window. The failed preparation sent no image bytes. The successful
attempt was armed first, then the battery was removed for five seconds and
reinserted, followed immediately by one short working-key press. The trigger
sensor value is `press`, not `pressed`. See the public project's guarded startup
procedure; never power-cycle an active or ambiguously active image transfer.

The active local index advertises only this normal-update image. Original upstream
images remain recovery references. Before an upstream downgrade, restore and
verify PressStart mode 1; upstream firmware does not implement mode 4.

After the successful update, HA rebuilt the firmware entity with the correct
installed version and `in_progress: false`, but its latest-version cache was
empty. This can display an `unknown` update state even after the uncached device
version and settings have been verified. A single targeted image notification
did not restore that metadata; leave it for a later normal OTA query rather than
restarting a working device or repeating the installation for a cosmetic state.

## Pinned upstream reference firmware

The repository includes the unmodified **battery EndDevice** build
`REMOTE_TUYA_BUTTON_TS0041_END_DEVICE`, release **1.1.3-ec57f81b**, from
[tuya-zigbee-switch](https://github.com/romasku/tuya-zigbee-switch).
This is experimental third-party firmware. The mains-powered Router build is
not appropriate for this coin-cell device.

`config/ota/tuya_ts0041/` contains the following artifacts:

- `tlc_switch-1.1.3-ec57f81b-from_tuya.zigbee`: conversion from stock firmware;
  manufacturer code 4417, image type 54179, OTA version `0xffffffff`.
- `tlc_switch-1.1.3-ec57f81b.zigbee`: subsequent updates of the converted device;
  manufacturer code 4417, image type 45636.
- `index.json`: active hold-to-off image path, SHA-512 checksum, size, and release URL.
  Matching is limited to the expected manufacturer and model identifiers.
- `provenance.json`: exact source, firmware, and quirk provenance.
- `UPSTREAM-LICENSE.txt`: upstream redistribution terms.

The conversion image's `0xffffffff` is an OTA conversion marker, not the
human-readable release number. A converted button should identify as
`TS0041-TB` / `mrpevh8p`. The target-only deployment ZHA quirk is stored at
`config/custom_zha_quirks/tuya_binding_switch.py`, with its license beside it.

Home Assistant loads the local provider through:

```yaml
zha:
  custom_quirks_path: /config/custom_zha_quirks/
  zigpy_config:
    ota:
      extra_providers:
        - type: z2m_local
          index_file: /config/ota/tuya_ts0041/index.json
```

Deploy the configuration, index, firmware images, and quirk together. Validate
HA configuration and restart HA once so the provider and quirk are loaded.
These are tracked configuration artifacts and are included by `tools/build.py`.
No network keys, device backups, access tokens, or private logs belong in Git.

## Back up before conversion

1. Create and download a fresh **ZHA network backup**. Store it privately: it
   contains the Zigbee network key. This protects the coordinator/network, not
   the button's original firmware.
2. Back up HA configuration, entity/device registries, and the affected
   automation. Make a consistent SQLite backup of the ZHA database when backing
   up a running instance; do not simply copy a live database and omit its WAL.
3. Record the button's IEEE, model, manufacturer, firmware version, and battery
   condition privately. Our starting OTA version was `0x00000043`.
4. Keep an independent working way to control the lights in HA during
   commissioning. Disable only the old button-triggered toggle automation.

Upstream supplies a factory reference dump for this model. It is **not a backup
of this individual button**. Do not write another device's MAC, network data,
or calibration blindly. Restoring factory firmware may require wired Telink
programming and a suitable original dump. See the upstream
[flashing guide](https://github.com/romasku/tuya-zigbee-switch/tree/main/docs/flashing).

## Run the OTA conversion

1. Use a healthy battery of the size fitted to the actual holder and a stable
   radio path. The owner found **CR2450** in this unit; the upstream device
   database's **CR2430** entry is not authoritative for its battery compartment.
   Both are 3 V cells, but CR2430 is 2 mm thinner. Verify secure contact rather
   than assuming that a powered LED proves a suitable fit for an OTA transfer.
   Prefer the same room as the
   coordinator; a short distance through a floor is not equivalent to a clear
   radio path.
2. Confirm the update entity offers `0xffffffff`, is not already updating, and
   the device still has the stock identity. Do not start a second updater.
3. Start `update.install` for the exact button update entity and version
   `0xffffffff` while the device is awake. In this installation the existing
   entity is `update.audio_button_firmware`; the old name is historical.
4. Briefly press the button every two seconds for up to 30 seconds if necessary
   to begin the transfer. Do not hold the pairing/reset button. Stop pressing
   once the device is continuously requesting firmware blocks.
5. Monitor actual update percentage and the completion result. Avoid HA,
   coordinator, or button power interruptions during the transfer.
6. Permit joining after completion. Confirm the new identity, firmware, and
   endpoints. The installed stack automatically interviews after OTA; let that
   finish before starting another interview. It also exposes a fresh interview
   through **Reconfigure** (`zha/devices/reconfigure`), which rebuilds the device when its
   signature changes. Try this before removal. The pinned upstream guide predates
   that capability and describes removing/re-pairing as the fallback; preserve
   the old registry details before using it. Do not remove or re-interview a
   device while it is updating.
7. Confirm configuration has completed and the custom quirk is loaded, then
   perform the binding and tests below.

During the first attempts, an asleep button either failed to receive the
notification or did not request an image. Repeated short presses allowed the
stock firmware to issue `QueryNextImage` and then `ImageBlock` requests.
An `in_progress: true` state without a percentage only proves that HA has
started waiting. It does not prove that image bytes have reached the device.

A custom WebSocket client must send strictly increasing request IDs. A rejected
`id_reuse` request never starts the OTA service. Run the updater independently
of an interactive SSH connection, retain a private progress log, and inspect the
live update state before retrying after any connection loss.

In the installed HA version, `zha/devices/reconfigure` starts an asynchronous
interview and emits reconfigure events instead of a normal WebSocket result.
Do not treat a generic RPC client's result timeout as proof that the interview
failed, or repeatedly restart it. Observe its events and verify the resulting
device identity, quirk, and endpoints separately.

When starting on a button press, filter both `event_type: zha_event` and the
exact `command: remote_button_short_press`; matching only the device IEEE can
also match lifecycle events during re-pairing. Recheck that the update entity
is available immediately before calling the service. A successful service
response without observed transfer is not a successful upgrade: read the
device identity and version, and do not proceed to binding on that basis.

## Native group and binding

The existing **`light.garage`** is an HA light group and remains useful for UI and
household scripts. Direct radio control additionally requires a **native ZHA
Zigbee group**:

- Name: `Garage Direct`.
- Group ID: **18177 / `0x4701`**.
- Members: all five `light.garage_bulb_one` through `light.garage_bulb_five`
  CREE bulbs, each on endpoint **10**.
- Source: converted button endpoint **1**, output cluster **On/Off / `0x0006`**.

Verify each bulb acknowledges group membership. A successful group-creation
API response may still contain fewer than the requested five members. A bulb
that is unreachable or unpowered must not silently be counted as commissioned.

Bind the button's On/Off output to this group using ZHA's group binding UI.
Verify the device's actual successful bind response: in this installed ZHA
version, the group-bind API can return success even when an individual radio
operation fails. Temporary `zigpy.zdo` debug logging exposes the bind status.
Restore the previous logging level after verification.

Configure its endpoint-1 On/Off Configuration cluster (`0x0007`) as follows:

- `switch_mode` (`0xff00`): **Momentary / 1**.
- `switch_actions` (`0x0010`): **ToggleSimple / 2**.
- `binded_mode` (`0xff05`): **ShortPressLongOff / 4**.
- `long_press_duration` (`0xff03`): **1000 ms**.

After the custom quirk finishes loading, these settings are also available as
HA select entities. Existing entity IDs were preserved during this conversion:

```yaml
action: select.select_option
target:
  entity_id: select.audio_button_switch_mode_1
data:
  option: Momentary
```

Use `select.audio_button_switch_actions_1` with option `ToggleSimple`, and
`select.audio_button_binded_mode_1` with option `ShortPressLongOff`; set
`number.audio_button_long_press_mode_1` to 1000 for the duration.
The historical `audio_button` prefix identifies the garage button; it does not
mean that an audio-system automation participates in direct control. Read the
values back from the device, rather than relying only on a successful service
response.

The new mode sends the short action on release and absolute Off at the hold
threshold. `ToggleSimple` inverts each bulb's current state, so a mixed group can
stay mixed after a short press. A hold resynchronizes reachable members to Off.
The previous `PressStart` mode remains available for rollback without reflashing.

Keep `automation.audio_button_toggle_audio_switch` disabled after verified
binding. Running both paths can toggle the bulbs twice and make a press appear
to do nothing. If conversion/binding is abandoned and the button still emits
stock events, re-enable the original automation to restore normal service.

## Upstream conversion verification (earlier on 2026-10-08)

- Conversion completed at 100%; the live device and HA update entity both
  report `0x11033000`, with no update in progress.
- ZHA loaded the custom `TS0041-TB` quirk while preserving the existing device
  identity and `audio_button` entity names.
- All five CREE bulbs are members of native group `0x4701`, endpoint 10 each.
- The button returned a successful group-bind acknowledgement. Uncached
  attribute reads confirmed Momentary, ToggleSimple, and PressStart. The raw
  read API names action value 2 `SwitchActions.ToggleToggle`; the custom quirk's
  select entity displays that same numeric value as `ToggleSimple`.
- The owner confirmed physical on/off operation and immediate switch-off,
  with `automation.audio_button_toggle_audio_switch` disabled throughout.
- A separate post-test unicast read succeeded for Garage One and Two, but
  Garage Three timed out and Garage Four/Five returned generic read errors.
  Individual HA telemetry is therefore not fully verified; do not infer
  physical lamp state from stale dashboard values. This is separate from the
  owner's successful direct-button on/off test.
- Pairing was closed and temporary Zigbee debug logging was restored to ERROR.
- No test with the entire HA process stopped was performed. Direct binding and
  the disabled automation establish the configured command path; a full
  outage test is a separate optional acceptance check.

## Acceptance tests

- Read the converted device's identity and firmware after its reboot.
- Confirm five acknowledged group members and a successful On/Off group bind.
- Read back the four current button settings above while it is awake.
- With the old HA toggle automation disabled, press once from all-off and
  confirm all five lamps turn on; press again and confirm all five turn off.
- Hold from all-on and verify all five lamps stay off after release; hold again
  from off and verify no initial flash or release Toggle.
- Check physical response as well as HA state. A stale entity state is not
  proof that a Zigbee lamp ignored a command.
- Verify the established HA group and household shutdown scripts still control
  all five bulbs.
- To demonstrate independence from HA, stop HA briefly while leaving the
  coordinator and Zigbee routers powered, test the button, then restore HA.
  A stopped-HA test must be planned so other household automations can tolerate
  the interruption. Independence from HA does not imply independence from the
  button's Zigbee parent/router or from electrical power.

## Troubleshooting

- **No percentage:** check wake-up timing, battery, and radio path. Inspect
  whether the device sent `QueryNextImage`; do not repeatedly restart HA.
- **Presses arrive but replies return `NWK_NO_ROUTE`:** successful reception is
  not proof of a working return path. Moving a sleepy device may leave its old
  parent relationship intact. With no update running, first try a battery
  power cycle near the coordinator. If re-pairing is needed, open joining on
  the intended parent and preserve the device identity and automation backup.
- **Progress stops:** inspect the OTA error and last confirmed offset. Do not
  launch overlapping updates. Confirm that the original update has ended
  before planning a retry.
- **Strong LQI but transmit failures:** LQI describes received frames, not a
  guarantee of bidirectional communication. A raw attribute read after
  re-pairing failed with `MAC_CHANNEL_ACCESS_FAILURE` despite LQI above 200.
  A later read returned `MAC_NO_ACK`; that read was not synchronized to a wake-up,
  so sleep remains a possible cause. Preserve that distinction when investigating
  channel contention and routes. Re-pairing near the coordinator does not itself
  prove that the coordinator became the device's parent; inspect the current
  neighbor tables and distinguish stale network addresses from the new one.
- **Old model/quirk after completion:** try the installed stack's Reconfigure
  action to request a fresh interview. Verify the resulting identity and
  endpoints. Use upstream remove/re-pair guidance only if necessary, after
  backing up the old identity; an HA restart alone may retain the cached signature.
- **Only some bulbs react:** check native group membership, physical mains
  power, and routes for each member. HA group membership is a separate setting.
- **A press turns lights on and straight back off:** check for the old toggle
  automation, duplicate event automations, and duplicate direct bindings.
- **Direct control works but HA state lags:** inspect bulb reporting and radio
  responses before changing binding or restoring the duplicate automation.

References: [updating procedure](https://github.com/romasku/tuya-zigbee-switch/blob/f3355011cd01e656c4d53d7847ae2029fefe199e/docs/updating.md),
[exact device support](https://github.com/romasku/tuya-zigbee-switch/issues/394),
[Home Assistant groups and binding](https://www.home-assistant.io/integrations/zha/#zigbee-groups-and-binding-devices).
