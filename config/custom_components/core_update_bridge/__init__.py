"""Expose the external k3s updater through Home Assistant's native update UI."""
from datetime import timedelta

import voluptuous as vol

from homeassistant.const import Platform
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import BridgeError, Client
from .const import DEFAULT_URL, DOMAIN

CONFIG_SCHEMA = vol.Schema({DOMAIN: vol.Schema({
    vol.Optional('url', default=DEFAULT_URL): cv.string,
    vol.Required('authorization'): cv.string,
})}, extra=vol.ALLOW_EXTRA)


async def async_setup(hass, config):
    if DOMAIN in config:
        hass.async_create_task(hass.config_entries.flow.async_init(
            DOMAIN, context={'source': 'import'}, data=config[DOMAIN]))
    return True


async def async_setup_entry(hass, entry):
    import logging
    client = Client(async_get_clientsession(hass), entry.data['url'], entry.data['authorization'])

    async def update():
        try:
            return await client.status()
        except BridgeError as error:
            raise UpdateFailed(str(error)) from error

    coordinator = DataUpdateCoordinator(hass, logging.getLogger(__name__), name=DOMAIN,
        config_entry=entry, update_method=update, update_interval=timedelta(seconds=15))
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = (coordinator, client)
    await hass.config_entries.async_forward_entry_setups(entry, [Platform.UPDATE])
    return True


async def async_unload_entry(hass, entry):
    return await hass.config_entries.async_unload_platforms(entry, [Platform.UPDATE])
