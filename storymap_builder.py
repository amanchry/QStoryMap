"""Main plugin class registered with QGIS."""

from pathlib import Path

from qgis.core import QgsProject
from qgis.PyQt.QtGui import QIcon
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

        # Reset dialog when the user opens or creates a different project.
        QgsProject.instance().cleared.connect(self._on_project_change)
        QgsProject.instance().readProject.connect(self._on_project_change)

    def _on_project_change(self, *_args):
        """Discard dialog state when a new project is loaded or created."""
        if self._dlg is not None:
            self._dlg.deleteLater()
            self._dlg = None

    def unload(self):
        try:
            QgsProject.instance().cleared.disconnect(self._on_project_change)
            QgsProject.instance().readProject.disconnect(self._on_project_change)
        except Exception:
            pass
        if self._dlg is not None:
            self._dlg.deleteLater()
            self._dlg = None
        if self.action:
            self.iface.removeWebToolBarIcon(self.action)
            self.iface.removePluginWebMenu("&QStoryMap", self.action)
            del self.action

    def run(self):
        # Keep the dialog alive for the current project session so all state is preserved.
        if self._dlg is None:
            self._dlg = QStoryMapDialog(self.plugin_dir, self.iface, self.iface.mainWindow())
            self._dlg.setModal(False)
        self._dlg.show()
        self._dlg.raise_()
        self._dlg.activateWindow()
