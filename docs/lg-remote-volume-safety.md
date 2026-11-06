# LG remote volume safety

The LG WebOS Remote Control card can keep sending volume commands after a
button is released. This is a frontend card defect, not a retry loop in the
native Home Assistant `webostv` integration. See
[upstream issue 180](https://github.com/madmicio/LG-WebOS-Remote-Control/issues/180).

## Cause and immediate recovery

The reviewed card bundle starts an interval every 100 ms when volume is held.
It cancels that interval only on `mouseup` or `touchend` on the same button.
Releasing outside the button can leave the interval running. Both buttons also
share one timer handle: starting the opposite direction can overwrite the
handle needed to stop the first interval.

Reload the affected HA browser page to stop its timers. Merely switching off
the TV does not stop the browser from sending commands. On HA 2026.11.0 the
native integration rejects them with `Device is off and cannot be controlled`.
Restarting HA or resetting the television is unnecessary for this failure.

## Local correction

`tools/patch_lg_remote_control.py` builds a separate, reviewed card asset with
single-step volume buttons. A click sends one command; holding or dragging a
button does not start an automatic repeat. The handlers are part of the card's
rendered template, so rebuilding the remote does not lose them. Existing
volume routing and button overrides are retained. The default route ignores
clicks while its player is off, unavailable or unknown. Explicit custom service
overrides retain their own target and availability policy.

The patcher checks the exact upstream SHA-256 and rejects unknown or damaged
input. The original HACS download stays untouched. The managed resource is
loaded instead of it, so an automatic HACS download cannot silently reintroduce
the unsafe timers. Do not load both assets: they register the same custom
element.

## Install and verify

1. Obtain the original `lg-remote-control.js` from the installed HACS component.
   The reviewed bundle has SHA-256
   `45fda8299d5553662b2bdd53616ec99daadc09431b5d19df1c199235c1e8825e`.
2. Generate and test the replacement:

   ```sh
   python3 tools/patch_lg_remote_control.py original.js lg-remote-control-safe.js
   node --check lg-remote-control-safe.js
   LG_REMOTE_CONTROL_SOURCE="$PWD/original.js" python3 -m unittest discover -s tests -p 'test_lg_remote_patch.py' -v
   ```

3. Install the result at `/config/www/ha-homelab/lg-remote-control-safe.js`.
   If serving a `.gz` companion, generate it from these exact bytes. Never
   leave a stale gzip file beside a newer JavaScript file.
4. Update the existing LG resource using `lovelace/resources/update` or the HA
   resource editor to `/local/ha-homelab/lg-remote-control-safe.js?v=single-step-1`.
   Retain its resource ID and module type. Do not add a second registration.
5. Reload every HA browser/companion view that previously loaded the old card.
   Already-running JavaScript is not changed by replacing a server file.
6. Check that idle volume calls have stopped. Test synthetic mouse, touch and
   keyboard events against a mocked service receiver before physical testing.
   A live TV or audible volume change is not needed to verify timer removal.

For rollback, restore the existing resource's original HACS URL and reload
clients. That restores the known defect too; use it only for a deliberate
comparison or after upstream has fixed the problem. When upgrading the card,
review its new source and repeat the regression tests before switching the
resource back. Do not bypass the patcher's checksum check for a new bundle.

## Verification scope

The incident was traced to repeated volume-up and volume-down calls from one
browser WebSocket session. Reloading that page stopped the stream. The
unmodified timer logic was reproduced offline. Regression tests cover
single-step controls without communicating with a television; physical audio
acceptance remains a separate, deliberate test.
