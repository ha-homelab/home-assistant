# MPPT fan

The former `switch.old_lamp` outlet is now **MPPT fan**, exposed as
`switch.mppt_fan` through the encrypted ESPHome native API. The verified KMC
30137 profile uses GPIO14 for the relay, GPIO1 for the physical button and an
inverted GPIO13 indicator. Its relay startup policy remains `ALWAYS_OFF`.

## Preserve the solar behavior

The owner explicitly retained rules 123 and 124. Replace only the old entity
reference in their conditions and actions. Keep every threshold, five-minute
timer, state guard, Heater Three action and notification unchanged.

The existing rules trigger on any individual configured input: the enable
rule uses heater power above 200 W or PV power above 300 W; the disable rule
uses heater power below 150 W or PV power below 300 W. These remain individual
threshold crossings, not aggregate-power or temperature control. No motion
automation is transferred to the fan.

Replace the old customization key and the existing Lovelace switch row,
retaining its position. Keep all manual override helpers, including Studio
sticky, and unrelated controls unchanged.

## Remove the old Kodi relationship

Update both `tools/kodi_ha_commands.json` and its installed copy beside the
resolved `~/k` launcher. `aa` and `aaf` retain only `switch.audio_l` with their
existing toggle and off services. Remove `aaa`, `al-o-mbp` and `al-o-mbpf`.
These lamp-only aliases then fail without sending a service request. Do not
redirect them to cooling, and do not edit or publish the private Kodi launcher.

## Adopt and verify

Verify the firmware loader and encrypted API against the exact private device
identity. Adopt the replacement, confirm its canonical relay and display name,
then update and validate the references before removing only the old
LocalTuya device. Preserve its shared integration and other device records.

Save the verified YAML as `mppt_fan.yaml` in both active ESPHome source trees.
Remove the workstation-specific `build_path` and use separate `mppt_fan_*`
secret references without overwriting existing credentials. Device addresses,
MACs, encryption keys and private connection files stay outside this repository.

Verify the persisted source, loaded solar relationships, dashboard replacement,
Kodi command map and absence of active old references. Compare unrelated source
and launcher hashes and check sticky states. Runtime validation requires no
manual load command or Home Assistant restart. Physical and restart tests were
waived by the owner and must not be described as newly passed tests.

DNS and additive Matter exposure are separate coordinated steps; preserve
existing bridge, endpoint and controller identities.
