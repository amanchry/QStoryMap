"""Main plugin class registered with QGIS."""

from pathlib import Path

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QAction

from .storymap_dialog import QStoryMapDialog


class QStoryMap:
    """QStoryMap: export vector layers to a static web story map."""

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = Path(__file__).resolve().parent
        self.action = None
        self._dlg = None

    def initGui(self):
        icon_path = self.plugin_dir / "icon.svg"
        self.action = QAction(
            QIcon(str(icon_path)) if icon_path.exists() else QIcon(),
            "QStoryMap…",
            self.iface.mainWindow(),
        )
        self.action.setObjectName("QStoryMapAction")
        self.action.triggered.connect(self.run)
        self.iface.addPluginToWebMenu("&QStoryMap", self.action)
        self.iface.addWebToolBarIcon(self.action)

    def unload(self):
        if self.action:
            self.iface.removeWebToolBarIcon(self.action)
            self.iface.removePluginWebMenu("&QStoryMap", self.action)
            del self.action

    def run(self):
        # Non-modal so the user can interact with the map canvas
        if self._dlg is None:
            self._dlg = QStoryMapDialog(self.plugin_dir, self.iface, self.iface.mainWindow())
            self._dlg.setModal(False)
            self._dlg.setAttribute(Qt.WA_DeleteOnClose, True)

            def _clear(_res=None):
                self._dlg = None

            try:
                self._dlg.finished.connect(_clear)
            except Exception:
                pass
        self._dlg.show()
        self._dlg.raise_()
        self._dlg.activateWindow()
