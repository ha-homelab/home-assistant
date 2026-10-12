# Script catalog

The YAML object key is the stable script identifier. Display names and file locations can change without renaming callers.

## Notification follow-up

Chrome callers now use modern HTML5 delivery to the registered `notify.chrome`
entity. The owner retired the old iPhone and Pushbullet destinations; their active
calls are removed. `tv_pic2` uses the confirmed LG notifier and supported camera
icon field. The original service-snapshot notes below describe the import, not
current delivery status.

## Scope

The source folder contains 54 scripts; the live instance also has scripts from other configuration sources. This repository does not replace those other sources.

## `backdoormotion`

**Backdoor: notify and pulse porch light**

Take a backdoor snapshot and notify desktops; between 20:30 and 22:00, also repeat the browser notification and run the existing porch-light fade.

- Entity: `script.backdoormotion`
- File: [config/notifications/backdoor_motion.yaml](../config/notifications/backdoor_motion.yaml)
- Source file: `scripts/backdoormotion.yaml`
- Review note: The time condition stops only the remaining phone/light actions; desktop notifications happen first. Preserve the fade sequence and final off state.
- Not registered in the source service snapshot: `notify.chrome`, `notify.mobile_app_als_iphone2`. Keep the script until the owner reviews its callers and device integration.

## `blinkmotion`

**Front porch: notify about motion**

Send the existing Chrome motion notification.

- Entity: `script.blinkmotion`
- File: [config/notifications/front_porch_motion.yaml](../config/notifications/front_porch_motion.yaml)
- Source file: `scripts/blinkmotion.yaml`
- Review note: Obsolete cloud Tuya switch pulses were removed at the owner's request; this script only delivers the existing browser notification.
- Not registered in the source service snapshot: `notify.chrome`, `notify.pushbullet`. Keep the script until the owner reviews its callers and device integration.

## `cast_downstairs_on_kitchen`

**Kitchen display: show default dashboard**

Cast the default Lovelace view to the kitchen display.

- Entity: `script.cast_downstairs_on_kitchen`
- File: [config/media/cast_dashboard_to_kitchen.yaml](../config/media/cast_dashboard_to_kitchen.yaml)
- Source file: `scripts/cast.yaml`

## `cast_plex_to_chromecast`

**Chromecast: play 2012 from Plex**

Play the movie 2012 from the Movies library on the Chromecast.

- Entity: `script.cast_plex_to_chromecast`
- File: [config/media/cast_plex_movie.yaml](../config/media/cast_plex_movie.yaml)
- Source file: `scripts/cast.yaml`

## `cast_porch_to_chromecast`

**Chromecast: show garage camera**

Stream the garage camera to the Chromecast; the legacy script key still contains porch.

- Entity: `script.cast_porch_to_chromecast`
- File: [config/media/cast_garage_camera.yaml](../config/media/cast_garage_camera.yaml)
- Source file: `scripts/cast.yaml`
- Review note: The public script key is retained for callers; the actual source is camera.garage_camera.

## `flash`

**Arc lamp: run ten-second flash**

Turn the arc lamp on, wait ten seconds, then send its existing turn-off command with a short flash.

- Entity: `script.flash`
- File: [config/lighting/flash_arc_lamp.yaml](../config/lighting/flash_arc_lamp.yaml)
- Source file: `scripts/flash.yaml`

## `frontmotion`

**Front camera: send motion notifications**

Take a front-camera snapshot and notify desktops; send browser notifications between 09:05 and 23:00.

- Entity: `script.frontmotion`
- File: [config/notifications/front_camera_motion.yaml](../config/notifications/front_camera_motion.yaml)
- Source file: `scripts/frontmotion.yaml`
- Review note: Keep the time condition after the snapshot and desktop notifications so those actions remain unconditional.
- Not registered in the source service snapshot: `notify.chrome`, `notify.mobile_app_als_iphone2`. Keep the script until the owner reviews its callers and device integration.

## `garagemotion`

**Garage camera: send motion notifications**

Take a garage-camera snapshot and notify desktops; send browser notifications between 09:05 and 23:00.

