"""Passive diagnostics using only native Roomba-owned MQTT connections."""
from __future__ import annotations

from datetime import timedelta
from typing import Callable

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import NATIVE_DOMAIN, SCAN_SECONDS
from .telemetry import Telemetry

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    manager = InsightsManager(hass)
    entry.runtime_data = manager
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    manager.start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        entry.runtime_data.close()
        return True
    return False


class NativeBinding:
    """Own our callbacks only; never connect, disconnect or command a robot."""

    def __init__(self, manager, entry, robot):
        self.manager = manager
        self.entry_id = entry.entry_id
        self.robot = robot
        self.active = True
        self.telemetry = Telemetry()
        self.telemetry.update(self.reported(), received_at=dt_util.utcnow().isoformat(), initial=True)
        robot.register_on_message_callback(self.on_message)
        robot.register_on_disconnect_callback(self.on_disconnect)

    def reported(self):
        state = self.robot.master_state.get("state", {})
        reported = state.get("reported", {}) if isinstance(state, dict) else {}
        return reported if isinstance(reported, dict) else {}

    def on_message(self, payload):
        if not self.active:
            return
        state = payload.get("state", {}) if isinstance(payload, dict) else {}
        delta = state.get("reported", {}) if isinstance(state, dict) else {}
        # Construct the snapshot in the MQTT callback, after the library merges
        # this message and before another MQTT message can alter the cache.
        self.telemetry.update(self.reported(), received_at=dt_util.utcnow().isoformat(), delta=delta)
        self.manager.hass.add_job(self.manager.async_notify, self.entry_id, self)

    def on_disconnect(self, _error):
        if self.active:
            self.manager.hass.add_job(self.manager.async_notify, self.entry_id, self)

    def close(self):
        self.active = False
        for callbacks, ours in (
            (self.robot.on_message_callbacks, self.on_message),
            (self.robot.on_disconnect_callbacks, self.on_disconnect),
        ):
            if ours in callbacks:
                callbacks.remove(ours)


class InsightsManager:
    def __init__(self, hass):
        self.hass = hass
        self.bindings = {}
        self.last_known = {}
        self.entities = {}
        self.entries = {}
        self.add_entities: Callable | None = None
        self.cancel_timer = None
        self.closed = False

    @callback
    def start(self):
        self.async_reconcile()
        self.cancel_timer = async_track_time_interval(self.hass, self.async_reconcile, timedelta(seconds=SCAN_SECONDS))

    @callback
    def async_reconcile(self, _now=None):
        if self.closed:
            return
        entries = {e.entry_id: e for e in self.hass.config_entries.async_entries(NATIVE_DOMAIN)}
        self.entries = entries
        registry = er.async_get(self.hass)
        for entry_id, binding in list(self.bindings.items()):
            entry = entries.get(entry_id)
            runtime = getattr(entry, "runtime_data", None) if entry else None
            if entry is None or entry.state != ConfigEntryState.LOADED or getattr(runtime, "roomba", None) is not binding.robot:
                binding.close()
                self.last_known[entry_id] = binding.telemetry
                del self.bindings[entry_id]
        for entry_id, entry in entries.items():
            if entry_id not in self.entities and self.add_entities is not None:
                from .sensor import RoombaTelemetrySensor
                sensor = RoombaTelemetrySensor(self, entry)
                self.entities[entry_id] = sensor
                self.add_entities([sensor])
            if entry.state == ConfigEntryState.LOADED and entry_id not in self.bindings:
                robot = getattr(getattr(entry, "runtime_data", None), "roomba", None)
                if robot is not None:
                    self.bindings[entry_id] = NativeBinding(self, entry, robot)
            if sensor := self.entities.get(entry_id):
                native = next((e for e in er.async_entries_for_config_entry(registry, entry_id)
                               if e.domain == "vacuum" and e.platform == NATIVE_DOMAIN), None)
                sensor.source_entity_id = native.entity_id if native else None
                self.async_notify(entry_id)
        for entry_id in set(self.last_known) - set(entries):
            del self.last_known[entry_id]
        for entry_id in set(self.entities) - set(entries):
            entity = self.entities.pop(entry_id)
            if entity.hass:
                self.hass.async_create_task(entity.async_remove())

    @callback
    def async_notify(self, entry_id, source=None):
        if self.closed or (source is not None and self.bindings.get(entry_id) is not source):
            return  # Ignore queued notifications from a detached native client.
        sensor = self.entities.get(entry_id)
        if sensor is not None and sensor.hass and sensor.entity_id:
            sensor.async_write_ha_state()

    def snapshot(self, entry_id, source_entity_id):
        entry = self.hass.config_entries.async_get_entry(entry_id)
        state = entry.state.value if entry is not None else "removed"
        binding = self.bindings.get(entry_id)
        telemetry = binding.telemetry if binding else self.last_known.get(entry_id, Telemetry())
        connected = bool(binding and entry is not None and entry.state == ConfigEntryState.LOADED
                         and getattr(getattr(entry, "runtime_data", None), "roomba", None) is binding.robot
                         and binding.robot.roomba_connected)
        return telemetry.snapshot(connected=connected, entry_state=state,
                                  source_entity_id=source_entity_id)

    @callback
    def close(self):
        self.closed = True
        if self.cancel_timer is not None:
            self.cancel_timer()
        for binding in self.bindings.values():
            binding.close()
        self.bindings.clear()
