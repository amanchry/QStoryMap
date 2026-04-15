"""Map QGIS vector renderers to a JSON style for the Leaflet client."""

from __future__ import annotations

from typing import Any

from qgis.PyQt.QtCore import QDate, QDateTime, Qt, QVariant
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    QgsCategorizedSymbolRenderer,
    QgsGraduatedSymbolRenderer,
    QgsMarkerSymbol,
    QgsRendererCategory,
    QgsSingleSymbolRenderer,
    QgsSymbol,
    QgsVectorLayer,
    QgsWkbTypes,
)


def _json_safe_value(v: Any) -> Any:
    """Ensure manifest ``style`` values are JSON-friendly (PyQt / QGIS variants)."""
    if v is None:
        return None
    if isinstance(v, QVariant):
        if not v.isValid() or v.isNull():
            return None
        return _json_safe_value(v.value())
    if isinstance(v, (QDate, QDateTime)):
        return v.toString(Qt.ISODate)
    if isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="replace")
    return str(v)


def _hex(c: QColor) -> str:
    if c.alpha() < 255:
        return f"rgba({c.red()},{c.green()},{c.blue()},{c.alpha() / 255.0})"
    return c.name()


def _geometry_category(geom_type: Any):
    """
    Normalize ``QgsVectorLayer.geometryType()`` for comparisons.

    QGIS 3.38+ returns ``QgsWkbTypes.GeometryType`` directly; older APIs return a
    WKB type that must be passed through ``QgsWkbTypes.geometryType()``.
    """
    try:
        return QgsWkbTypes.geometryType(geom_type)
    except TypeError:
        return geom_type


def _symbol_to_style(sym: QgsSymbol | None, geom_type: Any) -> dict[str, Any]:
    """Leaflet-oriented path / circle options."""
    if sym is None:
        return _geom_defaults(geom_type)

    out: dict[str, Any] = {"opacity": 1.0, "fillOpacity": 0.25}
    g = _geometry_category(geom_type)

    if g == QgsWkbTypes.PointGeometry:
        if isinstance(sym, QgsMarkerSymbol):
            out["kind"] = "point"
            out["radius"] = max(3, int(sym.size() / 2) or 4)
            out["color"] = _hex(sym.color())
            out["fillColor"] = _hex(sym.color())
            w = 1
            try:
                if hasattr(sym, "width") and sym.width():
                    w = max(1, int(sym.width()))
            except Exception:
                pass
            out["weight"] = w
            out["fillOpacity"] = sym.opacity() * 0.85
            out["opacity"] = sym.opacity()
        else:
            out.update(_geom_defaults(geom_type))
        return out

    if g == QgsWkbTypes.LineGeometry:
        w = 2
        try:
            if hasattr(sym, "width"):
                w = max(1, int(round(float(sym.width()) * 2)))
        except Exception:
            pass
        out["kind"] = "line"
        out["color"] = _hex(sym.color())
        out["weight"] = w
        out["opacity"] = sym.opacity()
        out["fillOpacity"] = 0
        return out

    # Polygon / unknown
    out["kind"] = "polygon"
    stroke = _hex(sym.color())
    fill = stroke
    weight = 2
    sl = sym.symbolLayer(0)
    if sl is not None:
        try:
            if hasattr(sl, "strokeColor"):
                stroke = _hex(sl.strokeColor())
            if hasattr(sl, "fillColor"):
                fill = _hex(sl.fillColor())
            if hasattr(sl, "strokeWidth"):
                weight = max(1, int(round(float(sl.strokeWidth()))))
        except Exception:
            pass
    out["color"] = stroke
    out["fillColor"] = fill
    out["weight"] = weight
    out["opacity"] = sym.opacity()
    out["fillOpacity"] = min(1.0, sym.opacity() * 0.35)
    return out


def _geom_defaults(geom_type: Any) -> dict[str, Any]:
    g = _geometry_category(geom_type)
    if g == QgsWkbTypes.PointGeometry:
        return {
            "kind": "point",
            "radius": 6,
            "color": "#3388ff",
            "fillColor": "#3388ff",
            "weight": 1,
            "opacity": 1,
            "fillOpacity": 0.7,
        }
    if g == QgsWkbTypes.LineGeometry:
        return {
            "kind": "line",
            "color": "#3388ff",
            "weight": 2,
            "opacity": 0.9,
            "fillOpacity": 0,
        }
    return {
        "kind": "polygon",
        "color": "#3388ff",
        "fillColor": "#3388ff",
        "weight": 2,
        "opacity": 0.9,
        "fillOpacity": 0.2,
    }


def vector_style_to_json(layer: QgsVectorLayer) -> dict[str, Any]:
    """Return manifest ``style`` object for ``layer``."""
    geom_type = layer.geometryType()
    r = layer.renderer()

    if isinstance(r, QgsSingleSymbolRenderer):
        sym = r.symbol()
        return {"mode": "single", "style": _symbol_to_style(sym, geom_type)}

    if isinstance(r, QgsCategorizedSymbolRenderer):
        field = r.classAttribute()
        categories: list[dict[str, Any]] = []
        for cat in r.categories():
            c: QgsRendererCategory = cat
            categories.append(
                {
                    "value": _json_safe_value(c.value()),
                    "label": c.label(),
                    "style": _symbol_to_style(c.symbol(), geom_type),
                }
            )
        return {"mode": "categorized", "field": field, "categories": categories}

    if isinstance(r, QgsGraduatedSymbolRenderer):
        field = r.classAttribute()
        method = r.classificationMethod().id() if r.classificationMethod() else ""
        ranges_out: list[dict[str, Any]] = []
        for rng in r.ranges():
            ranges_out.append(
                {
                    "lower": _json_safe_value(rng.lowerValue()),
                    "upper": _json_safe_value(rng.upperValue()),
                    "label": rng.label(),
                    "style": _symbol_to_style(rng.symbol(), geom_type),
                }
            )
        return {
            "mode": "graduated",
            "field": field,
            "method": method,
            "ranges": ranges_out,
        }

    return {"mode": "default"}
