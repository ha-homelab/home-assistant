# Echo Dot music from Plex

The default music source is the household Plex **Music** library. The
`echo_plex_music` package starts its **All Music** playlist on the Music Assistant
player `media_player.echo_dot_music`. It does not control another room's player.
Homeway handles speech; Music Assistant supplies the music catalogue and audio.

## Voice commands

Select the Sage Russian pipeline with `prefer_local_intents` enabled:

- “Играй музыку”, “Включи музыку” or “Включи музыку из Плекса”.
- “Останови музыку” or “Поставь на паузу музыку”.
- “Продолжи музыку”.
- “Следующий трек”.

The optional suffix “на эхо” is accepted. Equivalent English sentences are
included for an English Assist pipeline; the configured confirmations are in
Russian. These are music-specific intents, without an unrestricted `play
{query}` wildcard. Keep the separate EPG sentences scoped to television so they
do not intercept music requests.

Play resumes an existing Plex queue without rebuilding it; when that queue is
already playing, it leaves the current track and position alone. An empty queue
or a queue from another source is replaced with All Music. Source detection
uses the current item's Plex stream provider or Plex URI, including library
items whose URI starts with `library://`. This avoids repeatedly expanding the
entire smart playlist (16,472 tracks at commissioning) on the small home worker.
Keep queue inspection inside a single template: the service response can contain
nested enum values, so assigning its whole dictionary to a templated script
variable can turn it into a string. Export only the boolean source decision.
Pause/resume/next control that same queue. All four commands use one dispatcher
and check availability first. If the Echo music entity is missing or unavailable,
the returned voice response says so instead of announcing successful playback.
The package does not change volume, wake words, microphone settings or firmware.

## Restore and commission