- Entity: `script.garagemotion`
- File: [config/notifications/garage_camera_motion.yaml](../config/notifications/garage_camera_motion.yaml)
- Source file: `scripts/garagemotion.yaml`
- Review note: Keep the time condition after the snapshot and desktop notifications so those actions remain unconditional.
- Not registered in the source service snapshot: `notify.chrome`, `notify.mobile_app_als_iphone2`. Keep the script until the owner reviews its callers and device integration.

## `kk`

**Radio: run selected shell command**

Call shell_command.kk with the existing crossed selector mapping: pla receives input_select.sta and sta receives input_select.pla.

- Entity: `script.kk`
- File: [config/media/run_selected_radio_shell_command.yaml](../config/media/run_selected_radio_shell_command.yaml)
- Source file: `scripts/kk.yaml`
- Review note: Do not swap pla and sta without reviewing shell_command.kk and every caller; this mapping matches the live configuration.

## `kkk`

**Radio: play selected TuneIn station**

Play the radio selector value on the player selected by input_select.player using the existing TUNEIN media type.

- Entity: `script.kkk`
- File: [config/media/play_selected_tunein_station.yaml](../config/media/play_selected_tunein_station.yaml)
- Source file: `scripts/kkk.yaml`

## `living_room_display_2_temperature`

**Living room display 2: ask porch temperature**

Send the existing custom Google voice request for the porch temperature to living room display 2.

- Entity: `script.living_room_display_2_temperature`
- File: [config/media/ask_porch_temperature.yaml](../config/media/ask_porch_temperature.yaml)
- Source file: `scripts/temperature.yaml`

## `living_room_tv_picture_energy_saving`

**Living room TV: request energy-saving setting**

Show the existing webOS confirmation alert whose OK button applies the supplied energy-saving setting.

- Entity: `script.living_room_tv_picture_energy_saving`
- File: [config/television/living_room_energy_saving.yaml](../config/television/living_room_energy_saving.yaml)
- Source file: `scripts/lg.yaml`
- UI fields: `energy_saving`
- Review note: This uses the TV confirmation-button callback. Preserve the firmware-specific payload and string-valued energySavingModified.

## `mediaoff`

**Media: turn off household players**

Turn off the eight retained household media players in sequence, continuing when an individual player fails.

- Entity: `script.mediaoff`
- File: [config/media/stop_household_players.yaml](../config/media/stop_household_players.yaml)
- Source file: `scripts/mediaoff.yaml`

## `notify`

**Notifications: send desktop message**

Send a timestamped message to the Roomba and iMac notification targets.

- Entity: `script.notify`
- File: [config/notifications/desktop_message.yaml](../config/notifications/desktop_message.yaml)
- Source file: `scripts/notify.yaml`
- UI fields: `message`

## `notify_mqtt`

**Notifications: publish retained MQTT message**

Publish a correctly escaped JSON message to living_room/notifications with retention enabled; queue simultaneous calls.

- Entity: `script.notify_mqtt`
- File: [config/notifications/mqtt_message.yaml](../config/notifications/mqtt_message.yaml)
- Source file: `scripts/notify_mqtt.yaml`
- UI fields: `message`
- Review note: Escaping is verified with the real MQTT publish schema; decoded title/message fields and the retained topic are unchanged.

## `notify_mqtt_log`

**Notifications: publish retained MQTT switch log**

Publish the supplied message to living_room/switch_log with retention enabled.

- Entity: `script.notify_mqtt_log`
- File: [config/notifications/mqtt_switch_log.yaml](../config/notifications/mqtt_switch_log.yaml)
- Source file: `scripts/notify_mqtt_log.yaml`
- UI fields: `message`
- Review note: retain: true is part of the existing subscriber contract; a new subscriber can receive the last message.

## `notifymax`

**Notifications: send desktop and persistent message**

Send a timestamped message to the Roomba and iMac targets and create a persistent Home Assistant notification.

- Entity: `script.notifymax`
- File: [config/notifications/persistent_desktop_message.yaml](../config/notifications/persistent_desktop_message.yaml)
- Source file: `scripts/notify.yaml`
- UI fields: `message`

## `playplexplaylist`

**Living room Echo: play Dark Side of the Moon**

Request the Dark Side of the Moon album through AMAZON_MUSIC on the living room Echo; this script has no playback timeout.

