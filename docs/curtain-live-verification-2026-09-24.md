# Curtain commissioning: 24 September 2026

Tests used the authenticated floorplan WebSocket command endpoint, observed
LocalTuya packets and HA states, and physical observations supplied by the owner.
Targets were never substituted for measurements. Percentages below use Home
Assistant's convention: **0% closed, 100% open**. Times in this document are UTC.

## Applied configuration correction

Both rear-bedroom motors reported raw DP102=100 when physically closed. Their
LocalTuya `position_inverted` setting was false, so the map incorrectly displayed
100% open. At approximately 20:03, the supported LocalTuya options flow changed
only these two entity settings to true:

```diff
 cover.mishka_curtains_one_l:
-  position_inverted: false
+  position_inverted: true
 cover.mishka_curtains_two_l:
-  position_inverted: false
+  position_inverted: true
```

A comparison of the complete device configurations before and after the change
confirmed that no other device setting changed. HA itself was not restarted;
LocalTuya reloaded its entry. No local key, device ID, direction/reversing DP,
physical travel limit, or timing setting was changed.

The private pre-change backup is
`/config/backups/curtain-inversion-20260924T2003Z/core.config_entries`.
Do not commit that file: it contains credentials. Roll back using the same
LocalTuya options UI and setting just these two inversion flags to false, rather
than overwriting the whole HA storage file.

## Settings to preserve when rebuilding LocalTuya

All eight motors use absolute `position` mode and `open_close_stop` commands.
For the seven DP101 motors, command=101, observed position=102, target=104.
The office uses command=1, observed position=3, target=2; DP3 must not be selected
as a stop switch. Do not confuse the target DP with measured position.

- Kitchen `cover.kitchen_curtains_l`: inverted=true; the map uses it directly.
- Living sheer `cover.living_light_curtains_l`: inverted=true; map uses it directly.
- Living main `cover.living_curtains_l`: inverted=false; the map uses
  `cover.living_curtains_r`, whose position and target are `100 - raw`.
- Dining `cover.dining_curtains_l`: inverted=false; map uses
  `cover.dining_curtains_r`, whose position and target are `100 - raw`.
- Middle bedroom `cover.bedroom_curtains_l`: inverted=false; map uses
  `cover.bedroom_curtains_r`, whose position and target are `100 - raw`.
- Rear bedroom `cover.mishka_curtains_one_l` and
  `cover.mishka_curtains_two_l`: inverted=true; map uses each directly.
- Office `cover.office_curtains_office_curtains`: inverted=true; map uses
  `cover.office_curtains_r`, whose position and target are `100 - raw` and whose
  open/close actions are reversed. Preserve this combination as a whole.

The wrapper definitions are versioned in [covers.yaml](../config/covers.yaml).
LocalTuya UI settings live in HA's private configuration-entry storage, not in
that YAML file. Recreating only the YAML wrappers will not restore those settings.

Power bindings remain: living main + sheer → `switch.living_guard_1`;
middle bedroom → `switch.bedroom_guard_3_bedroom_guard_3`; both rear curtains →
`switch.laser_l`; kitchen → `switch.kitchen_guard_1`; office →
`switch.studio_guard_1`; dining → `switch.dining_guard_3`.

## Physical and telemetry checks

- Office before the power cycle: target 25 produced actual 26; owner confirmed
  approximately 75% closed. After recovery described below, target 75 produced
  actual 76; owner confirmed approximately 75% open.
- Living main: Close physically closed the curtain, but raw actual remained 50.
  The first target 25 was acknowledged as raw target 75 but did not move the
  curtain. After an ordinary full Open reported actual 100, target 25 produced 25
  and target 75 produced 75. The owner confirmed both partial positions. A final
  Close from 75 reached 1% opening; the measured value was not forced to zero.
- Living sheer: initially physically closed even though actual 50 was reported.
  Open reached 100 and was physically confirmed. Target 25 reached 24; owner
  confirmed approximately 25% open. Target 75 then reached 75 and was physically
  confirmed. A final Close from 75 reached 0.
- Dining: Close reported 100→0 opening and was physically confirmed. Target 25
  reached 25 and was physically confirmed. Target 75 reached 75 and was physically
  confirmed. A final Open from 75 reached 100.
- Middle bedroom: Close physically closed the curtain while actual 50 remained.
  Full Open reached 98. Target 25 reached 24 and target 75 reached 75; the owner
  confirmed both partial positions. A final Close from 75 reached 0.
