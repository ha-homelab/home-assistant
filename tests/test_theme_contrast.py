"""Keep dark themes and their explicit form colors readable.

This is a static configuration guard, not a replacement for browser checks:
HA supplies most of the palette; the mode check protects that inheritance.
Contrast checks protect explicit Paper/MDC, modern field and editor overrides.
Disabled controls are excluded.
"""

from pathlib import Path
import re
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
DARK_THEMES = {
    "darkblue/darkblue.yaml": "Dark - Blue",
    "darkbluepurple/darkbluepurple.yaml": "Dark - Blue/Purple",
    "darkbluepurple2/darkbluepurple2.yaml": "Dark - Blue/Purple 2",
    "noctis/noctis.yaml": "noctis",
}
LOCAL_THEMES = ("Dark - Blue", "Dark - Blue/Purple", "Dark - Blue/Purple 2")
# These pairs affect enabled field content, including its label and focus state.
# Check only pairs explicitly configured by a theme: unspecified colors belong
# to HA's inherited palette and require the separate live browser verification.
FIELD_COLORS = (
    ("paper-input-color", "paper-input-container-background-color"),
    ("paper-input-container-input-color", "paper-input-container-input-background-color"),
    ("paper-input-container-color", "paper-input-container-background-color"),
    ("input-text-color", "input-background-color"),
    ("input-ink-color", "input-fill-color"),
    ("input-label-ink-color", "input-fill-color"),
    ("mdc-text-field-ink-color", "mdc-text-field-fill-color"),
    ("mdc-text-field-label-ink-color", "mdc-text-field-fill-color"),
    ("mdc-filled-text-field-input-text-color", "mdc-filled-text-field-container-color"),
    ("mdc-filled-text-field-input-text-color", "mdc-filled-text-field-focus-container-color"),
    ("mdc-select-ink-color", "mdc-select-fill-color"),
    ("primary-text-color", "ha-color-form-background"),
)
# HA's current field labels use secondary text at rest and primary color when
# focused. Both label states must remain readable on normal and hover fills.
# The HACS-managed Noctis theme has a known upstream focused-label issue and is
# deliberately not represented as passing these additional local guarantees.
MODERN_FIELD_COLORS = (
    ("primary-color", "ha-color-form-background"),
    ("primary-color", "ha-color-form-background-hover"),
    ("secondary-text-color", "ha-color-form-background"),
    ("secondary-text-color", "ha-color-form-background-hover"),
    ("primary-text-color", "ha-color-form-background-hover"),
)


def effective_properties(theme):
    return theme | theme.get("modes", {}).get("dark", {})


def color(properties, token, seen=()):
    """Resolve local aliases to an opaque sRGB hex color, failing closed.

    These form overrides use hex values or whole-value var() aliases. A new
    syntax or a reference outside the theme needs an explicit test update;
    silently guessing a browser fallback could hide the original defect.
    """
    if token in seen:
        raise ValueError(f"CSS variable cycle: {' -> '.join((*seen, token))}")
    if token not in properties:
        raise ValueError(f"CSS variable is not defined in this theme: {token}")
    value = str(properties[token]).strip()
    alias = re.fullmatch(r"var\(\s*--([\w-]+)\s*\)", value)
    if alias:
        return color(properties, alias[1], (*seen, token))
    if not re.fullmatch(r"#(?:[\da-fA-F]{3}|[\da-fA-F]{6})", value):
        raise ValueError(f"Unsupported opaque form color for {token}: {value!r}")
    digits = value[1:]
    if len(digits) == 3:
        digits = "".join(channel * 2 for channel in digits)
    return tuple(int(digits[index:index + 2], 16) / 255 for index in (0, 2, 4))


def contrast(foreground, background):
    """WCAG relative-luminance contrast for opaque sRGB colors."""
    def luminance(rgb):
        linear = (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
                  for c in rgb)
        return sum(weight * channel for weight, channel in
                   zip((0.2126, 0.7152, 0.0722), linear))

    darker, lighter = sorted((luminance(foreground), luminance(background)))
    return (lighter + 0.05) / (darker + 0.05)


class ThemeContrastTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.themes = {
            name: yaml.safe_load((ROOT / "config/themes" / path).read_text())[name]
            for path, name in DARK_THEMES.items()
        }

    def assert_dark_base(self, theme):
        # With no modes, a user's light preference supplies pale form fills
        # underneath this theme's white foreground overrides.
        self.assertEqual(set(theme.get("modes", {})), {"dark"})
        self.assertIsInstance(theme["modes"]["dark"], dict)

    def assert_readable_pair(self, properties, foreground, background):
        ratio = contrast(color(properties, foreground), color(properties, background))
        self.assertGreaterEqual(ratio, 4.5,
                                f"{foreground} on {background}: {ratio:.3f}:1")

    def test_dark_themes_inherit_only_the_dark_base_palette(self):
        for name, theme in self.themes.items():
            with self.subTest(theme=name):
                self.assert_dark_base(theme)

    def test_explicit_enabled_form_colors_meet_normal_text_contrast(self):
        for name, theme in self.themes.items():
            properties = effective_properties(theme)
            for foreground, background in FIELD_COLORS:
                if foreground not in properties or background not in properties:
                    continue
                with self.subTest(theme=name, foreground=foreground, background=background):
                    self.assert_readable_pair(properties, foreground, background)

    def test_local_modern_fields_are_readable_at_rest_hover_and_focus(self):
        for name in LOCAL_THEMES:
            properties = effective_properties(self.themes[name])
            for foreground, background in MODERN_FIELD_COLORS:
                with self.subTest(theme=name, foreground=foreground, background=background):
                    self.assert_readable_pair(properties, foreground, background)

    def test_local_code_comments_are_readable_on_explicit_editor_backgrounds(self):
        for name in LOCAL_THEMES:
            properties = effective_properties(self.themes[name])
            if "code-editor-background-color" in properties:
                with self.subTest(theme=name):
                    self.assert_readable_pair(properties, "codemirror-comment",
                                              "code-editor-background-color")

    def test_guard_rejects_removing_dark_palette_inheritance(self):
        theme = self.themes["Dark - Blue/Purple"] | {"modes": {}}
        with self.assertRaises(AssertionError):
            self.assert_dark_base(theme)

    def test_guard_rejects_white_text_on_a_light_field(self):
        properties = effective_properties(self.themes["Dark - Blue/Purple"]) | {
            "primary-text-color": "#FFFFFF", "ha-color-form-background": "#F3F3F3",
        }
        with self.assertRaisesRegex(AssertionError, "primary-text-color on ha-color-form-background"):
            self.assert_readable_pair(properties, "primary-text-color", "ha-color-form-background")

    def test_guard_rejects_dark_code_comments_on_a_dark_editor(self):
        properties = effective_properties(self.themes["Dark - Blue/Purple"]) | {
            "codemirror-comment": "#101010",
        }
        with self.assertRaisesRegex(AssertionError, "codemirror-comment on code-editor-background-color"):
            self.assert_readable_pair(properties, "codemirror-comment", "code-editor-background-color")

    def test_contrast_calculation_matches_reference_limits(self):
        black, white, gray = (0, 0, 0), (1, 1, 1), (0.5, 0.5, 0.5)
        self.assertAlmostEqual(contrast(white, black), 21)
        self.assertAlmostEqual(contrast(gray, gray), 1)
        self.assertAlmostEqual(contrast(white, gray), 3.976653, places=6)


if __name__ == "__main__":
    unittest.main()
