# Air Purifier Living and Switch07

On 2026-10-11, the former standalone **Air Purifier Living** outlet was renamed
**Switch07** (`switch.switch07`) before transferring its role to outlet 2 of the
third KMC 30608. That outlet, formerly **Front Camera and Living Curtains**, is
now **Air Purifier Living** (`switch.air_purifier_living`). Its physical output
remains outlet 2, GPIO13; the other two KMC roles are unchanged.

## Control references

Self-consumption rules 085, 087, 088, 091, 096 and 098 keep the canonical
`switch.air_purifier_living` reference. They therefore address the new KMC
output, with the existing 235 W estimate, numerical thresholds, guards,
state-duration checks and action ordering unchanged. No active automation or
script referenced the former camera/curtain ID or either device directly.
Do not redirect these role references to the now-spare Switch07.

The standalone relay and its five diagnostics retain their registry and hardware
identities under Switch07 names. The device and integration display names are
also Switch07. Lovelace keeps Air Purifier Living at the former camera/curtain
row and moves Switch07 to the bottom, immediately after Switch06 and Switch05.
Renaming and dashboard verification issue no relay commands or device restarts.

## Standalone hardware recovery and saved source

The earlier Workdesk-to-Air-Purifier migration used an incorrect YM-WS-1 pin
profile. The 2026-10-11 recovery verified button GPIO1 (active low), relay
GPIO14 and indicator GPIO13 (active high). The owner confirmed that the test
lamp and indicator now turn on and off together. Relay startup remains
`ALWAYS_OFF`; a controlled mains-cycle test is still pending.

Its private source is now `switch07.yaml` in both HA's `/config/esphome` and
the ESPHome Dashboard's `/config`. Only the saved friendly name changes;
the native node/component names, secret values and corrected GPIO profile stay
stable. This metadata migration does not upload firmware, so the running
firmware may still advertise its previous friendly name beneath HA overrides.
The saved configuration validates with ESPHome 2026.9.1.

The original LocalTuya conversion and Workdesk role are historical evidence.
No additional integration removal, Matter fabric reset or network rename is
part of this reassignment. Private runtime backups retain the original records.
