import copy
import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / "scripts/reorganize_media_players.py"
spec = importlib.util.spec_from_file_location("media_layout", PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class MediaLayoutTests(unittest.TestCase):
    def fixture(self):
        devices = [{"entity": "media_player.phone", "name": "Phone", "available": False,
                    "source_list": ["701 — Station"],
                    "shortcuts": [{"name": "Station", "id": "701 — Station", "type": "source"}]},
                   {"entity": "media_player.speaker", "name": "Speaker", "available": False,
                    "shortcuts": [{"name": "Radio", "id": "https://example.com/radio.mp3", "type": "music"}]}]
        legacy = {"type": "grid", "columns": 3, "cards": [
            {"type": "vertical-stack", "cards": [{"type": "media-control", "entity": d["entity"]}]}
            for d in devices]}
        config = {"title": "House", "views": [
            {"path": "other", "cards": [{"type": "entities", "entities": ["light.example"]}]},
            {"path": "media", "badges": ["sun.sun"], "cards": [legacy,
                {"type": "custom:sonos-card", "entityId": "media_player.other"}]}]}
        return config, {"devices": devices}

    def test_only_target_block_changes_and_inputs_stay_intact(self):
        config, manifest = self.fixture()
        original = copy.deepcopy(config)
        result = module.migrate_media_view(config, manifest)
        self.assertEqual(config, original)
        self.assertEqual(result["views"][0], original["views"][0])
        media = result["views"][1]
        self.assertEqual(media["badges"], original["views"][1]["badges"])
        self.assertEqual(media["cards"][-1], original["views"][1]["cards"][-1])
        self.assertEqual(len(media["cards"]), 3)
        for wrapper, device in zip(media["cards"], manifest["devices"]):
            self.assertEqual(wrapper["cards"][0]["heading"], device["name"])
            player = wrapper["cards"][1]
            self.assertEqual(player["entity"], device["entity"])
            self.assertEqual(player["type"], "custom:mini-media-player")
            self.assertEqual(player["shortcuts"]["columns"], 2)
            self.assertNotIn("conditions", wrapper)

    def test_rerun_does_not_duplicate_players(self):
        config, manifest = self.fixture()
        first = module.migrate_media_view(config, manifest)
        self.assertEqual(module.migrate_media_view(first, manifest), first)

    def test_manual_edit_to_generated_cards_is_not_overwritten(self):
        config, manifest = self.fixture()
        first = module.migrate_media_view(config, manifest)
        first["views"][1]["cards"][0]["cards"][1]["artwork"] = "none"
        with self.assertRaises(ValueError):
            module.migrate_media_view(first, manifest)

    def test_unrelated_or_ambiguous_block_is_rejected(self):
        config, manifest = self.fixture()
        config["views"][1]["cards"].append(copy.deepcopy(config["views"][1]["cards"][0]))
        with self.assertRaises(ValueError):
            module.migrate_media_view(config, manifest)
        config["views"][1]["cards"] = []
        with self.assertRaises(ValueError):
            module.migrate_media_view(config, manifest)

    def test_wrong_source_and_nonportable_protocol_are_rejected(self):
        config, manifest = self.fixture()
        manifest["devices"][0]["shortcuts"][0]["id"] = "Not a source"
        with self.assertRaises(ValueError):
            module.migrate_media_view(config, manifest)
        config, manifest = self.fixture()
        manifest["devices"][1]["shortcuts"][0]["id"] = "x-rincon-mp3radio://https://example.com/radio"
        with self.assertRaises(ValueError):
            module.migrate_media_view(config, manifest)

    def test_duplicate_entity_and_credential_url_are_rejected(self):
        config, manifest = self.fixture()
        manifest["devices"][1]["entity"] = manifest["devices"][0]["entity"]
        with self.assertRaises(ValueError):
            module.migrate_media_view(config, manifest)
        config, manifest = self.fixture()
        manifest["devices"][1]["shortcuts"][0]["id"] = "https://user:secret@example.com/radio"
        with self.assertRaises(ValueError):
            module.migrate_media_view(config, manifest)


if __name__ == "__main__":
    unittest.main()
