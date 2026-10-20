"""Exercise the real patched HACS method without GitHub or Home Assistant."""

import ast
import textwrap
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from tools.patch_hacs_release_notes import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "tests/fixtures/hacs/update.py").read_text()


def release(tag, body):
    return SimpleNamespace(tag_name=tag, name=tag, body=body)


def entity(*, installed="v0.3.2", latest="v0.4.2", repository="ha-homelab/ha-desloc"):
    releases = [release("v0.4.2", "Latest changes"), release("v0.4.1", "Old changes"),
                release("v0.3.2", "Installed changes")]
    return SimpleNamespace(
        installed_version=installed, latest_version=latest,
        repository=SimpleNamespace(
            data=SimpleNamespace(full_name=repository, published_tags=[x.tag_name for x in releases],
                                 show_beta=False, category="integration"),
            releases=SimpleNamespace(objects=releases), pending_restart=False,
            pending_update=True, get_releases=AsyncMock(return_value=[])),
        hacs=SimpleNamespace(configuration=SimpleNamespace(release_limit=5)))


def method(source):
    start = source.index("    async def async_release_notes(")
    end = source.index("    async def async_added_to_hass(", start)
    tree = ast.parse(textwrap.dedent(source[start:end]))
    fn = tree.body[0]
    namespace = {"HacsCategory": SimpleNamespace(INTEGRATION="integration", PLUGIN="plugin")}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "hacs/update.py", "exec"), namespace)
    return namespace[fn.name]


class ReleaseNotesTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_offered_release_and_history_link(self):
        obj = entity()
        text = await method(patch(SOURCE))(obj)
        self.assertIn("Latest changes", text)
        self.assertNotIn("Old changes", text)
        self.assertNotIn("Installed changes", text)
        self.assertIn("[Full release history](https://github.com/ha-homelab/ha-desloc/releases)", text)
        self.assertIn("restart", text)
        obj.repository.get_releases.assert_not_called()

    async def test_current_install_still_shows_latest_notes(self):
        obj = entity(installed="v0.4.2")
        obj.repository.pending_update = False
        text = await method(patch(SOURCE))(obj)
        self.assertIn("Latest changes", text)
        self.assertNotIn("Old changes", text)
        self.assertNotIn("restart", text)

    async def test_cached_prerelease_cannot_replace_selected_stable(self):
        obj = entity()
        obj.repository.releases.objects.insert(0, release("v0.4.3-beta.2", "Beta changes"))
        text = await method(patch(SOURCE))(obj)
        self.assertIn("Latest changes", text)
        self.assertNotIn("Beta changes", text)

    async def test_missing_notes_never_fall_back_to_another_version(self):
        obj = entity(latest="v9.0.0")
        text = await method(patch(SOURCE))(obj)
        self.assertIn("Full release history", text)
        self.assertNotIn("Latest changes", text)

    async def test_fetch_respects_selected_release_channel(self):
        obj = entity(latest="v0.4.3-beta.2")
        obj.repository.data.show_beta = True
        obj.repository.get_releases.return_value = [release("v0.4.3-beta.2", "Beta changes")]
        text = await method(patch(SOURCE))(obj)
        self.assertIn("Beta changes", text)
        obj.repository.get_releases.assert_awaited_once_with(prerelease=True, returnlimit=5)

    async def test_other_repositories_keep_original_output(self):
        obj = entity(repository="example/integration")
        self.assertEqual(await method(SOURCE)(obj), await method(patch(SOURCE))(obj))

    async def test_pending_restart_keeps_original_behavior(self):
        obj = entity()
        obj.repository.pending_restart = True
        self.assertIsNone(await method(patch(SOURCE))(obj))

    def test_patch_is_idempotent_and_rejects_unknown_source(self):
        patched = patch(SOURCE)
        self.assertEqual(patch(patched), patched)
        with self.assertRaises(ValueError):
            patch(SOURCE + "\n# unreviewed change\n")
        with self.assertRaises(ValueError):
            patch(patched.replace("Full release history", "Changed history"))


if __name__ == "__main__":
    unittest.main()
