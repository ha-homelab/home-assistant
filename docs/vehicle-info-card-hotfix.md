# Vehicle Info Card hotfixes

Vehicle Info Card 1.12.3 calls its extra-map-card updater at module load, including
on dashboards that never display a vehicle card. The updater requests
`https://registry.npmjs.org/extra-map-card` and can repeatedly trigger endpoint
protection notifications. It then loads a newer module from jsDelivr and removes
extra-map-card resources from Lovelace. See the
[upstream loader](https://github.com/ngocjohn/vehicle-info-card/blob/main/src/utils/load-extra-map.ts).

The installed bundle already contains and registers extra-map-card before that
call. `tools/patch_vehicle_info_card.py` guards the call with the existing custom
element registration. The bundled map remains available, including the vehicle
card's map popup. The loader is still available if the element is absent. This
does not change Mac network or Defender settings or provide a proxy.

The patch accepts only the reviewed upstream SHA256
`ea1a5f23dfd4f28a2b2eb48d99adc2f40b65d3d2e36a8364442d6ddfdca9dcfe`.
It also verifies already patched input by reversing the replacement and checking
the original hash. Downloaded card bundles are not stored in Git.

## Tire pressure availability

The same reviewed 1.12.3 bundle passes nonnumeric states such as `unavailable`
to `parseFloat`, then to `Math.min`/`Math.max`, producing `NaN - NaN`. Its initial
entity lookup also drops unavailable sensors, preventing pressure from recovering
in an already loaded card. The v3 patch retains the four enabled, visible tire
sensor mappings and their warning sensor for the selected vehicle even while their states are missing or
unavailable. Other sections retain their original discovery behavior.

The summary now requires all four readings to be finite, nonnegative numbers
with the same nonempty unit. Otherwise it shows Home Assistant's localized
`Unavailable` text. It does not substitute zero, display a partial range or
present historical pressure as a fresh reading. Zero remains a valid numeric
reading; normal psi/bar formatting is preserved. The individual wheel panel
continues to use HA's state formatter. When telemetry recovers, the existing
card uses the retained entity mappings without a reload. An unavailable warning
sensor is also shown as unavailable, not as normal pressure.

Opening the tire panel used to eagerly render every other built-in panel,
including a door panel that crashes without lock telemetry. Panel dispatch is
now lazy: it only renders the selected panel. This also avoids unnecessary work
on every update and leaves custom cards and service controls unchanged.

The patcher accepts the original bundle, the previous bundled-map v1 hotfix,
and intact v2/v3 output. All paths reconstruct and verify the original SHA256
before applying the five reviewed replacements. Unknown or modified assets
are rejected. The existing extra-map-card loader guard is preserved.

## Apply and roll back

1. Back up `/config/www/community/vehicle-info-card/vehicle-info-card.js`, its
   `.js.gz` companion and the matching Lovelace resource outside `/config/www`.
   Capture the storage dashboard before changing its history graph, too.
2. Run `python3 tools/patch_vehicle_info_card.py original.js patched.js` and
   `node --check patched.js`. Import both bundles in an isolated browser with
   network calls stubbed: both must register `vehicle-info-card` and
   `extra-map-card`; the patched bundle must make no npm request.
3. Compare the live asset against the hash captured before patching again. Atomically replace
   it with the patched file and regenerate the gzip companion from those same
   bytes. Verify the uncompressed and gzip responses contain the patched asset.
4. Use the HA WebSocket `lovelace/resources/update` command to append
   `&ha_homelab=map-tires-v3` to this resource's URL (replacing any previous
   `ha_homelab` value), preserving its ID, type and
   `hacstag`. Reload the browser. An HA restart is not needed.
5. To roll back, restore both assets and the original resource URL from the
   backup, then reload the browser.

HACS updates or re-downloads can overwrite this hotfix. Keep updates enabled;
review the upstream loader after updating this card. Remove the hotfix suffix
when upstream fixes these issues. Do not patch unknown versions with the old
replacements. Reapply this reviewed patch after a re-download of version 1.12.3.

## Regression tests

CI downloads the upstream release asset and checks its SHA256. The Node tests
execute its real discovery and summary functions in an offline VM, reproducing
the old failure and checking unavailable-to-valid recovery, missing sensors,
partial data, malformed numbers, negative/non-finite values, zero, mixed/missing
units, psi/bar output and localization. Hidden/disabled sensors and other
vehicles remain excluded. Python tests verify original/v1/v2/v3 compatibility,
idempotence and rejection of altered assets. No vehicle commands or cloud
requests are made by these tests.

The same tests execute the full tire panel renderer and verify that unknown
warning status is not displayed as normal. Panel dispatch tests cover all five
built-in panels and custom cards, checking that only the selected panel runs.

```sh
VEHICLE_INFO_CARD_SOURCE=/path/to/vehicle-info-card.js \
  python -m unittest discover -s tests -p test_vehicle_info_card_patch.py -v
```

## Verification on 2026-09-25

The complete original and patched bundles were imported in isolated Chrome with
`fetch` stubbed. The original requested the npm registry once; the patched bundle
made zero fetch calls. Both registered the vehicle card and extra-map-card,
exposed the map's `setConfig` method, and reported no JavaScript errors. This
checks module startup; it does not exercise live map tiles or vehicle telemetry.

The deployed ordinary and gzip HTTP responses both returned 200 and decoded to
SHA256 `d627eb02237469c6837858729f6950aae0b292a4a382ad72b6a3f33308c54fa2`.
The prior assets and resource URL are saved in
`/config/.backups/vehicle-npm-warning/20260925T173343Z`.
JavaScript syntax, patch idempotence, rejection of modified inputs, and the
repository's YAML/configuration validator also passed.

## Verification on 2026-10-01

The Mercedes via Cerbo MQTT entry was loaded, but all 53 active entities were
unavailable. Cerbo's cloud client had received repeated HTTP 429 responses and
was in its persisted retry cooldown; the recorded next attempt was
2026-10-02 00:41 UTC. No additional cloud requests, availability overrides or
service restarts were used to bypass that cooldown. Fixing the frontend does
not restore telemetry while Mercedes rejects connections.

The v3 bundle was deployed at 22:41 UTC without restarting HA. Both ordinary
and gzip HTTP responses matched SHA256
`97faa3359c8aeaf21162ed3dab94fd03db0e280a92bafd9bcb1584f8898e02ee`.
The original assets, resource and storage dashboard are backed up privately in
`/config/.backups/vehicle-pressure-20261001T223843Z`.

Live Chrome verification showed `Unavailable` in the summary and for all four
wheels. The tire detail panel opened successfully and reported no JavaScript
errors from the v3 bundle. Recovery with numerical values was verified in the
offline JavaScript regression, not against a fresh vehicle update during the
cloud cooldown.

The adjacent **Tire Pressures** mini-graph-card had its own `NaN psi` current
value. Its storage dashboard configuration now includes:

```yaml
show:
  state: false
```

This hides only that redundant current-value label. The four entities, 48-hour
history, sampling density and graph remain unchanged; current readings are
provided by the vehicle card. To reproduce this part after a clean install,
apply the same setting to that existing history card. To roll it back, remove
only `show.state` from that card through the Lovelace API or editor, preserving
any later dashboard edits; do not overwrite a newer complete dashboard with
the backup.
