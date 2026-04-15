"""Export vector and raster layers to a static web story map."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from qgis.core import QgsProject, QgsRasterLayer, QgsVectorLayer

from .legend_export import build_legend_entry, write_legend_json
from .image_export import render_layer_to_png
from .tile_export import estimate_xyz_tile_count, export_layer_to_xyz_tiles


def _slugify(name: str) -> str:
    s = re.sub(r"[^\w\s-]", "", name, flags=re.UNICODE).strip().lower()
    s = re.sub(r"[-\s]+", "-", s)
    return s or "layer"


def _allocate_slug(base: str, used: set[str]) -> str:
    slug = base
    n = 2
    while slug in used:
        slug = f"{base}-{n}"
        n += 1
    used.add(slug)
    return slug


def export_story_map(
    output_dir: Path,
    ordered_items: list[dict[str, Any]],
    story_title: str,
    template_dir: Path,
    *,
    enable_tiling: bool = False,
    min_zoom: int = 0,
    max_zoom: int = 8,
    tile_size: int = 256,
    progress_cb=None,
    cancelled_cb=None,
    story_sections: list[dict[str, Any]] | None = None,
) -> tuple[bool, str]:
    """
    ``ordered_items`` are dicts with ``layer_id``, ``type`` (``vector`` | ``raster``).

    Exports a fully static site.

    Default mode:
    - One transparent PNG per checked layer (styled as in QGIS)
    - A manifest referencing those images as Leaflet image overlays using the layer's WGS84 bbox

    Tiled mode (enable_tiling=True):
    - One XYZ tile pyramid per checked layer under ``tiles/<slug>/<z>/<x>/<y>.png``
    - A manifest referencing those tiles with ``renderMode: "tiles"``
    """
    if not ordered_items:
        return False, "Select at least one layer."

    project = QgsProject.instance()
    output_dir = output_dir.resolve()
    legend_dir = output_dir / "legend"
    legend_dir.mkdir(parents=True, exist_ok=True)
    images_dir = output_dir / "images"
    if not enable_tiling:
        images_dir.mkdir(parents=True, exist_ok=True)

    used_slugs: set[str] = set()
    slug_by_layer_id: dict[str, str] = {}
    manifest_layers: list[dict[str, Any]] = []
    legend_entries: list[dict[str, Any]] = []
    warnings: list[str] = []

    def _intersect_bbox(a: list[float] | None, b: list[float] | None) -> list[float] | None:
        if not a or not b or len(a) != 4 or len(b) != 4:
            return None
        minx = max(float(a[0]), float(b[0]))
        miny = max(float(a[1]), float(b[1]))
        maxx = min(float(a[2]), float(b[2]))
        maxy = min(float(a[3]), float(b[3]))
        if maxx <= minx or maxy <= miny:
            return None
        return [minx, miny, maxx, maxy]

    # Pre-estimate total tiles for progress scaling across all layers.
    total_tiles = 0
    if enable_tiling and progress_cb:
        from .image_export import layer_bbox_wgs84

        for it in ordered_items:
            lid0 = it.get("layer_id")
            if not lid0:
                continue
            lyr0 = project.mapLayer(lid0)
            if lyr0 is None:
                continue
            bbox_layer0 = layer_bbox_wgs84(lyr0, project)
            bbox_aoi0 = it.get("aoi_bbox_wgs84")
            bbox0 = _intersect_bbox(bbox_layer0, bbox_aoi0) if bbox_aoi0 else bbox_layer0
            tile_cfg0 = (it.get("tile") or {}) if isinstance(it.get("tile"), dict) else {}
            mz0 = int(tile_cfg0.get("min_zoom", min_zoom))
            mz1 = int(tile_cfg0.get("max_zoom", max_zoom))
            total_tiles += estimate_xyz_tile_count(bbox0 or [], mz0, mz1)
        progress_cb(0, total_tiles, "Starting export…")
    global_done = 0

    for order, item in enumerate(ordered_items):
        if cancelled_cb and cancelled_cb():
            return False, "Export cancelled."
        lid = item.get("layer_id")
        if not lid:
            return False, "Invalid export item (missing layer_id)."
        layer = project.mapLayer(lid)
        if layer is None:
            return False, f"Layer not found in project (id={lid})."

        ltype = item.get("type")
        if ltype == "vector":
            if not isinstance(layer, QgsVectorLayer):
                return False, f'"{layer.name()}" is not a vector layer.'

            base = _slugify(layer.name())
            slug = _allocate_slug(base, used_slugs)
            slug_by_layer_id[str(lid)] = slug

            if enable_tiling:
                from .image_export import layer_bbox_wgs84

                bbox_layer = layer_bbox_wgs84(layer, project)
                bbox_aoi = item.get("aoi_bbox_wgs84")
                bbox = _intersect_bbox(bbox_layer, bbox_aoi) if bbox_aoi else bbox_layer
                tile_cfg = (item.get("tile") or {}) if isinstance(item.get("tile"), dict) else {}
                mz0 = int(tile_cfg.get("min_zoom", min_zoom))
                mz1 = int(tile_cfg.get("max_zoom", max_zoom))
                ts = int(tile_cfg.get("tile_size", tile_size))
                base_done = global_done

                def _prog(d: int, _t: int, label: str):
                    if progress_cb:
                        progress_cb(base_done + int(d), total_tiles, label)

                ok_t, warn_t, tmeta = export_layer_to_xyz_tiles(
                    layer,
                    slug=slug,
                    output_dir=output_dir,
                    project=project,
                    bbox_wgs84=bbox,
                    min_zoom=mz0,
                    max_zoom=mz1,
                    tile_size=ts,
                    progress_cb=_prog if progress_cb else None,
                    cancelled_cb=cancelled_cb,
                )
                if tmeta is not None:
                    global_done = base_done + int(tmeta.tile_count)
                if not ok_t or tmeta is None:
                    return False, warn_t or f'Failed to export tiles for "{layer.name()}".'
                if warn_t:
                    warnings.append(warn_t)
                entry = {
                    "type": "vector",
                    "renderMode": "tiles",
                    "order": order,
                    "id": slug,
                    "name": layer.name(),
                    "bbox": tmeta.bbox_wgs84,
                    "opacity": 1.0,
                    "tilesUrl": tmeta.tiles_url,
                    "minZoom": tmeta.min_zoom,
                    "maxZoom": tmeta.max_zoom,
                    "tileSize": tmeta.tile_size,
                    "tileCount": tmeta.tile_count,
                }
            else:
                ok_img, warn_img, img_meta = render_layer_to_png(
                    layer,
                    slug=slug,
                    output_dir=images_dir,
                    project=project,
                )
                if not ok_img or img_meta is None:
                    return False, warn_img or f'Failed to export image for "{layer.name()}".'
                if warn_img:
                    warnings.append(warn_img)
                entry = {
                    "type": "vector",
                    "renderMode": "image",
                    "order": order,
                    "id": slug,
                    "name": layer.name(),
                    "bbox": img_meta.bbox_wgs84,
                    "opacity": 1.0,
                    "image": img_meta.rel_path,
                    "imageWidth": img_meta.width,
                    "imageHeight": img_meta.height,
                }
            manifest_layers.append(entry)
            legend_entries.append(build_legend_entry(layer, legend_dir, slug))

        elif ltype == "raster":
            if not isinstance(layer, QgsRasterLayer):
                return False, f'"{layer.name()}" is not a raster layer.'

            base = _slugify(layer.name())
            slug = _allocate_slug(base, used_slugs)
            slug_by_layer_id[str(lid)] = slug

            if enable_tiling:
                # Compute bbox in WGS84 and export tiles.
                from .image_export import layer_bbox_wgs84

                bbox_layer = layer_bbox_wgs84(layer, project)
                bbox_aoi = item.get("aoi_bbox_wgs84")
                bbox = _intersect_bbox(bbox_layer, bbox_aoi) if bbox_aoi else bbox_layer
                tile_cfg = (item.get("tile") or {}) if isinstance(item.get("tile"), dict) else {}
                mz0 = int(tile_cfg.get("min_zoom", min_zoom))
                mz1 = int(tile_cfg.get("max_zoom", max_zoom))
                ts = int(tile_cfg.get("tile_size", tile_size))
                base_done = global_done

                def _prog(d: int, _t: int, label: str):
                    if progress_cb:
                        progress_cb(base_done + int(d), total_tiles, label)

                ok_t, warn_t, tmeta = export_layer_to_xyz_tiles(
                    layer,
                    slug=slug,
                    output_dir=output_dir,
                    project=project,
                    bbox_wgs84=bbox,
                    min_zoom=mz0,
                    max_zoom=mz1,
                    tile_size=ts,
                    progress_cb=_prog if progress_cb else None,
                    cancelled_cb=cancelled_cb,
                )
                if tmeta is not None:
                    global_done = base_done + int(tmeta.tile_count)
                if not ok_t or tmeta is None:
                    return False, warn_t or f'Failed to export tiles for "{layer.name()}".'
                if warn_t:
                    warnings.append(warn_t)
                entry = {
                    "type": "raster",
                    "renderMode": "tiles",
                    "order": order,
                    "id": slug,
                    "name": layer.name(),
                    "bbox": tmeta.bbox_wgs84,
                    "opacity": 1.0,
                    "queryable": False,
                    "tilesUrl": tmeta.tiles_url,
                    "minZoom": tmeta.min_zoom,
                    "maxZoom": tmeta.max_zoom,
                    "tileSize": tmeta.tile_size,
                    "tileCount": tmeta.tile_count,
                }
            else:
                ok_img, warn_img, img_meta = render_layer_to_png(
                    layer,
                    slug=slug,
                    output_dir=images_dir,
                    project=project,
                )
                if not ok_img or img_meta is None:
                    return False, warn_img or f'Failed to export image for "{layer.name()}".'
                if warn_img:
                    warnings.append(warn_img)
                entry = {
                    "type": "raster",
                    "renderMode": "image",
                    "order": order,
                    "id": slug,
                    "name": layer.name(),
                    "bbox": img_meta.bbox_wgs84,
                    "opacity": 1.0,
                    "queryable": False,
                    "image": img_meta.rel_path,
                    "imageWidth": img_meta.width,
                    "imageHeight": img_meta.height,
                }
            manifest_layers.append(entry)
            legend_entries.append(build_legend_entry(layer, legend_dir, slug))

        else:
            return False, f'Unknown layer type: {ltype!r}.'

    manifest_layers.sort(key=lambda m: m.get("order", 0))

    manifest: dict[str, Any] = {
        "version": 3,
        "title": story_title,
        "layers": manifest_layers,
    }

    # Story sections (ArcGIS-style side panel)
    if story_sections:
        out_sections: list[dict[str, Any]] = []
        for s in story_sections:
            if not isinstance(s, dict):
                continue
            key = s.get("key")
            title = (s.get("title") or "").strip()
            body = (s.get("body") or "").strip()
            center = s.get("center")
            zoom = s.get("zoom")
            # Skip empty intro sections (keeps output clean)
            if key in ("intro",) and not (title or body):
                continue
            out_sections.append(
                {
                    "key": key,
                    "title": title,
                    "body": body,
                    "center": center if isinstance(center, (list, tuple)) and len(center) == 2 else None,
                    "zoom": int(zoom) if zoom is not None else None,
                }
            )

        if out_sections:
            (output_dir / "story.json").write_text(
                json.dumps({"sections": out_sections}, indent=2),
                encoding="utf-8",
            )
            manifest["story"] = "story.json"

    if legend_entries:
        write_legend_json(output_dir, legend_entries)
        manifest["legend"] = "legend.json"

    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    for name in ("index.html", "style.css", "app.js"):
        src = template_dir / name
        if not src.is_file():
            return False, f"Missing template file: {name}"
        shutil.copy2(src, output_dir / name)

    msg = f"Story map written to:\n{output_dir}"
    if warnings:
        msg += "\n\nWarnings:\n" + "\n".join(f"  • {w}" for w in warnings)
    return True, msg