- Entity: `script.playplexplaylist`
- File: [config/media/play_amazon_music_album.yaml](../config/media/play_amazon_music_album.yaml)
- Source file: `scripts/play_plex_playlist_on_alexa.yaml`
- Review note: The historical Plex/two-hour name did not match execution. Only the display name changes; the AMAZON_MUSIC request is unchanged.

## `random_on_an2`

**AN2: run random playback command**

Invoke the existing shell_command.random_on_an2 helper; its implementation remains in the main configuration.

- Entity: `script.random_on_an2`
- File: [config/system/random_on_an2.yaml](../config/system/random_on_an2.yaml)
- Source file: `scripts/random_on_an2.yaml`

## `random_on_inew`

**iNew: run random playback command**

Invoke the existing shell_command.random_on_inew helper; its implementation remains in the main configuration.

- Entity: `script.random_on_inew`
- File: [config/system/random_on_inew.yaml](../config/system/random_on_inew.yaml)
- Source file: `scripts/random_on_inew.yaml`

## `receiver_inputcd`

**Receiver: select CD input**

Send InputCd to the Pioneer AV Receiver through Harmony.

- Entity: `script.receiver_inputcd`
- File: [config/receiver/input_cd.yaml](../config/receiver/input_cd.yaml)
- Source file: `scripts/receiver_turn_on.yaml`

## `receiver_inputtape`

**Receiver: select tape input**

Send InputTape to the Pioneer AV Receiver through Harmony.

- Entity: `script.receiver_inputtape`
- File: [config/receiver/input_tape.yaml](../config/receiver/input_tape.yaml)
- Source file: `scripts/receiver_turn_on.yaml`

## `receiver_inputtuner`

**Receiver: select tuner input**

Send InputTuner to the Pioneer AV Receiver through Harmony.

- Entity: `script.receiver_inputtuner`
- File: [config/receiver/input_tuner.yaml](../config/receiver/input_tuner.yaml)
- Source file: `scripts/receiver_turn_on.yaml`

## `receiver_surrmodestereo`

**Receiver: select stereo mode**

Send the existing Stereo command to the Pioneer AV Receiver through Harmony.

- Entity: `script.receiver_surrmodestereo`
- File: [config/receiver/stereo.yaml](../config/receiver/stereo.yaml)
- Source file: `scripts/receiver_turn_on.yaml`

## `receiver_surround`

**Receiver: send SR+ command**

Send the existing SR+ command to the Pioneer AV Receiver through Harmony.

- Entity: `script.receiver_surround`
- File: [config/receiver/surround.yaml](../config/receiver/surround.yaml)
- Source file: `scripts/receiver_turn_on.yaml`

## `receiver_surroundmodelogic7`

**Receiver: select Logic 7 mode**

Send the existing SurroundModeLogic7 command to the Pioneer AV Receiver through Harmony.

- Entity: `script.receiver_surroundmodelogic7`
- File: [config/receiver/logic7.yaml](../config/receiver/logic7.yaml)
- Source file: `scripts/receiver_turn_on.yaml`

## `receiver_turn_off`

**Receiver: power off**

Send PowerOff to the Pioneer AV Receiver through Harmony with the original 0.6-second command delay.

- Entity: `script.receiver_turn_off`
- File: [config/receiver/power_off.yaml](../config/receiver/power_off.yaml)
- Source file: `scripts/receiver_turn_off.yaml`

## `receiver_turn_on`

**Receiver: power on and select CD**

Send PowerOn followed by InputCd to the Pioneer AV Receiver through Harmony with the original 0.6-second command delay.

- Entity: `script.receiver_turn_on`
- File: [config/receiver/power_on_cd.yaml](../config/receiver/power_on_cd.yaml)
- Source file: `scripts/receiver_turn_on.yaml`

## `run_playlist_on_plex`

**Living room display: play Mult playlist**

Play the Mult Plex playlist on the living room display with shuffle enabled.

- Entity: `script.run_playlist_on_plex`
- File: [config/media/plex_mult_living_room.yaml](../config/media/plex_mult_living_room.yaml)
- Source file: `scripts/run_playlist_on_plex.yaml`

## `run_playlist_on_plex_ants`

**Android TV: play Ants playlist**

Play the Ants Plex playlist on the Android TV Chromecast with repeat-all enabled.

