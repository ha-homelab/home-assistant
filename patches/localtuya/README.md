# LocalTuya missing-position recovery kit

This directory preserves the exact difference between the unmodified LocalTuya
cover implementation and the hotfix installed on 2026-09-24. HACS can replace the
installed Python file during an update. Use this kit to recover the **behavior**
on the updated implementation; do not replace a newer integration with the old
complete `cover.py`.

- [Unified diff](2026.7.0-cover-missing-position.patch): the applied code changes,
  with original context and portable `a/` / `b/` paths.
- [Baseline metadata](baseline.json): upstream repository, tag, commit, source
  path, original SHA256 and installed output SHA256.
- [Generator](../../tools/patch_localtuya_cover.py): reproduces the installed
  hotfix from a compatible original file, writing a separate output file.
- [Behavior regressions](../../tests/test_localtuya_cover_patch.py): exercise the
  actual cover class with mocked HA and transport dependencies.
- [Patch round-trip regression](../../tests/test_localtuya_cover_patch_artifact.py):
  applies and reverses this diff, and verifies it matches the generator and hashes.
- [Incident and live verification](../../docs/localtuya-cover-hotfix.md): the
  original failure, device observations, deployment and remaining calibration work.

## Original behavior and failure

The office motor uses local Tuya protocol 3.4. DP1 is the command state, DP2 is
the requested target, and DP3 is the measured position. A valid local status
packet may contain only `{"1":"open"}`. In the original implementation, an
inverted cover immediately evaluates `100 - curr_pos`, even when DP3 was absent
and `curr_pos` is `None`. The callback raises `TypeError`, preventing normal
entity updates despite a responding motor.

Substituting DP2 or zero for absent DP3 would hide the exception but fabricate a
measurement. The invariant is: **unknown position is not closed, a requested
target is not an observation, and a partial packet must not erase an observation.**

## What each change does and why

1. **Constructor: initialize measured absolute position to `None`.** This applies
   only to `MODE_SET_POSITION` with a configured actual-position DP. It avoids
   claiming 0% closed before the first measurement. Other initialization paths,
   including time-based positioning, retain the original zero initialization.

2. **Constructor: initialize `_set_new_position` to `None`.** The original
   assignment `int | None` creates a Python union-type object, not an empty target
   value. A target becomes a number only when an actual target command is handled.

3. **`_current_state`: compare target and actual only when actual is known.**
   The existing within-five-percentage-points completion calculation remains
   unchanged for valid measurements. Missing measurements no longer enter
   subtraction or falsely imply that the requested target was reached.

4. **`is_closed`: return `None` for an unknown position.** Home Assistant can then
   represent uncertainty instead of receiving a misleading closed/open endpoint.

5. **`status_updated`: validate a numeric measurement before inversion.** Only
   values in `[0, 100]` are inverted and stored. Missing values, out-of-range
   numbers, NaN and infinity leave the last measurement untouched. If no actual
   measurement has arrived, it stays unknown. The pre-existing boolean/enum
   conversion and time-based estimation are preserved; this is not a redesign
   of those modes. The hotfix does not read the target DP as an actual position.

6. **`update_state`: accept an absolute target without a known starting position.**
   `async_set_cover_position` still sends the normal target, with the existing
   inversion, to the configured target DP. The bookkeeping stores the target but
   skips direction arithmetic if actual position is unknown. Here `STATE_STOPPED`
   is an internal tracking fallback: this branch sends **no additional Stop
   command**, does not claim measured motion, and does not move the displayed
   fabric to the requested target.

The leading version marker identifies this local patch. It is not a substitute
for comparing the full file or checking a checksum.

## Reproduce the known version

Run from this configuration repository with Python 3.10+ and Git. The commands
below create a temporary working directory; they do not contact a curtain or
modify Home Assistant.

```bash
curtain_work=$(mktemp -d)
mkdir -p "$curtain_work/custom_components/localtuya"
curl --fail --location --retry 2 --max-time 30 \
  https://raw.githubusercontent.com/xZetsubou/hass-localtuya/3d0c0ec737b59ebfb1eea65df42f5d902eafaecc/custom_components/localtuya/cover.py \
  --output "$curtain_work/custom_components/localtuya/cover.py"

LOCAL_TUYA_COVER_SOURCE="$curtain_work/custom_components/localtuya/cover.py" \
  python3 -m unittest discover -s tests -p 'test_localtuya_cover_patch*.py' -v

python3 tools/patch_localtuya_cover.py \
  "$curtain_work/custom_components/localtuya/cover.py" \
  "$curtain_work/cover.patched.py"
```

