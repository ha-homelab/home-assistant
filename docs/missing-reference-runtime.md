# Missing entity references: runtime classification

Last state and system-log snapshot checked: **2026-09-29 05:10:48 UTC**. Scope: the 21 unresolved entity IDs from the reliability audit, excluding the `binary_sensor.rf_` text-search false positive. No identity-based rename has been established. No live changes or device actions were performed for this review.

None of these missing references was proved to interrupt useful actions for existing devices. The snapshot contained no system-log entries mentioning these 21 IDs. This is a snapshot result, not a claim that their service calls can never produce warnings.

## Twelve IDs used as direct service targets

The installed Home Assistant 2026.9.1 entity-service handler filters missing/unavailable entities, logs a warning, and continues with the remaining matching entities. When no entity matches, these non-response service calls return without raising an exception. Verified in `homeassistant/helpers/service.py:722–766` and `homeassistant/helpers/target.py:136–155` from the installed image.

- `light.bedroom_five`
- `light.fireplace_led_ll`
- `switch.mishka_bedroom_desk_lamp_l`
- `switch.fireplace_led_ll`

These four targets occur in [05:35 lighting shutdown](https://github.com/ha-homelab/automations/blob/0ace04d06ec1ec973f6236f77444a36f27d98f64/config/074_lighting_turn_off_scheduled_lights_in_the_morning.yaml), [05:45 lighting shutdown](https://github.com/ha-homelab/automations/blob/0ace04d06ec1ec973f6236f77444a36f27d98f64/config/075_lighting_turn_off_scheduled_lights_except_the_living_room.yaml), or [household shutdown](https://github.com/ha-homelab/scripts/blob/8d9f8e8b5e1073ecbcdb8b25371018ee8e43e76e/config/lighting/household_lights_and_media_off.yaml). The morning actions already run in parallel. The household script additionally retains `continue_on_error` on both target batches, followed by the iNew shutdown helper. Missing members do not prevent existing lights/switches or the later helper from receiving their calls. Three of these IDs also appear as harmless dormant state-trigger IDs in automation 112.

- `media_player.kitchen_speaker_2`
- `media_player.family_room_speaker_2`
- `media_player.dinning_room_google_mini`
- `media_player.mishka_bedroom_google_mini`
- `media_player.living_room_google_home`

[Household media shutdown](https://github.com/ha-homelab/scripts/blob/8d9f8e8b5e1073ecbcdb8b25371018ee8e43e76e/config/media/stop_household_players.yaml) calls each target separately and already continues after individual runtime errors. These absent players are skipped by the service handler; subsequent existing players are still processed.

- `media_player.vitaly_s_echo` — the sole target of [the volume preset](https://github.com/ha-homelab/scripts/blob/8d9f8e8b5e1073ecbcdb8b25371018ee8e43e76e/config/media/set_household_volume_presets.yaml).
- `media_player.plex_plex_for_android_tv_chromecast_google_tv_hd` — the sole target of [the Ants Plex playlist](https://github.com/ha-homelab/scripts/blob/8d9f8e8b5e1073ecbcdb8b25371018ee8e43e76e/config/media/plex_ants_android_tv.yaml).
- `switch.smart_toilet_2` — the sole target of [warm-water pump start](https://github.com/ha-homelab/automations/blob/0ace04d06ec1ec973f6236f77444a36f27d98f64/config/016_bathroom_start_the_warm_water_pump_after_motion.yaml) and [stop](https://github.com/ha-homelab/automations/blob/0ace04d06ec1ec973f6236f77444a36f27d98f64/config/014_bathroom_stop_the_warm_water_pump_after_motion_clears.yaml).

Those three functions currently have no matching device to control. They can emit missing-target warnings when invoked, but do not block any other useful action in their sequences. Their intended hardware identity must be resolved before restoring or retiring the functions.

## Two IDs in an Alexa notification target list

- `media_player.mishka_bedroom_echo_dot`
- `media_player.vitaly_s_portal_2`

[Porch Alexa announcements](https://github.com/ha-homelab/automations/blob/0ace04d06ec1ec973f6236f77444a36f27d98f64/config/084_porch_announce_motion_through_alexa.yaml) retain three other configured targets. The installed Alexa Media Player provider converts notification targets with `filter_matches=True` before scheduling TTS, then calls available matched devices. Unmatched IDs do not invalidate the whole list. Verified in `/config/custom_components/alexa_media/notify.py:91–146,280–301`. No additional target filter is required to preserve delivery to existing devices.

## Six IDs used only as state triggers

- `switch.hall_sockets_behind_tv_3_l`
- `switch.hall_sockets_behind_tv_2_l`
- `switch.sockets_behind_fireplace_3_l`
- `switch.clock_l`
- `switch.ice_maker_l`
- `switch.attic_dehumidifier_l`

In [switch-state notifications](https://github.com/ha-homelab/automations/blob/0ace04d06ec1ec973f6236f77444a36f27d98f64/config/112_notifications_report_switch_state_changes.yaml), these IDs only watch for `off` → `on`. An absent entity cannot produce that transition. The other trigger IDs remain independent and functional. Retaining the dormant IDs produces no repeated service calls or missing-target warnings.

## One ID already excluded during load selection

- `light.garage_beam_light`

The ID remains in [the self-consumption load map](https://github.com/ha-homelab/automations/blob/0ace04d06ec1ec973f6236f77444a36f27d98f64/config/085_self_consumption_select_controllable_loads_from_grid_power.yaml). [The selector](../config/python_scripts/select_devices.py) checks `hass.states.get(entity_id)` and skips missing states before calculating candidate combinations. No service call is generated for this missing target.

## Decision

Keep the existing scenarios and IDs pending a verified identity or explicit retirement decision. Do not add guards solely to suppress theoretical warnings, remove user functions, or substitute similarly named devices. Revisit only if a future trace or log establishes an actual failure.

In particular, **`switch.smart_toilet_2` must not be replaced with `switch.smart_toilet_2_2`**: the latter is the currently used toilet-seat heater, while the old automations describe a warm-water pump. Their relationship is unconfirmed.
