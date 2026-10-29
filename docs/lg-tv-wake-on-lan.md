# Living-room LG: local ESPHome Wake-on-LAN

The normal HA power button and `media_player.turn_on` for
`media_player.living_room_tv_77` wake the wired LG through the existing RF
ESPHome node. The node broadcasts the magic packet on the home LAN. HA can run
outside that broadcast domain; no SSH connection or running `syn` VM is needed.
The other LG (`media_player.lg2`) is not targeted.

## Remote Power button and OTT startup

The optional `config/packages/lg_tv_ott_power.yaml` adds two scripts. Bind only
the living-room remote card's `keys.POWER` to `script.living_room_tv_power_ott`,
as shown in [the card example](dashboards/living-room-lg.yaml). An active TV is
turned off normally. From standby, the script calls the normal
`media_player.turn_on` path below and waits for the TV before selecting
**Media Station X** (LG app ID `de.benzac.msx`). The app keeps its existing OTT
startup configuration; HA does not replace its URL or send website credentials.
Other TV power buttons, voice requests and physical remote use are unchanged.

`script.living_room_tv_start_ott` is the separate idempotent start action: it
can also open Media Station X on an already-active TV without turning it off.
An already-active Media Station X session is left alone. Duplicate start
requests are ignored while startup runs. The Power button can still turn an
active TV off during startup: it cancels the pending app launch first.
Confirmation waits allow 120 seconds for power-on, 30 seconds for the app list,
and 30 seconds for app confirmation. Failures are reported rather than claiming
the app opened. These are state confirmation timeouts, not hard deadlines on
underlying service calls.

Do **not** set `mac` on this `custom:lg-remote-control` card. That option makes
its Power button call `wake_on_lan.send_magic_packet` directly, bypassing both
the configured `POWER` action and our local ESPHome/Harmony wake sequence. It
can therefore show “Action wake_on_lan.send_magic_packet not found” even while
RF ESPHome works. Remove the stale `mac` override instead of enabling a second
WOL path. Preserve the remaining card configuration and all other TV cards.

Deploy the package, validate HA configuration, and reload scripts. Then save
the targeted card through the Lovelace editor or supported configuration API;
no Core restart is required. Storage-mode dashboards remain private runtime
data and must not be copied into this public repository. Verify startup through
script/automation traces and the TV's `source` attribute. App selection alone
does not verify network access or playback inside the OTT website.

To revert this optional behavior, remove only the card's `keys.POWER` override,
then remove `lg_tv_ott_power.yaml` and reload scripts when no scripts are running.
Keep `mac` absent and retain the shared wake package: the ordinary Power button
will continue using the existing local wake and Harmony fallback.

## Shared wake automation

