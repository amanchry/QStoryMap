"""Export dialog for QStoryMap — export to static images and optional GitHub publish."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsProject,
    QgsRasterLayer,
    QgsVectorLayer,
)
from qgis.gui import QgsMapToolEmitPoint
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QApplication
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .core.export_engine import export_story_map
from .publish.github_publish import GitHubPagesConfig, publish_folder_to_github_pages
from .publish.github_settings import load_github_settings, save_github_settings

ROLE_LAYER_ID = Qt.UserRole
ROLE_LAYER_KIND = Qt.UserRole + 1
ROLE_LAYER_SETTINGS = Qt.UserRole + 2
ROLE_STORY_SECTION_KEY = Qt.UserRole + 3


def _section_key_for_layer(layer_id: str) -> str:
    return f"layer:{layer_id}"


def _is_layer_section_key(key: str) -> bool:
    return isinstance(key, str) and key.startswith("layer:")


def _layer_id_from_section_key(key: str) -> str | None:
    if not _is_layer_section_key(key):
        return None
    return key.split("layer:", 1)[1] or None


def _new_custom_section_key() -> str:
    return f"sec:{uuid4().hex[:10]}"


class LayerTileSettingsDialog(QDialog):
    def __init__(self, *, parent=None, min_zoom: int, max_zoom: int, tile_size: int, clip_to_aoi: bool):
        super().__init__(parent)
        self.setWindowTitle("Layer tile settings")
        self.setMinimumWidth(320)

        self.min_zoom = QSpinBox()
        self.min_zoom.setRange(0, 20)
        self.min_zoom.setValue(int(min_zoom))

        self.max_zoom = QSpinBox()
        self.max_zoom.setRange(0, 20)
        self.max_zoom.setValue(int(max_zoom))

        self.tile_size = QComboBox()
        self.tile_size.addItem("256", 256)
        self.tile_size.addItem("512", 512)
        idx = 0 if int(tile_size) <= 256 else 1
        self.tile_size.setCurrentIndex(idx)

        self.clip_to_aoi = QCheckBox("Only export within AOI (map canvas extent)")
        self.clip_to_aoi.setChecked(bool(clip_to_aoi))

        warn = QLabel("Higher max zoom creates many more tiles and can take a long time to export.")
        warn.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Min zoom", self.min_zoom)
        form.addRow("Max zoom", self.max_zoom)
        form.addRow("Tile size", self.tile_size)
        form.addRow(self.clip_to_aoi)
        form.addRow(warn)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(buttons)

    def value(self) -> dict:
        return {
            "min_zoom": int(self.min_zoom.value()),
            "max_zoom": int(self.max_zoom.value()),
            "tile_size": int(self.tile_size.currentData()),
            "clip_to_aoi": bool(self.clip_to_aoi.isChecked()),
        }


class QStoryMapDialog(QDialog):
    def __init__(self, plugin_dir: Path, iface, parent=None):
        super().__init__(parent)
        self.plugin_dir = Path(plugin_dir)
        self.iface = iface
        self.setWindowTitle("QStoryMap")
        self.setMinimumWidth(580)
        self.setMinimumHeight(520)

        tabs = QTabWidget()

        # --- Export tab ---
        tab_export = QWidget()
        export_layout = QVBoxLayout(tab_export)

        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Story title")
        proj = QgsProject.instance()
        self.title_edit.setText(proj.title() or "My story map")

        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("Choose output folder…")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_output)
        out_row = QHBoxLayout()
        out_row.addWidget(self.out_edit)
        out_row.addWidget(browse)

        layer_header = QHBoxLayout()
        layer_header.addWidget(QLabel("Layers (order = draw order; later on top)"))
        self.btn_up = QPushButton("Move up")
        self.btn_down = QPushButton("Move down")
        self.btn_layer_settings = QPushButton("Layer settings…")
        self.btn_up.clicked.connect(self._move_up)
        self.btn_down.clicked.connect(self._move_down)
        self.btn_layer_settings.clicked.connect(self._edit_layer_settings)
        layer_header.addWidget(self.btn_up)
        layer_header.addWidget(self.btn_down)
        layer_header.addWidget(self.btn_layer_settings)
        layer_header.addStretch()

        self.layer_list = QListWidget()
        self._populate_layers()

        export_hint = QLabel(
            "Checked layers are exported to story map."
        )
        export_hint.setWordWrap(True)

        self.enable_tiles = QCheckBox("Enable tiling (XYZ) for sharper zooming")
        self.enable_tiles.setChecked(True)

        self.min_zoom = QSpinBox()
        self.min_zoom.setRange(0, 20)
        self.min_zoom.setValue(0)
        self.max_zoom = QSpinBox()
        self.max_zoom.setRange(0, 20)
        self.max_zoom.setValue(10)

        self.default_tile_size = QComboBox()
        self.default_tile_size.addItem("256", 256)
        self.default_tile_size.addItem("512", 512)
        self.default_tile_size.setCurrentIndex(0)

        tiles_warn = QLabel(
            "Higher max zoom creates many more tiles and can take a long time to export.\n"
            "Example: zoom 0–10 is manageable; zoom 0–14 can be very slow for large extents."
        )
        tiles_warn.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Story title", self.title_edit)
        form.addRow("Output folder", out_row)
        form.addRow(self.enable_tiles)
        form.addRow("Min zoom", self.min_zoom)
        form.addRow("Max zoom", self.max_zoom)
        form.addRow("Tile size", self.default_tile_size)
        form.addRow(tiles_warn)

        export_layout.addWidget(export_hint)
        export_layout.addLayout(form)
        export_layout.addLayout(layer_header)
        export_layout.addWidget(self.layer_list, stretch=1)

        tabs.addTab(tab_export, "Export")

        # --- Story tab ---
        tab_story = QWidget()
        story_layout = QVBoxLayout(tab_story)

        story_hint = QLabel("Create story sections shown in the side panel.")
        story_hint.setWordWrap(True)

        self.export_story = QCheckBox("Export story")
        self.export_story.setChecked(False)

        story_btn_row = QHBoxLayout()
        self.btn_story_add = QPushButton("Add section")
        self.btn_story_remove = QPushButton("Remove section")
        self.btn_story_add.clicked.connect(self._story_add_section)
        self.btn_story_remove.clicked.connect(self._story_remove_section)
        story_btn_row.addWidget(self.btn_story_add)
        story_btn_row.addWidget(self.btn_story_remove)
        story_btn_row.addStretch()

        row = QHBoxLayout()
        self.story_list = QListWidget()
        self.story_list.currentItemChanged.connect(self._story_select)

        editor = QVBoxLayout()
        self.story_title = QLineEdit()
        self.story_title.setPlaceholderText("Section title")
        self.story_body = QTextEdit()
        self.story_body.setPlaceholderText("Section text")
        self.story_pick = QPushButton("Pick focus point on map…")
        self.story_pick.clicked.connect(self._story_pick_point)
        self.story_center = QLineEdit()
        self.story_center.setReadOnly(True)
        self.story_center.setPlaceholderText("No focus point selected")
        self.story_zoom = QSpinBox()
        self.story_zoom.setRange(0, 20)
        self.story_zoom.setValue(12)
        zoom_row = QHBoxLayout()
        zoom_row.addWidget(QLabel("Zoom"))
        zoom_row.addWidget(self.story_zoom)
        zoom_row.addStretch()

        btn_save = QPushButton("Save section")
        btn_save.clicked.connect(self._story_save_current)

        editor.addWidget(QLabel("Focus point"))
        editor.addWidget(self.story_pick)
        editor.addWidget(self.story_center)
        editor.addWidget(QLabel("Title"))
        editor.addWidget(self.story_title)
        editor.addWidget(QLabel("Text"))
        editor.addWidget(self.story_body, stretch=1)
        editor.addLayout(zoom_row)
        editor.addWidget(btn_save)

        row.addWidget(self.story_list, stretch=1)
        ed_wrap = QWidget()
        ed_wrap.setLayout(editor)
        row.addWidget(ed_wrap, stretch=2)

        story_layout.addWidget(story_hint)
        story_layout.addWidget(self.export_story)
        story_layout.addLayout(story_btn_row)
        story_layout.addLayout(row, stretch=1)

        tabs.addTab(tab_story, "Story")

        # --- Publish tab (GitHub Pages) ---
        tab_pub = QWidget()
        pub_layout = QVBoxLayout(tab_pub)

        pub_intro = QLabel(
            "After a successful export, you can host the output folder to GitHub Pages."
            "(needs GitHub account and personal access token)."
        )
        pub_intro.setWordWrap(True)

        self.gh_publish_after = QCheckBox("Host exported story-map to GitHub Pages")
        self.gh_publish_after.setChecked(False)

        pub_form = QFormLayout()
        self.gh_owner = QLineEdit()
        self.gh_owner.setPlaceholderText("GitHub username or organization")
        self.gh_repo = QLineEdit()
        self.gh_repo.setPlaceholderText("repository name (e.g. my-storymap)")
        self.gh_branch = QLineEdit()
        self.gh_branch.setPlaceholderText("gh-pages")
        self.gh_branch.setText("gh-pages")
        self.gh_token = QLineEdit()
        self.gh_token.setPlaceholderText("Personal access token (classic: repo scope)")
        self.gh_token.setEchoMode(QLineEdit.Password)

        pub_form.addRow("Owner", self.gh_owner)
        pub_form.addRow("Repository", self.gh_repo)
        pub_form.addRow("Branch", self.gh_branch)
        pub_form.addRow("Token", self.gh_token)

        self.gh_create_repo = QCheckBox("Create repository if it does not exist (owner must be your user login)")
        self.gh_create_repo.setChecked(False)

        self.gh_remember = QCheckBox("Remember GitHub settings")
        self.gh_remember_token = QCheckBox("Remember GitHub token")
        self.gh_remember_token.setChecked(False)

        pub_layout.addWidget(pub_intro)
        pub_layout.addWidget(self.gh_publish_after)
        pub_layout.addLayout(pub_form)
        pub_layout.addWidget(self.gh_create_repo)
        pub_layout.addWidget(self.gh_remember)
        pub_layout.addWidget(self.gh_remember_token)
        pub_layout.addStretch()

        tabs.addTab(tab_pub, "Publish")

        self._load_saved_github()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._export)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addWidget(tabs)
        root.addWidget(buttons)

        self._story_data: dict[str, dict] = {}
        self._point_tool: QgsMapToolEmitPoint | None = None
        self._prev_tool = None
        self._populate_story_sections()

    def _populate_layers(self):
        self.layer_list.clear()
        project = QgsProject.instance()
        for lid, layer in project.mapLayers().items():
            if isinstance(layer, QgsVectorLayer):
                item = QListWidgetItem(f"Vector: {layer.name()}")
                item.setData(ROLE_LAYER_ID, lid)
                item.setData(ROLE_LAYER_KIND, "vector")
            elif isinstance(layer, QgsRasterLayer):
                item = QListWidgetItem(f"Raster: {layer.name()}")
                item.setData(ROLE_LAYER_ID, lid)
                item.setData(ROLE_LAYER_KIND, "raster")
            else:
                continue
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            item.setData(ROLE_LAYER_SETTINGS, None)
            self.layer_list.addItem(item)

    def _populate_story_sections(self):
        # Default: Introduction only. Users can add/remove custom sections.
        self.story_list.clear()
        self._story_data.setdefault(
            "intro",
            {"key": "intro", "title": "Introduction", "body": "", "center": None, "zoom": 12},
        )

        intro = QListWidgetItem("Intro")
        intro.setData(ROLE_STORY_SECTION_KEY, "intro")
        self.story_list.addItem(intro)

        if self.story_list.count():
            self.story_list.setCurrentRow(0)

    def _story_add_section(self):
        key = _new_custom_section_key()
        self._story_data[key] = {"key": key, "title": "New section", "body": "", "center": None, "zoom": 12}
        item = QListWidgetItem("Section")
        item.setData(ROLE_STORY_SECTION_KEY, key)
        self.story_list.addItem(item)
        self.story_list.setCurrentItem(item)

    def _story_remove_section(self):
        item = self.story_list.currentItem()
        if item is None:
            return
        key = item.data(ROLE_STORY_SECTION_KEY)
        if key == "intro":
            QMessageBox.information(self, "QStoryMap", "Introduction section cannot be removed.")
            return
        row = self.story_list.row(item)
        self.story_list.takeItem(row)
        try:
            self._story_data.pop(key, None)
        except Exception:
            pass
        if self.story_list.count():
            self.story_list.setCurrentRow(max(0, row - 1))

    def _story_select(self, cur, prev):
        self._story_save_item(prev)
        self._story_load_item(cur)

    def _story_save_item(self, item):
        if item is None:
            return
        key = item.data(ROLE_STORY_SECTION_KEY)
        if not key:
            return
        self._story_data[key] = {
            "key": key,
            "title": self.story_title.text().strip(),
            "body": self.story_body.toPlainText().strip(),
            "center": (self._story_data.get(key) or {}).get("center"),
            "zoom": int(self.story_zoom.value()),
        }

    def _story_load_item(self, item):
        if item is None:
            return
        key = item.data(ROLE_STORY_SECTION_KEY)
        if not key:
            return
        d = self._story_data.get(key) or {}
        self.story_title.setText(d.get("title") or "")
        self.story_body.setPlainText(d.get("body") or "")
        self.story_zoom.setValue(int(d.get("zoom") or 12))
        c = d.get("center")
        if isinstance(c, (list, tuple)) and len(c) == 2:
            self.story_center.setText(f"Lon {c[0]:.6f}, Lat {c[1]:.6f}")
        else:
            self.story_center.setText("")

        # Intro/outro shouldn't default-focus
        if key in ("intro",):
            self.story_pick.setEnabled(False)
            self.story_zoom.setEnabled(True)
        else:
            self.story_pick.setEnabled(True)
            self.story_zoom.setEnabled(True)

    def _story_save_current(self):
        self._story_save_item(self.story_list.currentItem())

    def _move_up(self):
        row = self.layer_list.currentRow()
        if row <= 0:
            return
        item = self.layer_list.takeItem(row)
        self.layer_list.insertItem(row - 1, item)
        self.layer_list.setCurrentRow(row - 1)

    def _move_down(self):
        row = self.layer_list.currentRow()
        if row < 0 or row >= self.layer_list.count() - 1:
            return
        item = self.layer_list.takeItem(row)
        self.layer_list.insertItem(row + 1, item)
        self.layer_list.setCurrentRow(row + 1)

    def _story_pick_point(self):
        # Activate a temporary point-pick tool on the QGIS map canvas.
        try:
            canvas = self.iface.mapCanvas()
            if canvas is None:
                return
            # Hide dialog so canvas receives clicks even on some platforms/window managers.
            try:
                self.hide()
            except Exception:
                pass
            self._prev_tool = canvas.mapTool()
            self._point_tool = QgsMapToolEmitPoint(canvas)

            def _picked(pt, button):
                try:
                    if button != Qt.LeftButton:
                        return
                    # Transform to WGS84
                    src = canvas.mapSettings().destinationCrs()
                    wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
                    xform = QgsCoordinateTransform(src, wgs84, QgsProject.instance())
                    ll = xform.transform(pt)
                    lon, lat = float(ll.x()), float(ll.y())
                    item = self.story_list.currentItem()
                    if item is None:
                        return
                    key = item.data(ROLE_STORY_SECTION_KEY)
                    if not key or key == "intro":
                        return
                    d = self._story_data.get(key) or {}
                    d["center"] = [lon, lat]
                    self._story_data[key] = d
                    self.story_center.setText(f"Lon {lon:.6f}, Lat {lat:.6f}")
                finally:
                    # Restore tool
                    try:
                        canvas.setMapTool(self._prev_tool) if self._prev_tool else canvas.unsetMapTool(self._point_tool)
                    except Exception:
                        pass
                    try:
                        self.show()
                        self.raise_()
                        self.activateWindow()
                    except Exception:
                        pass

            self._point_tool.canvasClicked.connect(_picked)
            canvas.setMapTool(self._point_tool)
            try:
                canvas.setFocus()
            except Exception:
                pass
        except Exception:
            return

    def _browse_output(self):
        path = QFileDialog.getExistingDirectory(self, "QStoryMap export folder")
        if path:
            self.out_edit.setText(path)

    def _build_export_items(self) -> list[dict]:
        entries: list[dict] = []
        for i in range(self.layer_list.count()):
            item = self.layer_list.item(i)
            if item.checkState() != Qt.Checked:
                continue
            lid = item.data(ROLE_LAYER_ID)
            kind = item.data(ROLE_LAYER_KIND)
            settings = item.data(ROLE_LAYER_SETTINGS) or {}
            entries.append({"layer_id": lid, "type": kind, "tile": settings})
        return entries

    def _edit_layer_settings(self):
        row = self.layer_list.currentRow()
        if row < 0:
            QMessageBox.information(self, "QStoryMap", "Select a layer first.")
            return
        item = self.layer_list.item(row)
        if item is None:
            return
        cur = item.data(ROLE_LAYER_SETTINGS) or {}
        dlg = LayerTileSettingsDialog(
            parent=self,
            min_zoom=int(cur.get("min_zoom", self.min_zoom.value())),
            max_zoom=int(cur.get("max_zoom", self.max_zoom.value())),
            tile_size=int(cur.get("tile_size", int(self.default_tile_size.currentData()))),
            clip_to_aoi=bool(cur.get("clip_to_aoi", False)),
        )
        if dlg.exec() == QDialog.Accepted:
            item.setData(ROLE_LAYER_SETTINGS, dlg.value())

    def _aoi_bbox_wgs84(self) -> list[float] | None:
        """Map canvas extent as [minx,miny,maxx,maxy] in EPSG:4326."""
        try:
            canvas = self.iface.mapCanvas()
            if canvas is None:
                return None
            ext = canvas.extent()
            if ext is None or ext.isEmpty() or not ext.isFinite():
                return None
            src = canvas.mapSettings().destinationCrs()
            wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
            xform = QgsCoordinateTransform(src, wgs84, QgsProject.instance())
            e = xform.transformBoundingBox(ext)
            if e.isEmpty() or not e.isFinite():
                return None
            return [e.xMinimum(), e.yMinimum(), e.xMaximum(), e.yMaximum()]
        except Exception:
            return None

    def _export(self):
        out_path = self.out_edit.text().strip()
        if not out_path:
            QMessageBox.warning(self, "QStoryMap", "Choose an output folder.")
            return

        items = self._build_export_items()
        if not items:
            QMessageBox.warning(self, "QStoryMap", "Check at least one layer.")
            return

        # Persist current story edits
        self._story_save_current()

        save_github_settings(
            self.gh_remember.isChecked(),
            self.gh_owner.text().strip(),
            self.gh_repo.text().strip(),
            self.gh_branch.text().strip() or "gh-pages",
            self.gh_publish_after.isChecked(),
            self.gh_remember_token.isChecked(),
            self.gh_token.text(),
        )

        title = self.title_edit.text().strip() or "My story map"
        template_dir = self.plugin_dir / "templates"

        # Progress dialog (cancellable)
        prog = QProgressDialog("Exporting…", "Cancel", 0, 100, self)
        prog.setWindowTitle("QStoryMap")
        prog.setMinimumDuration(0)
        prog.setAutoClose(False)
        prog.setAutoReset(False)
        # Keep dialog size stable even when label text changes.
        prog.setMinimumWidth(520)
        prog.setSizeGripEnabled(False)
        prog.setValue(0)
        prog.show()
        QApplication.processEvents()

        def cancelled() -> bool:
            return bool(prog.wasCanceled())

        done_tiles = 0

        def on_progress(done: int, total: int, label: str):
            nonlocal done_tiles
            # total==0 => indeterminate
            if total and total > 0:
                if prog.maximum() != total:
                    prog.setMaximum(total)
                prog.setValue(min(int(done), int(total)))
            else:
                if prog.maximum() != 0:
                    prog.setMaximum(0)
            prog.setLabelText(label)
            done_tiles = int(done)
            QApplication.processEvents()

        # AOI bbox from canvas (used for per-layer clip_to_aoi setting)
        aoi = self._aoi_bbox_wgs84()

        # Apply AOI to items that requested it
        for it in items:
            tile = it.get("tile") or {}
            if tile.get("clip_to_aoi") and aoi:
                it["aoi_bbox_wgs84"] = aoi

        ok, msg = export_story_map(
            Path(out_path),
            items,
            title,
            template_dir,
            enable_tiling=self.enable_tiles.isChecked(),
            min_zoom=int(self.min_zoom.value()),
            max_zoom=int(self.max_zoom.value()),
            tile_size=int(self.default_tile_size.currentData()),
            progress_cb=on_progress,
            cancelled_cb=cancelled,
            story_sections=list(self._story_data.values()) if self.export_story.isChecked() else None,
        )
        prog.close()
        if not ok:
            QMessageBox.critical(self, "QStoryMap", msg)
            return

        final_msg = msg
        if self.gh_publish_after.isChecked():
            owner = self.gh_owner.text().strip()
            repo = self.gh_repo.text().strip()
            token = self.gh_token.text().strip()
            branch = (self.gh_branch.text().strip() or "gh-pages")
            if not owner or not repo:
                QMessageBox.warning(
                    self,
                    "QStoryMap",
                    "Export finished, but GitHub upload was skipped: enter Owner and Repository on the Publish tab.",
                )
                QMessageBox.information(self, "QStoryMap", final_msg)
                self.accept()
                return
            if not token:
                QMessageBox.warning(
                    self,
                    "QStoryMap",
                    "Export finished, but GitHub upload was skipped: enter a personal access token on the Publish tab.",
                )
                QMessageBox.information(self, "QStoryMap", final_msg)
                self.accept()
                return
            gh_cfg = GitHubPagesConfig(owner=owner, repo=repo, token=token, branch=branch)
            gh_ok, gh_detail, pages_url = publish_folder_to_github_pages(
                gh_cfg,
                Path(out_path),
                create_repo_if_missing=self.gh_create_repo.isChecked(),
            )
            if gh_ok and pages_url:
                final_msg += "\n\n" + gh_detail + "\n\nSite (after Pages is enabled):\n" + pages_url
            elif not gh_ok:
                QMessageBox.warning(
                    self,
                    "QStoryMap — GitHub",
                    "Export succeeded, but GitHub upload failed:\n" + gh_detail,
                )
                QMessageBox.information(self, "QStoryMap", msg)
                self.accept()
                return

        QMessageBox.information(self, "QStoryMap", final_msg)
        self.accept()

    def _load_saved_github(self):
        data = load_github_settings()
        if not data.get("remember"):
            return
        self.gh_remember.setChecked(True)
        self.gh_publish_after.setChecked(bool(data.get("publish_after_export")))
        self.gh_owner.setText(data.get("owner") or "")
        self.gh_repo.setText(data.get("repo") or "")
        self.gh_branch.setText(data.get("branch") or "gh-pages")
        self.gh_remember_token.setChecked(bool(data.get("remember_token")))
        if data.get("remember_token") and data.get("token"):
            self.gh_token.setText(data.get("token") or "")
