# Switch12

A second XS-SSA05 runs ESPHome 2026.9.1 as `switch.switch12`, using the accepted
Switch11 profile. The owner requested reuse without repeated physical checks.
Native and HA control and software restart to OFF passed; no new physical
button/load/indicator or mains-cycle acceptance is claimed.

GPIO12 is the relay, GPIO13 the active-low button, GPIO0 the active-low red
indicator following the relay. Inverted GPIO15 provides blue connection status;
GPIO4 stays off to avoid residual blue glow. The output switches on/off only.

Voltage, current, power and energy since boot are exposed as
`sensor.switch12_voltage`, `sensor.switch12_current`, `sensor.switch12_power` and
`sensor.switch12_energy_since_boot`. Readings remain uncalibrated, explicitly
marked by `sensor.switch12_meter_calibration`; energy resets at reboot.

The full source is saved as `switch12.yaml` in HA and ESPHome Dashboard, with
distinct named secrets and two compile workers. Both saved copies were verified
and deployed configuration validation passed. Lovelace places Switch12 after
Switch11. Final relay state: OFF. Runtime identity, credentials and firmware
remain private.
