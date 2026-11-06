# Local Samsung appliances with LocalThings

LocalThings connects Home Assistant directly to supported Samsung appliances on the home network. It provides an alternative path to the official SmartThings cloud integration. It does not replace a SmartThings hub or make arbitrary devices registered in SmartThings locally controllable.

This installation uses the native Home Assistant Marketplace to manage LocalThings. Keep the existing Marketplace maintenance and automatic-update policy. Do not reinstall legacy HACS or disable unrelated updates to add this integration.

## Verified installation on November 6, 2026

LocalThings **0.36.0** is installed through Marketplace on Home Assistant **2026.11.0**. The **Range hood Local** and **Range Local** entries are successfully paired and assigned to the **Kitchen** area. Their connection-mode and last-response diagnostics are enabled. A short independent observation confirmed Observe mode, advancing responses and no unavailable local entities. This establishes current local communication; it is not long-duration reliability or an Internet-outage test.

The existing SmartThings integration and all 52 pre-existing cloud entity IDs were retained. Their automation consumers have not been replaced. Existing automatic updates remain enabled under the installation's normal maintenance policy.

The Family Hub refrigerator is **not paired yet**. Its normal setup attempt returned `no_response`, with no model or port resolved. Subsequent bounded public OCF discovery on UDP 5683 and 49153 received no response from either the actual HA runtime or a Mac directly on the home LAN. The router has a matching neighbor for the reserved candidate address, but that does not prove this is the current appliance-control endpoint. The user reported that the fridge screen is asleep and deferred waking it until later. Confirmation of the address on the Family Hub Wi-Fi screen is pending; screen sleep has not been established as the cause. The incomplete setup flow was closed, and no further appliance probes are scheduled. That observed result is different from the upstream `unknown_ca` report discussed below; certificate rejection has not been demonstrated on this refrigerator.

One clock-synchronization command completed without a Home Assistant service error. The user confirmed that the physical clock display now shows the correct time. Fan, lamp, heating, cooking, power and filter-reset controls were not exercised; their presence is not proof of physical operation.

### Local entities now registered

**Range hood Local** exposes the hood fan; lamp and lamp-brightness controls; alarm, energy, energy-saved, filter-usage and filter-status readings; automatic-operation and after-run status; a firmware-update-available indicator; and connection-mode/last-response diagnostics. It also registers filter-reset and cancel-after-run buttons. Filter capacity is disabled by the integration by default. Existence of these controls does not mean they were activated during installation.

**Range Local** exposes oven cavity state, temperature, machine state, progress, operation time and estimated finish; aggregate cooktop running state, warming-center state, active-burner count and five individual burner indicators; door, child-lock, Smart Control, running, cloud-connection and firmware-update-available status; and connection-mode/last-response diagnostics. Registered controls include power, lamp, sound, energy saving, cooktop-on alert, setpoint, cook time, cooking mode, sync clock and stop. Only clock synchronization has been physically confirmed. Other control effects remain untested, and the physical positions of the five burner indicators have not been mapped here.

## What remains on the cloud path

Keep each appliance registered in the SmartThings app. Removing registration can reset its network settings when it next contacts Samsung. Retain existing cloud entities and automations while qualifying their local equivalents.

LocalThings can operate locally after setup, but that does not change the appliance's own Samsung connection. Some model families stop accumulating energy readings while disconnected from Samsung. Treat cloud independence of commands, status, energy counters and optional downloaded programs as separate capabilities.

## Install and add appliances

1. Open Settings → Devices & services → Marketplace and find **LocalThings** (`mbillow/localthings`). Install the reviewed stable release.
2. Follow Marketplace's result. The native Marketplace can discover a newly installed config-flow integration without restarting Core. Restart once only if it reports that a restart is required, after current update, backup and automation work is idle.
3. Add the **LocalThings** integration and enter one appliance's current private IP address. Avoid opening multiple setup or diagnostic sessions against the same appliance.
4. Follow the returned setup form. A normal certificate-compatible appliance can complete automatically. A credential-selection form means automatic authentication failed; it is not successful pairing. Do not guess a pre-shared key or publish private credentials.
5. Give the new entry a clear local-control name and retain its initial entities separately from the SmartThings ones. Confirm device identity and state meanings before changing any existing automation.

An IP address and successful ping are not proof of compatibility. LocalThings must reach and authenticate to an appliance's actual local API.

