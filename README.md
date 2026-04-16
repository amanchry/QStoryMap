# QStoryMap Plugin

**QStoryMap** is a free, open‑source QGIS plugin that exports QGIS project’s **vector and raster layers** into a **static Leaflet story map website**.

- **No server required**: exports layers as local **XYZ tiles** (and/or static images, depending on settings).
- **Story sections**: optional narrative sections that guide readers through the map.
- **One‑click publishing (optional)**: publish your story map directly to GitHub Pages from QGIS.

---

## Table of contents

1. [Example story map](#example-story-map)
2. [Installation](#installation)
3. [How to use](#how-to-use)
4. [Tips for export](#tips-for-export)
5. [Publish to GitHub Pages](#publish-to-github-pages)
6. [License](#license)

---

## Example story map

**[Kenya health access](https://amanchry.github.io/kenya-health-access/)** is a live example of what you can publish with QStoryMap — **directly from QGIS** using this plugin.

[![Kenya health access — story map preview](assets/example_thumb.png)](https://amanchry.github.io/kenya-health-access/)

---

## Installation

### Method A — Install from ZIP 

1. Download this repository as a ZIP.
2. Ensure your ZIP layout is correct. The first level inside the ZIP **must** be `metadata.txt` (and the rest of the plugin files next to it). 
3. In QGIS: **Plugins → Manage and Install Plugins… → Install from ZIP**.
4. Select the ZIP file, install, and enable **QStoryMap** on the **Installed** tab if needed.

### Method B — Copy into the QGIS plugins directory

Typical profile paths:

- **macOS:** `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/`
- **Windows:** `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\`
- **Linux:** `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`

Copy the **QStoryMap** plugin folder (the one that contains `metadata.txt`) into `plugins/` and restart QGIS (or enable the plugin).


---

## How to use

1. In QGIS, open **Web → QStoryMap…**
2. In the **Export** tab:
   - Select the layers you want to export (vector and/or raster).
   - Choose **image export** (fast) or **XYZ tiling** (better quality at higher zooms).
   - If tiling is enabled, set **min/max zoom** (max supported is **20**) and **tile size**.
3. (Optional) In the **Story** tab:
   - Enable **Export story**
   - Add/remove sections and write your narrative
4. (Optional) In the **Publish** tab, set your GitHub settings if you want to publish to GitHub Pages.
5. Click **OK / Export**, pick an output folder.

### Tips for export

- **Min/max zoom**: choose the range carefully. A **higher maximum zoom** creates many more tiles and the export can take **a long time** (especially with tiling enabled).
- **Zoom vs. area**: pick zoom levels that match your **area of interest**. Large map extents at high zoom multiply the number of tiles very quickly.
- **Layer order**: the order in the layer list is the **draw order** on the web map — the **top layer in the list** is drawn **on top**.

## Publish to GitHub Pages

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


- After setting credentials, choose the repo and branch (often `gh-pages`) and the **`/` (root)** folder. Your site URL will look like `https://YOURUSER.github.io/REPONAME/` for a project site.




---

## License

This project is licensed under the terms in `LICENSE`.