- Rear motors: Close reached raw 100 on both, physically confirmed. After the
  inversion correction, both displayed 0. Full Open reached 98 and 100 respectively;
  the owner confirmed both fully open. Target 25 produced 26 and 25 respectively;
  the owner confirmed both approximately 25% open. Target 75 subsequently produced
  76 and 75 respectively.
- Kitchen was not moved in this run. Its earlier target 50→actual 49 test was
  physically confirmed. At the start of this run it reported 97 and its power
  socket was intermittently unavailable; motor availability still took priority
  over an unavailable socket, as requested by the owner.

Small endpoint/target differences are retained as measured. An endpoint such as
98% is not silently rounded to 100. LocalTuya may leave its motion state at
`opening` when an endpoint stops below 100; this is distinct from position accuracy.

## Real office power-cycle result

1. At 19:56:13, switched Studio guard 1 off with the curtain at observed 26%.
   The map displayed **Power off · last known 26% open**, retained its position,
   and disabled movement controls. The server's persistent curtain store also
   contained 26%. At 19:56:37 both raw and wrapper entities became unavailable.
2. At 19:57:12, powered it on through the floorplan. The 45-second countdown was
   visible and movement controls stayed disabled. The entity reconnected after
   approximately 17 seconds. A Stop request during warm-up was rejected with
   `not_ready`; it did not bypass the countdown.
3. After 45 seconds, controls became available. **This did not prove correct
   percentage control.** A 75% request at 19:58:11 physically opened the curtain
   fully while HA retained 26%. Repeating 75% at 20:00:14, about 182 seconds after power-on, still did not
   produce a new actual position. This was not just a request sent before the
   45-second warm-up expired.
4. Ordinary Close then Open produced real endpoint reports 0 and 100. LocalTuya
   subsequently reloaded while the two rear inversion settings were saved.
   A new 75% request at 20:04:17 produced DP2=75 and actual DP3=76; the owner
   confirmed approximately 75% open.

The second power cycle isolated the reload question. At 20:08:12 the office was
powered off at 76%; both its UI and persistent memory retained 76%. It became
unavailable at 20:08:31. Power-on at 20:09:00 started a new 45-second countdown;
the entity reconnected at 20:09:08. A 25% request at 20:09:56 returned only the
direction DP1=`open`; the reported actual position remained 76. An ordinary Open
at 20:10:57 produced actual 100 at 20:11:06. A 75% request at 20:12:34 produced actual 76
at 20:12:36. **No LocalTuya reload or HA restart occurred during this second cycle.**

Thus persistent map memory, power switching and the countdown passed. Reliable
percentage control immediately after power-on **failed**. A full endpoint movement
restored percentage control without reloading the integration. This is consistent
with loss of the motor's travel reference, but the firmware's internal state was
not directly inspectable. Do not call this an entirely successful
power-cycle acceptance test or simply increase the 45-second timeout without
evidence. Do not automatically open curtains at boot to hide this failure.

Also, HA `last_updated` after reconnection can accompany a retained LocalTuya
position. It is not proof that the motor sent a fresh actual-position DP. The
floorplan currently cannot distinguish those two cases from HA state alone.

Leave power on while using partial positions. If position control fails after a
power cut, use a deliberate full endpoint movement when the room can be opened
or closed, wait for an actual endpoint report, then retry the partial target.
Do not initiate such a movement automatically when restoring power, especially
at night. This commissioning run did not change the energy-saving automations or
claim to make the motor retain its reference across power loss.

## Upgrade and recovery

Restore the mappings above through LocalTuya's UI, preserve the wrappers, and
follow the [upstream hotfix recovery kit](../patches/localtuya/README.md) after a
HACS upgrade. Re-run physical endpoints and at least two partial targets before
claiming calibration. A cloud target, command acknowledgement, cached HA number,
or completed boot countdown is not physical verification.

## Final observed state

Living main: 1%; living sheer: 0%; middle bedroom: 0%; dining: 100%;
office: 76%; rear motor one: 76%; rear motor two: 75%. Kitchen remained 97%.
Studio guard 1 was returned to on. The map UI was checked against these values.
The final physical cross-check of this last set was requested and was still
pending when this record was written. Earlier physical confirmations are listed
per motor above.

Private raw commissioning logs remain outside Git. This document intentionally
contains no cloud credentials, local keys, or Tuya device identifiers.
