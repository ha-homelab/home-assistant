# EPG voice playback

The package exposes a dynamic `input_select.home_tv` programme catalogue plus
`script.play_kukutiki`, `script.play_news_channel`, and
`script.play_rainbow_channel` fixed shortcuts. One private
controller refreshes the catalogue every five minutes and at startup. Choosing a
programme requests a new catalogue, resolves its exact title and channel against
the current guide, and casts a fresh signed HTTPS session to the configured
player. The gateway receives no Home Assistant token.

Google sees Home TV as a Sensor with the Modes trait. This is a finite catalogue
of advertised choices, not unrestricted spoken-title search. A candidate voice
command is "Hey Google, set Home TV option to Columbo" when Columbo is currently
listed. Verify recognition on the physical display; a synthetic Google request
or successful Cast API call is not a microphone or picture/audio test.

The dispatcher supplies the signed HLS URL and content type using HA's default
Cast behavior. It does not force a stream type or programme metadata. A minimal
launch sustained playback in receiver checks where the combined explicit LIVE
and metadata payload terminated early; those checks did not isolate which extra
field caused the difference. Programme selection still uses the current EPG.

The reusable package, API contracts, and YAML/Jinja behavior tests live in the
[`epg-voice-gateway`](https://github.com/4alvit/epg-voice-gateway) repository.
Start with its [ordered setup checklist](https://github.com/4alvit/epg-voice-gateway/blob/main/docs/setup-checklist.md).
The catalogue API requires gateway commit
`6dda2a7e10301690257fa38bb6a5759f639a33df` or a later compatible revision.

## Private configuration

Merge the `epg_voice_*` entries from `secrets.yaml.example` into private
`secrets.yaml`. Keep the gateway control API on the LAN. Configure an ordered
`EPG_VOICE_CHANNEL_IDS` allowlist on the gateway from channels tested on the
receiver. `EPG_VOICE_PREFERRED_QUERIES` prioritizes short programme names, while
`EPG_TITLE_ALIASES` maps spoken names to guide spellings. The catalogue defaults
to 30 titles and never publishes stream URLs.

Set `epg_voice_ren_channel_id` to the verified gateway channel ID for the
**Rainbow Channel** shortcut. The fixed wrapper calls the same private
dispatcher and configured display as the news shortcut. It still requires a
current programme in the guide and does not substitute another stream.

Only programmes currently airing on allowed channels appear. Catalogue refresh
failure clears choices to Ready and Unavailable. Neither polling, option-list
changes, nor those neutral values starts playback. Explicit repeated selections
are handled through a narrowly filtered service-call event. The controller
serializes requests and resets the selector to Ready; playback uses
`exact_title: true`, so a stale title cannot become a broader search for the next
programme. Missing, ambiguous, stale, or invalid responses stop safely. No
transcoding or automatic substitution is provided.

Validate each candidate channel on the intended receiver before treating it as
supported. A successful SD stream does not establish HD compatibility, and an
H.264/AAC probe alone does not prove playback. If a receiver fetches a playlist
and segment but stays idle while the proxy continues downloading normally,
record a receiver playback failure; the exact format cause remains unproven.
If playback starts and later exhausts upstream retries, record the source
failure separately. Neither outcome is fixed by changing EPG title matching.

## Google linking and automatic synchronization

`config/packages/google_assistant.yaml` configures the manual integration with
exposure disabled by default. Only Home TV and the three fixed shortcuts are
exposed. Both private dispatcher scripts and all bookkeeping helpers remain
unexposed. Follow the complete
[Google Console and OAuth setup](https://github.com/4alvit/epg-voice-gateway/blob/main/examples/home-assistant/README.md#first-time-manual-google-linking)
for the client ID, URLs, scopes, icon, and draft settings.
Select Scene and Sensor as device categories in Google Home Developer
Console. Configure trusted HTTPS `/auth/authorize`, `/auth/token`, and
`/api/google_assistant` endpoints; the gateway itself stays private.

Enable the HomeGraph API in the same Google project and create a dedicated
service account for HA. Save its JSON key as `home-media-service-account.json`
next to `secrets.yaml`, mode 0600. The secret
`epg_voice_google_service_account` includes that file. Keep it outside source
control, public diagnostics, and shared backups. No HA Cloud subscription or
billing activation is required for this manual integration. The reusable
[HomeGraph procedure](https://github.com/4alvit/epg-voice-gateway/blob/main/examples/home-assistant/README.md#homegraph-and-the-service-account-key)
covers Console steps, key handling, and obtaining the linking user's HA ID
without printing credentials. This repository uses
`service_account: !secret epg_voice_google_service_account`, with
`epg_voice_google_service_account: !include home-media-service-account.json`
in private `secrets.yaml`, instead of including the file directly in the package.

Set `epg_voice_google_agent_user_id` to the HA user ID that actually signs in
when linking Home Media in the Google Home mobile app. It is not a Google email,
service-account ID, or project ID. The package enables automatic Request Sync
for this deployment. Requests occur after the advertised options change.
`report_state` remains false; Google can query current state.

The stock HA Request Sync action discards the HomeGraph HTTP result. The status
helper therefore says that a request was attempted, not accepted. Confirm the
new options in Google Home and inspect protected HomeGraph diagnostics when
needed. A HomeGraph 404 can indicate an unlinked account, incorrect HA user ID,
or project mismatch; creating credentials or sending a synthetic admin SYNC does not complete mobile account
linking. After linking, ask Google to sync devices once to pick up the current
catalogue. Automatic requests ask Google to update subsequent changes; verify
that the new options are accepted.

Use the project-owner Google account in the Google Home app, add a Works with
Google Home integration, choose the draft Home Media integration, and sign in
with the dedicated HA login. The fixed scene command remains "Hey Google,
activate Play News Channel". Google exposes scripts as scenes and does not pass
arbitrary text into their fields.

For the REN TV shortcut, say **"Hey Google, activate Rainbow Channel."** Do not
append "on Home Channels": that names the separate virtual TV. This scene is
a fallback for media phrases that Google routes to YouTube or fails to
understand despite correct channel publication. Verify the actual microphone
command and picture/audio separately. A Routine can optionally map another
phrase to the working scene; it is not required for direct activation.

HA OAuth grants follow the signed-in user's permissions. Exposing a few devices
and requesting email/name scopes does not restrict the resulting token to those
devices. The dedicated non-admin user still has HA's ordinary all-entity
read/control permissions; exposure settings are not an authorization boundary.

## Deployment and recovery

Validate the complete staged configuration with the installed HA version before
replacing files. Back up the packages, secrets, and any existing key. Preserve
unrelated configuration, registries, secrets, and ongoing household actions.
Adding these helpers, the event automation, and HomeGraph credentials requires
a checked activation. Wait for a fresh idle window before an HA restart; do not
cancel active timers or reload automations to force installation.

On the tested HA 2026.9.2 integration, new YAML Google exposure entries require
an HA restart. `script.reload` can load a script but does not reread Google's
`entity_config`; reloading the Google config entry reuses cached YAML. After
checked activation, request sync for the linked HA user and confirm the named
scene in Google's actual stored inventory while preserving existing devices.

After activation, verify the controller, selector, advertised Modes settings,
neutral reset, repeated explicit selections, and failure handling. Then verify
real Google linking and a physical microphone invocation separately. For
rollback, restore the backed-up package and credential configuration, validate,
and activate only in another idle window. Gateway restarts invalidate existing
media sessions; request playback again afterward.

## Privacy

Scripts and the calling automation disable saved traces. Keep REST command
logging at warning or higher: the existing IGW package supplies this setting,
so the EPG package does not duplicate the logger key. Signed media URLs can
still appear in private Cast state, recorder history, logs, and backups. Keep
those private. Repository examples contain no deployment hostname, household
identifier, provider URL, credential, or service-account key.

## References

- [Home Assistant Google Assistant integration](https://www.home-assistant.io/integrations/google_assistant/)
- [Google Modes trait](https://developers.home.google.com/cloud-to-cloud/traits/modes)
- [Google Request Sync](https://developers.home.google.com/cloud-to-cloud/integration/request-sync)
- [Home Assistant REST command responses](https://www.home-assistant.io/integrations/rest_command/)
- [Home Assistant Cast integration](https://www.home-assistant.io/integrations/cast/)

## Optional free-text Assist input

`config/packages/epg_voice_assist.yaml` and the sentence files under
`config/custom_sentences/{en,ru}/epg_voice.yaml` add the `EPGVoicePlayMedia`
intent. They require the `epg_voice_channels` custom integration version 0.2.0
or later and the gateway's authenticated `/v1/play-text` API. The integration
source, installation procedure, and detailed behavior are maintained in the
[gateway Assist guide](https://github.com/4alvit/epg-voice-gateway/blob/main/examples/home-assistant/assist-README.md).

Examples: `play Example News on home channels`, `играй Кукутики`, and
`включи канал Example News`. Russian turn-on commands require a media noun or
fixed display suffix so ordinary commands such as turning on a light remain
available to Home Assistant. Configure a matching language and the Home Assistant
conversation agent in the Assist pipeline. The service response is English.

A signed-in user must have control permission on the integration's configured
display. The action carries that user's context and accepts query text only;
it does not accept an arbitrary receiver or URL. Ambiguous names request a more
specific complete query. No-match and unavailable results start no stream.
Google fulfillment keeps its separate dedicated-user restrictions.

Deploy only these three YAML files and the reviewed integration update after
backing up the live configuration. Validate with the installed HA checker, then
restart while the receiver is idle when installing `intent_script` for the first
time or replacing the component's Python code. For later sentence-only edits,
reload `conversation` and `intent_script`. Preserve unrelated live configuration
drift; this feature does not require replacing the entire overlay.

Verify typed Assist first, then a phone or Assist satellite. The Google/Lenovo
microphone does not automatically feed Assist. Google Channel voice commands
still select from their separately published names and synonyms. Confirm actual
moving video and sound independently of an accepted HA action.
