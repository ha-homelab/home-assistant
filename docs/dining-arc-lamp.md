# Dining Arc lamp

The existing ESPHome controller formerly named Studio wall lamp uses
**Dining Arc lamp**, with canonical control `switch.dining_arc_lamp`.
It exposes one relay, not dimming, RGB, or color-temperature control. The
separate SmartThings `light.purple_lamp` is not established as the same physical
device and must not be removed on the basis of its similar name.

## Keep the existing device identity

The ESPHome config entry uses the controller's MAC as its unique identity and
already connects to its reserved IP. In the installed Home Assistant integration,
the API client connects using that saved host, checks the reported MAC, and updates
the stored ESPHome device name after a successful connection. Changing the firmware
hostname to `dining-arc-lamp` therefore does not require deleting the config entry
or device. Keep the existing API/OTA authentication settings during this rename.

Follow the [ESPHome node-renaming procedure](https://esphome.io/components/esphome/#changing-esphome-node-name)
and upload using the controller's existing address. Replace its obsolete dashboard
YAML with one authoritative `dining_arc_lamp.yaml`, preserving shared includes and
private secrets. Verify the same MAC and reported firmware after OTA before
changing HA references.

A relay name or object-ID change can affect entity discovery independently of
the device identity. Inspect the post-OTA registry before selecting the canonical
relay. Keep one current control for this controller and rename its live firmware
diagnostic to `update.dining_arc_lamp_firmware`. Remove only confirmed obsolete
entities from this same device; retain the config entry, device, and current
diagnostic functionality.

The installed HA integration can initialize the update platform using the old
cached node name during a rename. If the relay is available but the retained
firmware entity is unavailable, first verify that the stored device name and
ESPHome dashboard mapping both match `dining-arc-lamp`. Then reload this existing
config entry and verify both entities again. This reload does not reboot Home
Assistant or the controller.

The owner identified the controller as YM-WS-1. Its corrected profile uses a
GPIO15 relay, GPIO13 button, and GPIO12 active-low indicator following the relay;
the inherited GPIO2 indicator setting did not work on this hardware. The owner
confirmed button/load operation and then the corrected indicator. These are
owner observations, not extra agent-operated load tests.

## Remove the old lighting role

The owner explicitly retired the lamp's former Studio automation role:

- Retire motion rules 110 and 111, which controlled only this lamp.
- Remove only the former lamp action from shared shutdown rules 074 and 075.
- Remove only its former 35 W entry from the load-selection map in rule 085.
- Remove only its former target from the household lights/media shutdown script.
- Replace the obsolete Office Wall Lamp card with the canonical Dining Arc lamp
  control, retaining neighboring cards and the surrounding Lighting layout.
- Clean the exact legacy lamp aliases in the inactive root `automations.yaml`
  without activating that historical configuration.

**Preserve `input_boolean.studio_sticky`, the Office manual-override button,
and notification rules 041 and 042.** The owner expressly retained these even
though the two retired motion rules previously consumed the helper. Preserve
the Studio motion sensor and unrelated lighting controls as well.

The owner separately requested motion control in the destination room. Add the
new relay to Dining room rules 033 (on) and 031 (off), alongside the existing wall
lights. Preserve both Dining motion sensors, the existing sun-elevation guards,
`input_boolean.dining_room_sticky`, the five-minute off timeout, recovery retries,
and every existing target. The independent on command uses the same
`continue_on_error` behavior as its siblings. Lobby rules 063/064, which also
control the wall-light switch from a different room, remain unchanged.

The new lamp does not inherit the old Studio motion rules, shared shutdown
schedules, or load-selection role. Validate the changed configuration and reload
only the affected automation and script integrations.

## Readback and Matter

Check the canonical relay's availability, the retained device/config-entry
identity, the live firmware diagnostic, the updated card, and the absence of the
retired rules and lamp references. Separately verify that the sticky helper,
its button, and rules 041/042 remain unchanged. Do not add physical load or
restart tests to the owner-authorized OTA and configuration work.

When the existing Matter bridge API is available, inspect whether the old relay
already has an endpoint before changing exposure. Preserve existing endpoints,
serials, unique IDs, and controller fabrics. If the API is unavailable, report
Matter as pending rather than resetting or recommissioning the bridge. HA and
Desktop migration do not depend on that unrelated bridge-management problem.

Keep firmware keys, network addresses, hardware identifiers, registry IDs, and
operational receipts in the private workbench rather than this repository.
