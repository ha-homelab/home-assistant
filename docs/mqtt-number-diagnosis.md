# MQTT Number diagnosis: BatteryLife SoC limit

Status: **corrected and deployed on 2026-09-22** after the owner's request to fix
this finding. The number now uses the live register's **0–100** bounds and reports
**5%** instead of `unknown`. Its ID, name, step, templates and MQTT topics are
unchanged. This also widens the existing writable number's accepted input range;
no value was written to Cerbo. The user minimum and effective threshold both
remain **15%**. See the [deployment and rollback evidence](releases/2026-09-22-mqtt-soc-limit.md).

The read-only diagnosis below was completed on 2026-09-15. The original
automation/script migration deliberately preserved these bounds until this
separate correction. Its evidence is retained below for context.

## Finding

All **217** `homeassistant.components.mqtt.number` errors in `runtime-log-before.txt` are the same failure:

```text
Invalid value for number.cerbo_gx_akku_soc_limit: 5 (range 20.0 - 90.0)
```

The private source snapshot (`raw-config/mqtt.yaml:509`) defines `unique_id: multiplus_soc_limit`, name `SOC Limit`, minimum **20**, maximum **90**, and step **5**. Its state and command paths both address `/Settings/CGwacs/BatteryLife/SocLimit` on the Cerbo settings service. The value template rounds the numeric JSON value; parsing succeeds. Home Assistant rejects the already-parsed value because it is outside this entity's configured range. This is a range/meaning mismatch, not a malformed MQTT payload or an availability-template failure.

`hass-cli state get number.cerbo_gx_akku_soc_limit` independently confirmed the entity remains `unknown`, with the 20–90 range. The same state appears in both the initial API snapshot and preflight snapshot.

## Read-only producer verification

The configured `Cerbo` SSH target reports Venus OS **v3.75**. Read-only D-Bus requests returned:

- Settings `/Settings/CGwacs/BatteryLife/SocLimit`: **5.0**.
- Settings `/Settings/CGwacs/BatteryLife/MinimumSocLimit`: **15.0**.
- System `/Control/ActiveSocLimit`: **15.0**.
- `GetAttributes` for `SocLimit`: default **10.0**, minimum **0.0**, maximum **100.0**, flags **1**.

The installed `/opt/victronenergy/dbus-systemcalc-py/delegates/batterylife.py` declares the same 0–100 range. It adjusts the dynamic limit as BatteryLife progresses and derives the active limit from the dynamic limit and the user's minimum. Its float transition can subtract two five-point increments: a dynamic value of five with a user minimum of fifteen is consistent with that algorithm.

`SocLimit` is therefore the **BatteryLife algorithm's dynamic register**; it is distinct from the **user's minimum discharge setting** (`MinimumSocLimit`) and the **currently effective threshold** (`ActiveSocLimit`). Do not change the Cerbo register to twenty merely to make Home Assistant's current limits accept it.

