# Switch11

The XS-SSA05 uses ESPHome 2026.9.1 under device/friendly name Switch11 and
entity `switch.switch11`. Its ordinary Tuya-Convert migration succeeded on this
sample's stock firmware 1.0.1; this does not establish OTA support for every
XS-SSA05 variant.

The GPIO12 relay starts OFF; the physical GPIO13 button toggles it. The active-low
GPIO0 red indicator follows the relay. Inverted GPIO15 blue indicates connection
or warning status, and the separate GPIO4 faint blue output is kept OFF.
The owner confirmed button/load/red-indicator operation. Native and HA state
commands and software restart to OFF passed. A controlled mains-cycle test
remains unperformed.

The shared meter exposes `sensor.switch11_voltage`, `sensor.switch11_current`,
`sensor.switch11_power`, `sensor.switch11_energy_since_boot` and
`sensor.switch11_meter_calibration`. These readings are **not calibrated**;
the initial voltage scale was visibly inaccurate. Energy resets at reboot.

The full source is saved as `switch11.yaml` in HA's `/config/esphome` and
ESPHome Dashboard's `/config`, with separate named secrets and two compile
workers. Runtime secrets, addresses, hardware identifiers and images stay private.
Lovelace includes Switch11 at the bottom after Switch10. No old HA identity
matched this device, so no previous entity was removed. Final relay state: OFF.
