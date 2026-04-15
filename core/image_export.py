"""Render QGIS layers to static transparent PNGs for Leaflet overlays."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from qgis.PyQt.QtCore import QSize, Qt
from qgis.PyQt.QtGui import QColor, QImage, QPainter
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsMapRendererCustomPainterJob,
    QgsMapSettings,
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
    QgsVectorLayer,
)


@dataclass
class ExportedImage:
    rel_path: str
    bbox_wgs84: list[float] | None  # [minx, miny, maxx, maxy]
    width: int
    height: int


def layer_bbox_wgs84(layer, project: QgsProject) -> list[float] | None:
    """Return [minx, miny, maxx, maxy] in EPSG:4326."""
    extent = layer.extent()
    if extent.isEmpty() or not extent.isFinite():
        return None
    src = layer.crs()
    wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
    xform = QgsCoordinateTransform(src, wgs84, project)
    try:
        e = xform.transformBoundingBox(extent)
    except Exception:
        return None
    if e.isEmpty() or not e.isFinite():
        return None
    return [e.xMinimum(), e.yMinimum(), e.xMaximum(), e.yMaximum()]


def _safe_size(w: int, h: int, *, max_dim: int) -> tuple[int, int, bool]:
    """Return (w2,h2,scaled) constrained to max_dim preserving aspect."""
    if w <= 0 or h <= 0:
        return 0, 0, False
    if max(w, h) <= max_dim:
        return w, h, False
    if w >= h:
        w2 = max_dim
        h2 = max(1, int(round(h * (max_dim / float(w)))))
    else:
        h2 = max_dim
        w2 = max(1, int(round(w * (max_dim / float(h)))))
    return w2, h2, True


def render_layer_to_png(
    layer,
    *,
    slug: str,
    output_dir: Path,
    project: QgsProject,
    max_vector_dim: int = 4096,
    max_raster_dim: int = 16384,
    min_raster_dim: int = 2048,
) -> tuple[bool, str, ExportedImage | None]:
    """
    Render the layer exactly as in QGIS (current symbology) onto a transparent PNG.

    - Raster: uses native grid size (layer.width/height), supersampled up to ``min_raster_dim``
      on the long edge when the source grid is smaller (sharper in the browser), then capped
      by ``max_raster_dim``.
    - Vector: long edge up to ``max_vector_dim`` px (aspect from extent); higher values reduce
      blur when the overlay is shown large on screen or zoomed in.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rel = f"images/{slug}.png"
    out_path = output_dir / f"{slug}.png"

    # Pick extent and output size
    extent: QgsRectangle = layer.extent()
    if extent.isEmpty() or not extent.isFinite():
        return False, f'Layer "{layer.name()}" has empty extent.', None

    if isinstance(layer, QgsRasterLayer):
        w0, h0 = int(layer.width()), int(layer.height())
        if w0 <= 0 or h0 <= 0:
            return False, f'Raster "{layer.name()}" has invalid dimensions.', None
        warn = ""
        native_w, native_h = w0, h0
        # Supersample small grids so the PNG has enough pixels for crisp map display.
        if max(w0, h0) < min_raster_dim:
            if w0 >= h0:
                w0 = min_raster_dim
                h0 = max(1, int(round(min_raster_dim * (native_h / float(native_w)))))
            else:
                h0 = min_raster_dim
                w0 = max(1, int(round(min_raster_dim * (native_w / float(native_h)))))
            warn = (
                f'Raster "{layer.name()}" native grid {native_w}×{native_h}px; '
                f"exported at {w0}×{h0}px for sharper display."
            )
        w, h, scaled = _safe_size(w0, h0, max_dim=max_raster_dim)
        if w <= 0 or h <= 0:
            return False, f'Raster "{layer.name()}" has invalid dimensions.', None
        if scaled:
            cap_msg = (
                f'Raster "{layer.name()}" is {w0}×{h0}px; exported as {w}×{h}px '
                f"(capped at {max_raster_dim})."
            )
            warn = f"{warn}\n{cap_msg}".strip() if warn else cap_msg
    elif isinstance(layer, QgsVectorLayer):
        # Keep aspect based on layer extent
        w0 = float(extent.width()) or 1.0
        h0 = float(extent.height()) or 1.0
        if w0 >= h0:
            w, h = max_vector_dim, max(1, int(round(max_vector_dim * (h0 / w0))))
        else:
            h, w = max_vector_dim, max(1, int(round(max_vector_dim * (w0 / h0))))
        warn = ""
    else:
        return False, f'Unsupported layer type for image export: "{layer.name()}".', None

    # Configure renderer
    ms = QgsMapSettings()
    ms.setLayers([layer])
    ms.setExtent(extent)
    ms.setOutputSize(QSize(int(w), int(h)))
    ms.setBackgroundColor(QColor(0, 0, 0, 0))
    # Render in the layer CRS so bbox mapping stays correct
    try:
        ms.setDestinationCrs(layer.crs())
    except Exception:
        pass
    try:
        ms.setTransformContext(project.transformContext())
    except Exception:
        pass

    img = QImage(int(w), int(h), QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    painter = QPainter(img)
    # Smooth strokes for vectors; avoid extra pixmap smoothing (can look soft when scaled).
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, False)

    job = QgsMapRendererCustomPainterJob(ms, painter)
    job.start()
    job.waitForFinished()
    painter.end()

    ok = img.save(str(out_path), "PNG")
    if not ok:
        return False, f'Failed to write PNG for "{layer.name()}".', None

    bbox = layer_bbox_wgs84(layer, project)
    meta = ExportedImage(rel_path=rel, bbox_wgs84=bbox, width=int(w), height=int(h))
    msg = warn
    return True, msg, meta

