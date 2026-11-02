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
        self.assertNotIn("cards", media)
        self.assertEqual(media["type"], "sections")
        self.assertEqual(media["max_columns"], 3)
        self.assertFalse(media["dense_section_placement"])
        sections = media["sections"]
        self.assertEqual(sections[0]["cards"], [original["views"][1]["cards"][-1]])
        self.assertEqual(sections[1]["column_span"], 3)
        self.assertEqual(sections[1]["cards"][0]["heading"], "Phones and Echo")
        self.assertEqual(len(sections), 4)
        for wrapper, device in zip(sections[2:], manifest["devices"]):
            self.assertEqual(wrapper["column_span"], 1)
            self.assertEqual(wrapper["cards"][0]["heading"], device["name"])
            self.assertEqual(wrapper["cards"][0]["grid_options"], {"columns": 12})
            player = wrapper["cards"][1]
            self.assertEqual(player["entity"], device["entity"])
            self.assertEqual(player["type"], "custom:mini-media-player")
            self.assertEqual(player["grid_options"], {"columns": 12})
            self.assertEqual(player["shortcuts"]["columns"], 2)
            self.assertNotIn("conditions", wrapper)

    def test_rerun_does_not_duplicate_players(self):
        config, manifest = self.fixture()
        first = module.migrate_media_view(config, manifest)
        self.assertEqual(module.migrate_media_view(first, manifest), first)

    def test_manual_edit_to_generated_cards_is_not_overwritten(self):
        config, manifest = self.fixture()
        first = module.migrate_media_view(config, manifest)
        first["views"][1]["sections"][2]["cards"][1]["artwork"] = "none"
        with self.assertRaises(ValueError):
            module.migrate_media_view(first, manifest)

    def test_prior_generated_cards_move_after_legacy_and_use_play_stop(self):
        config, manifest = self.fixture()
        previous = [module._card(device) for device in manifest["devices"]]
        legacy = config["views"][1]["cards"][-1]
        manifest["devices"][0]["transport"] = "play_stop"
        for order in (previous + [legacy], [legacy] + previous):
            with self.subTest(order=order):
                config["views"][1]["cards"] = order
                result = module.migrate_media_view(config, manifest)
                sections = result["views"][1]["sections"]
                self.assertEqual(sections[0]["cards"], [legacy])
                hide = sections[2]["cards"][1]["hide"]
                self.assertTrue(hide["play_pause"])
                self.assertFalse(hide["play_stop"])
                self.assertNotIn("play_pause", sections[3]["cards"][1]["hide"])
                self.assertEqual(module.migrate_media_view(result, manifest), result)

    def test_legacy_order_preserved_and_later_console_survives_rerun(self):
        config, manifest = self.fixture()
        before = {"type": "markdown", "content": "Before"}
        after = {"type": "markdown", "content": "After"}
        config["views"][1]["cards"].insert(0, before)
        config["views"][1]["cards"].append(after)
        result = module.migrate_media_view(config, manifest)
        sections = result["views"][1]["sections"]
        self.assertEqual([s["cards"][0] for s in sections[:3]],
                         [before, config["views"][1]["cards"][2], after])
        console = {"type": "grid", "column_span": 3,
                   "cards": [{"type": "markdown", "content": "Radio console"}]}
        sections.insert(3, console)
        self.assertEqual(module.migrate_media_view(result, manifest), result)

    def test_unknown_transport_is_rejected(self):
        config, manifest = self.fixture()
        manifest["devices"][0]["transport"] = "toggle"
        with self.assertRaises(ValueError):
            module.migrate_media_view(config, manifest)

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
