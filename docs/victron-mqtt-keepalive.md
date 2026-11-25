# Victron MQTT keepalive and telemetry refresh

Automation `1608310266736` (`automation.victron_mqtt_keep_alive`) keeps the
existing Venus MQTT stream active without requesting the complete item tree
every five seconds. Its entity ID, five-second schedule and five stored traces
remain unchanged. Execution changes from `single` to `queued` with `max: 2`.

The previous scheduled request published `{}` to the legacy
`victron/R/000000000000/system/0/Serial` keepalive topic. That alias also requests
a full item republish. Repeating it can fill a slow subscriber's receive queue
and delay control packets, including MQTT PINGRESP, behind telemetry.

## Request contract

The recurring Serial request uses:

```json
{"keepalive-options":["suppress-republish"]}
```

An accepted `online` birth announcement on `homeassistant/status` requests one
unsuppressed bootstrap, so startup and MQTT reconnection initialize unchanged
values. The scheduled keepalive then renews streaming with full republish suppressed.

The top-level condition admits the MQTT birth trigger, or a periodic trigger
only when `state_attr(this.entity_id, 'current') | int(0)` is zero. Periodic ticks
therefore do not accumulate while an invocation is running or queued. The second
slot allows a birth-triggered bootstrap to wait behind one in-flight refresh;
there is at most one running invocation and one waiting invocation.

Each accepted five-second heartbeat and birth invocation also issues an exact
read request to refresh the existing 90-second battery expiry even when the
value does not change:

- `victron/R/000000000000/system/0/Dc/Battery/Voltage` supplies
  `sensor.battery_voltage`.

