"""Authenticated, non-persistent relative cleaning-path images."""
from __future__ import annotations

from datetime import datetime
import logging

from homeassistant.components.image import ImageEntity
from homeassistant.const import EntityCategory
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

from .trail import render_png

MIN_RENDER_SECONDS = 5
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    config_entry.runtime_data.add_images = async_add_entities


class RoombaTrailImage(ImageEntity):
    _attr_has_entity_name = True
    _attr_name = "Relative cleaning path"
    _attr_icon = "mdi:map-marker-path"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_content_type = "image/png"
    _attr_should_poll = False
    _attr_available = False

    def __init__(self, manager, native_entry):
        super().__init__(manager.hass)
        self.manager = manager
        self.native_entry_id = native_entry.entry_id
        self._attr_unique_id = f"{native_entry.entry_id}_relative_cleaning_path"
        self._attr_suggested_object_id = f"{native_entry.title}_relative_cleaning_path"
        registry = dr.async_get(manager.hass)
        device = next(iter(dr.async_entries_for_config_entry(registry, native_entry.entry_id)), None)
        if device is not None:
            self._attr_device_info = {"identifiers": device.identifiers}
        self._desired = None
        self._displayed = None
        self._content = None
        self._timer = None
        self._render_task = None
        self._last_render = -MIN_RENDER_SECONDS
        self._removed = False

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.async_update_trail()

    async def async_will_remove_from_hass(self):
        self._removed = True
        if self._timer is not None:
            self._timer()
            self._timer = None
        if self._render_task is not None:
            self._render_task.cancel()
        self._content = None
        await super().async_will_remove_from_hass()

    @callback
    def async_update_trail(self):
        if self._removed:
            return
        self._desired = self.manager.snapshot_trail(self.native_entry_id)
        snapshot = self._desired
        if snapshot is None or not snapshot.has_path:
            changed = self._attr_available or self._displayed != snapshot
            self._attr_available = False
            self._content = None
            self._displayed = snapshot
            self._attr_image_last_updated = None
            if self._timer is not None:
                self._timer()
                self._timer = None
            if changed and self.hass and self.entity_id:
                self.async_write_ha_state()
            return
        if snapshot == self._displayed or self._timer is not None or self._render_task is not None:
            return
        delay = max(0, MIN_RENDER_SECONDS - (self.hass.loop.time() - self._last_render))
        if delay:
            self._timer = async_call_later(self.hass, delay, self._begin_render)
        else:
            self._begin_render(None)

    @callback
    def _begin_render(self, _now: datetime | None):
        self._timer = None
        if (self._removed or self._render_task is not None
                or self._desired is None or not self._desired.has_path):
            return
        self._render_task = self.hass.async_create_task(self._async_render())

    async def _async_render(self):
        snapshot = self._desired
        try:
            try:
                content = await self.hass.async_add_executor_job(render_png, snapshot)
            except Exception:
                # Do not retry a broken snapshot on every timer tick. A new
                # real message may try again; no raw payload is logged.
                _LOGGER.exception("Unable to render relative cleaning path")
                content = None
            if self._removed or self._desired != snapshot:
                return  # Never publish an image older than the desired snapshot.
            self._content = content
            self._displayed = snapshot
            self._attr_available = content is not None
            self._attr_image_last_updated = dt_util.utcnow() if content is not None else None
            if self.hass and self.entity_id:
                self.async_write_ha_state()
        finally:
            self._last_render = self.hass.loop.time()
            self._render_task = None
            if not self._removed:
                self.async_update_trail()

    async def async_image(self):
        return self._content if self._attr_available else None

    @property
    def extra_state_attributes(self):
        snapshot = self._displayed
        source = self.manager.entities.get(self.native_entry_id)
        return {
            "source": "native_roomba_pose_delta",
            "source_entity_id": getattr(source, "source_entity_id", None),
            "coordinate_frame": "relative_uncalibrated",
            "units": "device_units",
            "is_house_map": False,
            "observed_at": None,
            "timestamp_quality": "local_received",
            "collection_scope": "current process and current mission",
            "last_point_received_at": snapshot.last_point_received_at if snapshot else None,
            "point_count": snapshot.point_count if snapshot else 0,
            "segment_count": len(snapshot.segments) if snapshot else 0,
            "path_status": snapshot.status if snapshot else "waiting_for_pose",
            "connected": snapshot.connected if snapshot else False,
            "truncated": snapshot.truncated if snapshot else False,
        }
