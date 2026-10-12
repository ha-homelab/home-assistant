# Inherited behavior

This import makes the active automation library maintainable while preserving its behavior. It does not claim that every historical integration, device name, notification target, or policy is correct.

## Inactive source files

- `input_trigger_day.yaml` and `input_trigger_night.yaml` contained mappings, while `!include_dir_merge_list` consumes lists. They were ignored by the running loader.
- `knob.yaml` had the same mapping/list mismatch. Its comments and description are translated to English in the archive.
- `heater.yaml` and `heater_off.yaml` contained only disabled/commented content.

These five files remain outside the active include tree as `.yaml.disabled`. Enabling one would be a separate behavior change requiring device and dependency checks.

The source directory also contained editor backups with non-YAML suffixes. They remain in the private snapshot and are not duplicated in this library.

## Preserved historical details

- Two guest-departure automations perform the same operation. Both remain active, with distinct stable IDs and names, because removing either changes the source set.
- The legacy living-room loud-device motion rule has an empty action sequence. Its new description explicitly says so; this migration does not invent device actions.
- Four existing IDs include old numeric and placeholder-looking values. They are valid, already registered identities and remain unchanged.
- Historical action messages, dynamic service templates, sensor thresholds, trigger order, and device IDs remain byte-for-byte equivalent after YAML parsing. Display names describe the actual action where an old alias was misleading, such as the audio button that toggles garage lights.
- The root `automations.yaml` file is not part of the active directory include and is not activated by this repository.

## Runtime baseline

The captured installation used Home Assistant Container 2026.9.1 on k3s node `h7`. There were 130 available directory automations: 129 on and the explicitly disabled family-away rule off. The API also exposed a restored, unavailable `automation.notify_powerball_win` entity that is not one of these active automations.

Current dashboards reference the preserved `automation.off_lights` and `automation.off_lights_except_living_room` entities. A separate stale reference to `automation.zero_grid___smart_battery_management` exists in a dashboard; inventing or enabling a replacement energy controller is outside this identity-preserving import.

Configuration validation passed on the original installation. Existing warnings in the root configuration and theme files concern duplicate keys and the deprecated recorder purge interval; those belong to the root Home Assistant repository.
