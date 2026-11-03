"""Set up one authenticated external updater."""
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow
from homeassistant.helpers import selector

from .client import validate_settings
from .const import DEFAULT_URL, DOMAIN, UNIQUE_ID


class CoreUpdateFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_import(self, user_input):
        await self.async_set_unique_id(UNIQUE_ID)
        self._abort_if_unique_id_configured()
        url = validate_settings(user_input['url'], user_input['authorization'])
        return self.async_create_entry(title='Home Assistant Core',
                                      data={**user_input, 'url': url})

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                return await self.async_step_import(user_input)
            except ValueError:
                errors['base'] = 'invalid_settings'
        return self.async_show_form(step_id='user', errors=errors, data_schema=vol.Schema({
            vol.Required('url', default=DEFAULT_URL): str,
            vol.Required('authorization'): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
        }))
