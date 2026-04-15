# QStoryMap (QGIS Plugin)

**QStoryMap** exports your QGIS project layers (**vector + raster**) to a **static story map website** (Leaflet).  
It works **without GeoServer**: layers are exported as local **XYZ tiles** (recommended) or as single image overlays.

Optional **Story** sections create an ArcGIS-style side panel. Each section stores a **focus point + zoom** (picked from the QGIS map) and the web map **flies** to that view while scrolling.

---

## Table of contents

1. [What it does](#what-it-does)
2. [Requirements](#requirements)
3. [Installation](#installation)
4. [How to use](#how-to-use)
5. [Export output (what gets created)](#export-output-what-gets-created)
6. [Manifest format](#manifest-format)
7. [Testing](#testing)
8. [GitHub token (Publish to Pages)](#github-token-publish-to-pages)
9. [Deployment](#deployment)
10. [Troubleshooting](#troubleshooting)
11. [Project layout](#project-layout)
12. [Limitations (MVP)](#limitations-mvp)
13. [License](#license)

---

## What it does

- Adds **Web → QStoryMap…** (and a toolbar button on the **Web** toolbar) inside QGIS.
- **Layer list** includes all **vector** and **raster** layers in the project. **Move up / Move down** changes **draw order** (later items draw on top in the web map). **Checked** layers are exported, in list order.
- **Export** writes:
  - **Tiles mode (recommended)**: `tiles/<layer>/<z>/<x>/<y>.png`
  - **Image mode**: `images/<layer>.png`
  - `manifest.json`
  - optional `legend.json` + `sld/*.sld` (legend is built client-side from SLD)
  - optional `story.json` (side-panel story sections)
- The generated site is fully static. Open it with a local web server (or publish to GitHub Pages).

---

## Requirements

| Item | Details |
|------|---------|
| **QGIS** | **3.22** or newer (see `storymap_builder/metadata.txt`). |
| **Layers** | **QgsVectorLayer** and **QgsRasterLayer** instances in the project. |
| **Network** | The **exported site** loads Leaflet and OSM tiles from the public internet. |
| **Python** | QGIS’s bundled Python and **PyQGIS** only; no extra pip packages. |

---

## Installation

The installable unit is the folder **`storymap_builder/`** (it must contain `metadata.txt` at its root).

### Method A — Install from ZIP (recommended)

1. Ensure your ZIP layout is correct. The first level inside the ZIP **must** be the `storymap_builder` folder, for example:

   ```text
   my-plugin.zip
   └── storymap_builder/
       ├── metadata.txt
       ├── __init__.py
       ├── storymap_builder.py
       ├── storymap_dialog.py
       ├── export_engine.py
       ├── image_export.py
       ├── style_export.py
       ├── github_publish.py
       ├── github_settings.py
       ├── legend_export.py
       ├── icon.svg
       └── templates/
           ├── index.html
           ├── style.css
           └── app.js
   ```

2. In QGIS: **Plugins → Manage and Install Plugins… → Install from ZIP**.
3. Select the ZIP file, install, and enable **QStoryMap** on the **Installed** tab if needed.

### Method B — Copy into the QGIS plugins directory

Typical profile paths:

- **macOS:** `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/`
- **Windows:** `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\`
- **Linux:** `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`

Copy the **`storymap_builder`** folder there and restart QGIS (or enable the plugin).

### Method C — Development

Symlink your development **`storymap_builder`** into `python/plugins/storymap_builder` and reload QGIS or use a plugin reloader.

---

## How to use

1. Open a QGIS project with vector and/or raster layers.
2. **Web → QStoryMap…**
3. On the **Export** tab: set **story title** and **output folder** (prefer a new, empty folder).
4. (Recommended) Keep **Enable tiling (XYZ)** checked and choose **Min zoom** / **Max zoom**.
   - **Important**: a large **Max zoom** creates many more tiles and can take a long time to export.
5. **Reorder** layers with **Move up / Move down**; **check** layers to export.
6. Click **OK**.

---

## Export output (what gets created)

| Path | Purpose |
|------|---------|
| `index.html`, `style.css`, `app.js` | Static story map UI |
| `manifest.json` | **`version`: 3** — title, ordered **`layers`**, optional **`legend`** path |
| `legend.json` | Legend metadata per layer (references **`sld/<slug>.sld`**; the page parses SLD for display) |
| `sld/*.sld` | Exported QGIS style as SLD (one per layer) |
| `story.json` | Side-panel story sections (focus point + zoom; referenced by `manifest.json` as `story`) |
| `tiles/<layer>/<z>/<x>/<y>.png` | Local XYZ tiles when tiling is enabled (sharp when zooming) |
| `images/*.png` | One **transparent PNG** per layer (extent and resolution chosen per layer type in `image_export.py`) |

Slugs are derived from layer names; duplicates get numeric suffixes.

---

## Manifest format

- **`version`**: **`3`** (with **`legend`**) or **`2`** / missing for older packages.
- Each **`layers[]`** item: **`type`** `vector` | `raster`, **`order`**, **`id`** (slug).
- **Current export (tiles)**: `renderMode`: `tiles`, **`tilesUrl`** `tiles/<id>/{z}/{x}/{y}.png`, **`minZoom`**, **`maxZoom`**, optional **`tileCount`**, plus **`bbox`** `[minLon, minLat, maxLon, maxLat]`.
- **Current export (image)**: `renderMode`: `image`, **`image`** (path relative to the site root), **`bbox`** `[minLon, minLat, maxLon, maxLat]`, optional **`imageWidth`** / **`imageHeight`**, **`opacity`**.
- **Legacy** manifests may still list **`file`** (GeoJSON), **`styleTilesUrl`** (`renderMode`: `qgis`), or **`tilesUrl`** for XYZ rasters; the bundled `app.js` still attempts to render those if present.
- **`legend.json`**: top-level **`layers`** array; each entry has only **`id`**, **`name`**, **`type`** (`vector` | `raster`), and **`sld`** (path like `sld/<slug>.sld`). The page fetches each SLD and builds legend rows in the browser.
- **`story.json`**: top-level `sections` array; each section includes `title`, `body`, `center: [lon, lat]`, and `zoom`. The web map “flies” to that view on scroll.

---

## Testing

### In QGIS

1. Export a project with a **small vector** and/or **raster** layer and confirm PNGs, manifest, and story sections.

### Local web server

Browsers often block `fetch()` on `file://`. From the export folder:

```bash
python3 -m http.server 8000
```

Open **http://localhost:8000/**.

### Browser checks

- OSM basemap loads.
- Story scroll updates the map extent.
- Image overlays align with the basemap (bbox in WGS 84).

---

## GitHub token (Publish to Pages)

The **Publish** tab can upload your export folder to a GitHub repository over HTTPS. You need a **personal access token** (not your GitHub account password).

### Option A — Classic token (simplest)

1. In a browser, sign in to [GitHub](https://github.com) and open your profile menu (top right) → **Settings**.
2. In the left sidebar, scroll to the bottom and click **Developer settings**.
3. Click **Personal access tokens** → **Tokens (classic)**.
4. Click **Generate new token** → **Generate new token (classic)**.
5. Enter a **Note** (for example `QStoryMap QGIS`).
6. Set an **Expiration** (GitHub may require one; shorter is safer).
7. Enable the **`repo`** scope (full control of private repositories). This is enough for the plugin to create or update files in repositories your account can access.
8. Click **Generate token** at the bottom.
9. **Copy the token immediately** — GitHub shows it only once. If you lose it, generate a new token.
10. In QGIS, open **Web → QStoryMap…** → **Publish** tab → paste the value into **Token**.

### Option B — Fine-grained token

1. **Settings** → **Developer settings** → **Personal access tokens** → **Fine-grained tokens** → **Generate new token**.
2. Choose the **Resource owner** (your user or an organization) and, under **Repository access**, select **Only select repositories** and pick the repo you will publish to (or **All** if appropriate).
3. Under **Repository permissions**, set **Contents** to **Read and write**.
4. Generate the token, copy it once, and paste it into the **Publish** tab in QStoryMap.

### Security notes

- Treat the token like a password. Do not paste it into public issues or commit it into a repository.
- The plugin can optionally **remember the token** in QGIS `QSettings` as **plain text** on this machine — use only on trusted computers.
- After publishing, enable **GitHub Pages** on the repository (**Settings → Pages**): choose your branch (often `gh-pages`) and the **`/` (root)** folder. Your site URL will look like `https://YOURUSER.github.io/REPONAME/` for a project site.

---

## Deployment

The site is fully **static**. Upload the **entire** export directory (including `legend/` and `images/` when present) preserving paths, or use the **Publish** tab to push to GitHub after export.

---

## Troubleshooting

| Problem | What to try |
|---------|-------------|
| Image export failed | Check the QGIS message bar; ensure the layer has a valid extent and CRS. |
| `file://` blank page | Use **`python3 -m http.server`**. |
| Wrong map position | Fix layer CRS and extent in QGIS; bbox in the manifest is WGS 84. |
| Blurry overlay | Exports are finite resolution: vectors use up to **4096 px** on the long edge; small rasters are **supersampled** to at least **2048 px** on the long edge (see `render_layer_to_png` in `image_export.py`). Raise `max_vector_dim` / `min_raster_dim` there if you need more detail (larger files, slower export). |

---

## Project layout

```text
.
├── README.md
└── storymap_builder/
    ├── metadata.txt
    ├── __init__.py
    ├── storymap_builder.py   # Plugin entry
    ├── storymap_dialog.py    # UI
    ├── core/
    │   ├── __init__.py
    │   ├── export_engine.py  # Orchestrates export + manifest
    │   ├── image_export.py   # QGIS map render → PNG
    │   ├── tile_export.py    # XYZ tile export
    │   └── legend_export.py  # legend.json + SLD export
    ├── publish/
    │   ├── __init__.py
    │   ├── github_publish.py
    │   └── github_settings.py
    ├── style_export.py       # (optional) legacy vector styling helper
    ├── icon.svg
    └── templates/
        ├── index.html
        ├── style.css
        └── app.js
```

---

## Limitations (MVP)

- **Image overlays** are not interactive (no attribute popups on the PNG path).
- **Resolution** is bounded for performance; very large rasters are downsampled.
- **Legend** reflects the layer; complex renderers may be summarized generically.
- Story copy is **auto-generated** per layer, not a full CMS.

---

## Version

Plugin version **0.1.0** — see `storymap_builder/metadata.txt`.
