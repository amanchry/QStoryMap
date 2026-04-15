"""Render QGIS layers to local XYZ tiles (EPSG:3857) for Leaflet."""

from __future__ import annotations

import math
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
class ExportedTiles:
    tiles_url: str  # e.g. "tiles/roads/{z}/{x}/{y}.png"
    bbox_wgs84: list[float] | None  # [minx, miny, maxx, maxy]
    min_zoom: int
    max_zoom: int
    tile_size: int
    tile_count: int


def estimate_xyz_tile_count(bbox_wgs84: list[float], min_zoom: int, max_zoom: int) -> int:
    """Estimate number of XYZ tiles covering bbox across zoom range."""
    if not bbox_wgs84 or len(bbox_wgs84) != 4:
        return 0
    minx, miny, maxx, maxy = bbox_wgs84
    if maxx < minx:
        return 0
    est = 0
    for z in range(int(min_zoom), int(max_zoom) + 1):
        x0 = _lon2tilex(minx, z)
        x1 = _lon2tilex(maxx, z)
        y0 = _lat2tiley(maxy, z)  # north
        y1 = _lat2tiley(miny, z)  # south
        x0 = max(0, min((2**z) - 1, x0))
        x1 = max(0, min((2**z) - 1, x1))
        y0 = max(0, min((2**z) - 1, y0))
        y1 = max(0, min((2**z) - 1, y1))
        if x1 >= x0 and y1 >= y0:
            est += (x1 - x0 + 1) * (y1 - y0 + 1)
    return int(est)


def _clamp_lat(lat: float) -> float:
    # WebMercator valid latitude range
    return max(-85.05112878, min(85.05112878, lat))


def _lon2tilex(lon: float, z: int) -> int:
    n = 2**z
    return int(math.floor((lon + 180.0) / 360.0 * n))


def _lat2tiley(lat: float, z: int) -> int:
    lat = _clamp_lat(lat)
    n = 2**z
    lat_rad = math.radians(lat)
    return int(math.floor((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n))


def _tile_lon(x: int, z: int) -> float:
    return x / (2**z) * 360.0 - 180.0


def _tile_lat(y: int, z: int) -> float:
    n = math.pi - (2.0 * math.pi * y) / (2**z)
    return math.degrees(math.atan(math.sinh(n)))


def _tile_bounds_wgs84(z: int, x: int, y: int) -> QgsRectangle:
    # Returns lon/lat bounds: (west, south, east, north) as QgsRectangle(xmin, ymin, xmax, ymax)
    west = _tile_lon(x, z)
    east = _tile_lon(x + 1, z)
    north = _tile_lat(y, z)
    south = _tile_lat(y + 1, z)
    return QgsRectangle(west, south, east, north)


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def export_layer_to_xyz_tiles(
    layer,
    *,
    slug: str,
    output_dir: Path,
    project: QgsProject,
    bbox_wgs84: list[float] | None,
    min_zoom: int,
    max_zoom: int,
    tile_size: int = 256,
    progress_cb=None,
    cancelled_cb=None,
) -> tuple[bool, str, ExportedTiles | None]:
    """
    Render a single layer to local XYZ tiles.

    - Tiles are rendered in EPSG:3857 and saved as transparent PNGs.
    - Tile range is based on the layer bbox in EPSG:4326.
    """
    if bbox_wgs84 is None or len(bbox_wgs84) != 4:
        return False, f'Layer "{layer.name()}" has no valid WGS84 bbox.', None

    if min_zoom < 0 or max_zoom < 0 or max_zoom < min_zoom:
        return False, "Invalid zoom range.", None
    if max_zoom > 20 or min_zoom > 20:
        return False, "Max zoom for tile export is 20.", None

    if not isinstance(layer, (QgsVectorLayer, QgsRasterLayer)):
        return False, f'Unsupported layer type for tiles: "{layer.name()}".', None

    out_root = Path(output_dir) / "tiles" / slug
    _ensure_dir(out_root)

    wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
    webm = QgsCoordinateReferenceSystem("EPSG:3857")
    to_webm = QgsCoordinateTransform(wgs84, webm, project)

    minx, miny, maxx, maxy = bbox_wgs84
    # Handle dateline-ish cases conservatively (avoid massive tile counts)
    if maxx < minx:
        return False, f'Layer "{layer.name()}" crosses the dateline; tiling not supported yet.', None

    # Estimate tile count (used for warnings and progress scaling)
    est = estimate_xyz_tile_count(bbox_wgs84, min_zoom, max_zoom)

    # Render
    ms = QgsMapSettings()
    ms.setLayers([layer])
    ms.setOutputSize(QSize(int(tile_size), int(tile_size)))
    ms.setBackgroundColor(QColor(0, 0, 0, 0))
    ms.setDestinationCrs(webm)
    try:
        ms.setTransformContext(project.transformContext())
    except Exception:
        pass

    tile_count = 0
    for z in range(min_zoom, max_zoom + 1):
        x0 = _lon2tilex(minx, z)
        x1 = _lon2tilex(maxx, z)
        y0 = _lat2tiley(maxy, z)
        y1 = _lat2tiley(miny, z)
        max_index = (2**z) - 1
        x0 = max(0, min(max_index, x0))
        x1 = max(0, min(max_index, x1))
        y0 = max(0, min(max_index, y0))
        y1 = max(0, min(max_index, y1))

        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                if cancelled_cb and cancelled_cb():
                    return False, "Export cancelled.", None
                b = _tile_bounds_wgs84(z, x, y)
                try:
                    e3857 = to_webm.transformBoundingBox(b)
                except Exception:
                    continue
                if e3857.isEmpty() or not e3857.isFinite():
                    continue
                ms.setExtent(QgsRectangle(e3857))

                img = QImage(int(tile_size), int(tile_size), QImage.Format_ARGB32_Premultiplied)
                img.fill(Qt.transparent)
                painter = QPainter(img)
                painter.setRenderHint(QPainter.Antialiasing, True)
                painter.setRenderHint(QPainter.TextAntialiasing, True)
                painter.setRenderHint(QPainter.SmoothPixmapTransform, False)

                job = QgsMapRendererCustomPainterJob(ms, painter)
                job.start()
                job.waitForFinished()
                painter.end()

                out_dir = out_root / str(z) / str(x)
                _ensure_dir(out_dir)
                out_path = out_dir / f"{y}.png"
                if not img.save(str(out_path), "PNG"):
                    return False, f'Failed writing tile: z={z} x={x} y={y}', None
                tile_count += 1
                if progress_cb:
                    progress_cb(tile_count, est, f'Tiling "{layer.name()}"')

    meta = ExportedTiles(
        tiles_url=f"tiles/{slug}" + "/{z}/{x}/{y}.png",
        bbox_wgs84=bbox_wgs84,
        min_zoom=int(min_zoom),
        max_zoom=int(max_zoom),
        tile_size=int(tile_size),
        tile_count=int(tile_count),
    )

    warn = ""
    if est >= 5000:
        warn = f'High tile count (~{est}) for "{layer.name()}" at zoom {min_zoom}–{max_zoom}; export may take a long time.'
    return True, warn, meta

