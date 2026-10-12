# Lovelace input contrast

## Root cause and fix

`Dark - Blue/Purple` had dark cards and white text, but no `modes` declaration.
Home Assistant therefore based it on the default **light** palette. In HA
2026.9.1, the dashboard title input (`ha-input` / `wa-input`) gets its background
from `--ha-color-form-background`, while its text inherits the theme's white
`--primary-text-color`. The result was white text on `#f3f3f3`.

The theme now declares `modes: {dark: {}}`, so new controls inherit HA's complete
dark palette. This also covers form hover/disabled backgrounds, dropdowns and
other semantic colors without copying a version-specific list of tokens.
The old `app-theme-color-scheme: dark` entry did not select HA's base palette and
was removed. Legacy Paper/MDC text overrides now use the theme's text colors
instead of black on their existing dark input backgrounds.

See Home Assistant's [dark mode documentation](https://www.home-assistant.io/integrations/frontend/#dark-mode-support).
Changing only `input-fill-color`, `paper-input-*` or `mdc-text-field-*` does not
fix the current `ha-input` background.

## Apply and verify

1. Back up `themes/darkbluepurple/darkbluepurple.yaml` privately and compare the
   live hash with the expected source before replacing just this file.
2. Run `python3 tools/validate.py` and `git diff --check`.
3. Call `frontend.reload_themes`. No HA restart or automation reload is needed.
4. In Lovelace, open **Edit dashboard → Edit title**. Inspect the actual input,
   its background, focused state, and the icon picker/search. Close without
   updating the dashboard. Repeat after reloading the browser page.

Verified in the running HA 2026.9.1 installation on 2026-10-08:

- Before: `#ffffff` text on `#f3f3f3`, contrast **1.11:1**.
- After: `#ffffff` text on `#363636`, contrast **12.08:1**.
- Hover/focus check: `#ffffff` on `#4a4a4a`, contrast **8.86:1**.
- Icon selection and its search field were readable; the fix survived a full
  browser reload. The title stayed `Overview`; no dashboard content was saved.

These measurements describe the initial fix. The follow-up below improves the
focus labels, placeholders and editor comments as well. If an already-open
client still shows old colors, reload the page. Do not keep adding obsolete
input variables to mask a missing mode.

## Follow-up: labels, placeholders and YAML comments

All three locally managed themes (`Dark - Blue`, `Dark - Blue/Purple`, and
`Dark - Blue/Purple 2`) now declare the dark base. Their current form fills are
`#080D18` at rest and `#0D1220` on hover. This darker inset keeps the existing
blue focused labels and gray placeholders readable without changing global
primary colors or button styling. Installed frontend `20260826.6` uses
`primary-color` for focused material input/textarea labels and
`ha-color-neutral-60` for input placeholders; it exposes no separate theme
variable for the focused label.

For the least contrasting blue (`#007AFF`), the resulting contrast is
**4.84:1 at rest / 4.65:1 on hover**. Inherited placeholders (`#989898`) reach
**6.73:1 / 6.47:1**, and white input text reaches **19.42:1 / 18.68:1**.
Purple 2's legacy label was also raised from 4.29:1 to 4.59:1 on its existing
legacy field fill. Its separate black-on-light MDC palette was already readable
and remains intact.

The three local themes set `codemirror-comment: '#BAC0C6'`. Previously the
inherited dark comment color `#545454` reached only **2.27:1** on the active
editor background. The new color reaches **9.35:1**. Actual browser verification
covered the focused title label, typed mixed text/numbers, placeholder style,
and a YAML comment alongside property/string syntax in an unsaved Markdown card
preview. The preview was cancelled; dashboard content was not changed.

Run the regression guard with:

```bash
python3 -m unittest discover -s tests -p test_theme_contrast.py -v
```

The eight tests verify dark-mode inheritance for all four installed themes,
explicit enabled legacy field pairs, modern normal/hover/focus pairs for the
three local themes, and comments where an editor background is explicitly
configured. Negative cases demonstrate that a missing mode, white-on-light
field and dark-on-dark comment are rejected. Normal-text pairs require at least
**4.5:1**. Existing CI discovers these tests automatically.

This is a configuration guard, not a full accessibility certification or a
replacement for browser checks after HA upgrades. Inherited colors, disabled
controls and arbitrary community cards are outside its contrast guarantee.
Only the active theme received the live browser checks; alternate local themes
were validated through their explicit color pairs and installed theme schema.

## Ownership

Edit the three local themes through this repository. HACS metadata confirms
they are not HACS-managed, so a HACS theme update does not overwrite them.
`noctis` is managed by `aFFekopp/noctis` and remains unchanged. It already has a
dark base, but its upstream focus colors are outside the local modern-field
guarantee. Do not disable HACS maintenance to protect a locally managed theme.

## Deployment and rollback

This was a guarded, single-theme repair, not a full root configuration release.
The original file is retained on the HA volume at
`/config/.theme-backups/20261008-lovelace-contrast/darkbluepurple.yaml` and in a
private off-box snapshot. Source and installed hashes matched after replacement.
To roll back, restore that file only if the live theme has not since changed,
then call `frontend.reload_themes` again.

The follow-up also has private off-box snapshots, hash receipts and on-volume
backups under `/config/.theme-backups/20261008-contrast-hardening/`, one YAML file
per local theme. All three pre-installation hashes were checked before any file
was replaced. Only themes were reloaded; the backend-selected theme and dashboard
configuration were retained.
