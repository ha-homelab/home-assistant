# Switch21 — KMC 30137

Switch21 is the fourth converted KMC 30137, using ESPHome 2026.9.1 and the
previously accepted profile:

- `switch.switch21`: GPIO14 relay, ALWAYS_OFF at startup.
- GPIO1: active-low physical button, 20 ms debounce, toggles the relay.
- GPIO13: inverted relay indicator, follows ON/OFF.
- UART logging disabled because GPIO1 is the physical button input.

The owner confirmed the plug unloaded and reused the accepted profile without
repeated physical tests. Encrypted API identity, native relay control, software
restart from ON to OFF and HA ON/OFF commands passed. Final relay state is OFF.
No physical acceptance or measured boot transient is claimed for this unit.
No metering is configured by the accepted hardware profile.

Complete private configuration and distinct credentials are persisted in both
HA and ESPHome Dashboard as `switch21.yaml`, with two compilation workers.
Source readback and deployed configuration validation passed. Lovelace places
Switch21 immediately after Switch20 in the existing numbered controls.
