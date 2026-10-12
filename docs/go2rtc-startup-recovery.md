# Managed go2rtc startup recovery — 2026-09-26

The built-in `go2rtc` entry was in `setup_error`: initialization received HTTP 404
from `/api/schemes` after the server version check succeeded. The external Oracle
camera relays were healthy and were not the failing server.

Home Assistant 2026.9.1 starts its own go2rtc 1.9.14 (revision `b5948cf`). Its API
uses a generated authenticated Unix socket under `/tmp/go2rtc-*`; the ordinary
11984 TCP listener is disabled unless the debug UI is enabled. A closed TCP port
does not establish failure. Read the current generated configuration privately
when diagnosing the socket; it contains temporary credentials.

The running managed server later returned HTTP 200 for `/api`, `/api/schemes` and
`/api/streams`. The external Oracle relay also returned the expected API responses.
This establishes a transient initialization failure, consistent with API routes
becoming ready after the initial version check. A cold-start race was not separately
reproduced, so this is not a claim that an upstream startup defect was patched.

Reloading only the failed `go2rtc` config entry through
`homeassistant.reload_config_entry` restored its `loaded` state. No HA restart,
camera option changes, additional direct Wi-Fi camera connections, relay restarts
or version upgrades were needed.

If this specific failure recurs, verify the managed Unix-socket API first, then
reload the entry using its ID from `config_entries/get`. Check the entry state and
the camera WebRTC capability afterward. Do not introduce periodic blind reloads:
capture new startup evidence if the problem persists. Temporary socket paths and
credentials must never be committed. Existing go2rtc security restrictions remain
in effect.

## Restart reproduction and permanent guard

A Core restart on 2026-09-26 reproduced `setup_error`. Thirty isolated starts of
this installed binary (no cameras, temporary sockets/ports) produced 18 incomplete
scheme lists and two HTTP 404 responses. After adding a managed-server readiness
barrier, all 30 starts returned all 14 schemes and working streams/preload APIs.
The persistent startup guard and native recovery wiring live in
[home-assistant-k3s PR 9](https://github.com/4alvit/home-assistant-k3s/pull/9).
This supersedes the earlier reload-only recovery; see its deployment verification.
