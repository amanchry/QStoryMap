# Changelog

## [0.3.0] — 2026-04-23

### Changed
- **GitHub publish — git-based push:** replaced the per-file Contents API approach with a local `git init` / `git push --force`, making large tile exports publish in seconds instead of minutes.
- **Session persistence:** dialog state (layer selections, story content, zoom levels) is now kept in memory for the lifetime of the current QGIS project. Closing and reopening the dialog preserves all settings. State is cleared when a new or different project is opened.
- **Story — auto-capture zoom from map:** "Pick focus point" now also reads the current QGIS canvas scale and converts it to the equivalent Leaflet zoom level, pre-filling the Zoom field automatically.
- **Publish tab — simplified:** removed the separate "Remember GitHub token" checkbox; the single "Remember GitHub settings (including token)" checkbox saves everything together.
- **First tab renamed:** "Export" → "Layers" for clarity.

### Docs
- **`metadata.txt`:** expanded `about` section with feature highlights and a live example link.
- **README:** added "Install from QGIS Plugin Manager" as the recommended (first) installation method.
- **README:** added note that GitHub Pages can take ~5 minutes to go live after the first publish.

## [0.2.2] — 2026-04-17

- **`icon.png`:** add a 256×256 raster icon (exported from `icon.svg`) and set `metadata.txt` `icon=icon.png` for clearer display where PNG is preferred.

## [0.2.1] — 2026-04-16

- **`metadata.txt`:** set `icon=icon.svg` so QGIS and the plugin repository use the packaged icon (not the default placeholder).

## [0.2.0] — 2026-04-16

- **Bandit B310:** GitHub requests no longer use bare `urlopen` on unchecked URLs; only `https://` via a restricted opener.
- **detect-secrets:** Leaflet CDN SRI `integrity` attributes removed from `templates/index.html` (false “high entropy secret” flags).
- **GitHub failures:** API errors show short text instead of full HTML error pages; repo auto-create retries on **502 / 503 / 504**.

## [0.1.0] — 2026-04-16

- First release: static Leaflet export (images / optional XYZ tiles), SLD legend, optional story, GitHub Pages upload, saved GitHub fields.
