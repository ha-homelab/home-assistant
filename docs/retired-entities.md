# Retired entities and dependent code

The owner approved removal of obsolete dependencies on 2026-09-22. The assembled
release contains 117 folder automations and 51 folder scripts, plus the existing
root packages. Unchanged entities keep their IDs, enabled states and metadata.

Removed from active configuration:

- Four RF motion IDs: back porch, garage one, garage two, and the duplicated
  kitchen Zigbee occupancy ID formerly used by the bathroom rules.
- Eleven numeric cloud Tuya switch references. Their device identifiers match
  the retained Tuya/Tuya v2 registries and the historical cloud integration's
  numeric entity naming. The exact retired entity IDs no longer exist in the
  runtime registry; provenance therefore combines device records and the
  [historical Tuya source](https://github.com/home-assistant/core/blob/2021.7.4/homeassistant/components/tuya/switch.py#L50-L56).
- Four media-player targets: the old IP-named Kodi player, Al Mini, iMac21 and
  the bedroom Google Home.
- The unsupported Kodi catalogue selection chain: `script.play_kodi_channel`,
  `script.your_kodi_script` and `input_select.kodi_channel_selector`.
- The obsolete battery capture automation and `sensor.battery_out_since_5pm_yesterday`,
  which depended on the missing `input_number.battery_out_at_17_yesterday`.
- `script.resetcreebulb`, which only power-cycled a retired Tuya target.

Five guest-indicator rules and five obsolete Tuya device/quiet-mode rules have
no retained useful action and are retired, along with the battery capture rule.
The remaining bathroom automation uses the existing restroom motion sensor and
the same five-minute timeout and manual override. Front-porch Chrome delivery
remains enabled while its obsolete switch pulses and delays are removed.

The initial cleanup preserved LocalTuya configuration and entities. Several physical devices
have been repurposed as guard devices or a bathroom fan; the old commands must
not be redirected to them. On 2026-09-23 the owner also retired `switch.tv_l`
(unique ID `local_7636703898f4abd20462_1`). Its LocalTuya device is removed through
the integration's supported device-removal API. Five lighting rules no longer
depend on TV power, the switch notification rule no longer watches it, and
`script.turn_off_living_room` no longer sends it an off command.
Motion triggers, inactivity timeouts, solar-elevation checks and the living-room
manual override remain unchanged. The solar-elevation evening rule can now run
regardless of TV state. Other LocalTuya devices and notification destinations,
including the working TV notification service, remain unchanged.

The unrelated Kodi notification destinations, `/config/kodi` helper and radio
playback scripts remain in service. Other battery integration and energy
statistics are preserved.

The follow-up audit now contains 30 missing literal entity references, down
from 52. Immutable import baselines, inactive archives and retirement records
retain old IDs as historical evidence; they are not deployed code.

## Backyard camera retirement — 2026-09-24

The owner retired the unused Backyard camera. Remove its MJPEG integration and
four failing Local File entries through the supported config-entry API, its two
motion automation registry entries after reload, and its four-card snapshot stack
from the overview dashboard. The shared snapshot helper and legacy shell-command
configuration no longer accept or reference Backyard. Preserve the separate
`light.backyard1` and other devices whose names merely contain Backyard.

## Validation and rollback

Run all three repository validators and the retirement guardrail tests. Execute
the root HA runtime scenarios with the pinned child repositories, including lighting
without the retired TV, manual-override and daylight guards, the retained volume preset, and Chrome-only
front-porch delivery. Build against the declared active inventories, validate
with the installed HA configuration checker, then reload only changed domains
after a fresh idle check.

After reload, remove the explicitly retired automation/script registry entries
through the HA API, verify remaining IDs and enabled states against the private
snapshot, and check all active dashboards and files for retired references.
Keep the private full backup and selective rollback. Roll back both child pins
and root declarations together if needed; keep the current LocalTuya setup.

## Blink curtain exception (2026-09-24)

The owner retired the early evening curtain rule
`automation.close_curtains_in_the_evening_if_cloudy`, which required the removed
`sensor.blink_porch_temperature` to be below 15 degrees while sun elevation
crossed below 2 degrees. The entire special rule is removed, so its early
closing action does not become unconditional. The normal evening solar
thresholds, morning schedules, motor power sequencing, and
`input_boolean.curtains_sticky` override remain unchanged. The retired identity
is retained in the automation library's migration inventory.

## Postbox and Presence Sensor 1 (2026-09-24)

The owner retired `binary_sensor.postbox` and Presence Sensor 1, including its
MQTT entities and disabled ESPHome duplicate. Remove the two mailbox-only
notification/indicator automations and the Postbox trigger in general motion
notifications. Preserve the shared Sonoff RF bridge and its other entities.

Remove the Presence Sensor 1 branches from the six kitchen lighting rules.
Keep the working RF tea/counter triggers and `group.kitchen_motion`, the
35-minute table-lamp, 7-minute counter, and 3-minute tea-area inactivity timers,
all existing guards, and the shared availability-recovery blueprint. General
motion notifications keep the same destinations and exactly one Chrome copy.

Remove the Presence Sensor 1 card from the default dashboard through the
Lovelace API and its disabled ESPHome config entry through the config-entry
API. The MQTT entities are restored registry orphans: device diagnostics contain
no active discovery definitions, and a broker discovery subscription found no
matching retained announcements. Remove only these verified orphan entities
and the now-empty Presence Sensor 1 device; do not remove the shared MQTT
integration or the RF bridge. Keep private registry/config-entry/dashboard
backups and verify other automation identities and enabled states after reload.

## Listed light retirement (2026-09-25)

The owner retired 16 named SmartThings lights and 12 audio-system/iNew LED
entities from MQTT and ESPHome. Preserve the SmartThings balcony and three
garage lights, all LocalTuya/ZHA/Matter lights, and the physical audio/iNew
relays, buttons and telemetry. Remove only the listed light registry entries.
For managed entities, set `disabled_by: user` through the entity-registry API
before removing them: HA preserves that setting in its deleted-entry record,
so rediscovery can restore only a disabled registry entry, not an active light.
Do not unpair devices in the SmartThings account or remove shared integrations.

Retire eight old rules whose only targets or required trigger/guard depend on
the retired arc, black or purple lamp, plus the arc-only `script.flash`. Do not
drop a required guard and thereby broaden the old conditional actions. Remove
the retired targets from the two shared morning shutdown rules and the household
shutdown script; keep all remaining targets, schedules and commands. Remove
the two explicit lamp cards from the dashboard and preserve their sibling cards.

## Maria iPhone naming and retired registrations (2026-09-28)

The owner opened HA on Maria's current phone. Fresh GPS and sensor updates
identified Mobile App entry `180f91d38eef338c2694d778876c85d4`, historically titled
`iPhone 13 Pro`, now reporting hardware `iPhone19,2`. Keep this entry and its 31
entities. The owner requested the name **Maria iPhone**: rename the entry/device
and entity IDs to `maria_iphone`, retaining unique identities and enabled/disabled
flags. The tracker is `device_tracker.maria_iphone`; its notification entity is
`notify.maria_iphone`. The existing Companion notification service
`notify.mobile_app_marias_iphone` remains available. The complete old/new entity
map is in [maria-iphone-entity-renames.json](maria-iphone-entity-renames.json).
Registry renaming timestamps are not evidence of a fresh phone measurement.

Remove the two owner-confirmed retired Mobile App entries through the supported
config-entry API: iPhone 11 Pro/iOS 13.3.1 and iPhone12,3/iOS 14.4.2, including their two
devices and 36 entities. Their obsolete trackers are
`device_tracker.marias_iphone_11_pro` and `device_tracker.marias_iphone_2`.
The latter's old `home` state must not be treated as a fresh location report.

Also remove the disabled Maria iPhone 6s device and its two battery entities
from the legacy iOS integration. Back up the private `.ios.conf` source and remove
only its `marias_iphone` device entry, verified against the device's permanent ID;
leave the other legacy device and settings untouched. Disable the two entities
explicitly before removing them through the registry API. Legacy iOS also lacks
a device-removal callback, so HA rejects removal of its empty device through the
API. Remove only that device record while HA is stopped, with a private snapshot
and identity guards; preserve every other registry record. Restart HA to clear its in-memory
`notify.ios_marias_iphone` target and verify it is not recreated from disk.
This does not remove the current Mobile App registration.

The reference scan found only recorder exclusions for retired entities, with no
live automation, script, group, package, or dashboard references requiring
replacement. Remove 33 recorder exclusion rows: 29 distinct retired Mobile App
entities, one duplicate, two earlier aliases absent from the registry, and one
legacy iOS entity. No recorder purge or database/history deletion is required.
The recorder file cleanup alone needs no reload; the legacy iOS target requires
the restart described above. Keep private local registry/configuration snapshots
for rollback and continue the existing weekly NAS backup schedule.

## Disabled cloud Tuya registrations (2026-09-29)

The owner confirmed that the home uses LocalTuya, not either cloud Tuya
integration. `ha entity list` still showed 85 `tuya_v2` entities because it lists
disabled registry entries as well as active entities. Both `tuya` and `tuya_v2`
were disabled by the user and not loaded; none of the 85 entities had a live
state. The old `tuya` entry had no entities but still owned 63 device records;
`tuya_v2` owned another 58. None of these 121 records was shared with LocalTuya.

Remove both cloud config entries through HA's config-entry API and uninstall
`tuya/tuya-home-assistant` through HACS. This also removes HACS's Tuya v2 device,
`update.tuya_v2_update` and `switch.tuya_v2_pre_release`. HA automatically removes
two dependent `switch_as_x` helpers: `light.fireplace_led_tuya` from
`switch.fireplace_led`, and `light.tv_backlight` from `switch.tv_backlight`.
Both helpers were already disabled by their cloud devices and had no live state.
The [retired entity inventory](cloud-tuya-retirement.json) records all 89 removed
entities; no physical device was unpaired or operated.

The legacy custom component could not import because its `tuya_iot` dependency
was missing. HA imports a disabled integration during config-entry removal,
before clearing its registries. To complete removal without loading or enabling
cloud control, its backed-up initializer was temporarily replaced with an
importable, removal-only module containing the domain constant. The original
component had no removal callback. HACS then removed the entire `tuya_v2`
directory, including this temporary module. This was a one-time retirement step,
not a retained integration patch. No running `.storage` files were edited.

Verification completed in HA 2026.9.1:

- All cloud entries, their 121 device records, 85 entities, two dependent helpers
  and HACS's two entities/one device are gone from the live registries. Persisted
  config entries and the entity registry also reflect the removal.
- LocalTuya remains loaded at HACS version `2026.7.0`. Its 59 entity records,
  53 device records and complete configuration are unchanged; its source files
  were not rewritten. All 117 automation enabled states are preserved.
- A scan of 442 configuration and settings files found no remaining references
  to the removed targets. No automation, script, dashboard or recorder changes
  were necessary. Historical import/audit records remain historical evidence.
- The installed configuration checker reports zero errors and zero warnings.
  No integration reload, automation reload or HA restart was performed.

A private, checksum-verified 1.39 MB selective rollback archive was retained on
the HA volume and the operator's workstation. It includes the affected component
and pre-change config-entry, entity, device and HACS registries. This was not a
new full backup or SQL dump; the weekly Synology backup policy is unchanged.
If reversal is required, use a controlled restore of the selected records and
component from that archive. Do not overwrite current registries wholesale or
re-enable cloud entries during an ordinary LocalTuya recovery.

## Stale registry cleanup (2026-09-29)

The owner approved the four groups in
[stale-entity-retirement.json](stale-entity-retirement.json), exactly 171 entities:

- **121 old Frigate entities:** remove only disabled config entry
  `be937b1f311cc478b5a5cf1a88335601`. The active registration
  `01KP4Y82YP0YK2F3PAXTPGKH7J` retains all 126 entities. Both entries describe
  the same server, but their entity and device identities are separate. The
  active configuration and dashboards reference neither the old entities nor
  their devices. On startup, Frigate's built-in migration automatically removes
  the `_2` suffix from eight current object-count sensors when those names
  become free. They retain their current registration and unique IDs; no active
  configuration or dashboard references their former names. The inventory
  records this map. Camera, occupancy and notification entity IDs stay unchanged.
- **29 restored orphans:** old network throughput, AirVisual, FAA, Zestimate,
  Updater, Powerball and OhmConnect entities; three retired scripts; the old
  iNew energy integrator and corrected battery SOC 2. These have no config
  entry or loaded YAML definition. Keep `sensor.corrected_battery_soc` and
  the current energy integrators. Remove registry records, without purging
  recorded history or statistics.
- **19 HACS records:** ten unavailable update entities and nine disabled
  pre-release switches for repositories already uninstalled or no longer
  present in the catalogue. Remove only their registry records and the ten
  resulting empty HACS devices. Do not invoke HACS repository uninstall:
  `custom_components/mbapi2020` now implements the active **Mercedes via
  Cerbo MQTT** bridge and must remain installed with its 56 entities.
- **Two iPhone 6 Plus battery entities:** retire the final legacy `ios`
  config entry `5e65dd432b7e445db931e54d6f93189f`, its disabled device and
  the `als_ip` device source in private `.ios.conf`. Remove `ios:` from the
  root YAML and its last recorder exclusion. Modern Companion phones use
  `mobile_app`; preserve Maria iPhone, Vitaly iPhone Air, Apple Watch and all
  unrelated mobile registrations.

Before removal, refresh the registry, HACS inventory, live state and reference
scan, and save a private selective rollback archive of the registries, HACS
metadata, `.ios.conf`, root YAML and recorder configuration. Do not create an
additional full NAS backup or SQL dump; the weekly backup schedule is unchanged.
Use HA's config-entry and entity-registry APIs for removals. Legacy iOS has no
unload support, so its old notify target requires one HA restart. The installed
HACS version also lacks a device-removal callback: remove only the ten verified
empty device records while HA is fully stopped, backing up that file again and
preserving all other records. Never edit a registry file in a running HA process.

Build the committed source with bundled automation/script libraries. Validate
against the installed HA image, promote only the two changed configuration
files with hash guards, and wait for an idle automation/script boundary before
the restart. After startup, compare the registry to the captured inventory:
exactly 171 old unique identities, two config entries and 16 devices must
disappear; all other unique identities and enablement flags must remain. Account
for the eight native Frigate renames separately: a reused entity ID does not
mean that the old integration record returned. Confirm the retired identities
and `notify.ios_als_ip` do not return, and verify LocalTuya, current
Frigate, both current phones and the Cerbo MQTT bridge remain loaded. This
cleanup does not assert that every retained device is online.

For rollback, restore only the affected records and source files from the
private archive while HA is stopped, preserving any unrelated changes since
that archive. Revert the two root configuration edits as well. Whole-registry
restoration is appropriate only if no intervening registry changes occurred.

The maintenance run required three controlled HA restarts. The first helper
process exited with status 137 before changing the registry; reducing its input
and increasing its temporary memory limit resolved that failure. The second
attempt's guard stopped before writing because Frigate had reused eight old
names for current sensors. The final guard compares integration ownership and
unique IDs, with the documented rename map, rather than entity names alone.
Every attempt restarted HA in its `finally` block. Temporary helper pods were
removed; no persistent resource limits were changed.


## Man at work and legacy solar enforcement (2026-10-11)

The owner retired `input_boolean.man_at_work` and its two automation consumers:
`automation.solar_on` (rule 106) and `automation.power_above_three_hundreds`
(rule 098). Pin the companion automation retirement before reloading the helper
configuration. The first rule no longer re-enables Heater One and Heater Two;
the second no longer switches off Solar S2000 on the legacy grid-import condition.

For the storage-mode dashboard, remove the `input_boolean.man_at_work` entity row
from Overview / Lighting (`lovelace`, view `switches`) through the Lovelace API.
After reloading automations and input booleans, remove only the three retired
entity-registry records if they remain. The live removal was checked with HA's
installed configuration validator. No relay commands or HA restart are needed.
Tasmota's local 30-minute Wi-Fi watchdog and power-on settings are unchanged.