## Network requirements

CoAP devices advertise a secure UDP port, which may change. UDP 5684 is a fallback rather than the only possible destination. Discovery also uses standard plaintext CoAP and model-specific fallback ports. Use the actual discovered endpoint when diagnosing connectivity; do not expose these ports to the public Internet.

Older appliances may use HTTPS on TCP 8888 and return a setup token to Home Assistant on TCP 8889. That callback requires an appliance-to-Core route. Host networking alone does not guarantee it when Core runs on a remote node or behind a VPN. The older transport also needs legacy TLS settings confined to that connection.

Reserve appliance addresses in DHCP where practical. If an address changes and discovery cannot follow it, use **Reconfigure** on the existing entry. Deleting and recreating entries can change entity identities.

## Set and synchronize the range clock

LocalThings 0.36.0 includes **Sync clock** for the installed `TP1X_DA-KS-RANGE-0101X` range. Open Settings → Devices & services → LocalThings → **Range Local**, then press **Sync clock**. Its current entity ID is:

```text
button.samsung_range_tp1x_da_ks_range_0101x_sync_clock
```

The button generates the time when pressed using Home Assistant's local clock. It sends `YYYY-MM-DDTHH:MM:SS` as `x.com.samsung.da.currentTime` to `/configuration/vs/0`. This installation uses **America/Los_Angeles**, so each synchronization uses the correct current daylight-saving offset. It does not make the appliance an NTP client or prove that the appliance will adjust itself at a future daylight-saving transition.

The clock command is explicitly marked as not requiring Smart Control by the integration. It does not change cooking mode, temperature, power or the global remote-control restriction. The resource is write-only: the appliance does not echo its clock on GET, and the button timestamp records a press rather than a verified clock reading. Confirm the physical display after the initial synchronization.

### Observed result

On November 6, 2026 at **02:37 PST**, the clock button completed without a service error while the range was idle and Smart Control was off. Home Assistant's configured time zone was verified. The user then confirmed the correct time on the physical display. This verifies one successful clock correction, not long-term clock accuracy or resistance to later power interruptions.

### Optional automatic synchronization

The following is a ready-to-adapt **example**, not an activated automation in this rollout. After confirming the physical clock, it can synchronize daily, after HA starts, and after the local clock entity returns from unavailable. It skips cooking; a skipped run waits for the next trigger. The 04:05 daily run occurs after the local daylight-saving transition hour.

```yaml
automation:
  - id: samsung_range_local_clock_sync
    alias: "Kitchen: synchronize the range clock"
    triggers:
      - trigger: time
        at: "04:05:00"
      - trigger: homeassistant
        event: start
      - trigger: state
        entity_id: button.samsung_range_tp1x_da_ks_range_0101x_sync_clock
        from: "unavailable"
        for: "00:01:00"
    conditions:
      - condition: state
        entity_id: sensor.samsung_range_tp1x_da_ks_range_0101x_machine_state
        state: "idle"
      - condition: state
        entity_id: binary_sensor.samsung_range_tp1x_da_ks_range_0101x_running
        state: "off"
      - condition: template
        value_template: >-
          {{ states('sensor.samsung_range_tp1x_da_ks_range_0101x_cooktop_running_state')
             | lower == 'ready' }}
      - condition: template
        value_template: >-
          {{ not is_state('button.samsung_range_tp1x_da_ks_range_0101x_sync_clock',
                          'unavailable') }}
    actions:
      - action: button.press
        target:
          entity_id: button.samsung_range_tp1x_da_ks_range_0101x_sync_clock
    mode: single
```

Use the actual entity IDs on another installation. A `Sync clock` button can legitimately be `unknown` before its first press; that does not itself mean the appliance is unavailable. If HA starts before the integration is ready, its startup run may skip and the later availability/daily trigger provides another opportunity. A brief power interruption that never marks the entity unavailable may likewise need the next daily run or a manual press.

If the display is still wrong, verify HA's time zone and host clock first, then inspect the LocalThings service error and connection diagnostics. A successful API response cannot replace a display check for this write-only resource. Do not change the whole HA time zone merely to compensate for one appliance.