The current HA snapshot also contains `number.gx_device_ess_min_soc_limit = 15` and `sensor.gx_device_active_soc_limit = 15.0`, which already expose those separate concepts. The upstream [Victron BatteryLife implementation](https://github.com/victronenergy/dbus-systemcalc-py/blob/master/delegates/batterylife.py) corroborates the installed source; the live firmware and D-Bus reads above are the evidence for this installation.

## Consumers and identities

A literal scan of **all extracted text files under `raw-config/`, including `.storage`**, found:

- `number.cerbo_gx_akku_soc_limit`: one occurrence, its `.storage/core.entity_registry` entry.
- `multiplus_soc_limit`: its `mqtt.yaml` definition and that registry entry.
- No explicit automation, script, template, scene, group, or stored dashboard reference to this exact entity ID in the extracted configuration.

The registry links the legacy entity ID to stable unique ID `multiplus_soc_limit`; it is enabled and not hidden. Any future domain/identity migration must preserve or deliberately migrate this mapping. The scan does not prove absence of dynamic selectors, auto-generated entity UI, broad event listeners, external dashboards, or outside API clients. Those are separate consumption boundaries.

## Installed-runtime reproduction without device actions

A separate Python process in `homeassistant/home-assistant-0` on node `h7` imported the installed **Home Assistant 2026.9.1** MQTT Number implementation with bytecode writes disabled. It did not connect to the live HA event loop or MQTT broker. The publisher was replaced by an in-memory capture function.

Results:

- Current range 20–90 plus JSON payload `{"value": 5.0}` reproduces the exact invalid-value error and leaves the numeric state unset.
- Candidate range 0–100 accepts the same payload as **5.0**, with zero errors.
- Receiving a state update publishes **zero commands** in either case.
- Existing command values **20, 25, 50, and 90** produce identical JSON payloads through the unchanged command template under both configurations.

This verifies the parsing/range correction and existing command payload compatibility. It deliberately does **not** prove that newly permitted commands below twenty or above ninety are desirable for the household.

The installed number service wrapper (`homeassistant/components/number/__init__.py`, `async_set_value`) validates writes against the **same entity min/max** used by the MQTT state receiver. Consequently, expanding the range necessarily expands the values accepted by `number.set_value`; there is no independent MQTT Number state-only range setting. See the [HA Number service implementation](https://github.com/home-assistant/core/blob/2026.9.1/homeassistant/components/number/__init__.py) and [MQTT Number receiver](https://github.com/home-assistant/core/blob/2026.9.1/homeassistant/components/mqtt/number.py).

## Remediation options

### 1. Preserve current behavior now — selected for the initial migration

Leave the current number's range, topics, templates, and identity unchanged. Keep the diagnosed error visible and track this as a separate, bounded change after the automation/script deployment is verified. Do not clamp five to twenty, return a fabricated value, discard legitimate telemetry, or suppress the logger.

### 2. Match the live firmware's register range — deployed 2026-09-22

Change only this entry's bounds:

```yaml
min: 0
max: 100
```

Keep its unique ID, entity ID mapping, command/state topics, command template, rounding, and step unchanged. Consider the clearer display label `BatteryLife dynamic SoC limit` separately. This is the smallest truthful state correction and requires no change to the physical register. The offline test confirms that valid existing commands retain their payloads and receipt of five does not send a command.

**Boundary:** the UI and `number.set_value` now accept values in 0–100 instead of
20–90. The owner-requested correction preserves the existing control interface
and makes this range change explicit. The separate user minimum and effective
limit are not modified, and receiving telemetry does not publish a command.

### 3. Treat the dynamic register as read-only telemetry

Introduce a clearly named MQTT sensor for BatteryLife's dynamic limit; retain the user-facing minimum setting and effective-limit sensor as separate concepts. Retiring or replacing the legacy writable number would stop exposing an algorithm-owned value as a normal household setting.

**Boundary:** this changes/removes the existing control interface and potentially its entity domain. Before doing it, document the entity migration, review dynamic/external consumers, and decide whether a compatibility control is required. Simply adding a sensor while retaining the unchanged number would not remove the existing errors.

## MQTT YAML reload scope

The installed MQTT integration's `_reload_config` handler (`homeassistant/components/mqtt/__init__.py:410`) loads and validates the full MQTT YAML configuration, enumerates loaded MQTT entity platforms, removes every manually configured entity whose `_discovery_data` is absent, and invokes the registered reload handlers. It then fires `event_mqtt_reloaded`.

**`mqtt.reload` is not an entity-scoped reload.** It recreates the manually configured MQTT entities across platforms, not just this number. Discovery-managed entities are excluded from that removal loop. The handler does not itself restart the broker or call the number's command method, but subscriptions and entity states can be recreated; retained messages and resulting state transitions may affect existing automation consumers. See [Home Assistant MQTT reload documentation](https://www.home-assistant.io/integrations/mqtt/#event-event_mqtt_reloaded).

The September 22 correction passed staged and installed full configuration
checks, then used one `mqtt.reload` after a fresh idle check. All 292 MQTT
registry identities and state entities were retained, with no new unavailable
or unknown entities. The raw limit reports five while the user minimum and
effective threshold remain fifteen. No HA restart or Cerbo setting write was
needed. The [release record](releases/2026-09-22-mqtt-soc-limit.md) documents the
runtime receiver check, post-reload observation and rollback copy.
