"""A single bounded diagnostics entity per existing native Roomba entry."""
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers import device_registry as dr


async def async_setup_entry(hass, config_entry, async_add_entities):
    config_entry.runtime_data.add_entities = async_add_entities


class RoombaTelemetrySensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Local telemetry"
    _attr_icon = "mdi:robot-vacuum"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = False

    def __init__(self, manager, native_entry):
        self.manager = manager
        self.native_entry_id = native_entry.entry_id
        self.source_entity_id = None
        self._attr_unique_id = f"{native_entry.entry_id}_local_telemetry"
        registry = dr.async_get(manager.hass)
        device = next(iter(dr.async_entries_for_config_entry(registry, native_entry.entry_id)), None)
        if device is not None:
            # Reuse the existing device; do not copy credentials, addresses or
            # native client objects into state attributes.
            self._attr_device_info = {"identifiers": device.identifiers}
        self._attr_suggested_object_id = f"{native_entry.title}_local_telemetry"

    @property
    def native_value(self):
        data = self.extra_state_attributes
        if not data["connected"]:
            return "disconnected" if data["native_entry_state"] == "loaded" else data["native_entry_state"]
        return data.get("mission", {}).get("phase") or "connected"

    @property
    def extra_state_attributes(self):
        return self.manager.snapshot(self.native_entry_id, self.source_entity_id)
