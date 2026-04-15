"""QGIS QStoryMap plugin package."""

def classFactory(iface):  # noqa: N802 — QGIS entry point
    from .storymap_builder import QStoryMap

    return QStoryMap(iface)