References: [original request for this same range model](https://github.com/mbillow/localthings/issues/404), [clock support implementation](https://github.com/mbillow/localthings/pull/428), and [tagged range capability](https://github.com/mbillow/localthings/blob/v0.36.0/custom_components/localthings/registry/capabilities/range.py).

## Qualification before migration

Observe each local entity through naturally occurring operation before assigning it to an automation. Check:

- whether values change promptly rather than remaining plausible but stale;
- how on/off, ready/running, mode and alarm values correspond to the cloud entities;
- completion times, units and energy-counter behavior;
- availability and recovery after ordinary appliance and HA restarts;
- whether a phone app or another local client interferes with the connection.

A successful initial read does not establish reliable continuous updates. In particular, an upstream report for the `TP1X_DA-KS-RANGE-0101X` range family on firmware ending `40240205` describes silently stale burner state and rejected lamp commands. Do not promote such a range to the only automation input based on setup success alone.

For the `25K_REF_LCD_FHUB10.0` Family Hub family on firmware `20251031.075639`, upstream reports automatic certificate rejection (`unknown_ca`). A confirmed secure UDP responder therefore does not establish a usable authenticated session. Our current normal setup stopped earlier with `no_response`; do not relabel that failure as a certificate problem without further evidence.

The `AHD-WW-TP1-22-COMMON` range-hood family has a fixture in the reviewed stable release and is a reasonable first candidate. A fixture confirms a supported resource map, not the current credentials or network behavior of every individual appliance.

## Preserve existing automations

LocalThings creates its own unique entity identities. It does not automatically replace SmartThings entities or migrate device triggers. Keep a deliberate mapping of old entity, new entity, state meanings, units and consumers.

The Range's existing `binary_sensor.range_operating_state` and `sensor.range_operating_state` both represent aggregate **cooktop** activity. Their state vocabularies differ: `off`/`on` versus `ready`/`run`. Oven machine/job-state entities are separate. An entity name alone is insufficient to select a replacement.

Migrate one proven mapping at a time. Preserve existing sticky, notification, debounce and recovery conditions. Do not enable duplicate cloud and local automations that issue the same command. Keep the cloud alternative available until the local path is accepted.

## Troubleshooting

**Appliance cannot be found:** confirm its current address and power, then check targeted routing from the actual Core node. A fixed-port firewall assumption can hide a valid dynamically advertised endpoint.

**Authentication is rejected:** preserve the exact setup error and model/firmware. Follow the supported credential path; repeatedly retrying the same rejected certificate does not obtain a missing credential.

**States stop updating:** compare naturally changing values with the appliance or app. A connected session may still contain stale state. Check for competing local clients and relevant model-specific issues before relying on the values.

**Commands are refused:** keep the default remote-control restriction. Some appliances require physical Smart Control activation or prohibit particular remote starts. A rejected command is not a reason to bypass those limits globally.

**Old 8888 setup receives no token:** check the reverse route to Core TCP 8889 and the appliance's documented Smart Control state. Avoid overlapping token requests.

**Rollback:** disable the affected LocalThings entry under Settings → Devices & services. The retained cloud entities and existing consumers remain available. If any consumer is migrated later, restore its recorded cloud mapping first. Do not unpair the appliance from the Samsung account or restore an unrelated full configuration over current data.

**Credentials and diagnostics:** keep certificate keys, device tokens, pre-shared keys and config-entry backups in the protected private HA configuration and recovery storage. Do not put them in Git, this runbook, screenshots or public issue attachments. Inspect even automatically redacted diagnostics before sharing them. Public documentation should use device roles and model families rather than private endpoints, MAC addresses or entry UUIDs.

## Reviewed baseline and references

LocalThings v0.36.0 was installed through native Marketplace on Home Assistant 2026.11.0. Independent manifest verification matched the upstream tagged file; the resolved protocol library is smartthings-local 0.1.24. The hood and range subsequently paired and returned local observations as described above. The refrigerator remains unresolved. Apart from the confirmed clock correction, physical control effects, extended reliability and Internet-outage behavior have not been accepted.

- [LocalThings stable release](https://github.com/mbillow/localthings/releases/tag/v0.36.0)
- [Setup and known behavior](https://github.com/mbillow/localthings/blob/v0.36.0/README.md)
- [Range state-staleness report](https://github.com/mbillow/localthings/issues/738)
- [Family Hub authentication report](https://github.com/mbillow/localthings/issues/435#issuecomment-6675386050)
- [Range-hood resource fixture](https://github.com/mbillow/localthings/blob/v0.36.0/tests/fixtures/range_hood_device.json)
