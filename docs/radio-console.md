# Radio and speaker console

`custom:radio-console-card` adds one compact radio selector below the existing
Media cards. It uses Home Assistant's existing media-player integrations; it
does not add helpers, a backend service, an audio server or a new integration.
The resource is `config/www/radio-console-card.js` and loads as a JavaScript
module. Register its deployed `/local/` URL as a Lovelace resource.

The deployed Media view uses sparse Sections layout. Existing media blocks come
first, followed by the full-width console and then a full-width **Phones and Echo**
heading. Individual endpoint sections follow it. This guarantees that the phone
inventory starts below the old players instead of filling gaps beside them.

## Using the console

1. Search and choose a station, or enter a direct HTTP(S) audio URL.
2. Select one speaker, several speaker chips, or a configured group.
3. Press **Play selected**. Nothing plays merely by opening the card, choosing
   a station, selecting a group or moving the volume slider.
4. **Stop selected** and **Apply volume** are separate explicit actions.

No speakers are selected on a fresh card. Offline speakers remain visible, with
their names and current status. An offline or unsupported recipient is skipped
with an explanation. Each actual request gets a **Sent** or failure receipt;
**Sent** acknowledges the HA request, not independently verified audible sound.
The card does not retry failed actions or print private service errors.

Mixed groups play the same selection but are **not synchronized**. Cisco's
Asterisk media path and a normal Echo HTTP player do not share an audio clock.
Use an existing compatible Music Assistant or Sonos sync group when synchronized
playback is required; do not infer synchronization from selecting several chips.

## Private configuration

Keep actual player mappings, station URLs and deployment details in private
Lovelace configuration. This is a fictional example:

```yaml
type: custom:radio-console-card
title: Radio & speakers
players:
  - entity: media_player.example_phone
    name: Desk phone
    icon: mdi:phone-classic
  - entity: media_player.example_speaker
    name: Speaker
stations:
  - id: example_radio
    name: Example radio
    url: https://audio.example.org/radio.mp3
    sources:
      media_player.example_phone: "701 — Example radio"
groups:
  - name: Both speakers
    entities:
      - media_player.example_phone
      - media_player.example_speaker
limits:
  - name: Phone radio capacity
    entities:
      - media_player.example_phone
    max: 4
```

A station's `sources` dictionary takes priority for its listed players. The
console sends that exact string through `media_player.select_source`, after
checking the player's current `source_list` and `SELECT_SOURCE` capability.
This accommodates different source labels on Cisco and LifeSize without
guessing names or dialing arbitrary phone numbers. A missing source does not
silently fall back to another playback route.

Other station recipients receive its `url` through `media_player.play_media`
with content type `music` and the station title as metadata, provided they
advertise `PLAY_MEDIA`. A custom URL always requires that capability. A player
that exposes only preset sources, such as the current LifeSize adapter, cannot
play arbitrary URLs and is explicitly skipped. A URL must point to audio, not
a website, Spotify page or YouTube page. The relevant integration still enforces
its own allowed origins, codecs, session limits and telephone-call protections.

## Capacity and operating limits

Configure `limits` from the deployed PBX settings. Before **Play**, each limit
counts the available, supported recipients that would receive a command. If any
limit is exceeded, the whole play operation is refused before sending anything.
Capacity limits do not prevent stopping playback or adjusting volume.

The console cannot count phone sessions started elsewhere. Such sessions may
consume capacity after this check; a subsequent integration failure is shown
for that recipient. It does not end other calls to make room. Calls are sent
sequentially, with no automatic rollback or retry after partial success.

Groups replace the current chip selection. **All available** may select more
phones than the configured capacity permits; reduce that selection before Play.
Current states remain visible while the card is open. Existing top-of-page
players and their settings are independent of this console.

## Rebuilding the private catalog

Use the reviewed PBX `radio-catalog.json` and fresh, deduplicated HA player
metadata. Each private target supplies `entity`, `name`, optional `icon`, `caps`
(the current `supported_features` integer), `source_list`, `group`, and `kind`
(`phone` for targets that consume a phone session).

```sh
python3 scripts/build_radio_console.py \
  /private/path/radio-catalog.json /private/path/targets.json \
  /private/path/console.json
```

The output is owner-readable only. Phones receive exact source labels already
present in their metadata, preserving the reviewed PBX preset's port and resolver
policy. Other direct audio-capable players use the catalog URL; JSON resolver
endpoints and HLS presets are kept on existing phone source routes instead of
being mistaken for generic audio URLs. A missing phone preset stops generation
instead of silently switching to the arbitrary-URL route. Refresh the inventory after deploying a new PBX catalog and
reloading the affected HA controls. Keep endpoints and generated output private.

The LifeSize adapter uses native outgoing SIP radio calls, so it does not need
to enable persistent auto-answer. Its own guarded Play/Stop and station switch
keep ordinary telephone calls separate. Arbitrary custom URLs use the existing
managed Cisco player or a compatible speaker; LifeSize uses the curated catalog.

Run the pure routing and dispatch tests without a browser or HA connection:

```sh
node --test tests/radio_console_card.cjs
```

Validation covers source-specific routing, unsupported custom URLs, offline
recipients, group capacity, explicit volume actions, service allowlisting and
per-target failures. Browser verification should also check theme contrast,
station search, selection labels and narrow layouts. No audio playback is
required for layout testing.
