# LocalTuya cover packets without a position

The [recovery kit](../patches/localtuya/README.md) contains the exact original-to-
installed diff, baseline hashes, a change-by-change explanation, and instructions
for testing and porting the behavior after a HACS update.

The office motor can return only `{"1":"open"}` over its working local Tuya
3.4 connection. LocalTuya 2026.07.0 attempts to invert the absent actual-position
DP3 with `100 - None`. Its state callback raises `TypeError`, leaving the cover
unavailable even though the device is connected. The configured local key matches
the current Tuya device key. DP2 is the requested target, not an observation.

`tools/patch_localtuya_cover.py` creates a patched copy of the installed HACS
`cover.py`. It preserves the last observed position on partial/invalid packets,
starts absolute-position covers with an unknown position, and handles absolute
commands without inventing a starting position or motion direction. Timed covers
keep their existing initialization. No device IDs, keys or HACS source are stored
in this repository.

## Reproduce and validate

The supported upstream source is tag `2026.7.0`, commit
`3d0c0ec737b59ebfb1eea65df42f5d902eafaecc`. Its `cover.py` SHA256 is
`e5a0f563de34a0252cd2f732f264deab9f6e9c9dc5d32fbf9ee4e34545424af9`.
CI downloads that exact source and verifies its checksum before testing the
patched class with mocked HA/device dependencies. The tests do not contact HA
or issue physical commands.

```bash
python tools/patch_localtuya_cover.py /private/cover.py /private/cover.patched.py
LOCAL_TUYA_COVER_SOURCE=/private/cover.py \
  python -m unittest discover -s tests -p test_localtuya_cover_patch.py -v
```

Before deployment, retain the installed file as a backup and verify it still
matches the tested input. Compile the output, replace only
`/config/custom_components/localtuya/cover.py` atomically, and restart HA once
when no automation/script, update or backup is running. Rollback restores the
backed-up file followed by the same restart. Do not edit `.storage` or local keys.

This is a local HACS hotfix. A LocalTuya update can replace it. Inspect the new
upstream version before reapplying; the tool refuses unexpected source patterns.
The patch should be removed once the equivalent fix is present upstream.

## Live verification, 2026-09-23 local time

- Installed output SHA256:
  `0849c2c0d2e78dd1a1778c44d9396d54040721a428fea899c3a1e6b0f15eea46`.
- Backup: `/config/backups/localtuya_cover/20260924T040730Z/cover.py`.
- After restart, the office entity loads with position `unknown` rather than
  failing as unavailable. A HA `cover.stop_cover` call was acknowledged by the
  motor's local `raw_state` changing from `open` to `stop`.
- Status queries, explicit DP queries and an update request still returned no
  actual position. No percentage is claimed as measured and no open/close or
  percentage movement was requested. The floorplan's office wrapper remains
  unavailable until a real percentage is received; physical direction and
  calibration require follow-up with the user.
- The user subsequently confirmed the office curtain is physically **fully
  closed** and explicitly prohibited opening it at night. No further motion
  commands are authorized for this test. The reported cloud DP3 value of zero
  agrees with that physical observation, but the local connection still supplies
  no DP3. Do not substitute the cloud target DP2 (53) for its actual position.
- Kitchen guard 1 retains its DHCP address and matches its cloud local key,
  but TCP 6668 remains in SYN_SENT even from the home router and Tuya reports
  it offline. It needs device/network recovery; no mapping change can establish
  a missing connection. Other curtain motors retain their existing mappings.

## Daytime follow-up, 2026-09-24

The user enabled the guards and explicitly authorized office movement after the
room became free. Kitchen connectivity recovered: a 50% target produced measured
97 → 86 → 69 → 57 → 49%, and the user confirmed partial closure.

The first office 25% attempt ended at a measured 0%; the user confirmed fully
closed. An ordinary Open command then produced DP3=100. A subsequent 50% command
was acknowledged as DP2=50 and completed with DP3=51 over the local connection.
The user confirmed that final partial opening physically: the office curtain is
approximately halfway open. After the HA restart, the map retained and displayed
the kitchen's 49% and office's 51%. These observations do not establish that every
motor's percentage direction is calibrated.

The office template now stays available when its active LocalTuya source reports a
valid command state without a percentage. Its position remains `none` until an
actual measurement arrives, rather than converting a missing value into an endpoint.
Restored and disconnected sources remain unavailable. A HA-runtime regression
renders the real templates for unknown, observed, restored and disconnected states.
Deploy `config/covers.yaml` to the existing template include and reload template
entities, or restart once alongside the floorplan update. Back up the old include
first; restoring it and reloading templates rolls back this template change.

See the [subsequent physical commissioning log](curtain-live-verification-2026-09-24.md)
for all-motor checks, corrected rear-bedroom inversion settings, and the real
power-cycle result. A completed reconnect countdown did not by itself restore
reliable office percentage control.
