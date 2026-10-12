# KMC Switch17–Switch19

A fourth KMC 30608 runs ESPHome 2026.9.1 using the accepted profile:

- Physical outlet 1, GPIO15: `switch.switch17` / Switch17.
- Physical outlet 2, GPIO13: `switch.switch18` / Switch18.
- Physical outlet 3, GPIO14: `switch.switch19` / Switch19.
- The fourth physical outlet is always on and has no relay entity.

The GPIO16 button turns all three relays off if any is on, or all on if all
are off. GPIO1 supplies inverted network status. Individual outlet indicator
behavior was not re-investigated. Repeated physical tests were waived by the
owner; independent native/HA control and software restart to all OFF passed.

The shared HLW8012 exposes `sensor.kmc_switch17_19_voltage`,
`sensor.kmc_switch17_19_current`, `sensor.kmc_switch17_19_power` and
`sensor.kmc_switch17_19_energy_since_boot`. These are shared readings, not
measurements for each outlet. They remain uncalibrated, explicitly marked by
`sensor.kmc_switch17_19_meter_calibration`; energy resets at reboot.

Complete private source and distinct secrets are saved in HA and ESPHome
Dashboard as `kmc-switch17-19.yaml` with two compile workers. Both source
copies and deployed configuration validation passed. Lovelace places all
three controls after Switch16. Final relay states are all OFF.
