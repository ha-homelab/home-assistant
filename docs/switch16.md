# Switch16

A fourth XS-SSA05 runs ESPHome 2026.9.1 as `switch.switch16`, using the accepted
Switch11 profile. The owner requested reuse without repeated physical checks.
Native and HA control and software restart to OFF passed; no new physical
button/load/indicator or mains-cycle acceptance is claimed.

GPIO12 is the relay, GPIO13 the active-low button, GPIO0 the active-low red
indicator following the relay. Inverted GPIO15 provides blue connection status;
GPIO4 stays off to avoid residual blue glow. The output switches on/off only.

Voltage, current, power and energy since boot are exposed as
`sensor.switch16_voltage`, `sensor.switch16_current`, `sensor.switch16_power` and
`sensor.switch16_energy_since_boot`. Readings remain uncalibrated, explicitly
marked by `sensor.switch16_meter_calibration`; energy resets at reboot.

The full source is saved as `switch16.yaml` in HA and ESPHome Dashboard, with
distinct named secrets and two compile workers. Both saved copies were verified
and deployed configuration validation passed. Lovelace places Switch16 after
Switch15. The owner explicitly chose number 16. Final relay state: OFF. Runtime identity, credentials and firmware
remain private.
