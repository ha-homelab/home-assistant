"""Native update entity with exact-version, single-candidate approval."""
from copy import deepcopy
import re

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import ACTIVE, BridgeError
from .const import DOMAIN, UNIQUE_ID


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator, client = entry.runtime_data
    async_add_entities([CoreUpdate(coordinator, client)])


class CoreUpdate(CoordinatorEntity, UpdateEntity):
    _attr_unique_id = UNIQUE_ID
    _attr_has_entity_name = True
    _attr_name = 'Core'
    _attr_title = 'Home Assistant Core'
    _attr_icon = 'mdi:home-assistant'
    _attr_entity_category = EntityCategory.CONFIG
    _attr_supported_features = (UpdateEntityFeature.INSTALL | UpdateEntityFeature.SPECIFIC_VERSION
                                | UpdateEntityFeature.RELEASE_NOTES | UpdateEntityFeature.PROGRESS)
    _attr_device_info = DeviceInfo(identifiers={(DOMAIN, UNIQUE_ID)}, name='Home Assistant',
                                  manufacturer='Home Assistant', model='k3s Core update controller')

    def __init__(self, coordinator, client):
        super().__init__(coordinator)
        self.client = client
        self.entity_id = 'update.home_assistant_core'
        self._approving = False

    @property
    def installed_version(self):
        return self.coordinator.data['installed_version']

    @property
    def latest_version(self):
        return self.coordinator.data.get('latest_version') or self.installed_version

    @property
    def in_progress(self):
        return self._approving or self.coordinator.data['stage'] in ACTIVE

    @property
    def release_url(self):
        return 'https://github.com/home-assistant/core/releases/tag/' + self.latest_version

    @property
    def release_summary(self):
        return ('Stable Core updates. Stage: ' + self.coordinator.data['stage'] + '. '
                'Install approves this exact version, with a configuration backup and preflight '
                'before PR merge and restart. Open release notes for the proposal link.')

    async def async_release_notes(self):
        data = self.coordinator.data
        lines = ['Stable Core updates. Stage: **' + data['stage'] + '**.',
                 'Install approves this exact version. The external updater creates a configuration backup, '
                 'checks the candidate, merges its PR and restarts Core.']
        url = data.get('pull_request_url') or ''
        if re.fullmatch(r'https://github\.com/[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+/pull/[1-9][0-9]*', url):
            lines.append('[Review the version pull request](' + url + ').')
        if data.get('last_error'):
            lines.append('The previous operation needs attention; see Core Updates for details.')
        return '\n\n'.join(lines)

    @property
    def extra_state_attributes(self):
        return {key: self.coordinator.data.get(key) for key in (
            'stage', 'candidate_id', 'target_version', 'expires_at', 'last_error', 'check_error',
            'proposal_sha', 'pull_request_number', 'pull_request_url', 'backup_mode')}

    async def async_install(self, version, backup, **kwargs):
        if self._approving:
            raise HomeAssistantError('An update approval is already in progress')
        displayed = deepcopy(self.coordinator.data)
        self._approving = True
        self.async_write_ha_state()
        try:
            accepted = await self.client.approve(displayed, version)
            self.coordinator.async_set_updated_data(accepted)
        except BridgeError as error:
            raise HomeAssistantError(str(error)) from error
        finally:
            self._approving = False
            self.async_write_ha_state()
