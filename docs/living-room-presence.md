# Living-room presence lighting

`binary_sensor.living_room_presence` is the ZHA TS0225 presence sensor. The
package `config/packages/living_room_presence_lamp.yaml` controls only
`switch.living_lamp`, the second outlet of the living-room KMC.

The operating window matches the scheduled main living-room curtains: it starts
when the descending sun falls below 0.2 degrees and ends at sunrise or 06:30,
whichever is later. Manual curtain movements and the curtain sticky override do
not change this lighting window. Automatic curtains separately require both
Curtains Sticky and the relevant room Sticky to be OFF.

Presence turns the lamp on, including when it is already detected as the evening
window begins. Continuous confirmed absence turns it off after 20 minutes; renewed
presence cancels that timer. Unavailable or unknown readings never count as absence.
At the morning boundary the lamp turns off even if presence remains detected.
Ordinary daytime use is not polled off. The shared 05:35 shutdown no longer includes
this lamp. Other shared/manual shutdown scripts remain available; during overnight
presence the controller will turn the lamp back on only when Living room sticky
is explicitly OFF.

`input_boolean.living_room_sticky` pauses **all** commands from this presence
controller: turning on, the absence timeout, the morning boundary, startup,
reload and periodic reconciliation. With Sticky ON, manual OFF stays off and
manual ON stays on. A missing, unknown or unavailable sticky helper also blocks
automatic light commands. Sticky does not issue a light command itself.

The guard is checked both when the automation starts and immediately before each
command. Dining room sticky controls dining lights; it does not replace the
living-room override. Shared lights and other motion paths are documented in
[Room Sticky policy](motion-light-sticky.md).

Startup, automation reload, lamp availability recovery and a once-a-minute check
reconcile the current state. If a reload loses the normal `for` timer, the current
confirmed-absence age still allows shutdown. After a complete HA restart, a sensor
that returns as absent receives a fresh conservative 20-minute wait. An overnight
HA outage spanning the morning boundary does not retrospectively switch off a
manually operated daytime lamp.

The package needs a working ZHA sensor. Pairing and a reported ON state alone do
not establish that stationary-person detection or the sensor's own clearing delay
is correct. The 20-minute delay begins when this entity reports OFF.

## Dashboard history

Overview / Lighting contains a 24-hour history card immediately below the button
row with Living lamp. Its two timelines compare the raw presence report with the
actual lamp switch state, including unavailable periods. Follow the card's History
link to inspect a shorter interval when checking the 20-minute absence delay.
The sensor only has recorded history from its recent pairing onward.

Above the graph, a live status card explicitly shows **Detected**, **Not detected**,
**Sensor unavailable**, or **Status unknown** in English. It follows the raw
presence entity, so missing data is never presented as confirmed absence.
An ON/OFF value can still be the last known report during a radio outage; the
status card does not independently test connectivity with the sensor.

The storage-mode dashboard remains private runtime data; the reusable card is
recorded in [dashboards/living-room-presence.yaml](dashboards/living-room-presence.yaml).
It uses the built-in [History graph card](https://www.home-assistant.io/dashboards/history-graph/)
and the existing recorder. No integration reload or additional sensor is required.

## Coordinator recovery on 2026-10-11

The SLZB-06 runs the SMLIGHT core firmware v2.5.2 and a separate CC2652P Zigbee
firmware. Its Mode page initially showed no selected radio role because the core
reported the radio type and version as unknown. ZHA still identified the radio as
a coordinator running Z-Stack 20240710; the empty selectors alone did not mean the
radio was disabled.

A complete ZHA network backup and a consistent SQLite backup of `zigbee.db` were
saved privately before reinstalling the official
`CC1352P2_CC2652P_other_coordinator_20240710.bin` image at 115200 baud. ZHA was
temporarily disabled during flashing and enabled again afterward. The adapter
reported successful flashing, and the Mode page now identifies Zigbee Coordinator
20240710. The core firmware was not changed.

ZHA loaded with all 19 device records, preserving the coordinator IEEE, PAN ID,
extended PAN ID, network key and channel 25. Fresh, uncached reads from Garage Four,
Porch One and Bathroom mirror still failed; the logs still contained
`MAC_CHANNEL_ACCESS_FAILURE`. Powering off the presence sensor had not restored
communication either. Firmware installation and network restoration succeeded,
but lamp control was **not** verified working at that stage.

After returning the coordinator to its former cable, power supply and placement,
the user reported that some lamps worked again. An uncached on/off-attribute
read at approximately 20:09–20:10 PDT succeeded for Garage One, Garage Three,
Garage Five, Bathroom mirror and Porch One. Garage Two, Garage Four and Porch
Two did not answer that pass. The garage failures returned `NWK_NO_ROUTE`;
the Porch Two failure returned `MAC_CHANNEL_ACCESS_FAILURE`. This establishes
partial radio recovery, not full recovery or proof of which physical change
caused the fault. A single power
cycle of the three unresponsive lamps was requested; the coordinator and network
settings remain unchanged. Balcony was already unavailable before this incident
and was not included in this recovery probe.

Bluetooth Proxy was discussed but not enabled. SMLIGHT provides a combined
[Zigbee + Bluetooth ESPHome firmware](https://github.com/smlight-dev/slzb-06-fw-esphome/),
which replaces the core firmware and its existing web interface. Keep that change
separate from diagnosing the current radio outage.
