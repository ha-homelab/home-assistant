# RuView notifications in OTTPlayer

Applied on 2026-11-06 at the user's request. This replaces the October 23 policy that retained RuView notifications with compact labels.

The source was the OTTPlayer controller's direct Home Assistant event bridge, not a Home Assistant notification automation. Nine dedicated rules covered motion-on, presence-on and presence-off for RuView nodes 1–3.

## Current policy and applied change

- Removed those nine rules from the active `home_assistant.rules` array: 20 rules became 11.
- Preserved all eleven unrelated rules exactly, including camera, other motion/presence, light and outlet notifications.
- Preserved the nine original rules in `ruview-notifications.disabled.json`, both alongside the private local configuration and as a separate key in the existing controller Secret. JSON does not support comments; this separate file is not loaded by the controller.
- Synchronized the active rules in `~/.config/ottplay-control/server.json` and `~/.config/ottplay-control/ha-rules-expanded.json`.
- Restarted only the OTTPlayer controller with its existing image. Home Assistant, RuView sensing and the players were not restarted.

## Verification

The installed controller executable accepted the candidate configuration. Readback confirmed zero RuView references in active rules, exact preservation of the other eleven rules, unchanged unrelated Secret data and agreement of both local source files. The controller rollout completed and its HA bridge reconnected; the notification queue was empty. No synthetic notification or appliance command was sent.

## Restore later

Review the nine rules in the private `ruview-notifications.disabled.json` and reinsert them into the **current** active configuration and expanded rules. Validate with the installed executable, apply the corresponding Secret update and restart only the controller. Do not restore an older complete configuration, which could overwrite newer device registrations or other rules.

The disabled rule IDs are `ruview-nodeN-motion-on`, `ruview-nodeN-occupancy-on` and `ruview-nodeN-occupancy-off`, where N is 1, 2 or 3. The preserved file includes their original filters, labels, cooldowns and delivery settings.


## Keep this policy during later deployments

The private controller configuration is the source of the event allowlist. This HA repository documents the policy but does not contain the live controller Secret, tokens or registrations. A Home Assistant configuration deployment alone cannot mute or restore these controller rules.

When updating the controller, carry forward the eleven active rules and retain the separate disabled-rule file. Do not regenerate the former twenty-rule set from historical October 23 material. Check both the dedicated RuView rules and generic motion/presence allowlists so the six node entities are not silently reintroduced through another rule.

To inspect without sending a notification, use the controller's `ott ha status -j` command and verify the bridge is connected. Validate the current controller configuration before a restart. A healthy bridge alone does not establish which allowlist was loaded: also verify the deployed configuration contains no active RuView rule or entity reference.
