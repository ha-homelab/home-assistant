# Display templates during startup and reload

The display sensors keep their entity IDs and ordinary calculations when their
sources are temporarily absent during HA startup or `template.reload`.

`Battery in yesterday` and `Battery out yesterday` read the `last_period`
attribute of `sensor.today_battery_in` and `sensor.today_battery_out`. Safe
`state_attr` access returns no value when the entity or attribute is absent.
Availability requires a finite numeric attribute: missing, unknown or invalid
history is unavailable rather than a fabricated zero. A genuine zero remains
zero. A valid retained `last_period` is still usable when the current-period
meter state is unavailable; yesterday's measurement has not become unknown.
The original values, classifications and identities remain unchanged.

`Solar Age` safely checks for a regex match before formatting the leading
integer from `sensor.solar_days`. An absent or unmatched source displays
`unknown`, preserving the original intended fallback without an `IndexError`.
Zero still displays `0 days`. The existing 365-day years, 30-day months, remainder
calculation, pluralization and leading-integer handling remain unchanged.

The real-HA tests in `tests/test_water_calendar_templates.py` load these entities
with absent sources, reject missing/invalid values, accept real zero and verify
recovery without template errors. They also preserve the established formatting
for valid solar-age values and the two independent battery-history sources.

Deploy through a controlled template reload without restarting HA. Follow the
[water reload precautions](water-pump-levels.md#water-fill-speed-source) because
that reload also recreates water-level templates. Historical system-log groups
retain earlier messages: check new occurrences and current entity states rather
than treating every old message in an aggregate as a new failure.
