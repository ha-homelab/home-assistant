# ESPHome build isolation

The 2026-11-17 audit found 23 private outlet configurations that share
`esphome.name: tuya-plug` and use `name_add_mac_suffix: true`. Their running
devices have distinct suffixed identities, but the builder selects its default
directory from the unsuffixed configuration name. These configurations therefore
share one build directory. Compiling another outlet can replace the firmware
left there for a later upload.

Give each YAML file its own build directory. Keep the existing name and MAC
suffix setting: changing `build_path` separates local build artifacts without
renaming devices, changing Home Assistant identities or uploading firmware.

## Verified compatibility boundary

The strict read-only configuration audit checked 45 current configurations:

- 42 passed validation with ESPHome **2026.10.2**, including all 37 encrypted
  ESP8266 switch configurations.
- The [RF Airbridge receiver](rf-airbridge.md) requires **2026.8.2** because its
  local receiver patch deliberately rejects other versions. Use a separate,
  explicitly pinned builder for that node.
- Two configurations with external BMS components were not qualified within
  this read-only audit. Their result is unresolved; it does not establish an
  incompatible device or a successful build.

Configuration validation checks the supplied configuration. It does not prove a
firmware build, upload, recovery image or physical device operation.

## One directory per YAML file

For an anonymized configuration named `outlet-a.yaml`, add only `build_path` to
its existing `esphome` section:

```yaml
esphome:
  name: tuya-plug
  name_add_mac_suffix: true
  build_path: build/outlet-a
```

Use `build/outlet-b` for `outlet-b.yaml`, and verify that every selected YAML
resolves to a different absolute directory. With the inspected Dashboard's
data directory, the example resolves to
`/config/.esphome/build/outlet-a`.

ESPHome 2026.10.2 resolves a relative `build_path` beneath its data directory,
which normally is `.esphome` beside the configuration. Consequently, entering
`.esphome/build/outlet-a` as the setting would add a second `.esphome` segment.
Add-on deployments and `ESPHOME_DATA_DIR` can use another data directory; inspect
the resolved path in the actual builder. See the versioned
[path resolution](https://github.com/esphome/esphome/blob/2026.10.2/esphome/core/config.py#L468)
and [data-directory selection](https://github.com/esphome/esphome/blob/2026.10.2/esphome/core/__init__.py#L777).

The 23 path corrections were applied to both the Dashboard configuration volume
and the HA mirror on 2026-11-17. All 46 files passed old-content checks before
replacement and exact new-content readback afterward, with owner and mode
preserved. Before application, each candidate passed ESPHome 2026.10.2 validation;
the normalized configuration changed only in `esphome.build_path`. No outlet was
restarted or flashed for this correction.

## Maintenance and upload procedure

1. Coordinate with any active build or upload before changing its inputs. Retain
   the private configuration, includes, secrets and an identified recovery image.
   Record the intended physical device, hardware identity, board, existing
   encrypted API identity and expected entity/action inventory privately.
2. Change only `esphome.build_path` in the intended source copies. Preserve names,
   suffix settings, credentials, pins, relay behavior and radio parameters.
   Validate with the appropriate pinned ESPHome version and verify unique
   resolved build paths before compiling.
3. Compile the intended YAML without uploading. Copy its resulting binary to a
   separate private artifact path and record its SHA-256, size, source hashes,
   builder version and intended device. A filename or successful build alone
   does not bind a binary to a physical device.
4. Before an authorized upload, recheck the target address against the recorded
   hardware identity and the live API inventory. Stop on a mismatch. Verify that
   the selected YAML and preserved binary belong to the same reviewed build;
   a shared node-name prefix or a recently modified `firmware.bin` is insufficient.
5. Recheck the preserved binary's hash and pass its absolute path explicitly with
   `--file`. Use the same pinned builder that produced it. For example, after
   setting the three variables from the verified private manifest:

   ```sh
   : "${VERIFIED_DEVICE_ADDRESS:?Set the verified target address}"
   : "${VERIFIED_FIRMWARE_FILE:?Set the preserved binary absolute path}"
   : "${VERIFIED_FIRMWARE_SHA256:?Set the reviewed SHA-256}"
   actual_sha256=$(shasum -a 256 -- "$VERIFIED_FIRMWARE_FILE" | cut -d ' ' -f 1)
   test "$actual_sha256" = "$VERIFIED_FIRMWARE_SHA256" || exit 1
   esphome upload outlet-a.yaml \
     --device "$VERIFIED_DEVICE_ADDRESS" \
     --file "$VERIFIED_FIRMWARE_FILE"
   ```

6. After upload, verify reconnection, expected firmware metadata and preserved
   entity/action identities before reporting completion. Keep physical control
   checks separate from API availability. Preserve the recovery image until the
   intended device has passed its acceptance checks.

The path correction itself requires no firmware upload. Existing shared build
directories are not reliable recovery archives; identify their contents and
active users before any cleanup.
