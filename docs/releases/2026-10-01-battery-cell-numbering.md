# Correct battery cell numbering in Home Assistant

The 16 YAML MQTT cell-voltage sensors for each battery chain were rotated by one
position. Displayed cells 1–15 read `/Cell/1/Voltage` through `/Cell/15/Voltage`,
and displayed cell 16 read `/Cell/0/Voltage`.

Cerbo's installed `dbus-mqtt-battery` services use zero-based GUI paths:
`/Cell/0/Voltage` is physical cell 1 and `/Cell/15/Voltage` is physical cell 16.
Their legacy `/Voltages/Cell1` through `/Voltages/Cell16` paths use one-based
numbers. Read-only D-Bus checks on both real services (instances 512 and 513)
confirmed this correspondence; `/Cell/16/Voltage` does not exist.

The HA definitions now map displayed cell `n` to `/Cell/{n-1}/Voltage` for both
chains. Only the 32 state-topic subscriptions change. Entity names/IDs, templates,
measurement metadata and the direct ESPHome per-BMS entities remain unchanged.
No monitor firmware or Cerbo battery settings change.

## Validation and activation

The regression test feeds distinct values for every index in both chains, so
either the old rotation or a cross-chain subscription fails. It reproduced both
old rotations and passed after the correction. Repository validation and the
installed HA staged/live configuration checks passed with zero errors or warnings.

One `mqtt.reload` applied the correction at **2026-10-01 06:41:21 UTC**, with no
active automation/script action at that boundary. This action reloads all YAML
MQTT entities; HA itself was not restarted. The previous file is saved privately
at `/config/.cell-numbering-backup-k9unz08t/mqtt.yaml`.

After activation, all 32 corrected topics delivered fresh messages and all 32 HA
states matched their assigned source values. The same 32 YAML entity IDs and all
337 registered MQTT identities were retained, with no newly unavailable
registered MQTT entities. Both chains' minimum/maximum templates remained numeric.
At the reload boundary, those four existing templates briefly logged a numeric
validation error for `unavailable`, as in the previous MQTT reload. All four
recovered; the observation window found no repeat of those errors.

Existing history is retained without rewriting database rows. Before this
activation, a displayed cell 1–15 represented the next physical cell, while
displayed cell 16 represented physical cell 1. Future measurements use the
correct labels. The min/max templates already cover all 16 cells and require no
mapping changes because the old error was a permutation of the same values.

## Rollback

Compare the current MQTT file with this change before restoring the private
backup, to avoid overwriting later edits. Validate the restored configuration
and reload MQTT once. A rollback restores the old, incorrect cell ordering.
