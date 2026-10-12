# BatteryLife dynamic SoC bounds correction · 2026-09-22

`number.cerbo_gx_akku_soc_limit` rejected the real BatteryLife dynamic limit of
five and stayed `unknown` because its MQTT definition allowed only 20–90.
Set this one definition's bounds to **0–100**, matching the installed Cerbo
register attributes. The current value in Home Assistant is now **5%**.

This is the BatteryLife algorithm's dynamic register, not the household's
minimum discharge setting. Read-only D-Bus checks before and after deployment
returned dynamic limit **5.0**, user minimum **15.0** and effective limit **15.0**
on Venus OS v3.75. No setting write or hardware action was issued. The existing
writable number now accepts 0–100 in both its state receiver and manual input.
Its entity/unique IDs, name, step of five, topics and templates are preserved.

Only `mqtt.yaml` was changed on the running HA 2026.9.1 instance. Structural
comparison verified that the two bounds were the only configuration changes;
the source also includes a comment distinguishing the three limit concepts.
A fresh literal reference scan found this number only in its definition and
registry/restore records, including old registry backups, with no direct
automation, script or stored-dashboard consumer. Dynamic or external consumers
are outside that literal scan.

## Validation and activation

- Repository YAML/include/credential validation passed.
- The installed MQTT Number receiver and template renderer reproduced rejection
  of five with the old bounds and accepted 0, 5, 15 and 100 with the corrected
  bounds. Values -5 and 105 were still rejected. Telemetry receipt published
  zero commands. Mocked writes of 20, 25, 50 and 90 retained identical command
  topics and payloads. This isolated process did not connect to the broker.
- Staged and installed complete HA configuration checks each returned zero
  errors and zero warnings.
- One `mqtt.reload` was invoked at **2026-09-22 18:35:28 UTC**, after a fresh
  check found no running automation or script actions. This reload applies to
  all YAML MQTT entities; it is not scoped to this number.
- All **292** MQTT registry identities and state entities were retained. No
  previously valid MQTT entity became unavailable or unknown. The corrected
  entity reported five with min 0, max 100 and its original step/mode.
- The first 113 seconds of post-reload logs contained no MQTT errors or
  invalid-value errors for this number. The HA pod identity and restart count
  remained unchanged.

At the reload boundary, four existing cell-voltage template sensors briefly
received `unavailable` from their MQTT inputs and logged numeric-state validation
errors. All four resumed valid voltage readings; these four errors did not
repeat during the observation window. Their availability templates were not
changed by this bounds correction.

Private before/after state and registry exports, configuration checks and
runtime receiver results are retained with the deployment evidence.

## Rollback

The original file is `/config/.mqtt-soc-backup-e39y251u/mqtt.yaml`. Restore it
only after checking for later edits, validate the complete configuration, wait
for idle execution and call `mqtt.reload` once. This restores the old 20–90
bounds and therefore restores rejection of the legitimate value five.

The reviewed stage is `/config/.mqtt-soc-stage-cdnvl0tz`. The installed
`mqtt.yaml` SHA-256 is
`9796fc3b5cf6cdd62aea811506bb06bf68fe9c29093a75c644acc7b5a9c4995c`;
the original/rollback SHA-256 is
`7de22140db6d92674114f531e7084cc607c3cfdedeb35180cd23956c352f516e`.