- Entity: `script.run_playlist_on_plex_ants`
- File: [config/media/plex_ants_android_tv.yaml](../config/media/plex_ants_android_tv.yaml)
- Source file: `scripts/play_plex_playlist_on_alexa.yaml`

## `run_playlist_on_plex_bathroom_ants`

**Bathroom: play Ants playlist**

Play the Ants Plex playlist on the bathroom speaker with repeat-all enabled.

- Entity: `script.run_playlist_on_plex_bathroom_ants`
- File: [config/media/plex_ants_bathroom.yaml](../config/media/plex_ants_bathroom.yaml)
- Source file: `scripts/play_plex_playlist_on_alexa.yaml`

## `run_playlist_on_plex_hub`

**Family Hub: request Sailor through Alexa**

Send the existing custom Alexa request for the Caboomers Sailor track to the Family Hub.

- Entity: `script.run_playlist_on_plex_hub`
- File: [config/media/plex_sailor_family_hub_voice.yaml](../config/media/plex_sailor_family_hub_voice.yaml)
- Source file: `scripts/run_playlist_on_plex.yaml`

## `run_playlist_on_plex_hubold`

**Family Hub: play Sailor directly from Plex**

Play the existing Caboomers Sailor track selection from the Plex Music library on the Family Hub with shuffle enabled.

- Entity: `script.run_playlist_on_plex_hubold`
- File: [config/media/plex_sailor_family_hub_direct.yaml](../config/media/plex_sailor_family_hub_direct.yaml)
- Source file: `scripts/run_playlist_on_plex.yaml`

## `run_playlist_on_plex_mobile_ants`

**Dining room: play Ants playlist**

Play the Ants Plex playlist on the dining room speaker with repeat-all enabled.

- Entity: `script.run_playlist_on_plex_mobile_ants`
- File: [config/media/plex_ants_dining_room.yaml](../config/media/plex_ants_dining_room.yaml)
- Source file: `scripts/play_plex_playlist_on_alexa.yaml`

## `shutdown_inew`

**iNew: shut down host**

Invoke the existing shell_command.shutdown_inew helper to shut down its configured host.

- Entity: `script.shutdown_inew`
- File: [config/system/shutdown_inew.yaml](../config/system/shutdown_inew.yaml)
- Source file: `scripts/shutdown_inew.yaml`

## `stopplexplaylist`

**Living room Echo: stop playback**

Stop media playback on the living room Echo.

- Entity: `script.stopplexplaylist`
- File: [config/media/stop_living_room_echo.yaml](../config/media/stop_living_room_echo.yaml)
- Source file: `scripts/play_plex_playlist_on_alexa.yaml`

## `turn_off_lg2_tv_screen`

**LG2 TV: turn screen off**

Send the webOS screen-off command to the LG2 TV.

- Entity: `script.turn_off_lg2_tv_screen`
- File: [config/television/lg2_screen_off.yaml](../config/television/lg2_screen_off.yaml)
- Source file: `scripts/lg.yaml`

## `turn_off_lg_tv_screen`

**Living room TV: turn screen off**

Send the webOS screen-off command to the living room 77-inch TV without changing the existing power behavior.

- Entity: `script.turn_off_lg_tv_screen`
- File: [config/television/living_room_screen_off.yaml](../config/television/living_room_screen_off.yaml)
- Source file: `scripts/lg.yaml`

## `turn_off_living_room`

**Household: turn off lights and media power**

Turn off the original multi-room light and switch lists, then invoke the iNew host shutdown helper.

- Entity: `script.turn_off_living_room`
- File: [config/lighting/household_lights_and_media_off.yaml](../config/lighting/household_lights_and_media_off.yaml)
- Source file: `scripts/turn_off_living_room.yaml`
- Review note: Despite the stable legacy key, this affects multiple rooms and shuts down iNew. Do not narrow the targets as a naming cleanup.

## `turn_on_lg2_tv_screen`

**LG2 TV: turn screen on**

Send the webOS screen-on command to the LG2 TV.

- Entity: `script.turn_on_lg2_tv_screen`
- File: [config/television/lg2_screen_on.yaml](../config/television/lg2_screen_on.yaml)
- Source file: `scripts/lg.yaml`

