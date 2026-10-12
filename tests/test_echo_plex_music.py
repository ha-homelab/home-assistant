"""Exercise music queue reuse in an isolated HA with no real audio services."""
import os
from enum import StrEnum
from pathlib import Path
import tempfile
import unittest

try:
    import yaml
    from homeassistant import loader
    from homeassistant.bootstrap import async_load_base_functionality
    from homeassistant.config_entries import ConfigEntries
    from homeassistant.core import HomeAssistant, SupportsResponse
    from homeassistant.setup import async_setup_component
except ImportError:
    HA_AVAILABLE = False
else:
    HA_AVAILABLE = True

ROOT = Path(os.environ.get('ECHO_TEST_ROOT', Path(__file__).resolve().parents[1]))
PLAYER = 'media_player.echo_dot_music'


@unittest.skipUnless(HA_AVAILABLE, 'Requires the deployed Home Assistant runtime')
class EchoPlexMusicTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='echo-plex-test-')
        self.hass = HomeAssistant(self.temp.name)
        loader.async_setup(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self.hass.config.skip_pip = True
        self.assertTrue(await async_load_base_functionality(self.hass))
        self.calls = []
        self.queue = {'items': 0, 'current_item': None}
        self.hass.states.async_set(PLAYER, 'idle')
        self.hass.services.async_register('music_assistant', 'get_queue', self.get_queue,
                                         supports_response=SupportsResponse.ONLY)
        self.hass.services.async_register('music_assistant', 'play_media', self.record)
        for action in ('media_play', 'media_pause', 'media_next_track'):
            self.hass.services.async_register('media_player', action, self.record)
        config = yaml.safe_load((ROOT / 'config/packages/echo_plex_music.yaml').read_text())
        self.assertTrue(await async_setup_component(self.hass, 'script', {'script': config['script']}))
        await self.hass.async_start()

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.temp.cleanup()

    async def get_queue(self, call):
        self.assertEqual(call.data['entity_id'], [PLAYER])
        return {PLAYER: self.queue}

    async def record(self, call):
        self.assertEqual(call.data['entity_id'], [PLAYER])
        self.calls.append((call.domain, call.service, dict(call.data)))

    async def request(self, command='play'):
        return await self.hass.services.async_call('script', 'echo_plex_music',
            {'command': command}, blocking=True, return_response=True)

    def actions(self):
        return [(domain, service) for domain, service, _ in self.calls]

    async def test_empty_queue_loads_default_playlist(self):
        result = await self.request()
        self.assertTrue(result['success'])
        self.assertEqual(self.actions(), [('music_assistant', 'play_media')])
        self.assertEqual(self.calls[0][2]['media_id'], 'plex--home-music://playlist//playlists/60771')

    async def test_library_uri_uses_plex_stream_provider_to_resume(self):
        self.queue = {'items': 16472, 'current_item': {
            'media_item': {'uri': 'library://track/2'},
            'stream_details': {'provider': 'plex--home-music'}}}
        await self.request()
        self.assertEqual(self.actions(), [('media_player', 'media_play')])

    async def test_nested_enum_in_queue_does_not_coerce_response_to_string(self):
        class MediaType(StrEnum):
            TRACK = 'track'

        self.queue = {'items': 16472, 'current_item': {
            'media_item': {'uri': 'library://track/2', 'media_type': MediaType.TRACK},
            'stream_details': {'provider': 'plex--home-music'}}}
        result = await self.request()
        self.assertTrue(result['success'])
        self.assertEqual(self.actions(), [('media_player', 'media_play')])

    async def test_plex_uri_resumes_without_stream_details(self):
        self.queue = {'items': 5, 'current_item': {
            'media_item': {'uri': 'plex--home-music://track//library/metadata/123'}}}
        await self.request()
        self.assertEqual(self.actions(), [('media_player', 'media_play')])

    async def test_already_playing_plex_keeps_current_position(self):
        self.hass.states.async_set(PLAYER, 'playing')
        self.queue = {'items': 5, 'current_item': {'stream_details': {'provider': 'plex--home-music'}}}
        await self.request()
        self.assertEqual(self.calls, [])

    async def test_other_source_and_missing_metadata_load_default(self):
        for current in (None, {'media_item': {'uri': None}},
                        {'media_item': {'uri': 'spotify://track/123'}},
                        {'stream_details': {'provider': 'different-plex-server'}}):
            with self.subTest(current=current):
                self.calls.clear()
                self.queue = {'items': 12, 'current_item': current}
                await self.request()
                self.assertEqual(self.actions(), [('music_assistant', 'play_media')])

    async def test_unavailable_speaker_and_invalid_command_do_not_play(self):
        for state in ('unavailable', 'unknown'):
            self.hass.states.async_set(PLAYER, state)
            self.assertFalse((await self.request())['success'])
        self.hass.states.async_set(PLAYER, 'idle')
        self.assertFalse((await self.request('unsupported'))['success'])
        self.assertEqual(self.calls, [])

    async def test_transport_commands_do_not_rebuild_the_playlist(self):
        for command in ('pause', 'resume', 'next'):
            self.assertTrue((await self.request(command))['success'])
        self.assertEqual(self.actions(), [('media_player', 'media_pause'),
            ('media_player', 'media_play'), ('media_player', 'media_next_track')])


if __name__ == '__main__':
    unittest.main()
