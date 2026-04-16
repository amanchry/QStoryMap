"""Persist QStoryMap dialog state (layers, story, export options) across dialog closes."""

from __future__ import annotations

import json
from typing import Any

from qgis.PyQt.QtCore import QSettings

GROUP = "QStoryMap"
KEY_SESSION = "dialog/session_json"


def save_dialog_session(payload: dict[str, Any]) -> None:
    s = QSettings()
    s.beginGroup(GROUP)
    s.setValue(KEY_SESSION, json.dumps(payload, ensure_ascii=False))
    s.endGroup()


def load_dialog_session() -> dict[str, Any] | None:
    s = QSettings()
    s.beginGroup(GROUP)
    raw = s.value(KEY_SESSION, "", type=str)
    s.endGroup()
    if not raw or not isinstance(raw, str):
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    return data if isinstance(data, dict) else None