`binary_sensor.victron_grid_connected` expires on the same 90-second schedule,
but its request carries the VE.Bus device instance. The
[instance-following discovery package](#instance-following-mqtt-entities) reads
it at the announced instance, so this rule pins no device instance. The existing
bridge carries the `victron/` namespace. Requests remain reads; there are no
inverter mode commands or `W/` writes in this automation.

## Instance-following MQTT entities

`289` was the VE.Bus device instance of the Quattro
(`com.victronenergy.vebus.ttyUSB1`) while the MK3-USB adapter enumerated on
`ttyUSB1`. Venus derives the instance from the USB port index (`288 + N`), and
v3.85 has no persisted instance setting for the VE.Bus class, so a reboot that
enumerates the adapter on a different `ttyUSB` number publishes the whole device
under a new instance. MQTT YAML entities cannot wildcard a topic, so
[`mqtt.yaml`](../config/mqtt.yaml) no longer defines these three entities at all.

[`config/packages/victron_vebus_discovery.yaml`](../config/packages/victron_vebus_discovery.yaml)
follows the instance instead. It subscribes to `victron/N/+/vebus/+/Mode`, takes
the portal identifier and instance from that topic, and republishes retained MQTT
discovery for:

- `switch.victron_quattro` (`unique_id: victron_quattro`) on `vebus/<n>/Mode`,
- `binary_sensor.victron_grid_connected` (`unique_id: victron_grid_connected`)
  on `vebus/<n>/Ac/ActiveIn/Connected`, and
- `number.cerbo_gx_netz_max_strom` (`unique_id: multiplus_ac_current_limit`)
  on `vebus/<n>/Ac/ActiveIn/CurrentLimit`, still with `min: 0`, `max: 100`.

The payloads repeat the reviewed `unique_id` and `default_entity_id` values, so
the entity registry, automations, dashboards and history keep the same entities;
only their topics change. The same package refreshes the grid input every five
seconds at the announced instance, which is why rule 118 no longer reads it.
Nothing in either file carries a portal identifier or a device instance: both
come from the topics the installation already uses.

On start the retained discovery configurations are consumed before any telemetry
arrives, and the `homeassistant` start and MQTT birth triggers republish them
from the last announced topic stored in
`input_text.victron_vebus_grid_topic`. A renumbered instance is adopted from the
next `Mode` publication, which the keepalive bootstrap requests through the
Serial alias. An unchanged, still-present instance also keeps republishing its
configuration, so a broker that lost retained messages recovers without an edit.

The first deployment publishes these configurations only after the inverter
announces its instance; a configuration without them leaves the three entities
absent, so confirm the retained topics
(`homeassistant/{switch,binary_sensor,number}/…/config`), the unchanged entity
IDs, and valid states before relying on the midnight rule. If the package fails,
restore the previous `mqtt.yaml`, reload `mqtt` and `automations`, and clear the
retained discovery topics.

Sending a request does not make a measurement fresh. Only received notifications
refresh the MQTT entities. Invalid or absent measurements retain their existing
availability behavior, and both entities still expire after 90 seconds without
a message. The persistent [Off-grid policy](victron-black-start.md) controls shutdowns;
these read requests do not change the operating mode.

## Source and release ownership

The definition lives in the
[`automations` library](../dependencies/automations/config/118_victron_keep_mqtt_telemetry_active.yaml).
Merge and review its change first, then commit the resulting exact revision at
`dependencies/automations` in this root repository. Future builds copy that
pinned definition into
`/config/automations/118_victron_keep_mqtt_telemetry_active.yaml`.

Run the child validator and focused keepalive runtime tests, followed by the
root validator. CI validates source and does not activate it on h7. Follow the
[normal release procedure](deployment.md#later-releases) for a reconciled full
bundle; the build requires a clean committed root checkout and matching clean
bundled libraries.

The automation library's identity seeder preserves the reviewed `queued` mode
and execution limit while restoring legacy display aliases for identity
registration. It must not silently restore the superseded `single` mode.
Inventory tests and the reviewed behavior fingerprint cover this distinction;
an identity seed is not a rollback of reviewed execution behavior.

## Targeted runtime update

A focused runtime repair can replace only the keepalive definition while other
configuration changes are in progress. Record it separately from a full release:

1. Record the target HA pod identity, automation entity ID and enabled state,
   current file hash, reviewed source revision and replacement file hash. Keep a
   private backup of the current file before changing it.
2. Compare the live file with the reviewed baseline again immediately before
   replacement. Stop on unexpected drift. Install the exact reviewed file and
   run configuration validation with the installed HA version.
3. Export fresh runtime states and pass the existing idle check immediately
   before `automation.reload`. Preserve the automation's enabled state and
   stable identity. A reload resets pending automation `for` timers, so do not
   use repeated reloads as a diagnostic loop.
4. Verify the installed file hash matches the reviewed commit, then perform the
   runtime checks below. Retain the private backup and a receipt of the checks.

This update requires an automation reload, not an HA or MQTT broker restart.
Do not use whole-directory promotion to overwrite unrelated live changes.
`tools/promote.py --scope automations` replaces the managed automation directory
and requires the rest of the staged configuration to match; it is appropriate
only after that complete bundle has been reconciled.

For a targeted repair, `/config/release.json` may still describe an earlier full
release. Do not rewrite it to imply the complete current root revision was
deployed. The separate receipt should identify the exact changed file and
bundled component tree hash. A merged source PR or matching file hash alone does not
establish runtime acceptance.

## Runtime acceptance and rollback

Observe naturally occurring traffic for at least five minutes, covering several
90-second expiry windows. Confirm that periodic Serial requests suppress full
republish, the two exact requests produce real notifications, both measurements
remain fresh when the devices are available, and the automation retains its
identity and enabled state with `mode: queued` and `max: 2`. Observe a normal HA
MQTT birth when one occurs; do not restart HA or disconnect a working bridge
merely to generate it.

Both HA MQTT entities use the default `force_update: false`. An unchanged
notification can renew the 90-second expiry without a state write, so
`last_reported` can remain old while messages continue to arrive. Do not require
that timestamp to advance or treat it as a receipt clock. Confirm both entities
are available with valid states at every sample over a measured interval longer
than 90 seconds, and record the sampling interval. For example, 25-second samples
can miss brief gaps and establish sampled availability, not continuous availability.

For the Venus MCP subscriber, compare receive-queue progress, PINGRESP decoding
and disconnect events with the recorded failure window. Check its data freshness
independently using MCP receipt ages; HA availability alone does not establish
MCP freshness or prove that every received payload was a valid measurement. Keep its existing
30-second protocol keepalive, freshness checks and resource policy. Continued
keepalive failures or rising receive backlog require further investigation;
this automation change does not prove every historical network fault resolved.

If validation fails before reload, restore the guarded backup. For a later
rollback, first verify that the live file still matches this repair, restore
only its prior definition, validate, obtain a fresh idle check and reload once.
The old definition restores periodic full-tree requests, so record that behavior
and observe subscriber load. Preserve the current entity registry and unrelated
automation files throughout rollback.
