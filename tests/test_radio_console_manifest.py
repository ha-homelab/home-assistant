import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("console_manifest", Path(__file__).resolve().parents[1] / "scripts/build_radio_console.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ConsoleManifestTests(unittest.TestCase):
    def test_actual_sources_and_audio_urls_use_the_right_transport(self):
        catalog = {"stations": {"radio": {"name": "Radio", "extension": "711", "url": "https://example.org/live.mp3"},
                                "resolved": {"name": "Resolved", "extension": "712", "url": "https://example.org/api", "resolver": "api"}}}
        targets = [{"entity": "media_player.preset", "name": "Preset", "caps": 2048, "group": "Phones", "kind": "phone",
                    "source_list": ["Radio · 711", "Resolved · 712"]},
                   {"entity": "media_player.managed", "name": "Managed", "caps": 2560, "group": "Phones", "kind": "phone",
                    "source_list": ["711 — Radio", "712 — Resolved"]},
                   {"entity": "media_player.speaker", "name": "Speaker", "caps": 512, "group": "Speakers"}]
        result = module.build_console(catalog, targets)
        direct, resolved = result["stations"]
        self.assertEqual(direct["sources"], {
            "media_player.preset": "Radio · 711", "media_player.managed": "711 — Radio"})
        self.assertNotIn("url", resolved)
        self.assertEqual(set(resolved["sources"]), {"media_player.preset", "media_player.managed"})
        self.assertEqual(result["limits"][0]["entities"], ["media_player.preset", "media_player.managed"])
        self.assertEqual(len(result["players"]), 3)

    def test_missing_source_is_never_invented(self):
        result = module.build_console({"stations": {"x": {"name": "New", "extension": "722", "url": "https://example.org/live"}}},
                                      [{"entity": "media_player.preset", "name": "Preset", "caps": 2048, "group": "Phones", "source_list": ["Wrong · 722"]}])
        self.assertEqual(result["stations"][0]["sources"], {})

    def test_phone_missing_source_cannot_fall_back_to_arbitrary_url(self):
        with self.assertRaisesRegex(ValueError, "Refresh phone source inventory"):
            module.build_console(
                {"stations": {"x": {"name": "New", "extension": "722", "url": "https://example.org/live"}}},
                [{"entity": "media_player.phone", "name": "Phone", "caps": 2560,
                  "group": "Phones", "kind": "phone", "source_list": ["Old · 701"]}])


if __name__ == "__main__":
    unittest.main()
