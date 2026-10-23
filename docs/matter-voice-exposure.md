# Household voice control through the existing Matter bridge

The existing **RiDDiX Home Assistant Matter Hub (HAMH)** exports selected Home
Assistant entities to its already paired controllers. This is separate from
Home Assistant's Matter integration and Matter Server, which import devices
into HA. No new bridge or controller fabric is needed to publish another light.

## Porch names and controls

The canonical controls are:

- `light.porch_one` → **Porch Light 1**
- `light.porch_two` → **Porch Light 2**
- `light.porch_light` → **Porch Light**, the two-light group

The group is a persistent HA UI helper. Its two members are `light.porch_one`
and `light.porch_two`, with `hide_members: false` and `all: false`. It was created
once through the group configuration flow. Preserve the existing helper and its
entity ID; do not recreate it during every YAML deployment. On an installation
where it is missing, create a Light Group helper with these members and confirm
its entity ID before applying the exposure manifest. The publisher deliberately
fails if a manifest entity is absent from the bridge's filter preview.

The individual HA names were aligned with the Matter names, the existing Porch
area was assigned, and previous HA voice aliases were retained. Those aliases
apply to HA Assist only. Matter has one name per endpoint; it does not carry
multiple voice aliases into Alexa or Google Home. Explicit HAMH `customName`
mappings keep names stable even when HA changes its generated `friendly_name`.
See the project's [name and alias explanation](https://riddix.github.io/home-assistant-matter-hub/faq).

Expected commands after each controller has accepted the endpoints include
“turn on Porch Light”, “turn off Porch Light 1”, and “turn on Porch Light 2”.
The first controls the group; numbered commands control individual lights.

## Recorded deployment result — 2026-10-22

The reviewed [manifest](matter-household-exposure.json) added **46** household
controls to the **22** previously exported endpoints, producing **68** endpoints.
Live readback verified all 46 custom names, all 22 prior endpoint identities,
and all three existing controller fabrics. No factory reset, identity suffix
change, or new fabric was used.

At the initial readback, **36 of the 46 additions were reachable**. Ten were
unavailable: eight curtain endpoints whose supplies were off, Balcony Light,
and Living Wall Dimmer. Publication is not evidence that an offline physical
device can respond.

Alexa initially imported only part of the new catalog. A command for Porch
Light 1 incorrectly selected Backdoor Porch Light; that light was restored to
its initial off state. Logs showed a successful invoke followed by an initial
subscription-report timeout. After discovery and one bridge-scoped restart
with unchanged storage, Google completed its full subscription in about 11
seconds and Alexa in about 64 seconds. All 68 endpoint identities, three
fabrics and bridge configuration remained intact.

After the catalog updated, Alexa web commands to turn each numbered Porch
light on and off succeeded with a positive Alexa response. HA state readback
confirmed that only the requested bulb changed; Backdoor Porch Light stayed
off. This verifies Alexa text-command intent and the Matter control path, not
microphone speech recognition. Google Home app/voice acceptance remains a
separate check; a completed subscription alone is not that test.

The newly discovered group still produced an Alexa "unreachable" response
despite successful Matter invokes and physical state changes. One failed
off request was followed by an additional Alexa-originated on invoke. No
matching bridge timeout or dropped-state warning accompanied those group
commands. Do not assume that a spoken failure means the lights did not change.

Two controller-side routines were therefore saved and read back as a voice
fallback, without altering the existing routines:

- **Porch lights on via Matter**: phrase `turn on porch light`; turn on
  **Porch Light 1**, then **Porch Light 2**.
- **Porch lights off via Matter**: phrase `turn off porch light`; turn off
  **Porch Light 1**, then **Porch Light 2**.

They deliberately exclude the bridged group and Backdoor Porch Light. Alexa's
web interface confirmed the saved triggers/actions but does not expose their
enabled status or support running routines. An Echo or the Alexa mobile app
must verify enablement, execution and the spoken phrases; these checks remain
pending. The group remains available in HA and Matter for other controllers.
The user reported seeing the Porch entries in Google Home, but an observed
Google-originated control command is still required to complete that test.

## Apply or audit the manifest

`tools/matter_exposure.py` uses the Python standard library and the inspected
HAMH **2.0.56** API contract. It operates only on an existing running, commissioned
bridge. Obtain the URL and bridge ID from the private deployment inventory.
Never put them, HA tokens, controller keys, QR codes or pairing codes in Git.

```bash
export MATTER_HUB_URL='http://your-existing-hub:8482'
export MATTER_HUB_BRIDGE_ID='your-existing-bridge-id'
python3 tools/matter_exposure.py
```

The default is a **dry-run**: GET the existing configuration, mapping inventory
and endpoint graph, then POST to the read-only filter preview. It prints counts,
entity names to update and no raw bridge response. `--url` and `--bridge` are
also supported. An optional reverse-proxy bearer token can be supplied through
`MATTER_HUB_TOKEN`; there is no token command-line argument.

Review the plan, then explicitly apply it:

```bash
python3 tools/matter_exposure.py --apply
```

The publisher:

1. Accepts only exact entity IDs in the reviewed control domains. It rejects
   wildcards, duplicate names and names exceeding 32 UTF-8 bytes.
2. Appends missing exact `pattern` includes; preserves all existing includes,
   excludes, feature flags, port and identity settings.
