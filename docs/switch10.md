# Switch10

The sixth converted WP5 uses ESPHome 2026.9.1. Its device name, friendly name
and entity ID are Switch10, Switch10 and `switch.switch10` respectively.

It reuses the previously accepted WP5 profile: GPIO13 active-low button,
GPIO15 relay and inverted GPIO2 indicator. The relay uses `ALWAYS_OFF` and the
indicator follows its commanded state. GPIO0 remains unassigned. The different
Gosund WP5 map must not be substituted based only on the model name.

Encrypted API identity, native and HA on/off state control, and software restart
from ON to OFF passed. Repeated physical button/load, indicator and controlled
mains-cycle tests were skipped under the owner's existing profile-reuse request;
these checks are not recorded as physically passed for this unit.

The complete source is saved as `switch10.yaml` in HA's `/config/esphome` and
ESPHome Dashboard's `/config`, using distinct named secrets and a two-worker
compile limit. Credentials, device identifiers, firmware and logs remain private.

Overview / Lighting includes Switch10 immediately after Switch09 at the bottom.
Reusable rows are in [dashboards/retained-switches.yaml](dashboards/retained-switches.yaml).
No old HA identity matched this plug; no previous entities were removed.
Final state: OFF.