1. Restore Music Assistant using the infrastructure repository's
   [local Plex and weekly recovery runbook](https://github.com/4alvit/home-assistant-k3s/blob/main/companions/README-music-assistant.md).
   It runs on `syn` at `192.168.175.130`; Plex is `192.168.167.25:32400`.
   Audio must stay on this LAN path. HA's control connection may still use OCI.
2. Enable EchoLocal Sendspin and register `192.168.163.44` in the Music Assistant
   Sendspin provider's manual discovery addresses. The speaker listens on TCP
   8928. Do not run two Music Assistant instances against the same player.
3. Keep the native ESPHome speaker for Assist responses. Rename the **Music
   Assistant** entity for this same Echo to `media_player.echo_dot_music` and
   expose it to Assist. Assign it and the satellite to their actual room.
4. Restore the authenticated Plex provider (`plex--home-music`). If recreating
   it produces a different provider ID, use the playlist URI returned by Music
   Assistant and update this package. The verified current URI is
   `plex--home-music://playlist//playlists/60771`; the slash is part of Plex's
   item ID. A bare rating key `60771` is not a valid provider playlist path.
5. Deploy `config/packages/echo_plex_music.yaml` and the two
   `config/custom_sentences/{ru,en}/plex_music.yaml` files. Check the active HA
   configuration, then reload scripts, intent scripts and conversation sentences.
   These domains are already loaded; HA does not need a restart.
6. Verify a real spoken request and audible playback, pause/resume/next, and
   recovery after a speaker reconnect. A successful service call alone does not
   establish that sound reached the speaker.

Expose `script.echo_plex_music` to Assist if the conversation agent should also
be able to invoke the default playlist. Custom local sentences already target
the script directly. Arbitrary artist/title requests use Music Assistant's
catalogue and require a correctly exposed player and area; they are not matched
by these fixed default-playlist sentences.

## October 2, 2026 verification

Music Assistant was moved from OCI to the home worker without changing its
server ID or restarting HA. The authenticated Plex provider resolves **All
Music**. Its reported playlist leaf count was initially stale; actual expansion
returned the full 16,472-track music library. The initial weekly-format snapshot was saved on
Synology, independently extracted, and both SQLite databases passed integrity
checks. Scheduling is weekly; no Plex music files are copied into the backup.

The three YAML files passed the installed HA configuration check and were loaded
using script, intent-script and conversation reloads. All 27 sentence-recognition
cases passed, including unrelated TV/light requests that must not match. Four
live text requests through Assist returned the explicit unavailable-speaker
response, with no audio played. The default script is exposed to Assist.

The recovered Echo registered as `media_player.echo_dot_music`, exposed to
Assist. Sendspin manual discovery is enabled and the temporary diagnostic
firewall hold was removed. Echo logs confirm receipt and decoding of stereo
48 kHz / 16-bit FLAC; play, resume from the saved position, and next-track
controls were exercised. Playback tests ended with the speaker idle and its
original hardware volume restored. The user subsequently confirmed audible playback from a spoken request; the
latency and stability observations below qualify that result.

The current Sendspin path implements pause by stopping the transport while
Music Assistant retains the queue position. HA can therefore display `idle`
after pause; resume still continues the same track. During commissioning the
home VM also exhibited CPU contention and several-second server response
delays. Do not treat a successful service response alone as proof of continuous
audio or blame these delays on Wi-Fi without packet evidence.

The queue-source template regression was reproduced with a nested enum in the
Music Assistant response, then fixed without serializing the queue into an
intermediate script variable. All eight isolated HA runtime tests passed. A
live text Assist request, “играй музыку”, started the retained Plex queue in
1.809 seconds; pause, resume from 13 seconds, and next-track commands also
succeeded. This checks the intent/service/playback path, not microphone
recognition or subjective audio quality.

A subsequent native-log inspection showed uptime resetting near the final music
test (approximately 22:50:14–22:50:44 UTC). This suggests a system reboot and
is consistent with the delayed final stop/volume state. Its cause is
unconfirmed: the retained EchoLocal log contains no boot-reason, watchdog,
panic or OOM marker, and the read-only native interface does not expose prior
kernel logs. No reboot command was issued by the music test. Both players were
finally verified idle and the original hardware volume was restored to 22/30.
Do not infer continuous playback stability from the successful command tests;
the reboot cause and stable playback remain separate acceptance items.

### Spoken playback and stability

The user's later spoken “играй музыку” reached the script at 23:07:52.980 UTC.
Queue inspection took about 0.5 ms, and `media_play` returned at 23:07:55.979 UTC;
the existing queue was reused. These timings measure the HA action, not the
whole spoken-request-to-audible-music delay.

The Echo's native log showed that the first decoded FLAC chunk was already
available while its clock model placed the start about 22.463 seconds in the
future. Audio rendering resumed near that scheduled time, after TTS had ended.
Early clock-offset samples contained a large step; the source of that step is
unconfirmed. The clock model later settled without a forced reconnect. A
separate IPv6 autodiscovery URL error was also observed; the configured IPv4
manual connection remains the working path.

The user also reported intermittent grinding/stuttering. A native buffer sample
of 8 ms could not fill the next 21.333 ms render frame, explaining a short
zero-filled gap even though the dropped-packet counter was zero. This is separate
from the initial clock delay.

At 23:19:52 UTC the two manually started Plex catalogue sync jobs were cancelled
to reduce background work during the user's playback. Playback and volume were
left unchanged. The imported 14,060 unique tracks were retained; the complete
source contains 16,472 tracks and catalogue import is not yet complete. Automatic
12-hour sync schedules remain enabled; the next run was 03:51 PDT on October 3.
An incomplete/cancelled sync does not reach the provider's deletion pass.

The first observed window after cancellation contained no new late chunks and
no sampled buffer below 218 ms. This is a short technical observation, not proof
that audible stuttering is resolved. During playback the 750m CPU limit still
throttled 93 of 204 sampled CFS periods (4.228 seconds across a 20.53-second
measurement); the home VM also showed substantial hypervisor CPU steal. Neither
measurement alone attributes every audible defect to CPU contention.

The cluster does not expose the `pods/resize` API. Increasing this deployment's
CPU limit therefore requires a rollout that interrupts Music Assistant playback.
Do that only in a suitable playback window, preserving queue position and volume;
HA itself does not need a restart. These diagnostics did not change resource
limits, firmware, microphones or wake-word settings, or force a Sendspin reconnect.
