# RF Airbridge: MQTT reception, RCSwitch transmission, and Dooya curtains

`config/packages/rf_airbridge.yaml` adds a counter-only MQTT consumer alongside
the existing motion automations, and a parameterized `script.rf_send_code` for
explicit RCSwitch transmission. The separate
`config/packages/living_curtains_rf.yaml` package adds learned Dooya transmission
with Wi-Fi fallback for the living-room curtains. Existing ESPHome motion
entity IDs and their callers are unchanged. The receive example never calls the
transmitter or a load.

Bluetooth lighting uses a separate radio path: the ESP8266 RF node has no
Bluetooth hardware. See [Bluetooth proxy commissioning](bluetooth-lighting.md)
for the enabled EchoLocal receivers, private remote captures, and the remaining
requirements before controlling the living-room chandelier.

## Source and deployment status

The source is the public [RF Airbridge project](https://github.com/ha-homelab/rf-airbridge).
The Dooya deployment was based on reviewed public revision
[`d33918a39135f07aafbd76e92f60470abf9c945b`](https://github.com/ha-homelab/rf-airbridge/commit/d33918a39135f07aafbd76e92f60470abf9c945b),
which adds a Dooya action alongside RCSwitch. The current deployment also
includes the [RM433 receive decoder](https://github.com/ha-homelab/rf-airbridge/commit/91ba2a9428c6208b9379b000f00322495675366e),
with its commissioning record below. The initial RCSwitch deployment
used
[`5337ae75c9d5b40daa845faf20a3572ef21c68a8`](https://github.com/ha-homelab/rf-airbridge/commit/5337ae75c9d5b40daa845faf20a3572ef21c68a8);
its runtime evidence below remains historical. The corrected public RCSwitch
Home Assistant example is pinned separately to
[`adf9c0fdc025566754ca63e19557433c1785b2ed`](https://github.com/ha-homelab/rf-airbridge/blob/adf9c0fdc025566754ca63e19557433c1785b2ed/examples/home-assistant.yaml).
This private adaptation removes the YAML counter definition and replaces the
synthetic match with the existing Hallway Two Motion code from the local ESPHome
source. The private code stays in this repository.

The storage-backed counter helper has been created and its exact entity ID
verified without restarting Home Assistant. The initial package passed the
installed configuration check and was loaded through guarded domain reloads,
but its transmit script remained unavailable. Home Assistant's recursive package
merge discarded the empty `text: {}` selector before validating the script.
The corrected package uses `text: {multiline: false}` so that the selector type
survives that merge. It is now installed from private revision
[`bc91eec0a3f3713f7563d5c338f65049477db6eb`](https://github.com/ha-homelab/home-assistant/commit/bc91eec0a3f3713f7563d5c338f65049477db6eb),
and the transmit script is available. The receive automation, rejection paths,
firmware transmit completion, and return to reception were verified as recorded
below. Delivery to an independent target receiver was not verified.

## RM433 receiver tuning on 2026-10-11

Commissioning a Sonoff RM433 did not initially produce a repeatable sequence
of eight decoded button codes. The capture contained the existing motion
codes and malformed short-pulse frames. The device configuration used a
250 microsecond input filter, above the approximately 238 microsecond pulse
reported for RM433 in the
[Tasmota receive example](https://tasmota.github.io/docs/RF-Protocol/#receiving-rf-codes).
The filter was lowered to `100us`; frequency, 30% tolerance, 4 ms idle timeout,
the 15 motion definitions, and both transmit actions were preserved.

Nearby captures confirmed approximately 240 microsecond pulses and eight
distinct button codes. Lowering the filter alone was insufficient: ESPHome's
stock protocol-1 decoder assumes 350 microseconds. RF Airbridge now has a
separate bounded 24-bit decoder that publishes `format: rm433` events. It checks
the entire frame and trailing sync, and suppresses copies of the same code
until a 350 ms quiet interval. Existing motion decoding is unchanged.

The receiver patch remains pinned to ESPHome **2026.8.2**. The final firmware
compiled and uploaded successfully: 461,344 bytes, SHA-256
`aa00305e89d2bc50a97dcef248545e3dad7ca5f23247000eb9b2c3e577320124`.
All 37 source tests passed, including malformed-frame rejection, repeated
packets, different buttons, and timer rollover. Native API comparison confirmed
all 16 pre-existing entities and both action signatures unchanged. All 15
motion entities remained available, and existing motion codes were received.
This does not establish individual physical testing of every sensor.

The tuned source was saved in the ESPHome dashboard's `/config/rf.yaml` and
HA's `/config/esphome/rf.yaml`. HA's older source copy lacked the Airbridge
package; its required package, headers, and receiver component were copied
alongside it. Previous files and the exact prior firmware are retained for
rollback. The installed dashboard runs ESPHome 2026.9.1, so its normal build
command intentionally fails the receiver component's version guard; use
2026.8.2 until that component is reviewed and rebased. Do not remove the guard
merely to make a newer build pass.

The retained MQTT discovery manifest is
[`config/mqtt_discovery/sonoff_rm433.json`](../config/mqtt_discovery/sonoff_rm433.json).
It creates the **Sonoff RM433** device, eight
`event.sonoff_rm433_button_1` through `event.sonoff_rm433_button_8` entities, and
eight device-automation triggers. Numbering follows the user's physical pass:
left to right, top to bottom. Event templates require the exact bridge, radio
origin, format, bit count, and learned code; unrelated messages produce an
empty dictionary, which MQTT event entities ignore. Discovery is retained at
QoS 1; radio events are not retained. To restore discovery, publish each JSON
entry's `payload` as JSON to its `topic` with QoS 1 and retain enabled.

One final physical press of button 1 produced exactly one radio event, and HA's
Button 1 entity stored the same radio event ID. The other seven entities stayed
untouched. No synthetic receive event was injected. Raw learning was disabled
after commissioning. The user requested buttons only: no load-control actions
or automatic RF retransmission were added. Private capture, build, comparison,
and rollback evidence lives under `ha/rm433-assessment` in the operator workspace.

## Dooya firmware upgrade on 2026-10-06

The private device configuration was compiled with ESPHome 2026.8.2 against
public revision `d33918a39135f07aafbd76e92f60470abf9c945b`. The binary is
460,944 bytes with SHA-256
`2ef6e213f62e8cb6d82a480b70d98dcb20f12ee4fc823568b08f15fc523b62d3`.
The build reported RAM use of 41,332/81,920 bytes and flash use of
456,795/1,044,464 bytes.

OTA completed successfully. All 15 legacy RF sensor entities remained present,
and the native API and Home Assistant expose both `esphome.rf_send_rf_code`
and `esphome.rf_send_dooya_code`. A Dooya request with `remote_id: -1` produced
`invalid_request` without transmission. The existing RCSwitch receive example
and package were retained.

The [living-room curtain runbook](living-curtains-rf.md) records the separate
helper package, three scheduled callers, Wi-Fi fallback, scoped HA installation,
and commissioning results. The live Close-both helper test completed two Dooya
transmit sequences and both independent Wi-Fi fallbacks. Real RF reception
resumed on the same post-OTA boot. Physical curtain movement and RF delivery to
either motor have not been visually confirmed; `send_finished` remains a
firmware result, not an acknowledgement. Firmware and installation receipts are
retained privately under `work/rf-dooya-upgrade-private`; no learned identifiers are
stored in public documentation.

## Initial RCSwitch runtime verification on 2026-10-06

The corrected package alone was installed at
`/config/packages/rf_airbridge.yaml`, with SHA-256
`7b72a098137ec6d49c7cfbb12486f65f19ffbd576b6e8cef14c7f30d9fc33f10`.
The installed Home Assistant configuration checker reported zero errors.
Unrelated configuration and `/config/release.json` were preserved. The private
package receipt is `work/rf-upgrade-private/ha-selector-install-bc91eec0.json`;
the remote rollback copy and check log are under
`/config/.rf-airbridge-selector-fix-u5o3n1sn`. These private artifacts are not
stored in this repository.

- **Reload guards:** the initial guards refused reloads while existing camera
  and motion actions were active. Later guarded script and automation reloads
  succeeded. After installing the selector correction, a fresh guarded script
  reload succeeded and `script.rf_send_code` became available.
- **Existing behavior:** all 15 existing RF entities remained available in Home
  Assistant, and the four previously disabled automations remained off. Entity
  availability does not establish that every physical sensor was individually
  exercised during this test.
- **MQTT consumer:** one deliberately injected matching message changed
  `counter.rf_received_example` from 2 to 3. Its unique test marker appeared in
  the automation trace, which reached `action/1`. This confirms MQTT-to-HA
  consumption; this particular message was synthetic, not a radio reception.
- **Raw learning:** enabling raw learning through Home Assistant produced two
  raw frames. Turning it off left both the API and MQTT entities off.
- **HA input validation:** an invalid script request returned HTTP 200, but its
  trace stopped as aborted at `sequence/0/then/0`, with no transmit action. The
  HTTP status alone therefore does not establish that a code was accepted.
- **Firmware input validation:** a direct native-action request with protocol 0
  produced `invalid_request` over MQTT and no `send_finished` event.
- **Valid transmit sequence:** a synthetic 64-bit code with protocol 1 and three
  repeats was sent through `script.rf_send_code`. Firmware reported
  `send_finished`, `receiver_resumed: true`, and `delivery_confirmed: false`.
  This establishes completion of the firmware's transmit sequence, not receipt
  or operation of a separate device.
- **Reception after transmit:** a real received frame appeared 3.927 seconds
  later with the same boot ID, and 87 post-transmit frames were observed. The
  node therefore returned to receiving without a reboot in this observation.
  One 334 ms API operation warning occurred during the blocking transmit call.

An independent target-delivery test was not available. Do not treat
`send_finished` as an RF acknowledgement or remove `delivery_confirmed: false`
from that interpretation. The verified path is the HA request, firmware
transmit completion, and subsequent radio reception.

## Required helper

Create the Counter helper **RF received example** in Home Assistant with:

- Entity ID: `counter.rf_received_example`.
- Initial value: `0`.
- Step: `1`.
- Restore state: enabled.
- Icon: `mdi:counter`.

Use **Settings > Devices & services > Helpers > Create helper > Counter**.
The existing counter integration has no YAML reload action in this installation;
creating the storage-backed helper avoids restarting Home Assistant. If an
existing helper already has this exact entity ID, reuse it instead of creating a
suffixed duplicate. The package intentionally omits `counter:` so that storage
and YAML do not compete for the same identity.

The helper's definition and restored value are runtime storage, not Git files.
Include Home Assistant storage in normal backups. After restoring configuration
without storage, recreate the helper with the same entity ID before loading the
automation. No received-event history is required by this demonstration.

## Receive behavior

The new automation has immutable ID `rf_mqtt_received_example` and English alias
**RF: Count a received motion code**. It listens to `rf/received`, accepts JSON
objects only, and requires the configured source, radio origin, RC-Switch format,
integer protocol, integer bit length, and exact binary code. A match increments
the helper once, then keeps the automation occupied for 750 ms. `mode: single`
discards further matching invocations during that interval. A long RF burst can
produce another count after the interval; this is not a motion occupancy sensor.

The event stream uses QoS 0 and nonretained messages. It is a live observation
stream, not an event archive. Do not infer an off state from silence. The
`origin` field is descriptive, not authenticated; trust and restrict broker
publishers. A deliberately injected matching MQTT message tests the MQTT and HA
path only. Natural reception and a changing counter establish the additional RF
path.

## RCSwitch transmit behavior

The code field's text selector must contain `multiline: false`; do not simplify
it to an empty mapping. The test suite loads the package through Home
Assistant's actual YAML include and package-merge path, verifies the script is
registered, and reproduces the dropped selector with the old empty mapping.

Call `script.rf_send_code` from **Developer tools > Actions**, supplying a binary
string `code`, integer `protocol` from 1 to 8, and optional integer `repeats` from
1 to 10. Repeats default to 3. Quote codes in YAML to preserve leading zeroes.
The script rejects invalid values before calling `esphome.rf_send_rf_code`.
Home Assistant records this `stop`/`error` path as an aborted script; the
top-level service request may still return normally. Check the trace and absence
of a transmit action rather than treating an HTTP status as input validation.
It has no scheduled trigger and is not called by the receive example.

The ESPHome native API action must be registered for the connected `rf` node.
An action call is not an acknowledgement from the target RF device. The firmware
must support the requested protocol, and physical operation needs separate
observation. The CC1101 pauses reception while transmitting through its shared
data pin. Never connect the receive stream directly back to this script.

## Dooya transmit behavior

Use `esphome.rf_send_dooya_code` for the separate Dooya 40-bit frame format.
Its integer fields are `remote_id` (0–16,777,215), `channel` (0–255),
`button` and `check` (0–15 each), and `repeats` (1–10). Supply a verified learned
profile rather than adapting an RCSwitch binary string. The living-room helper
uses private secret references, observed Open/Close variants, three repeats,
and two seconds between dispatches.

Both formats share one firmware transmit worker. Requests received during a
transmission or its 750 ms cooldown return `busy`; the firmware does not queue
them. A `send_finished` result precedes the end of this cooldown and still has
`delivery_confirmed: false`. Use the queued HA helper for the curtain schedules
and retain their independent Wi-Fi fallbacks. The MQTT receive bridge continues
to decode stock RCSwitch frames; this upgrade does not add Dooya receive decoding
or change receiver timing. See the pinned public
[Dooya protocol guide](https://github.com/ha-homelab/rf-airbridge/blob/d33918a39135f07aafbd76e92f60470abf9c945b/docs/dooya-transmission.md)
for frame and shared-worker details.

## Initial RCSwitch deployment: stage all, deploy only the RF package

The initial prepared root revision was
`5242f9ee5b44f05cb624acdbec3e28b6e9d95a07` from
[PR #74](https://github.com/ha-homelab/home-assistant/pull/74). The immutable
`config/packages/rf_airbridge.yaml` file had SHA-256
`2c2e1bea81bf511c436e8b0bf805bd7b7da98e4ad013495d08d3e772e1cb475b`.
That package is superseded by the text-selector correction described above. The
corrected package from `bc91eec0a3f3713f7563d5c338f65049477db6eb` has SHA-256
`7b72a098137ec6d49c7cfbb12486f65f19ffbd576b6e8cef14c7f30d9fc33f10`,
matching the installed file recorded above.

Full staging initially failed because a private YAML `!include` target was
absent. In addition to `secrets.yaml`, this installation requires the referenced
`home-media-service-account.json` alongside it in the staged configuration.
Copy required private include files from the existing secret source to the
private staging directory, preserve restrictive permissions, and rerun the
installed configuration check. Do not put their contents in Git or command
output. `tools/build.py --secrets` copies only the explicitly supplied secrets
file; it does not automatically copy files referenced by that file. With the
required private include present, the complete staged configuration passed.

The comparison with the running instance found other differences in
`configuration.yaml`, custom sentences, HACS maintenance configuration, and the
scripts directory. A successful staged check does not establish that those
unrelated differences should be promoted. This deployment therefore installs
only the RF package, using the existing live configuration for its final check.

Do not use `tools/promote.py --scope overlay` for this scoped deployment: it
would also replace unrelated live files. Its `--scope automations` option does
not include packages. Keep `/config/release.json` unchanged, because the running
configuration as a whole does not match the assembled root release. Record this
package's source revision and checksum in a separate private deployment receipt.

## Scoped deployment and verification procedure

1. Create or verify the helper above. Do not change existing helpers or disabled
   automation states.
2. Build a clean, committed root checkout with its bundled libraries using the
   [normal staging workflow](deployment.md). Include the private referenced files
   described above, and check the staged configuration with the installed Home
   Assistant version. Keep credentials outside Git.
3. Verify the RF package checksum against the immutable merged revision. Back
   up the existing `/config/packages/rf_airbridge.yaml`, or record that it did
   not exist. Write the new package to a temporary file on the same filesystem,
   then atomically replace that one destination. Do not copy other staged files
   or the staged `release.json` into the live configuration.
4. Run the installed Home Assistant configuration checker against the live
   configuration before reloading anything. If it reports errors, atomically
   restore the previous package, or remove the newly added file if none existed,
   and recheck. Retain the private backup and failed-check output for diagnosis.
5. Record the package source revision, SHA-256, previous-file state or checksum,
   backup location, destination, and configuration-check result in the separate
   private package receipt. This receipt supplements the existing root release
   metadata without replacing it.
6. Take a fresh state export and pass `tools/verify_idle.py` immediately before
   each reload. Reload scripts and automations after active work completes.
   A counter reload is neither required nor available here.
7. Confirm `script.rf_send_code`, the new automation, and the exact helper
   identity. Verify existing motion entity IDs and enabled states are unchanged.
8. Observe a natural matching RF event and counter increment. A synthetic MQTT
   match may separately verify broker-to-automation plumbing but is not radio
   evidence. Test invalid script input and confirm no transmitter call occurs.
9. Verify actual transmission separately with an intended receiver or an
   independent passive receiver, recording what was observed. Do not label
   successful API dispatch as physical transmission proof.

For rollback after a reload, restore only the previous RF package state, rerun
the installed configuration check, and reload scripts and automations only after
fresh idle checks. Leave unrelated configuration and `release.json` untouched.
The helper can remain for diagnosis; remove it separately if desired after its
automation has been unloaded. Keep the private package receipt, previous release,
and firmware backups until recovery is accepted.
