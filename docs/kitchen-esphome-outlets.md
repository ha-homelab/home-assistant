# Kitchen ESPHome outlets

The completed kitchen migrations use:

- **LED Under Cabinet**: `switch.led_under_cabinet`, formerly
  `light.led_under_cabinet_l`.
- **Tea table**: `switch.tea_table`, formerly `light.led_under_cabinet_2_l`.
  The obsolete group spelling `light.led_under_cabinet_2l` resolves to this same
  replacement.

The automation and script dependencies use matching switch services. The
household shutdown's mixed light/switch list uses `homeassistant.turn_off`.
Groups, customizations and the floorplan's two kitchen light bindings follow the
new IDs. Existing geometry, unrelated targets, guards and delays are preserved.

The counter's seven-minute motion-clear behavior and manual-on handling are
unchanged: an ordinary manual OFF-to-ON transition is not availability recovery.
The existing unknown/unavailable recovery policy remains in the shipped rule.

Tea table retains its three-minute motion-clear timeout, kitchen sticky guard,
and solar elevation threshold below 0.60 degrees. Daytime motion therefore does
not switch it on. The self-consumption map retains its 35 W estimate.

The original migration verified actual counter-motion control. Tea table passed
an HA service ON/OFF cycle that restored the original state; its daytime motion
guard was verified without bypassing it. These are earlier migration results;
the later garage reference cleanup does not repeat physical testing.

Private firmware source and per-device secrets remain in the HA and ESPHome
Dashboard source trees. They are not copied into this public configuration
repository. Historical audits and original import baselines remain unchanged.
