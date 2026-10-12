# Bluetooth proxy commissioning and the living-room chandelier

## Hardware and scope

The RF node is an ESP8266 NodeMCU v2 with a CC1101, not an ESP32. Its live
ESPHome API reports model `nodemcuv2` and Bluetooth feature flags `0`. Neither
chip supplies a Bluetooth radio, so the existing RF firmware cannot become a
Bluetooth proxy. The RF configuration and curtain automations remain unchanged.

The living-room chandelier is an older, unbranded Chinese fixture operated by
a physical remote marked **GM2.4G**. The owner remembers a Bluetooth marking
on the module, but there is no known phone app. The remote's 2.4 GHz label does
not establish Bluetooth compatibility. Its protocol and a matching HA light
integration are not yet established. Do not infer a working light from the
existence of a Bluetooth proxy or from an assumed HA state.

## Proxies enabled on 2026-10-06

Two existing EchoLocal devices expose Bluetooth proxy switches through their
ESPHome integrations:

- `switch.echo_audiocenter_bluetooth_proxy`
- `switch.echo_dot_002_bluetooth_proxy`

Both switches were initially off. Both are now on, and Home Assistant's
Bluetooth scanner subscription reports both remote scanner sources. The
observed EchoLocal device reports Bluetooth feature flags `97`, corresponding
to passive scanning, raw advertisements, and scanner state/mode support.
This does not include GATT connections or a service for transmitting arbitrary
lamp-control advertisements. Native service discovery did not expose a
`ble_adv_proxy` transmitter on the inspected Echo.

The configuration also contains an ESP32 `presence1` with a Bluetooth proxy,
but its configured hostname did not resolve and it is not an active scanner
in HA. Do not treat the YAML file alone as evidence of available hardware.
The ESP32 JBD battery monitors have existing BLE responsibilities and were not
changed for lighting.

Proxy switches are device settings; no new startup automation forces their
state. They can be enabled with the standard HA `switch.turn_on` action. To
undo this commissioning change, call `switch.turn_off` for the two entities
above. No HA restart, configuration reload or RF firmware upload was needed.

## Verified behavior

- Before commissioning, HA reported no active Bluetooth scanner sources.
- After enabling the proxies, live BLE advertisements arrived from both
  sources, including raw advertising bytes.
- The existing Govee H5106 temperature, humidity and PM2.5 entities changed
  from unavailable to numeric readings.
- Both Echo voice satellites and their speakers were available and idle in
  the post-change snapshot. This is an availability check, not an acoustic
  playback test.
- All 15 `binary_sensor.rf_*` entities remained available. The three living
  curtain helper scripts remained available and idle.
- The public RF Airbridge capture tool completed a live read-only test:
  both subscriptions were acknowledged, events were written with mode 0600,
  and the access token was absent from the saved file.

The first three **On** presses and a second series of ten **Brightness +**
presses did not produce a command recognized by the 53 codec variants in the
offline decoder. The owner confirmed that the chandelier responds to the
remote. Existing nearby BLE traffic was received during the test, so reception
was operational. No new strong signal could confidently be linked to the
button presses. The completed capture contains 69 observations from 29 device
addresses through two scanner sources, with no known lamp-codec matches.
This result does not prove that the chandelier uses a different radio standard:
the remote signal may be unsupported, missed, or carried over an active
connection. The GM2.4G marking makes proprietary 2.4 GHz RF a candidate, rather
than confirming the original Bluetooth assumption.

## GM2.4G identification boundary

A related [2.4G driver manual distributed by Lowe's](https://pdf.lowes.com/productdocuments/72a8bf2f-8d2e-4931-b533-8cb172b4f5c2/62447664.pdf)
describes paired remote groups, brightness/color operation and pairing reset
sequences. It does not document the over-the-air protocol or prove that this
particular remote is interchangeable with other 2.4 GHz products. No pairing
or reset sequence was performed during this investigation.

For comparison, [esp8266_milight_hub](https://github.com/sidoh/esp8266_milight_hub)
supports specific MiLight CCT remotes and combines an ESP with an NRF24L01+
or LT8900 radio. It offers passive packet listening and MQTT integration with
HA. **GM2.4G compatibility has not been verified**: neither a similar case nor
the frequency is sufficient evidence. Do not buy a gateway or flash the
working RF bridge assuming compatibility. Its CC1101 cannot receive 2.4 GHz.

A [first-hand report with teardown photographs of GM-marked remotes](https://github.com/sidoh/esp8266_milight_hub/issues/266#issuecomment-518480502)
describes MiLight-like CCT hardware that did not work with that bridge. This is
historical evidence about similar hardware, not identification of this remote,
but it reinforces why visual similarity alone is not a compatibility test.

The next useful evidence is a clear view of the remote's button layout and
labels, followed by the radio-chip marking if its battery-powered case can
be opened easily. Do not open the mains-powered chandelier for this step.
If a compatible 2.4 GHz protocol is established, use a suitable separate
transceiver; if not, a different hardware approach will be required.

## Next commissioning steps

Use the [RF Airbridge Bluetooth guide](https://github.com/ha-homelab/rf-airbridge/blob/main/docs/bluetooth.md)
and `tools/capture_bluetooth.py` to record one button at a time. Captures are
private because they contain nearby devices' identities and payloads. Local
evidence and the offline decoder are under `work/bluetooth-light-private`; no
captures, remote identifiers, access tokens or keys are committed here.

The offline decoder was taken from
[`NicoIIT/ha-ble-adv` revision `10fb6edac13930cc78a56811147aa8d262d49eb9`](https://github.com/NicoIIT/ha-ble-adv/commit/10fb6edac13930cc78a56811147aa8d262d49eb9).
A known upstream test vector decoded successfully before examining live
captures. The decoder was run locally; the custom integration was not installed
in production HA. Matching a packet must still be tied to the physical button
and the chandelier's response.

If the remote uses a supported BLE advertising protocol, add a compatible
transmitter and the matching integration. A standard EchoLocal receive proxy
alone is insufficient for this path. If the fixture uses GATT, choose the
appropriate integration and an active-connection-capable adapter instead.
Do not pair blindly or create a synthetic light entity that merely reports
success without operating the fixture.

Acceptance requires physical On/Off, at least two brightness values, both
warmer and cooler settings, operation of the original remote, and recovery
after a proxy reconnect. Record which states are acknowledged versus assumed.