The artifact regression verifies the original hash before applying the patch,
then checks both the installed output hash and exact reversal to the original.
The generator alone checks expected source fragments, **not the entire upstream
version**. A successful generation or `git apply --check` on another version is
not evidence that it is compatible.

## Port the logic after a HACS update

1. Save the newly installed, unmodified `cover.py` and `manifest.json` outside
   `custom_components/localtuya`, plus the current HA configuration backup. Record
   the HACS version, corresponding upstream commit and file SHA256. Preserve that
   **new-version original** for rollback. A copy with our marker is not a clean
   upstream baseline; locate the matching unmodified release instead.

2. Compare three things: the pinned original above, this diff, and the new
   upstream `cover.py`. Inspect the constructor, position storage, state/closed
   properties, packet handling and absolute-command bookkeeping. If upstream
   already handles the missing-position case correctly, test it without adding
   the old patch or its marker.

3. If the bug remains, implement the six behavioral requirements above on a copy
   of the **new** file. Keep its new APIs, command transport, features and upstream
   fixes. Do not force old hunks, replace the entire new file with the old patched
   file, or weaken a numeric guard just to make the patch apply.

4. Test that candidate directly, without running the old generator on it:

   ```bash
   LOCAL_TUYA_COVER_SOURCE=/private/new-release/cover.py \
   LOCAL_TUYA_COVER_CANDIDATE=/private/new-release/cover.ported.py \
     python3 -m unittest discover -s tests -p test_localtuya_cover_patch.py -v
   python3 -m py_compile /private/new-release/cover.ported.py
   ```

   Replace the example paths with the original and reviewed candidate copies.
   Candidate mode runs the behavior cases and skips only the old generator's
   idempotence check. If upstream class APIs changed, adapt the test harness to
   them while retaining the behavioral assertions. These focused tests do not
   replace a full HA load and service check.

5. For the new supported release, add a newly named diff and baseline metadata;
   retain this historical pair. Update the generator, pinned-source CI download
   and checksum, and artifact regression together. Verify that the new diff
   reproduces the reviewed candidate and reverses exactly to its own original.
   Commit the new rationale, tests and provenance before treating the port as
   reproducible.

6. Back up the deployed file, install the reviewed candidate atomically, run HA
   configuration validation, and restart once when no update or active device
   sequence is running. Verify that command-only packets load without exceptions,
   unknown stays unknown, partial packets retain the last measurement, and a
   newly reported position updates normally. Coordinate any physical movement
   test with the household. Rollback restores the saved **new-version original**
   and restarts HA; do not roll back the rest of the integration to an older file
   set accidentally.

## Related logic that must remain consistent

The LocalTuya diff fixes packet handling; the surrounding behavior has separate
owners and must not be moved into the transport hotfix:

- [Office template](../../config/covers.yaml), `office_curtains_r`: a valid
  `raw_state` from an active, non-restored motor keeps commands available even
  without a percentage. Missing actual position renders `none`; actual values
  retain the existing `100 - actual` transformation. Open/Close remain reversed
  for this particular motor. See the [HA template regression](../../tests/test_office_cover_template.py).
- The private floorplan repository, commit
  [`dc709a7`](https://github.com/ha-homelab/home-floorplan-3d/commit/dc709a7ec7d8d6747d9ccc2250f4641d83f423e3),
  separates motor availability from position, retains measured positions across
  power loss, labels remembered values, and keeps the recorded 45-second warm-up
  when a guard becomes unavailable. Its `curtains.py`, `curtain-state.js` and
  `static/panel.js` contain that logic. No target is used as a fabric measurement.
- Device mappings remain in LocalTuya runtime configuration. Office uses command
  DP1, actual DP3, target DP2, inverted positioning, and no stop-switch DP3.
  Kitchen uses command DP101, actual DP102, target DP104 and inverted positioning.
  These are device-specific observations, not defaults to impose on other motors.
  HACS normally replaces integration code rather than these mappings; verify
  them separately if the integration migrates its configuration.

No full third-party source, local keys, cloud credentials or runtime storage is
included in this kit. Nothing here automatically patches future HACS releases.
