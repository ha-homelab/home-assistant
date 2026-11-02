# Phones, Media, and Cerbo GX

The **Phones** dashboard keeps the full endpoint inventory visible, including
offline devices. Its overview opens a separate controls view for each endpoint.
Media playback stays on **Media**; voice assistants, microphone settings,
Bluetooth proxies, calls, timers, reminders, diagnostics and firmware controls
belong on Phones.

The inventory contains ten Cisco handsets, one LifeSize conference phone, two
Echo Shows and two converted Echo Dots. An endpoint receives only the controls
that its integration actually exposes. In particular, the LifeSize phone does
not acquire Bluetooth-proxy support or a device-owned alarm by appearing here.
Cisco secondary lines belong to their physical handset; they are not extra
phones. Software clients and Cast displays are likewise distinct endpoints.

The old Echo display URLs remain valid but are hidden from the sidebar, so
device launchers and existing navigation actions continue to work. The previous
Existing endpoints URL is retained and titled Phones. Legacy iframe dashboards
and Zero Grid are removed. Shared energy sensors and inverter controls remain.

## Rebuilding the dashboards

`scripts/build_phones_dashboard.py` renders JSON from a private manifest:

```sh
python3 scripts/build_phones_dashboard.py private-manifest.json private-dashboard.json
```

The manifest contains `url_path`, optional `title` and `icon`, a `devices` list,
and optional `extra_views`. Each device specifies a unique `key`, `title`,
`family`, a status entity, optional player, explicit entity IDs, and optional
existing action cards. It must be constructed from the actual entity registry,
not from a guessed naming pattern. The renderer does not filter by availability
or enable disabled entities. It preserves action cards and checks that all
requested controls occur in the generated view.

Set `persistent_labels` to `true` when Mushroom cards are installed. This keeps
the explicit device name and navigation available even before an integration
has created its first state during HA startup. The default renderer uses native
Tile cards and does not require Mushroom.

Cerbo GX's inventory is selected by the integration entry owning the GX firmware
update entity, then grouped by device. The initial inventory renderer creates a
separate dashboard; the layout migration below moves its contents into a
**Cerbo GX** tab in the main Lovelace dashboard. All controller settings and
statuses are inline on that tab, including complete charging schedules. Other
ecosystem devices retain detail subviews with a back link to the same tab.
The firmware tile opens the normal update dialog; opening the dashboard never
installs an update.

Keep manifests, generated dashboards, registry exports and room assignments
private. Before saving via `lovelace/config/save`, re-read the current dashboard
and compare the section being replaced. Preserve unrelated concurrent edits.
Validate explicit entity references against the current registry and check the
rendered overview, an offline endpoint and each added control type in the UI.

## Main dashboard layout

The Cerbo tab lives at `/lovelace/cerbo-gx`. Its old sidebar entry is hidden;
the previous dashboard remains available for existing bookmarks. The new tab
does not require an **All GX settings and statuses** button: controller controls
are already present, grouped into firmware and health, Dynamic ESS, charging
limits, grid control, battery and solar measurements, and charging schedules.
The migration checks that every original ecosystem entity remains represented.
Energy controls use their own grouping rules instead of phone keywords; for
example, `dynamic_ess` must not match a microphone group and `available_version`
must not match a Bluetooth group.

