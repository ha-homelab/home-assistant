# DESLOC release notes in HACS 2.0.5

HACS 2.0.5 combines the bodies of releases between the installed and offered
versions. This makes the DESLOC update dialog long; an already open dialog may
also retain the previous notes after installation.

This local compatibility patch shows only the release matching the offered
DESLOC version, followed by **Full release history**, linking to
https://github.com/ha-homelab/ha-desloc/releases. It preserves HACS's restart
warning, release-channel filtering, installation behavior, and all other
repositories. If the exact release is unavailable, it shows the history link
instead of substituting notes from a different version.

- [Generator](../../tools/patch_hacs_release_notes.py): accepts only the reviewed
  upstream SHA-256 or its exact patched form. It writes a separate output file.
- [Diff](2.0.5-desloc-release-notes.patch) and [baseline hashes](baseline.json).
- [Behavior tests](../../tests/test_hacs_release_notes.py): run the actual patched
  method with synthetic releases, including stable/beta selection, an up-to-date
  installation, missing notes, and unrelated repositories.
- [Pinned upstream test fixture](../../tests/fixtures/hacs/update.py), from
  [HACS 2.0.5](https://github.com/hacs/integration/blob/c0dfd8b44297c3673c21973e2539375a53687a9c/custom_components/hacs/update.py),
  distributed under its [MIT license](../../tests/fixtures/hacs/LICENSE).

## Apply and recover

Run the generator against a copy of the installed `custom_components/hacs/update.py`:

```sh
python3 tools/patch_hacs_release_notes.py update.original.py update.patched.py
python3 -m unittest tests.test_hacs_release_notes -v
```

Keep the original outside `www`, compare the installed file with the original
hash immediately before replacing it, and install only the generated file. Check
the Home Assistant configuration, then restart Home Assistant to load the Python
change. Reloading only the integration does not reliably reload Python modules.
Close and reopen the DESLOC update dialog so it fetches fresh notes.

The patch does not operate any lock. Existing Home Assistant startup automations
still follow their configured behavior during a restart. Roll back by restoring
the original file and restarting Home Assistant.

HACS updates can replace this file. Do not reapply to a different version or
unreviewed source: first check whether the upstream behavior satisfies this need,
then port and review the patch if still necessary. This patch is maintained in
the Home Assistant configuration repository, not injected by the DESLOC integration.
