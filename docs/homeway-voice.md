# Homeway voice for Echo Dot and Echo Show 5

Homeway supplies speech recognition, conversation and speech synthesis to the
existing HA Container through Wyoming at
`homeway.homeassistant.svc.cluster.local:11027`. There is no additional Whisper,
Piper or server-side wake-word deployment for these devices.

The existing English **Sage** assistant remains preferred. The separate
**Sage Russian** assistant is ready for explicit selection on each converted
device. Its reproducible settings are in
[sage-russian-pipeline.json](voice/sage-russian-pipeline.json): overall language
`ru`, recognition/conversation/synthesis `ru-RU`, and the existing Homeway engines.
The current pipeline ID is `01m3x4axcts4wn3hwqgr30d22y`; recreating it produces a
new ID. The voice remains `homeway-website-controlled`, so account-side Homeway
voice changes also affect this assistant. `prefer_local_intents` is enabled to
let HA handle supported commands before the conversation agent.

## Network and audio contract

HA runs on h7 in OCI. Home devices reach its private address **10.0.0.58** through
the existing site-to-site IPSec connection. The internal URL is now
`http://10.0.0.58:8123`; the external URL comes from the local `home_assistant_external_url` secret.

The former internal hostname resolved inside Kubernetes and
through public resolver 1.1.1.1, but the home resolver 192.168.160.1 returned no
address. A generated TTS URL consequently failed to resolve from Synology.
The private IP avoids this observed DNS failure. Do not restore the hostname
without verifying it from the actual device network. This HTTP endpoint remains
private and uses the existing encrypted IPSec route; do not expose port 8123 to
the public internet. Reassess the URL if h7's private address changes.

Wake-word detection should run on the device. Speech is sent to HA/Homeway after
activation, rather than continuously streaming room audio to OCI. Homeway voice
processing needs internet connectivity. A local wake detector does not make
recognition or responses work offline.

HA can return MP3 to Android clients and transcode Homeway TTS to WAV for
ESPHome satellites. The tested satellite format is PCM, 16 kHz, mono, 16 bit.
Streaming WAV headers can carry a placeholder length; measure received PCM
frames instead of treating that header as the duration.

## Echo Dot: EchoLocal 0.0.8

The conversion task owns firmware, device backups, Wi-Fi and EchoLocal setup.
EchoLocal speaks the ESPHome native API; it is not an ESP32 firmware build.
After installation:

1. Add the Dot through the stock ESPHome integration using its reserved LAN IP
   and individual Noise encryption key. HA must reach the device on TCP 6053.
   Do not depend on multicast discovery across IPSec.
2. Assign its real room and explicitly select **Sage Russian** for the active
   wake-word/pipeline slot. Start with a bundled model such as Okay Nabu or
   Hey Jarvis. EchoLocal supports two independent slots; a second English slot
   can be added later if needed.
3. Confirm the microphone reaches Assist and a Russian answer plays through the
   physical speaker. For HTTP reply delivery, verify the actual media URL from
   the Dot; the NAS reachability check is not a substitute for this test.
4. Verify wake detection, mute, interruption, recovery after Wi-Fi loss and a
   device reboot before relying on hands-free operation.

The pinned release bundles English wake models Okay Nabu, Hey Jarvis and
Hey Mycroft. Stop is a separate interruption detector. Changing the pipeline
language does not retrain these models. EchoLocal supports custom microWakeWord
and openWakeWord models, so a Russian wake phrase is technically possible, but
no Russian model has been installed or acoustically validated here. For the
HA custom microWakeWord route, the model and metadata live under
`/config/custom_wake_words/`; verify model compatibility and the device's access
to HA's offered download URL before selecting one. Preserve a working bundled
model for rollback. See the
[pinned EchoLocal documentation](https://github.com/ygelfand/echolocal/tree/0.0.8).

## Echo Show 5: LineageOS and Android

The separate conversion task owns hardware identification, unlock and the ROM.
Its initial client is HA Companion 2026.8.4 minimal for ARMv7, without GApps.
Once Android is installed, connect it to HA, grant microphone access and select
**Sage Russian**. First verify Assist using its button, then enable experimental
wake detection with Home Assistant set as the default digital assistant.

The [official Android instructions](https://www.home-assistant.io/voice_control/android/)
document local microWakeWord and the supplied Hey Nabu, Hey Jarvis and
Hey Mycroft choices. They do not document uploading an arbitrary Russian model.
Microphone, speaker, echo cancellation and background operation on this Show
remain hardware acceptance tests, not results established by server tests.

If a custom Russian phrase is required on Android, VACA is an optional next
step: its [custom-file support](https://github.com/msp1974/ViewAssist_Companion_App/wiki/Custom-Files)
accepts microWakeWord `.tflite` plus `.json` models. VACA uses its own Android
app and HA integration; its Wyoming satellite port defaults to TCP 10800.
Do not configure it as an ESPHome device or leave two apps competing for the
microphone. Start with the simpler Companion path until the converted hardware
passes audio tests.

## Verification: October 1, 2026 PDT

- Homeway's Wyoming capabilities advertised `ru-RU` for all three voice stages.
  Both Homeway and HA pods were Ready with zero container restarts.
- A synthesized Russian recording was submitted as 16 kHz PCM to the live
  `assist_pipeline/run` WebSocket API, through STT, conversation and TTS.
  The recognized request was “Ответь одним словом по-русски: «Готово».” and the
  response was “Готово”. Pipeline execution took 2.15 seconds in this single
  server test; it is not a latency guarantee for real microphones.
- Response MP3 returned HTTP 200 and decoded successfully. A separate Russian
  WAV request returned HTTP 200 with 61,008 bytes and about 1.9 seconds of actual
  PCM at 16 kHz, mono, 16 bit. The HA-generated URL was successfully fetched
  from Synology over the home-to-OCI private route after the internal URL fix.
- The installed HA configuration check returned `valid`, with no errors or
  warnings. The URL was applied through `config/core/update` without restarting
  HA, and the matching YAML change persists across future starts.
- Physical Dot and Show commissioning remains with the two conversion tasks.
  No real-device wake-word reliability or audio quality is claimed yet.

## Restore and rollback

The native HA backup includes Assist's runtime pipeline storage. Restore that
backup first and check Settings → Voice assistants for **Sage Russian** before
creating anything. This repository's build does not overwrite `.storage`.

For a fresh instance without a usable backup, restore the Homeway deployment
and its account pairing from the infrastructure recovery set, then add its
Wyoming endpoint and confirm the STT, TTS and conversation entities are loaded.
Create the Russian assistant in the UI using the JSON settings above, adapting
engine IDs if HA assigned different names. Alternatively, use HA's authenticated
WebSocket API: list `assist_pipeline/pipeline/list` first, then send
`assist_pipeline/pipeline/create` with those fields only if it is missing.
Do not overwrite a different existing assistant by name or change the preferred
English pipeline. Re-select the newly created assistant on each device.

To disable Russian voice, reassign the devices to Sage and remove Sage Russian
through the UI. To reverse the URL change, restore the previous value in both
`configuration.yaml` and `config/core/update`, but only after fixing and testing
home DNS. The pre-change live configuration is saved privately under
`/config/.backups/homeway-voice-20261002T014338Z/`. Credentials, device encryption
keys, test recordings and temporary media URLs are not committed to Git.