## `turn_on_lg_tv_screen`

**Living room TV: turn screen on**

Send the webOS screen-on command to the living room 77-inch TV.

- Entity: `script.turn_on_lg_tv_screen`
- File: [config/television/living_room_screen_on.yaml](../config/television/living_room_screen_on.yaml)
- Source file: `scripts/lg.yaml`

## `tv_pic`

**Living room TV: open front-camera snapshot**

Open the h7-hosted front-camera snapshot URL with the webOS launcher.

- Entity: `script.tv_pic`
- File: [config/television/open_front_snapshot.yaml](../config/television/open_front_snapshot.yaml)
- Source file: `scripts/receiver_turn_on.yaml`
- Review note: The h2 snapshot hostname is retained from the live configuration; changing it needs endpoint verification.

## `tv_pic2`

**Living room TV: notify with front-camera snapshot**

Send the existing front-camera notification and attachment data to the living room TV.

- Entity: `script.tv_pic2`
- File: [config/television/notify_front_snapshot.yaml](../config/television/notify_front_snapshot.yaml)
- Source file: `scripts/receiver_turn_on.yaml`
- Review note: The existing h2 attachment URL and local image paths are retained; changing the notification format needs TV verification.
- Not registered in the source service snapshot: `notify.living_room_tv`. Keep the script until the owner reviews its callers and device integration.

## `tv_pic3`

**Living room TV: play REN channel**

Play the existing REN channel name on the living room TV, preserving the provider-facing Cyrillic identifier.

- Entity: `script.tv_pic3`
- File: [config/television/play_ren_channel.yaml](../config/television/play_ren_channel.yaml)
- Source file: `scripts/receiver_turn_on.yaml`

## `tv_pic4`

**Living room TV: play channel 1**

Play channel identifier 1 on the living room TV.

- Entity: `script.tv_pic4`
- File: [config/television/play_channel_one.yaml](../config/television/play_channel_one.yaml)
- Source file: `scripts/receiver_turn_on.yaml`

## `tv_random_channel`

**Living room TV: choose channel 30-1214**

Send digits for a random channel from 30 through 1214 to the LG TV through Harmony with a 0.4-second delay.

- Entity: `script.tv_random_channel`
- File: [config/television/random_channel_30_1214.yaml](../config/television/random_channel_30_1214.yaml)
- Source file: `scripts/tv_random_channel.yaml`

## `tv_random_channel2`

**Living room TV: send random channel digits**

Send four independently generated digits using the original exclusive range bounds and 0.1-second Harmony delay.

- Entity: `script.tv_random_channel2`
- File: [config/television/random_channel_digits.yaml](../config/television/random_channel_digits.yaml)
- Source file: `scripts/tv_random_channel.yaml`
- Review note: Jinja range upper bounds are exclusive: the first digit is always 1; the other ranges remain exactly as deployed.

## `tv_random_channel_p`

**Living room TV: choose channel 1216-1399**

Send digits for a random channel from 1216 through 1399 to the LG TV through Harmony with a 0.4-second delay.

- Entity: `script.tv_random_channel_p`
- File: [config/television/random_channel_1216_1399.yaml](../config/television/random_channel_1216_1399.yaml)
- Source file: `scripts/tv_random_channel.yaml`

## `tv_type`

**Living room TV: send legacy test keys**

Send the fixed Harmony key sequence 1, A, S, D, A to the LG TV.

- Entity: `script.tv_type`
- File: [config/television/send_harmony_test_keys.yaml](../config/television/send_harmony_test_keys.yaml)
- Source file: `scripts/tv_random_channel.yaml`

## `tv_type2`

**Living room TV: insert legacy test text**

Insert the literal text 123 through the existing webOS input-method command with replace set to zero.

- Entity: `script.tv_type2`
- File: [config/television/insert_webos_test_text.yaml](../config/television/insert_webos_test_text.yaml)
- Source file: `scripts/tv_random_channel.yaml`

## `volume_down`

**Media: set household volume presets**

Set the retained Echo volume preset to 20 percent.

- Entity: `script.volume_down`
- File: [config/media/set_household_volume_presets.yaml](../config/media/set_household_volume_presets.yaml)
- Source file: `scripts/volume_down.yaml`
