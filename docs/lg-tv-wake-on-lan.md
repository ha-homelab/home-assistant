# Living-room LG: Ethernet Wake-on-LAN

The LG OLED77C5 (`media_player.living_room_tv_77`) uses an installation-specific
IP and Ethernet MAC kept in the local network and relay configuration. A local magic-packet test on
2026-10-02 woke it from standby: HA changed from `off` to `on` in about three
seconds. The other LG (`media_player.lg2`) is not part of this configuration.

HA runs in OCI, outside the Ethernet broadcast domain. The package
`config/packages/lg_tv_wake_on_lan.yaml` handles the official
[`webostv.turn_on` trigger](https://www.home-assistant.io/triggers/webostv.turn_on/)
and sends one SSH command to the existing home worker `syn` through its cluster DNS name. CoreDNS maintains that name
from the Kubernetes node address (resolved at runtime).
There, `tools/lg_tv_wol_relay.py` emits three 102-byte UDP packets to the LAN
broadcast configured for the installation, on UDP port 9. This requires no daemon,
container, router broadcast forwarding or cloud audio/video transport.

The normal HA power button and `media_player.turn_on` use the relay first. If
SSH fails, the automation immediately tries the existing Harmony hub's discrete
`PowerOn` command for `LG TV`. If SSH succeeds but the TV does not confirm waking
within 45 seconds, it also tries Harmony. The fallback has its own 45-second
confirmation window. Sending a packet or accepting an IR command is not treated
as proof that the television is on; a missing final confirmation is an error.
Duplicate requests during either confirmation window are ignored. An already-on
TV is left untouched.

The fallback uses `remote.harmonyhub` and its configured `LG TV` device. It does
not start an activity or send `PowerToggle`, so a late Wake-on-LAN response cannot
turn the TV back off. Keep these identifiers aligned with the Harmony setup.
The second LG (`media_player.lg2`) and other Harmony devices are not targeted.

## Provision or restore the relay

1. On a trusted administrator machine, generate a dedicated Ed25519 key:
   `ssh-keygen -q -t ed25519 -N '' -C ha-living-room-tv-wol -f living_room_tv_wol`.
   Transfer the private key into HA at `/config/.ssh/living_room_tv_wol`
   with mode `0600`; keep `/config/.ssh` at `0700`. Never commit the key.
2. Copy `tools/lg_tv_wol_relay.py` to the home worker at
   `/home/OPERATOR/.local/lib/home-assistant/lg_tv_wol_relay.py` (mode `0700`).
   It uses only Python's standard library and needs no root permissions.
   Before replacing an existing relay, provision `lg_tv_wol_relay.json` beside
   the script (mode `0600`) with exactly `mac` and `broadcast` string fields.
   Set `mac` to the TV's colon-separated Ethernet MAC and `broadcast` to the
   IPv4 broadcast for its LAN. Both values are private installation data;
   do not commit this JSON file. Missing or invalid configuration returns
   exit code 3 without opening a network socket. Back up this file privately.
3. Append the dedicated public key to the operator's `~/.ssh/authorized_keys`
   (mode `0600`) with this exact prefix, on the same line as the public key:

   ```text
   restrict,command="/usr/bin/python3 /home/OPERATOR/.local/lib/home-assistant/lg_tv_wol_relay.py"
   ```

   `restrict` disables forwarding, PTY and user rc execution. The forced
   command additionally rejects every original command except
   `wake-living-room-tv`. Do not substitute an administrator's unrestricted
   SSH key. Preserve existing authorized keys when installing or removing it.
4. Obtain `/etc/ssh/ssh_host_ed25519_key.pub` through an already trusted SSH
   connection to `syn`. Store a known-hosts line beginning with
   `living-room-tv-wol` and that public host key in
   `/config/.ssh/living_room_tv_wol_known_hosts` (mode `0600`). Host-key
   checking is mandatory; verify a replacement worker's new key before use.
   The SSH `HostKeyAlias=living-room-tv-wol` pins that identity independently
   of the worker address. Keep the dedicated private key unchanged.
5. Deploy the package, run HA's configuration check, then reload
   `shell_command` followed by `automation`. HA does not need a restart.
   From standby, call `media_player.turn_on` for `media_player.living_room_tv_77`
   and confirm both its state and the automation trace. A negative SSH test
   with an original command such as `id` must fail without waking the TV.

HA's private configuration backup must retain these two `.ssh` files. The
worker-side script and restricted authorized-key line must also be restored
after losing `syn`; restoring only the HA configuration is insufficient.
The relay lets the kernel choose the source interface for the fixed LAN
broadcast; it does not bind to a worker IP that may change. An address change
within the same LAN is handled by the node DNS record and this route selection.
After a subnet change, update the broadcast address in the local JSON file. Never
run another LAN broadcast service in OCI as a substitute.

The TV already accepted Wake-on-LAN during commissioning. If a firmware reset
disables it, consult the [official LG webOS integration documentation](https://www.home-assistant.io/integrations/webostv/#wakeonlan-does-not-work):
on newer TVs the setting can be under **Support → IP control settings → Wake
on LAN**. Keep Ethernet connected and the television in standby.

## Diagnose without interrupting playback

Check the automation trace before retrying a wake request. An SSH connection
timeout points to reachability or name resolution; it is not evidence that the
TV rejected a magic packet. Resolve `syn` from the HA container and compare it
with the Kubernetes node address. A restricted `id` request must still return
exit code 2 and `Only wake-living-room-tv is allowed`. That negative test checks
SSH connectivity, authentication and the command restriction without sending
a packet.

Also inspect the selected route from the HA host to that resolved address. A
correct DNS record does not prove that the preferred route works. In the
2026-10-23 incident the wake trigger ran normally, but SSH to `syn` timed out;
the old sequence aborted before sending any packet. A direct Harmony `PowerOn`
worked. The fallback now preserves the normal `media_player.turn_on` interface
during that transport failure; it does not repair the underlying network route.
In a successful fallback trace, the relay can still show return code 255 while
the later Harmony command and observed TV-on state confirm recovery.

A successful relay response confirms only that three packets were sent. The
automation separately waits for the TV state. Test a full wake from standby
when the TV is already off; do not power-cycle it while someone is watching.
An earlier October 2026 outage was caused by a stale SSH IP and a second stale IP in
`socket.bind`, so fixing only the connection endpoint would not have repaired
the relay.

`tests/test_lg_tv_wake.py` runs the actual action sequence in an isolated Home
Assistant instance with recorded service calls. It covers confirmed WOL, SSH
failure, shell exceptions, packet success without wake confirmation, failure of
both methods and already-on behavior. `tests/test_lg_tv_wol_relay.py` separately
checks packet construction and the restricted SSH command. Neither test sends
network packets or operates a real television.