`config/packages/lg_tv_wake_on_lan.yaml` keeps the existing automation ID,
`living_room_tv_wake_on_lan`, and official
[`webostv.turn_on` trigger](https://www.home-assistant.io/triggers/webostv.turn_on/).
It uses this bounded sequence:

1. Leave an already-on TV untouched, including `playing`, `paused`, `idle` and
   `buffering` states.
2. Require a known `on` or `off` state from `switch.living_tv_guard`. Start the
   two-minute `timer.living_room_tv_wake_grace` to protect this explicit request
   from inactivity shutdown, including when the outlet was already on.
3. If the outlet is off, start `script.living_room_tv_restore_power`
   independently and allow **10 seconds** for the outlet to report `on`.
   An unavailable outlet or a request without actual `on` confirmation stops the
   sequence with an error; a successful service call alone proves nothing. After power
   returns, allow **30 seconds** for cold startup, ending early if the TV reports
   an on state. A TV that starts itself needs no WOL or Harmony command.
4. Start `script.living_room_tv_send_wake_packet` with the nonblocking
   `script.turn_on` action. The helper calls `esphome.rf_wake_living_tv`.
5. Allow up to **10 seconds** for the TV to report an on state. A successful
   service call only confirms the request, not that the TV actually woke.
   A missing ESPHome action, offline node or helper error does not abort this
   parent sequence; the bounded wait still leads to Harmony.
6. If waking is still unconfirmed and outlet power is still on, send the Harmony hub's discrete `PowerOn`
   command for `LG TV`, then allow **45 seconds** for confirmation.
7. Record an automation error if neither route produces confirmation or outlet
   power is lost during the sequence.

A powered TV in standby skips the outlet command and cold-start wait, retaining
the fast WOL path. The HA timer is not restored across Core restarts and stays
bounded even after a failed request. Duplicate requests do not extend it.
Lighting Sticky overrides do not block an explicit TV power-on request and are
never changed by it; they still protect automatic media-outlet control.

The confirmation waits do not impose a wall-clock deadline on every HA service
call. Harmony `remote.send_command` is synchronous: a slow call delays the start
of its 45-second confirmation wait. The independent outlet helper can finish
after the caller's power-confirmation deadline; timeout does not cancel an
already dispatched outlet request. The two-minute shutdown grace expires
independently of slow service calls. A hard deadline for the entire sequence is
not guaranteed.

The companion [media guard package](dining-media-guard.md) cuts TV power only
after this timer is idle **and** the outlet has continuously reported `on` for
two minutes. This also protects cold power restored by occupancy or the outlet's
button. Both protections are additional to the existing ten-minute quiet-room,
explicit TV `off`, and Living Sticky conditions. A missing timer fails closed
for TV power shutdown, so install and reload these two packages together.

Duplicate requests while this sequence runs are ignored. The fallback does not
start a Harmony activity or use `PowerToggle`, so a late WOL response cannot
turn the TV back off. Keep `remote.harmonyhub` and its `LG TV` device name aligned
with the Harmony setup.

## Configure the RF node

The installed RF board is an **ESP8266 NodeMCU v2 with CC1101**. Its Wi-Fi
interface can send WOL; CC1101 is not involved, and no additional hardware or
GPIO is required. The RF project provides the optional
`packages/wake-on-lan.yaml` package and its small WiFiUDP helper. Keep the current
RF configuration and add the package rather than replacing the existing node:

```yaml
packages:
  living_tv_wake: !include packages/wake-on-lan.yaml
```

Set `living_tv_mac_address` in the installation's private ESPHome secrets file.
It must be the TV's **Ethernet MAC**, not its Wi-Fi MAC. Keep the existing native
API configuration and RF receive/transmit settings. Compile the full firmware
and check RAM, flash and OTA headroom before upload.

The node exposes the native API action `wake_living_tv`, expected in HA as
`esphome.rf_wake_living_tv`. Verify that actual registered action after OTA;
do not deploy based on an assumed name. No extra button entity or MQTT-discovered
copy is required. There is no boot trigger, so restarting RF must not wake the TV.

The built-in ESPHome WOL button supports ESP8266, but enabling the `button`
component conflicts with the existing Dooya API's parameter named `button`.
The small UDP helper preserves that public RF action signature. It sends only to
the TV MAC configured at build time; this is not an arbitrary network-packet API.

The independent HA helper is intentional: HA does not suppress `ServiceNotFound`
with `continue_on_error`. Starting the helper with `script.turn_on` contains a
missing ESPHome action or disconnect inside that helper, while the parent still
reaches Harmony. A normal blocking call to the helper would lose this property.

## Network requirements

The RF helper sends a 102-byte UDP magic packet to
**`255.255.255.255:9`**. The destination is fixed; the package only accepts the
private TV MAC. The RF node and TV must therefore share a reachable LAN broadcast domain. Guest Wi-Fi isolation, VLAN
separation or blocked Wi-Fi-to-Ethernet broadcast can prevent waking even when
HA can still reach the node's API. Physical proximity to the TV does not replace
this network requirement.

WOL requires standby power and network wake support. Explicit HA requests now
restore the controlled outlet first if necessary; a direct ESPHome WOL call does
not manage that outlet. A local WOL test
on 2026-10-02 woke this TV in about three seconds, which informs the 10-second
primary confirmation window. That earlier test is not proof of a later RF
firmware deployment. See the
[official LG webOS guidance](https://www.home-assistant.io/integrations/webostv/#wakeonlan-does-not-work)
if a TV reset disables WOL; newer models may expose it under
**Support → IP control settings → Wake on LAN**.

## Deploy and verify

1. Build and upload the RF firmware; wait for its existing sensors and new WOL
   API action to register. Confirm the actual action name.
2. Apply this HA package together with `dining_media_guard_evening.yaml` and run
   HA's configuration check. The new timer and power helper must be present.
3. Reload timer configuration and scripts while none are running, then reload
   both affected automations. Confirm `timer.living_room_tv_wake_grace` is `idle`.
   When replacing the old SSH package, also reload
   `shell_command` to remove the retired `living_room_tv_wake` action. A core
   restart is unnecessary. If that reload action is unavailable on an older HA
   version, the unused shell action can remain loaded until a normal restart;
   this automation no longer calls it.
4. When the TV is already off and the room can be disturbed, call
   `esphome.rf_wake_living_tv` directly and confirm the TV state. This isolates ESPHome from the Harmony
   fallback. Do not turn off a TV that someone is watching for a test.
5. From standby, exercise `media_player.turn_on` and inspect the automation trace.
   Confirm WOL succeeded without a Harmony call, or that an unconfirmed wake
   invoked only the explicit `PowerOn` fallback. Test missing-action/offline/error
   conditions in the isolated runtime tests rather than by taking RF offline.

The RF node remains responsible for its existing motion reception and curtain
transmission. Verify those entities reconnect after OTA. The WOL addition must
not automatically move curtains or change RF transmission permissions.

## Troubleshooting and previous relay

A missing WOL action means the action name, RF firmware or native API connection
needs checking. An action that accepts a request but does not wake the TV calls
for checking broadcast delivery, Ethernet MAC and TV standby settings. The automation's final state check prevents either case from appearing
as a confirmed wake merely because a service accepted the request.

The previous implementation ran `tools/lg_tv_wol_relay.py` over a restricted SSH
key on `syn`. On 2026-10-23 its SSH connection timed out while Harmony `PowerOn`
worked. The `syn` VM was subsequently found shut down, although the Synology NAS
itself was reachable. A NAS response did not imply the VM relay was running.
The current package removes that VM dependency completely.

The legacy relay tool and its packet/command tests remain in the repository for
reference; they are not used by this automation. Its private MAC/broadcast JSON,
SSH private key, pinned known-hosts entry and restricted authorized-key line are
not needed by the ESPHome path. Retire those installation artifacts separately
once their lack of other callers is confirmed; do not delete unrelated SSH keys
or weaken host-key checking to repair a retired path.

`tests/test_lg_tv_wake.py` validates and runs the actual action sequence inside an
isolated Home Assistant instance with recorded services. It covers immediate
and delayed WOL confirmation, a missing ESPHome action, API errors, unconfirmed
packet delivery, failure of both routes, every already-on state, and duplicate
requests. It loads the real HA script integration for the independent helper,
so the tests exercise error isolation rather than mocking `script.turn_on`.
It also loads the real timer and companion media automation to exercise cold
and warm manual requests while inactivity checks run, plus shutdown after grace
expiry. Outlet failures, missing actions, stalled actions, startup power loss,
Sticky-on explicit requests and duplicate timer deadlines are covered. Only
the test copies shorten waits; timer expiry is also exercised through HA's
timer service. Unknown/unavailable TV states cannot pass the final confirmation check. The test
never sends network packets or operates a real TV. `tests/test_lg_tv_wol_relay.py` keeps
the legacy relay's packet construction and restricted-command checks.
