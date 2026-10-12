# Switch08 and Switch09

The second SUPERNIGHT CV01 uses ESPHome 2026.9.1 and exposes two independent
controls under one device, **Switch08 + Switch09**:

- `switch.switch08` — Switch08, the owner's left-hand control, ADC button and GPIO12 relay.
- `switch.switch09` — Switch09, the owner's right-hand control, GPIO1 button and GPIO3 relay.

A separate left-button press confirmed the ADC input in the owner's viewing
orientation. The previous CV01's button-to-relay coupling is retained. The owner
explicitly requested reuse of that profile and waived repeated outlet/load,
button/load and controlled mains-cycle tests. Native API control of each relay
and a software restart from both ON to both OFF passed. Physical load mapping
and mains-cycle acceptance for this sample remain unverified.

Both controls use `ALWAYS_OFF`. Voltage, current, power and energy since boot
are available for the complete device, with a `Not calibrated` diagnostic.
The shared measurements use the `sensor.switch08_switch09_` prefix; they do
not provide separate power readings for the two outlets.

The complete source is saved as `switch08-switch09.yaml` in HA's
`/config/esphome` and ESPHome Dashboard's `/config`, with separate named secrets.
Firmware images, credentials, device identifiers and raw logs remain private.

Overview / Lighting includes both controls at the bottom, after Ping02.
Reusable rows are in [dashboards/retained-switches.yaml](dashboards/retained-switches.yaml).
No preexisting LocalTuya or MQTT record matched this unit. No old device was
removed or reassigned.

The unidentified white-and-silver outlet previously reserved as Switch08
remains deferred and unflashed. Its number reservation was released when the
owner assigned Switch08 to this CV01.
