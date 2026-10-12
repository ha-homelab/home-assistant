# Roomba connection recovery

`config/packages/roomba_recovery.yaml` shares one recovery loop across all five
Roomba config entries. It does not change the built-in integration or its retries.
The loop runs every minute, including after automation reloads and HA restarts.

A robot is eligible only when:

- Its dedicated Ping sensor has continuously reported online for at least 60 seconds.
- Its vacuum entity has been unavailable/unknown for at least 120 seconds.
- Its enabled Roomba entry is loaded or awaiting a setup retry, not setting up,
  unloading, awaiting credentials, or manually disabled.
- Its last extra recovery attempt was at least 15 minutes ago.

The loop records an attempt before reloading that robot's entry with
`homeassistant.reload_config_entry`. Each robot has a persistent date/time helper,
so an unsuccessful reload or an HA restart does not erase the cooldown. A failed
reload does not block eligible robots later in the list. A missing helper stops
recovery for that robot. Working robots receive no actions; cleaning is never
started, stopped or commanded by this automation.

## Ping setup

Create one stock Ping entry per address using Settings / Devices & services or
the supported configuration-flow API. Set Count to 2 and Consider home to 0;
retain the default 30-second polling interval. Give the binary sensor the exact
ID below. Existing unrelated Ping entries, including the retired Eero Shed,
must remain unchanged.

- `192.168.167.6`: `binary_sensor.roomba_network` → `vacuum.roomba`
- `192.168.167.26`: `binary_sensor.roombaryan_network` → `vacuum.roombaryan`
- `192.168.167.27`: `binary_sensor.i7_network` → `vacuum.i7`
- `192.168.167.36`: `binary_sensor.roombaalex_network` → `vacuum.roombaalex`
- `192.168.167.12`: `binary_sensor.roomba9_network` → `vacuum.roomba9`

Keep these robot addresses reserved in DHCP. After installing the package, reload
`input_datetime` and then `automation`; an HA restart is unnecessary. Disabling
this one automation disables the extra recovery loop while native retries remain.

This supplements native retry handling; it does not suppress offline attempts,
repair Wi-Fi, or prove that an ICMP-responsive robot can accept an MQTT connection.
During commissioning the four other robots responded from the HA container while
i7 did not respond to ICMP or TCP 8883. Its next successful reconnection therefore
remains a live observation, not a claimed test result.

References: [Ping](https://www.home-assistant.io/integrations/ping/),
[integration reload](https://www.home-assistant.io/integrations/homeassistant/),
[native setup retries](https://developers.home-assistant.io/docs/integration_setup_failures/).
