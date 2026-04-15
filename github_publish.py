"""Upload a static folder to a GitHub repository branch (GitHub Pages–ready)."""

from __future__ import annotations

import base64
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


API = "https://api.github.com"
USER_AGENT = "QStoryMap-QGIS-Plugin/0.1"


@dataclass
class GitHubPagesConfig:
    owner: str
    repo: str
    token: str
    branch: str = "gh-pages"

    def pages_url(self) -> str:
        """Typical GitHub Pages URL for a project site (branch must be enabled in repo settings)."""
        o = self.owner.strip().replace("/", "")
        r = self.repo.strip().replace("/", "")
        return f"https://{o}.github.io/{r}/"


def _contents_path_url(owner: str, repo: str, file_path: str) -> str:
    """Build .../repos/o/r/contents/<path> with per-segment encoding."""
    o = urllib.parse.quote(owner.strip(), safe="")
    r = urllib.parse.quote(repo.strip(), safe="")
    norm = file_path.replace("\\", "/").strip("/")
    enc = "/".join(urllib.parse.quote(seg, safe="") for seg in norm.split("/") if seg)
    return f"{API}/repos/{o}/{r}/contents/{enc}"


def _request(
    method: str,
    url: str,
    token: str,
    data: bytes | None = None,
    content_type: str | None = None,
    timeout: int = 120,
) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token.strip()}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if content_type and data is not None:
        req.add_header("Content-Type", content_type)
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.getcode(), resp.read()
    except urllib.error.HTTPError as e:
        body = e.read() if e.fp else b""
        return e.code, body


def _get_file_sha(cfg: GitHubPagesConfig, rel_path: str) -> str | None:
    url = _contents_path_url(cfg.owner, cfg.repo, rel_path)
    url += f"?ref={urllib.parse.quote(cfg.branch.strip() or 'gh-pages')}"
    code, body = _request("GET", url, cfg.token)
    if code == 404:
        return None
    if code != 200:
        return None
    try:
        doc = json.loads(body.decode())
        s = doc.get("sha")
        return str(s) if s else None
    except Exception:
        return None


def _put_file(
    cfg: GitHubPagesConfig,
    rel_path: str,
    raw: bytes,
    message: str,
) -> tuple[bool, str]:
    url = _contents_path_url(cfg.owner, cfg.repo, rel_path)
    b64 = base64.standard_b64encode(raw).decode("ascii")
    branch = (cfg.branch or "gh-pages").strip()
    payload: dict[str, Any] = {
        "message": message,
        "content": b64,
        "branch": branch,
    }
    sha = _get_file_sha(cfg, rel_path)
    if sha:
        payload["sha"] = sha
    body = json.dumps(payload).encode("utf-8")
    code, resp = _request("PUT", url, cfg.token, data=body, content_type="application/json")
    if code in (200, 201):
        return True, ""
    try:
        err = json.loads(resp.decode()).get("message", resp[:400].decode(errors="replace"))
    except Exception:
        err = resp[:500].decode(errors="replace")
    return False, f"{rel_path}: HTTP {code} — {err}"


def _token_user_login(token: str) -> str | None:
    code, body = _request("GET", f"{API}/user", token)
    if code != 200:
        return None
    try:
        return str(json.loads(body.decode()).get("login") or "")
    except Exception:
        return None


def ensure_repo_exists(cfg: GitHubPagesConfig) -> tuple[bool, str]:
    """Create a public empty repo under your user account if missing (not for org-owned repos)."""
    o = cfg.owner.strip()
    r = cfg.repo.strip()
    check = f"{API}/repos/{urllib.parse.quote(o, safe='')}/{urllib.parse.quote(r, safe='')}"
    code, _ = _request("GET", check, cfg.token)
    if code == 200:
        return True, ""
    if code != 404:
        return False, f"Could not check repository ({code})."
    login = _token_user_login(cfg.token)
    if not login:
        return False, "Invalid or expired token (GitHub /user failed)."
    if login.lower() != o.lower():
        return (
            False,
            f'Repository not found. Auto-create only works when Owner is your login ({login}). '
            "Create the repository on GitHub first, or set Owner to match your account.",
        )
    create_url = f"{API}/user/repos"
    payload = json.dumps(
        {
            "name": r,
            "private": False,
            "auto_init": False,
            "description": "QStoryMap static site",
        }
    ).encode()
    code2, body2 = _request("POST", create_url, cfg.token, data=payload, content_type="application/json")
    if code2 in (200, 201):
        return True, ""
    try:
        msg = json.loads(body2.decode()).get("message", body2[:300].decode(errors="replace"))
    except Exception:
        msg = body2[:400].decode(errors="replace")
    return False, f"Could not create repository ({code2}): {msg}"


def iter_site_files(root: Path) -> list[tuple[str, bytes]]:
    """Relative POSIX path and file bytes (skips dotfiles / .git)."""
    root = root.resolve()
    out: list[tuple[str, bytes]] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        try:
            rel = p.relative_to(root).as_posix()
        except ValueError:
            continue
        if ".git/" in rel or rel.startswith(".git"):
            continue
        if p.name in (".DS_Store", "Thumbs.db"):
            continue
        out.append((rel, p.read_bytes()))
    # Ensure Jekyll does not strip unknown files on Pages
    if not any(r == ".nojekyll" for r, _ in out):
        out.insert(0, (".nojekyll", b""))
    return out


def publish_folder_to_github_pages(
    cfg: GitHubPagesConfig,
    local_dir: Path,
    *,
    create_repo_if_missing: bool = False,
) -> tuple[bool, str, str | None]:
    """
    Upload every file under ``local_dir`` to ``cfg.branch`` via the Contents API.

    Returns ``(ok, message, pages_base_url_or_none)``.
    """
    if not cfg.token.strip():
        return False, "GitHub token is empty.", None
    if not cfg.owner.strip() or not cfg.repo.strip():
        return False, "Owner and repository name are required.", None

    local_dir = local_dir.resolve()
    if not local_dir.is_dir():
        return False, f"Not a directory: {local_dir}", None

    if create_repo_if_missing:
        ok_r, err_r = ensure_repo_exists(cfg)
        if not ok_r:
            return False, err_r, None

    files = iter_site_files(local_dir)
    if not files:
        return False, "No files to upload.", None

    uploaded = 0
    for rel, raw in files:
        ok, err = _put_file(cfg, rel, raw, f"QStoryMap: update {rel}")
        if not ok:
            return False, f"GitHub upload failed: {err}", None
        uploaded += 1

    tip = (
        f"Uploaded {uploaded} file(s). Enable GitHub Pages on this repo "
        f"(Settings → Pages → Branch: {cfg.branch or 'gh-pages'}, folder / (root)) if you have not already."
    )
    return True, tip, cfg.pages_url()
