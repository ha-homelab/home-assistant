# Switch06 ESPHome maintenance

## Current name: Switch06

After the earlier update below, the owner renamed s6 to **Switch06** on
2026-10-11. The controls are now `switch.switch06` and secondary
`switch.switch06_mqtt`. All 25 entity IDs/display names, both device names and
the ESPHome integration title follow Switch06; their registry and hardware
identities remain unchanged by this second rename. The shared MQTT integration
keeps its original title. Seven active automations now use Switch06 references,
with all existing thresholds, the 750 W estimate and action order preserved.

Lovelace places Switch06 immediately after Switch05 and before Switch07 at
the bottom of the Lighting entities card. The saved source is `switch06.yaml`
in both HA and ESPHome Dashboard. Its friendly name is Switch06; native node
name `s6`, component names, MQTT topics, calibration and credentials remain
unchanged. This rename performs no OTA, relay command or device restart.
HA overrides expose the requested names until a future firmware update.

## Earlier update and initial s6 name

On 2026-10-11, the existing iNewSwitch ESP8266 outlet was updated from ESPHome
2025.4.0 to stable 2026.9.1 and renamed **s6**. The primary control is
`switch.s6`; the existing secondary MQTT control is `switch.s6_mqtt`.
Both device records use the display name s6.

The existing relay/button/LED GPIOs, power-meter calibration, credentials and
`ALWAYS_OFF` behavior were retained. The uptime unit was corrected from
`minutes` to Home Assistant's supported `min`; the numeric measurement is
unchanged. Internal component names and the MQTT state/command prefix remain
stable for existing consumers.

Twenty-five entity IDs and display names were normalized. Twenty-two existing
registry identities, including the primary API entities and energy
measurements, were retained. ESPHome changed the secondary MQTT unique IDs for
signal, uptime and version; these three diagnostics now use new identities.
The invalid old uptime registry entry and superseded retained discovery topics
were removed; recorder history was not edited or purged.

Seven existing automations now reference `switch.s6` or `sensor.s6_signal`.
Their schedules, guards, actions, 750 W load estimate and persistent automation
IDs are unchanged. Lovelace's existing outlet item was updated in place. The
legacy `random_on_inew` and `shutdown_inew` scripts control a separate host and
were not renamed.

Private firmware source is stored as `s6.yaml` in both HA's `/config/esphome`
and the ESPHome Dashboard's `/config`. It replaces `inewswitch.yaml`; the total
remains 25 plug configurations. No credentials or compiled firmware are stored
in this repository.

Validation: firmware compiled below 512 KiB; OTA and subsequent API reconnect
succeeded; Dashboard 2026.9.1 validated the source; HA's complete configuration
check passed. The seven changed automations were reloaded individually by ID,
preserving two unrelated active motion-off timers. Both controls reported OFF,
the firmware-version sensor reported 2026.9.1, and voltage/current/power/uptime
were available. No relay toggle was requested for verification.

After a node rename, refresh HA's ESPHome Dashboard coordinator before reloading
that device's config entry. Its five-minute cache can temporarily lack the new
name and cause the existing firmware-update entity to interrupt reconnect.
`homeassistant.update_entity` on an already-loaded ESPHome firmware-update
entity refreshes this metadata without installing firmware.
