# Entity display names and the local Kodi remote

Several LocalTuya devices supplied the same complete label at both the device
and entity levels while `has_entity_name` was enabled. Home Assistant combined
these into labels such as `LED under cabinet l LED under cabinet l`. The state
notification rules already used the state's friendly name once; the duplication
was in entity metadata, not in their message templates.

The 100 complete labels at the end of `config/customize.yaml` remove this
repetition, including repeated device prefixes in ESPHome/MQTT diagnostics and the
water-level and backup sensors. Registry `name`
overrides are synchronized to those labels so entity selectors also show them
correctly. Existing user overrides are preserved. The two cabinet lights are
`LED Under Cabinet 1` and `LED Under Cabinet 2`. No entity ID, unique ID, device
membership, physical setting, automation trigger or notification destination
changes. Existing scripts and automations pick up the clean friendly names.
The labels are declarative in Git; registry overrides also survive in HA's
normal backup. No custom-integration source patch is required.

Deploy from an immutable root build, preserving unrelated live configuration.
Back up `customize.yaml` and the entity registry privately; check the installed
HA configuration, synchronize only the 100 names through
`config/entity_registry/update`, then call `homeassistant.reload_core_config`.
Do not reload LocalTuya, MQTT, automations or scripts, or restart HA. Verify the
rendered notifications, stable entity identities and automation enabled states.
Rollback restores the previous `name` values through the same API, restores the
old customization file, and reloads core configuration.

Restored MQTT placeholders have no loaded entity object to refresh their cached
state labels. After confirming each registry identity and `restored: true`, update
only its `friendly_name` through the state API, preserving `unavailable`, all
other attributes and `last_changed`. This is a label refresh, not a new device
measurement or a change to availability. Do not use this exception for an
active entity or synthesize a working state.

## Local `~/k`

`~/k` resolves through `~/kodi` to the existing Dropbox Kodi script. Its media
commands remain in that script. The HA shortcut cases delegate to the tracked
`tools/kodi_ha.py` and `tools/kodi_ha_commands.json`, installed beside the resolved
script. They use stable entity IDs, so display-name changes need no target
migration. Never copy the old Kodi script into Git: it contains legacy private
connection settings unrelated to this change.

The HA helper replaces the old embedded token and retired server address. Store
its connection in `~/.config/kodi-ha/connection.json`, mode **0600**, with `server`
and `token` keys. This file stays outside Dropbox and Git. Alternatively supply
both `HASS_SERVER` and `HASS_TOKEN`; `KODI_HA_CONFIG` selects another private file.
TLS verification stays enabled, redirects do not receive the bearer token, and
service POSTs are never retried automatically.

The existing single-argument `T` and `M` shortcuts resolve the current enabled
LocalTuya/MQTT registration by domain before reload, instead of hard-coded
entry IDs. An ambiguous match fails without a reload. `harestart` and its
historical alias `hareload` both still mean a full HA restart, now using the
correct REST service path. This cleanup does not invoke any of these actions.

All targets in a shortcut are checked before one service call. Missing or
unavailable targets fail visibly without partly executing a group. Retired
kitchen-table, purple-lamp, TV-relay, `oneon` and `resetcreebulb` shortcuts report
why they are retired; they are not redirected to guessed replacement devices.
The `aa` and `aaf` commands retain only `switch.audio_l`. The former lamp
now powers the MPPT fan and is intentionally absent from audio commands.
The lamp-only `aaa`, `al-o-mbp` and `al-o-mbpf` shortcuts are removed and
fail as unknown commands without a service request. The historical `tabletf`
toggle behavior is preserved.

Use `~/k ha-check` for a read-only connectivity/integration check, and
`KODI_HA_DRY_RUN=1 ~/k po` to validate and display the Porch command without
operating it. HA shortcut failures return a nonzero exit code immediately;
Kodi playback dispatch does not run afterward. The media-only `V`, `L`, `LB`,
`L_`, `L__`, host arguments and playback commands retain their original bodies.

To reinstall, copy the two helper files next to the resolved Kodi script and
keep its HA dispatch cases calling the following function, then exiting with
its status. The manifest is the authoritative list of HA aliases. Preserve the
media cases when updating that dispatch list.

```bash
_ha_alias() {
  local kodi_ha_client
  kodi_ha_client="$(python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve().with_name("kodi_ha.py"))' "${BASH_SOURCE[0]}")" || return
  python3 "$kodi_ha_client" "$@"
}
```

The helper's tests use fake HTTP transport to cover stable IDs, complete-group
validation, unavailable/missing targets, retired commands, read-only dry runs,
current integration selection, ambiguous reloads and the restart route. Validate
the modified local script with `bash -n`; only read-only checks are run against
live HA.