On Media, each phone and Echo occupies a normal-width masonry card. Do not put
the whole endpoint inventory inside another three-column Grid card: that divides
one dashboard column into tiny players. Each endpoint uses
[`custom:mini-media-player`](https://github.com/kalkih/mini-media-player#shortcuts-object)
with a persistent heading, volume controls and two columns of preset buttons.
The heading identifies an endpoint even when it is offline. Unrelated existing
players and remote controls retain their configuration.

Presets are device-specific. Cisco and LifeSize buttons use `type: source` with
the exact strings advertised in each player's `source_list`. Their PBX radio
sources are not interchangeable with arbitrary stream URLs. Echo buttons use
compatible direct HTTP(S) music presets from the existing reference player;
Sonos-specific protocols and device-specific private feeds are not copied.
The renderer never calls a playback service.

Prepare an updated main dashboard from fresh private exports:

```sh
python3 scripts/prepare_lovelace_layout.py \
  private-main.json private-cerbo.json private-media-manifest.json \
  private-main-updated.json
```

The media manifest has a `devices` array. Each device contains `entity`, `name`,
an optional `icon`, `shortcuts`, and `source_list` when source presets are used.
Each shortcut has `name`, `type`, `id`, and optionally `icon`. IDs and stream URLs
come from the private deployment, not a public list of household devices.

The two migration modules are pure transformations. They preserve unrelated
views, keep ecosystem subviews out of the top tab bar, and reject ambiguous
targets or edits to previously generated cards. The CLI writes only the new
private JSON file with owner-only permissions; it does not deploy or restart HA.
Before applying, re-read the live configuration and compare it with the input
export. Save through `lovelace/config/save` only if it still matches, verify the
result, then hide the old sidebar entry with `lovelace/dashboards/update`.

Check in the browser that the new Cerbo tab opens, its controller settings are
visible without another page, and device detail views return to it. On Media,
check a connected player and an offline player, preset labels, and card width.
Validate every source preset against the live player's advertised sources and
verify music playback support before copying stream presets. Layout verification
does not require starting audio throughout the house or changing energy settings.

## LifeSize media and native controls

`config/packages/phones_controls.yaml` adds a Universal media player and native
controls. Radio selection dials an existing, allowlisted PBX radio service from
the conference speaker. It is not a generic URL-streaming or casting receiver.
The media Stop command only ends an observed outgoing radio call. A separate
Hang up control deliberately ends the current call.

`scripts/lifesize_ha_bridge.py` uses the `cisco_lifesize.py` driver from
[cisco-home-telephony](https://github.com/4alvit/cisco-home-telephony).
Install both files in the private runtime directory referenced by the package,
together with an owner-only `config.json` containing:

```json
{
  "line": "222",
  "device": {
    "host": "192.168.50.20",
    "identity_file": "/private/path/identity",
    "known_hosts_file": "/private/path/known_hosts",
    "host_key_alias": "verified-phone-alias",
    "legacy_rsa": true,
    "label": "Conference phone"
  },
  "allowed_destinations": ["701"],
  "radio_destinations": ["701"]
}
```

These are example addresses and paths. Reuse an existing verified SSH identity
and host key. Never publish either file, disable host-key verification, or
broaden SSH algorithms globally. The adapter uses a bounded SSH connection,
the driver's call-state checks and readback for settings, and no automatic
retry of commands with an uncertain outcome.

The native phone constrains which settings can change while idle or in a call.
Speaker volume, microphone mute and call DND require a connected call; ringer,
auto-answer and auto-mute changes require an idle phone. Auto-answer is a
persistent phone preference, not an instruction to answer only the next call.

The command-line sensor refreshes native state periodically and after a
successful action. Offline SSH state makes the player unavailable instead of
pretending playback succeeded. Confirm the adapter's read-only `status` result
before loading the package. A new Universal platform needs initial HA loading;
subsequent script, helper and template adjustments can use their reload services.

## Echo timers and troubleshooting

Kitchen and Living Dot timers are owned by the device, with the returned timer
ID saved in a helper. Pause, resume, add-time and cancel actions target that ID.
The same separation applies to alarms and spoken reminders. Editing a time or
label does not arm anything; the explicit action does.

If a panel action fails after renaming an ESPHome node, compare the action name
with the live service registry. Entity IDs can remain unchanged while ESPHome
action prefixes change. Correct the action prefix and reload scripts; do not
rename every entity to make an obsolete service name look consistent.

If an offline phone disappears, remove availability conditions from the
inventory view. If two players represent the same speaker, use the native
endpoint player once and exclude proxy duplicates from automatic media lists.
Keep device-specific remote pages accessible even when their old sidebar entries
are hidden.
