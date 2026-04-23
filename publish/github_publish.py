"""Publish a static folder to GitHub Pages using a local git push."""

from __future__ import annotations

import json
import shutil
import ssl
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


API = "https://api.github.com"
USER_AGENT = "QStoryMap-QGIS-Plugin/0.1"


# ---------------------------------------------------------------------------
# GitHub API helpers (used only for repo creation check)
# ---------------------------------------------------------------------------

def _github_error_summary(code: int, body: bytes, *, max_len: int = 280) -> str:
    if not body:
        if code == 504:
            return (
                "Gateway timeout (504): GitHub did not respond in time. "
                "Wait a minute and try again, or create the repo on github.com first."
            )
        if code in (502, 503):
            return "GitHub was temporarily unavailable (502/503). Try again shortly."
        return f"HTTP {code} (empty body)."

    text = body.decode("utf-8", errors="replace").strip()
    if text.startswith("<!DOCTYPE") or text.lstrip().lower().startswith("<html"):
        if code == 504:
            return (
                "Gateway timeout (504): GitHub's servers timed out. "
                "Retry in a minute or create the repository on GitHub manually."
            )
        if code in (502, 503):
            return "GitHub returned an error page (service busy). Try again in a few minutes."
        return f"GitHub returned an HTML error page (HTTP {code})."

    try:
        doc = json.loads(text)
        m = doc.get("message")
        if isinstance(m, str) and m.strip():
            return m.strip()
    except Exception:
        pass
    return text[:max_len] + ("…" if len(text) > max_len else "")


def _github_https_open(req: urllib.request.Request, *, timeout: int, ctx: ssl.SSLContext) -> tuple[int, bytes]:
    full = req.get_full_url()
    parsed = urllib.parse.urlparse(full)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Only https:// requests to GitHub API are allowed.")
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
    try:
        with opener.open(req, timeout=timeout) as resp:
            return resp.getcode(), resp.read()
    except urllib.error.HTTPError as e:
        body = e.read() if e.fp else b""
        return e.code, body


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
    return _github_https_open(req, timeout=timeout, ctx=ctx)


def _token_user_login(token: str) -> str | None:
    code, body = _request("GET", f"{API}/user", token)
    if code != 200:
        return None
    try:
        return str(json.loads(body.decode()).get("login") or "")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class GitHubPagesConfig:
    owner: str
    repo: str
    token: str
    branch: str = "gh-pages"

    def pages_url(self) -> str:
        o = self.owner.strip().replace("/", "")
        r = self.repo.strip().replace("/", "")
        return f"https://{o}.github.io/{r}/"


# ---------------------------------------------------------------------------
# Repo creation (API only — used when create_repo_if_missing=True)
# ---------------------------------------------------------------------------

def ensure_repo_exists(cfg: GitHubPagesConfig) -> tuple[bool, str]:
    """Create a public repo under the user account if it does not already exist."""
    o = cfg.owner.strip()
    r = cfg.repo.strip()
    check = f"{API}/repos/{urllib.parse.quote(o, safe='')}/{urllib.parse.quote(r, safe='')}"
    code, body_chk = _request("GET", check, cfg.token)
    if code == 200:
        return True, ""
    if code != 404:
        return False, f"Could not check repository ({code}): {_github_error_summary(code, body_chk)}"
    login = _token_user_login(cfg.token)
    if not login:
        return False, "Invalid or expired token (GitHub /user failed)."
    if login.lower() != o.lower():
        return (
            False,
            f"Repository not found. Auto-create only works when Owner is your login ({login}). "
            "Create the repository on GitHub first, or set Owner to match your account.",
        )
    create_url = f"{API}/user/repos"
    payload = json.dumps(
        {"name": r, "private": False, "auto_init": False, "description": "QStoryMap static site"}
    ).encode()
    code2, body2 = b"", 0
    for attempt in range(3):
        code2, body2 = _request("POST", create_url, cfg.token, data=payload, content_type="application/json")
        if code2 in (200, 201):
            return True, ""
        if code2 in (502, 503, 504) and attempt < 2:
            time.sleep(2.0 * (attempt + 1))
            continue
        break
    return False, f"Could not create repository ({code2}): {_github_error_summary(code2, body2)}"


# ---------------------------------------------------------------------------
# Git-based publish (fast — one push regardless of tile count)
# ---------------------------------------------------------------------------

def _run_git(args: list[str], cwd: Path, timeout: int = 120) -> tuple[bool, str]:
    """Run a git subcommand; return (success, output text)."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
        return False, (result.stderr.strip() or result.stdout.strip())
    except subprocess.TimeoutExpired:
        return False, "Git command timed out."
    except FileNotFoundError:
        return False, "git not found — install Git and ensure it is on your PATH."
    except Exception as e:
        return False, str(e)


def publish_folder_to_github_pages(
    cfg: GitHubPagesConfig,
    local_dir: Path,
    *,
    create_repo_if_missing: bool = False,
) -> tuple[bool, str, str | None]:
    """
    Push ``local_dir`` to ``cfg.branch`` on GitHub using a local git push.

    Much faster than the Contents API for large tile exports — everything is
    sent in a single packfile rather than one HTTP request per file.

    Returns ``(ok, message, pages_url_or_none)``.
    """
    if not cfg.token.strip():
        return False, "GitHub token is empty.", None
    if not cfg.owner.strip() or not cfg.repo.strip():
        return False, "Owner and repository name are required.", None

    local_dir = local_dir.resolve()
    if not local_dir.is_dir():
        return False, f"Not a directory: {local_dir}", None

    # Verify git is available before doing anything.
    ok, out = _run_git(["--version"], local_dir)
    if not ok:
        return False, out, None

    if create_repo_if_missing:
        ok_r, err_r = ensure_repo_exists(cfg)
        if not ok_r:
            return False, err_r, None

    branch = (cfg.branch or "gh-pages").strip()
    owner = cfg.owner.strip()
    repo = cfg.repo.strip()
    token = cfg.token.strip()

    # Always start from a clean git state so there are no stale history issues.
    git_dir = local_dir / ".git"
    if git_dir.exists():
        shutil.rmtree(git_dir, ignore_errors=True)

    ok, out = _run_git(["init"], local_dir)
    if not ok:
        return False, f"git init failed: {out}", None

    # Point HEAD at the target branch before the first commit (works on all git versions).
    _run_git(["symbolic-ref", "HEAD", f"refs/heads/{branch}"], local_dir)

    # Minimal identity required by git for a commit.
    _run_git(["config", "user.email", "qstorymap@localhost"], local_dir)
    _run_git(["config", "user.name", "QStoryMap"], local_dir)

    ok, out = _run_git(["add", "-A"], local_dir)
    if not ok:
        return False, f"git add failed: {out}", None

    ok, out = _run_git(["commit", "-m", "QStoryMap: publish story map"], local_dir)
    if not ok:
        return False, f"git commit failed: {out}", None

    # Embed token using the x-access-token scheme (GitHub-recommended for PATs in URLs).
    remote_url = f"https://x-access-token:{token}@github.com/{owner}/{repo}.git"
    ok, out = _run_git(["remote", "add", "origin", remote_url], local_dir)
    if not ok:
        return False, f"Failed to add remote: {out.replace(token, '***')}", None

    # Force-push so gh-pages is always replaced cleanly.
    ok, out = _run_git(
        ["push", "--force", "origin", f"HEAD:{branch}"],
        local_dir,
        timeout=300,
    )
    if not ok:
        return False, f"git push failed: {out.replace(token, '***')}", None

    return True, "", cfg.pages_url()
