"""Welche Dateien werden analysiert, in welcher Sprache, zu welchem Projekt gehören sie."""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass, field
from pathlib import Path

from .config import DEFAULT_EXCLUDES, matches_any

# Endung -> (Sprachkennung, Anzeigename). Nur Sprachen, die lizard versteht.
LANGUAGES: dict[str, tuple[str, str]] = {
    ".ts": ("typescript", "TypeScript"),
    ".mts": ("typescript", "TypeScript"),
    ".cts": ("typescript", "TypeScript"),
    ".tsx": ("tsx", "TypeScript"),
    ".js": ("javascript", "JavaScript"),
    ".jsx": ("javascript", "JavaScript"),
    ".mjs": ("javascript", "JavaScript"),
    ".cjs": ("javascript", "JavaScript"),
    ".java": ("java", "Java"),
    ".py": ("python", "Python"),
    ".kt": ("kotlin", "Kotlin"),
    ".go": ("go", "Go"),
    ".cs": ("csharp", "C#"),
    ".rb": ("ruby", "Ruby"),
    ".php": ("php", "PHP"),
    ".swift": ("swift", "Swift"),
    ".rs": ("rust", "Rust"),
    ".scala": ("scala", "Scala"),
    ".c": ("c", "C"),
    ".h": ("c", "C"),
    ".cpp": ("cpp", "C++"),
    ".cc": ("cpp", "C++"),
    ".hpp": ("cpp", "C++"),
    ".lua": ("lua", "Lua"),
    ".vue": ("vue", "Vue"),
}

# Sprachen mit Import-Auflösung (struktureller Graph)
DEP_FAMILY = {
    "typescript": "ts",
    "tsx": "ts",
    "javascript": "ts",
    "java": "java",
    "python": "python",
}

PROJECT_MARKERS = {
    "project.json",
    "package.json",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "go.mod",
    "Cargo.toml",
}

_TEST_NAME = re.compile(
    r"(\.(spec|test|e2e-spec|cy)\.[cm]?[jt]sx?$)|(^test_.*\.py$)|(_test\.(py|go)$)"
    r"|((Test|Tests|IT|Spec)\.(java|kt)$)|(_spec\.rb$)"
)
_TEST_DIR = re.compile(r"(^|/)(__tests__|tests?|e2e|cypress|playwright|testing|src/test)(/|$)")


def is_test_file(path: str) -> bool:
    name = posixpath.basename(path)
    return bool(_TEST_NAME.search(name) or _TEST_DIR.search(posixpath.dirname(path)))


@dataclass
class SourceFile:
    path: str
    lang: str
    lang_name: str
    project: str
    package: str
    is_test: bool


@dataclass
class Inventory:
    files: list[SourceFile]
    tracked: set[str]  # alle getrackten Dateien (auch nicht analysierte), für Auflösung/Configs
    projects: list[str]
    skipped: dict[str, int] = field(default_factory=dict)


def build_inventory(root: Path, tracked: list[str], cfg: dict) -> Inventory:
    excludes = DEFAULT_EXCLUDES + list(cfg["analysis"]["exclude"])
    max_bytes = cfg["analysis"]["max_file_bytes"]
    test_globs = list(cfg["analysis"].get("test_globs", []))
    project_dirs = sorted(
        {posixpath.dirname(p) for p in tracked if posixpath.basename(p) in PROJECT_MARKERS and not matches_any(p, excludes)},
        key=len,
        reverse=True,
    )
    skipped = {"excluded": 0, "too_large": 0, "other_language": 0}
    files: list[SourceFile] = []
    for path in tracked:
        ext = posixpath.splitext(path)[1].lower()
        if ext not in LANGUAGES:
            skipped["other_language"] += 1
            continue
        if matches_any(path, excludes):
            skipped["excluded"] += 1
            continue
        if (root / path).stat().st_size > max_bytes:
            skipped["too_large"] += 1
            continue
        lang, lang_name = LANGUAGES[ext]
        project = next((d for d in project_dirs if d == "" or path.startswith(d + "/")), "")
        files.append(
            SourceFile(
                path=path,
                lang=lang,
                lang_name=lang_name,
                project=project or ".",
                package=posixpath.dirname(path) or ".",
                is_test=is_test_file(path) or matches_any(path, test_globs),
            )
        )
    files.sort(key=lambda f: f.path)
    projects = sorted({f.project for f in files})
    return Inventory(files=files, tracked=set(tracked), projects=projects, skipped=skipped)