3. Merges `customName` into each current mapping. HAMH's mapping PUT **replaces**
   the mapping, so sending only the new name would lose explicit types or other
   fields. The tool reads those fields first and verifies the saved merge.
4. Refreshes the HA registry and the bridge using their supported API actions.
5. Compares all previous endpoint identities and controller fabrics, checks the
   original HA entity bindings, exact configuration and final device-count
   limit, and verifies names and reachability of the requested endpoints for
   up to 60 seconds.

An ordinary repeat is idempotent: no duplicate filters or unnecessary mapping
PUTs. An unavailable endpoint produces a nonzero exit and an explicit
`unreachable` list even if configuration publication succeeded. A dropped HTTP
response may also follow a successful write. The tool never retries a failed
write or blindly rolls changes back: inspect readback, run a fresh dry-run, and
review before another `--apply`. It does not save snapshots or raw API payloads.

The default preview ceiling is **80 devices**, below the project's approximate
Alexa pairing limit of 80–100. `--max-devices` can set a reviewed ceiling up to
100; it does not make unsupported device types work. The manifest is additive,
not a complete replacement for private bridge configuration or identity storage.

## Exposure scope

The manifest contains household lights, deliberately assigned power relays,
curtains and the thermostat. Infrastructure power, unmapped spare outputs,
duplicate wrappers and maintenance buttons are outside this change. Existing
previously published controls remain intact.

Do not replace the manifest with `*` or broad `button.*`/`automation.*` filters.
HAMH represents buttons, scripts, scenes and automations as momentary outlets;
a voice “turn on” executes their action. Controller support also varies for
sensors, appliances and media players. Full vacuum voice support can require
one-device server-mode bridges, so this manifest does not change the robot
vacuum topology. See [supported device mappings](https://riddix.github.io/home-assistant-matter-hub/supported-device-types).

## Alexa and Google Home acceptance

First inspect the existing bridge and newly added endpoints in each controller
app. Matter bridges update their endpoint lists without needing their fabrics
to be reset. Assign rooms or groups in each app where necessary; HAMH's HA area
labels do not automatically populate the controllers' room assignments.

If an ecosystem genuinely is not linked, open an additional-controller
commissioning window and use its current temporary code. In Alexa use
**Devices → + → Add Device → Matter**. In Google Home use **Add → Matter-enabled
device**. Keep the existing fabrics; do not reuse an expired code or reset the
bridge to obtain another one. An online Matter-capable hub is required in each
ecosystem. The publisher does not log into cloud accounts or perform pairing.

- [Amazon's Matter connection guide](https://developer.amazon.com/docs/alexaplus/smarthome/matter-support)
- [Google's setup and multi-admin guide](https://support.google.com/googlehome/answer/13127223?hl=en)
- [HAMH's multiple-controller guide](https://riddix.github.io/home-assistant-matter-hub/guides/connect-multiple-fabrics)

Verify a numbered Porch light in each app, observe its HA state, then issue the
spoken command. Separately test the Porch Light group. A working group should
control both members; an individual command should affect only its member.
Bridge endpoint reachability, app control and spoken-name recognition are three
different checks. Record them separately rather than declaring all controllers
working from a successful API request.

## Troubleshooting

- **Entity absent from preview:** confirm the canonical HA entity exists and is
  not excluded by an existing filter. Refresh the HA registry and recheck. Do not
  remove unrelated exclusions merely to make the preview larger.
- **New name absent in HAMH:** inspect the per-entity mapping and refresh support
  in the installed version. A global name-preference flag is unnecessary when
  explicit `customName` values are present.
- **HAMH name correct but Alexa still misunderstands:** inspect duplicate or
  stale names in Alexa and its room/group assignments. Rename only the affected
  controller entry if needed. Changing the bridge's Unique ID Suffix replaces
  every identity and is not a routine name repair.
- **Alexa controls a light but says it is offline:** correlate the command with
  the bridge log and the actual HA state. A successful invoke followed by a
  subscription timeout is a different problem from a failed device command.
  Partial discovery and rejected subscriptions are tracked upstream in
  [issue #500](https://github.com/RiDDiX/home-assistant-matter-hub/issues/500) and
  [issue #517](https://github.com/RiDDiX/home-assistant-matter-hub/issues/517).
  Let an active rediscovery complete; do not repeatedly reset identities or
  re-pair while the controller is still importing endpoints.
- **All devices offline in one controller:** inspect HAMH controller health and
  subscriptions, local IPv6 reachability and mDNS binding. An HTTP web interface
  responding does not prove that the Matter transport works. Keep the Alexa
  bridge on UDP 5540. See [connectivity diagnostics](https://riddix.github.io/home-assistant-matter-hub/guides/connectivity-issues).
- **Only one endpoint offline:** inspect its underlying HA integration and power
  first. Publishing an unavailable HA entity cannot make its device reachable.

## Offline regression checks

```bash
python3 -m unittest discover -s tests -p test_matter_exposure.py -v
```

The mock bridge exercises additive filters, mapping replacement semantics,
feature/identity preservation, idempotence, drift detection, endpoint/fabric
changes, unavailable devices, limits, unsafe manifests and secret-free errors.
These tests do not connect to hardware or prove Alexa/Google voice control.
