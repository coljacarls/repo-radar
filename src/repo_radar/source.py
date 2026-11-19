"""Repo finden oder klonen, Dateien über git auflisten."""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

CACHE_DIR = Path.home() / ".cache" / "repo-radar" / "repos"


class SourceError(RuntimeError):
    pass


def git(repo: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", "-c", "core.quotePath=false", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and proc.returncode != 0:
        raise SourceError(f"git {' '.join(args)} fehlgeschlagen: {proc.stderr.strip()}")
    return proc.stdout


@dataclass
class RepoSource:
    root: Path  # Wurzel des Git-Repos
    subdir: str  # "" oder relativer Unterpfad, auf den die Analyse beschränkt ist
    name: str
    url: str | None
    head: str  # "" bei Repos ohne Commits
    branch: str
    head_time: int  # Referenzzeitpunkt für Alter/Zeitfenster; ohne Commits: jetzt
    untracked: bool = False  # auch ungetrackte (nicht ignorierte) Dateien analysieren

    @property
    def has_commits(self) -> bool:
        return bool(self.head)


def is_url(target: str) -> bool:
    return bool(re.match(r"^(https?://|ssh://|git@|file://)", target))


def _slug(url: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", re.sub(r"^\w+://", "", url)).strip("_")[:120]


def _clone_or_update(url: str, cache: Path) -> Path:
    dest = cache / _slug(url)
    if (dest / ".git").exists():
        git(dest, "fetch", "--quiet", "--prune", "origin")
        git(dest, "remote", "set-head", "origin", "--auto", check=False)
        git(dest, "reset", "--quiet", "--hard", "origin/HEAD")
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            ["git", "clone", "--quiet", "--no-recurse-submodules", url, str(dest)],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise SourceError(f"Klonen fehlgeschlagen: {proc.stderr.strip()}")
    return dest


def open_source(target: str, cache: Path = CACHE_DIR, untracked: bool = False) -> RepoSource:
    url = None
    if is_url(target):
        url = target
        path = _clone_or_update(target, cache)
    else:
        path = Path(target).expanduser().resolve()
        if not path.exists():
            raise SourceError(f"Pfad existiert nicht: {path}")
    top = git(path if path.is_dir() else path.parent, "rev-parse", "--show-toplevel", check=False).strip()
    if not top:
        raise SourceError(f"Kein Git-Repository: {path}")
    root = Path(top)
    subdir = "" if path == root else path.relative_to(root).as_posix()
    head = git(root, "rev-parse", "--verify", "--quiet", "HEAD", check=False).strip()
    if head:
        branch = git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()
        head_time = int(git(root, "log", "-1", "--format=%ct").strip())
    else:
        # Repo ohne Commits: Arbeitsverzeichnis analysieren, Historie entfällt
        branch = git(root, "symbolic-ref", "--short", "HEAD", check=False).strip() or "?"
        head_time = int(time.time())
        untracked = True
    if url is None:
        url = git(root, "remote", "get-url", "origin", check=False).strip() or None
    base = re.sub(r"\.git$", "", url.rstrip("/").rsplit("/", 1)[-1].rsplit(":", 1)[-1]) if is_url(target) and url else root.name
    name = base if not subdir else f"{base}/{subdir}"
    return RepoSource(root, subdir, name, url, head, branch, head_time, untracked)


def list_tracked_files(src: RepoSource) -> list[str]:
    """Getrackte Dateien; mit `untracked` zusätzlich ungetrackte, die nicht per .gitignore ausgeschlossen sind."""
    args = ["ls-files", "-z", "--cached"]
    if src.untracked:
        args += ["--others", "--exclude-standard"]
    if src.subdir:
        args += ["--", src.subdir]
    out = git(src.root, *args)
    return [p for p in out.split("\0") if p and (src.root / p).is_file()]
