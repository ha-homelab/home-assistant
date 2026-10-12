# Ping outlets

The 2026-10-11 additions appear at the bottom of Overview / Lighting immediately
after Switch07: **Ping01**, then **Ping02**. The later
[Switch08 / Switch09](switch08-switch09.md) addition follows Ping02. The reusable rows are in
[dashboards/retained-switches.yaml](dashboards/retained-switches.yaml).

- `switch.ping01` — former AirBnB Fridge AWP02L-N, converted from Tuya.
  GPIO13 active-low button, GPIO15 relay, inverted GPIO2 indicator.
- `switch.ping02` — former Ozon Tasmota MJ_XS-SSA01, migrated to ESPHome.
  GPIO13 active-low button, GPIO15 relay, inverted GPIO12 indicator.

Both run ESPHome 2026.9.1 with encrypted API/OTA and `ALWAYS_OFF`. The owner
confirmed physical button, actual load and indicator operation. Software
restart from ON returned each relay to OFF; controlled mains-cycle checks
remain pending. Ping02's earlier load failure did not recur in this test.

The old `switch.airbnb_fridge_2` device was removed from LocalTuya, preserving
all other device configurations. Ozon's exact MQTT device and retained
Home Assistant discovery topics were removed, including `switch.ozon`,
`binary_sensor.sonoff_button1_3`, and `sensor.sonoff_status_3`. The latter two
obsolete customization entries were removed. No Ozon LocalTuya match existed.
No active automations, scripts or other dashboard rows referenced these old IDs.

Private sources `ping01.yaml` and `ping02.yaml` are stored in both HA
`/config/esphome` and the ESPHome Dashboard `/config`. Credentials, firmware
images, raw registry backups and hardware MAC addresses remain private.
