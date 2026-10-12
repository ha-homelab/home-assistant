# KMC and Supernight outlet roles

The owner reassigned KMC and Supernight outputs on 2026-10-10. Automations use logical role
entity IDs; they must continue to address the newly assigned outlets rather
than follow the previously named physical plugs.

- On the **second KMC 30608**, output 1 (GPIO15) is `switch.recliner`, named
  **Recliner**, and output 2 (GPIO13) is `switch.living_lamp`, named **Living lamp**.
  Output 3 (GPIO14) remains `switch.tv_backlight_l`.
- On **Supernight**, the right output (GPIO12) is `switch.studio_tv`, named
  **Studio TV**; the left output (GPIO3) is `switch.studio_guard`, named
  **Studio Guard**. Right and left were confirmed by the owner.
- The former standalone Recliner, Living lamp and Studio Guard plugs remain
  registered and enabled as `switch.switch01`, `switch.switch02` and
  `switch.switch03`, respectively. Their device and integration display names
  are Switch01, Switch02 and Switch03.
- The old LocalTuya AirBnB TV remains registered. Its active dashboard and other
  control references are replaced by Studio TV. Retaining the old device does
  not mean it should remain a target for the TV role.

## First KMC: Garage water equipment power and Laundry

The **first** KMC is in the garage and is displayed as **Garage KMC Water and Laundry**.
Its shared meter names and Lovelace labels also include Garage; entity IDs and
relay role names stay unchanged. HA device and integration name overrides persist
without reflashing the device. It is assigned as follows. The second KMC's living-room
roles and the third KMC's generic outputs are unchanged by this reassignment.

- Outlet 1: `switch.moen_flo_water_monitor_power`, **Moen Flo Water Monitor
  Power**. This supplies the monitor; it is not a water-valve command.
- Outlet 2: `switch.pump_power_enable`, **Pump Power Enable**. This supplies or
  enables the pump; it is not a command to start a pumping cycle.
- Outlet 3: `switch.laundry`, **Laundry**.

The former Moen, Pump and Laundry Zigbee controllers remain separate retained
devices and can be renamed for reuse. Active pump control now follows the KMC
relay and its shared total meter as described in the
[water runbook](water-pump-levels.md). Renaming retained hardware does not move
the new KMC roles back onto it.

Do not blindly replace the first KMC's old Flare, Fireplace and Stage LED IDs
in control routines. Remove the old Fireplace and Stage LED targets from
morning lighting shutdown (074) and household lights/media shutdown. Remove
the old Stage LED action from decorative surplus-power rule 091, leaving its
Tea table action and notification intact. Only switch-state notification rule
112 follows all three new IDs; its messages use each entity's friendly name.

The Lighting view groups these three controls and their shared power reading
under **Garage KMC Water and Laundry**.
The owner subsequently removed current, voltage, energy-since-boot and meter-
calibration rows from this view; keep those diagnostics outside this fragment.
Use [this row fragment](dashboards/water-laundry-power.yaml) in its existing
entities card, removing the two obsolete lighting rows first. Keep the older
Moen, Pump and Laundry Zigbee rows. The Matter bridge uses explicit includes;
the old first-KMC IDs and all three new IDs are absent from those includes.
No automatic Matter export is introduced by this change.

Validate configuration and read back registry identities, compiled references
and dashboard rows. Do not toggle a relay or run a household scenario to check
these names. Restore old lighting targets only if the owner physically returns
the strip to its former lighting roles.

## Preserve the distinction between roles and hardware

Free the three occupied role IDs before assigning them to their new outputs.
Verify every source entity against the device and unique ID recorded in the
private live inventory; names alone cannot distinguish the two KMC strips.
Use Home Assistant's entity, device and config-entry registry APIs. Do not edit
registry storage files directly or regenerate unique IDs.

Keep existing `switch.recliner`, `switch.living_lamp` and `switch.studio_guard`
references in place. Do **not** rewrite them to Switch01–03. Replace outgoing
`switch.tablet` references with Recliner and `switch.audio_l` references with
Living lamp only where the consumer remains appropriate for the new role.
Remove a duplicate row if both the old and new role appeared in the same list.

The household shutdown script keeps its former second-KMC-output target under
the new `switch.living_lamp` ID. Error continuation, the mixed-domain lighting
action, all other targets and the final iNew shutdown action remain unchanged.
The living-lamp evening condition and the Studio Guard curtain-power rules
retain their logical IDs, thresholds and delays.

Diagnostic entities belong to their physical device. In particular, the former
Studio Guard red indicator stays with Switch03. Do not redirect its control or
device reference to Supernight. Firmware names, encrypted API credentials,
addresses and hardware identities are deliberately outside this role change.

## Total-power rows in Lovelace

Overview / Lighting shows **KMC Recliner Total Power** immediately above
`switch.recliner` and **KMC Living TV Total Power** immediately above
`switch.living_tv_guard`. Each row displays the existing ESPHome total-power
sensor, in watts, belonging to the same device as the switch below it. These
are whole-strip readings, not estimates for the single named outlet.

Select each sensor by matching its device-registry ID to the corresponding
switch and verifying `device_class: power` and `unit_of_measurement: W`.
The exact diagnostic IDs and runtime dashboard backup remain private.
Only the two sensor rows and their display names were added; the underlying
entities and relay controls were preserved. Saving and reading back the
Lovelace configuration requires no relay commands or firmware changes.

## Dashboard controls for retained plugs

The main storage-mode Overview dashboard's Lighting view keeps Switch01,
Switch02, Switch03, z01, Switch04, Switch05, Switch06 and Switch07 after the
bottom Garage Floodlight row, in that order. Switch06 is the former s6 device;
Switch07 is the former standalone Air Purifier Living. Each appears exactly
once as a normal row in the existing entities card.

The third KMC's outlet 2, formerly Front Camera and Living Curtains, now carries
Air Purifier Living. Its canonical role ID remains
`switch.air_purifier_living`, and existing purifier automations continue to
address it. The other two KMC outputs retain their roles. See the
[role handover and corrected standalone profile](air-purifier-living.md).

[The portable row fragment](dashboards/retained-switches.yaml) records the
bottom-row order. Check for existing controls before inserting rows; do not
replace the whole dashboard with the fragment. The full dashboard and backups
remain private runtime data. Saving these rows requires no relay commands or
restart.

## Verification and troubleshooting

Check the final entity registry by unique ID and confirm that every destination
occurs exactly once. Also check that the second KMC third output, old
AirBnB TV and diagnostic identities are unchanged. Compare physical relay
states by unique ID before and after, not by the reassigned entity ID.

Audit active YAML, stored dashboards, scenes, groups, helpers and export
filters. Historical recorder rows, retained old-device metadata and immutable
source-baseline contracts are evidence, not active control references.
Validate the affected configuration and reload only the changed domains.
No relay toggle, firmware update, Home Assistant restart or whole-house script
execution is needed to verify this reassignment.

The unused root `automations.yaml` also contained a legacy audio-button rule.
That rule is disabled and its action is an explicit stop; it is not redirected
to Living lamp. The garage button already uses direct Zigbee binding. The live
configuration includes the `automations/` directory, not this historical file.

If a dashboard still shows Tablet, Audio or AirBnB TV, inspect that dashboard's
stored entity ID and explicit `name` override. If a role drives an old plug,
look for an automatically migrated reference to Switch01–03 or a direct old
device/registry ID. Restore the logical role reference after verifying its new
physical outlet; do not compensate by swapping hardware unique IDs.

The subsequent [Ping01/Ping02 additions](ping-outlets.md) follow Switch07 at the
bottom of Overview / Lighting.
