"""Build legend.json and export SLD per layer (no rasterized legend images)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from qgis.core import QgsRasterLayer, QgsVectorLayer
from qgis.PyQt.QtXml import QDomDocument


def _export_layer_sld(layer, legend_dir: Path, slug: str) -> str | None:
    """
    Export layer style as SLD XML (best effort) and write it under ``sld/<slug>.sld``.

    Note: SLD export fidelity depends on QGIS renderer support.
    """
    try:
        sld_dir = legend_dir.parent / "sld"
        sld_dir.mkdir(parents=True, exist_ok=True)
        out_path = sld_dir / f"{slug}.sld"
        # Prefer API that writes directly to file (most stable across versions).
        try:
            res = layer.saveSldStyle(str(out_path))
            # QGIS commonly returns (message: str, ok: bool)
            if isinstance(res, tuple) and len(res) >= 2:
                ok = bool(res[1])
            else:
                ok = bool(res)
            if ok and out_path.is_file() and out_path.stat().st_size > 20:
                return f"sld/{slug}.sld"
        except Exception:
            pass

        # Fallback: export to QDomDocument and write ourselves.
        doc = QDomDocument("sld")
        try:
            ok = bool(layer.exportSldStyle(doc))
        except Exception:
            ok = False
        if not ok:
            return None
        xml = doc.toString(2)
        if not xml or len(xml.strip()) < 20:
            return None
        out_path.write_text(xml, encoding="utf-8")
        return f"sld/{slug}.sld"
    except Exception:
        return None


def build_legend_entry(layer, legend_dir: Path, slug: str) -> dict[str, Any]:
    """Return one legend block for ``legend.json`` (``id``, ``name``, ``type``, ``sld`` only)."""
    legend_dir.mkdir(parents=True, exist_ok=True)
    sld = _export_layer_sld(layer, legend_dir, slug)
    if isinstance(layer, QgsVectorLayer):
        return {"id": slug, "name": layer.name(), "type": "vector", "sld": sld}
    if isinstance(layer, QgsRasterLayer):
        return {"id": slug, "name": layer.name(), "type": "raster", "sld": sld}
    return {"id": slug, "name": layer.name(), "type": "unknown", "sld": sld}


def write_legend_json(output_dir: Path, entries: list[dict[str, Any]]) -> None:
    path = output_dir / "legend.json"
    path.write_text(json.dumps({"layers": entries}, indent=2), encoding="utf-8")
