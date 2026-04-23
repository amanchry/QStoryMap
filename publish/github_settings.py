"""Optional QSettings persistence for GitHub Pages publish fields."""

from __future__ import annotations

from typing import Any

from qgis.PyQt.QtCore import QSettings

GROUP = "QStoryMap"
KEY_GH_REMEMBER = "github/remember"
KEY_GH_OWNER = "github/owner"
KEY_GH_REPO = "github/repo"
KEY_GH_BRANCH = "github/branch"
KEY_GH_ENABLE = "github/publish_after_export"
KEY_GH_TOKEN = "github/token"


def load_github_settings() -> dict[str, Any]:
    s = QSettings()
    s.beginGroup(GROUP)
    data = {
        "remember": s.value(KEY_GH_REMEMBER, False, type=bool),
        "owner": s.value(KEY_GH_OWNER, "", type=str),
        "repo": s.value(KEY_GH_REPO, "", type=str),
        "branch": s.value(KEY_GH_BRANCH, "gh-pages", type=str),
        "publish_after_export": s.value(KEY_GH_ENABLE, False, type=bool),
        "token": s.value(KEY_GH_TOKEN, "", type=str),
    }
    s.endGroup()
    return data


def save_github_settings(
    remember: bool,
    owner: str,
    repo: str,
    branch: str,
    publish_after_export: bool,
    token: str,
) -> None:
    s = QSettings()
    s.beginGroup(GROUP)
    s.setValue(KEY_GH_REMEMBER, remember)
    s.setValue(KEY_GH_ENABLE, publish_after_export)
    if remember:
        s.setValue(KEY_GH_OWNER, owner)
        s.setValue(KEY_GH_REPO, repo)
        s.setValue(KEY_GH_BRANCH, branch or "gh-pages")
        s.setValue(KEY_GH_TOKEN, token)
    else:
        for k in (KEY_GH_OWNER, KEY_GH_REPO, KEY_GH_BRANCH, KEY_GH_ENABLE, KEY_GH_TOKEN):
            s.remove(k)
    s.endGroup()
