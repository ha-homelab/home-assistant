# Home Feed Card compatibility

The installed and latest upstream `gadgetchnnel/lovelace-home-feed-card` release
is 0.6.5. Its `hass` setter reads `Object.keys(hass.resources)[0]`, but modern HA
no longer supplies `resources`. That throws before the feed can render on HA
2026.9.1. See [upstream issue 126](https://github.com/gadgetchnnel/lovelace-home-feed-card/issues/126).

`tools/patch_home_feed_card.py` changes only language selection: prefer
`hass.locale.language`, then `hass.language`, then the guarded legacy resources
map, finally English. It accepts only the reviewed upstream SHA256 and verifies
already patched input by reversing the single replacement. Unknown versions and
damaged patched assets fail closed. No downloaded card bundle is kept in Git.

The feed configuration, calendar sources, entity list, history, notification
filters, title and click behavior stay unchanged. The fork mentioned in the
upstream issue also changes calendar configuration; it was not needed for this
bounded compatibility fix.

## Applying or rolling back

1. Copy `/config/www/community/lovelace-home-feed-card/lovelace-home-feed-card.js`
   and its `.js.gz` companion to a private backup and confirm the JS SHA256 is
   `7f6003b1156457b88a511b01b63977ef47fceeb9955054745597a817b222eedd`.
2. Run `python3 tools/patch_home_feed_card.py original.js patched.js`; run
   `node --check patched.js` and `python3 -m unittest discover -s tests -p test_home_feed_patch.py`.
3. Compare the live file with the backup again, then atomically install the
   patched file. Regenerate its gzip companion from the same patched bytes;
   verify decompression exactly matches the JS. Otherwise browsers accepting
   gzip can still receive the broken original. Do not change any other HACS asset.
4. Use `lovelace/resources/update` to append `&ha_homelab=language-v1` to this
   resource's existing URL, retaining its ID, type and `hacstag`. Reload the
   browser and verify Feed content and no new home-feed-card console error.
   A Home Assistant restart is not required.
5. To roll back, restore both original asset files and resource URL from the backup,
   then reload the browser.

HACS updates or a re-download can overwrite the hotfix. Keep updates enabled.
After either operation, check the new upstream code/version and Feed rendering.
If the upstream fix exists, remove this hotfix and its cache-bust suffix. If the
same 0.6.5 asset is installed, the guarded tool can reproduce this fix; never
silently patch a different release.
