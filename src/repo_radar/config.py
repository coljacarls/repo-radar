"""Defaults und Laden der optionalen `radar.toml`."""

from __future__ import annotations

import copy
import re
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any

DEFAULT_EXCLUDES = [
    "**/node_modules/**",
    "**/dist/**",
    "**/build/**",
    "**/out/**",
    "**/target/**",
    "**/coverage/**",
    "**/.angular/**",
    "**/.nx/**",
    "**/vendor/**",
    "**/third_party/**",
    "**/__pycache__/**",
    "**/.venv/**",
    "**/venv/**",
    "**/*.min.js",
    "**/*.bundle.js",
    "**/*.d.ts",
    "**/*_pb2.py",
    "**/*_pb2_grpc.py",
    "**/*.pb.go",
    "**/*.generated.*",
    "**/generated/**",
    # Migrationen sind meist generiert und werden nach dem Anlegen nicht mehr gepflegt
    "**/migrations/**",
    "**/pb_migrations/**",
    "**/db/migrate/**",
]

# Schwellwerte: "Literatur" = SIG-Wartbarkeitsmodell (Heitlager/Kuipers/Visser 2007,
# Baggen et al. 2012), "Heuristik" = eigene, offen dokumentierte Setzung.
DEFAULTS: dict[str, Any] = {
    "analysis": {
        "exclude": [],
        # zusätzliche Globs für Testcode (zählt nicht in Noten und Graph-Metriken), z. B. ["integration/**"]
        "test_globs": [],
        "max_file_bytes": 1_000_000,
        "duplication": True,
        "min_dup_tokens": 50,
    },
    "history": {
        "since": "12 months",
        "max_files_per_commit": 50,
        "min_shared_commits": 5,
        "min_degree": 0.3,
        "hidden_min_degree": 0.5,
        "fix_pattern": r"\b(fix(e[sd])?|bug|hotfix|patch|fehler|behoben|korrigiert)\b",
    },
    "grades": {
        # Risiko-Kategorien je Funktion (CCN) und erlaubter NLOC-Anteil je Note
        "complexity": {
            "risk": [10, 20, 50],
            "profile": {"A": [25, 0, 0], "B": [30, 5, 0], "C": [40, 10, 0], "D": [50, 15, 5]},
        },
        "unit_size": {
            "risk": [15, 30, 60],
            "profile": {
                "A": [19.5, 10.9, 3.9],
                "B": [26.0, 15.5, 6.5],
                "C": [34.1, 22.2, 11.0],
                "D": [45.9, 31.4, 18.1],
            },
        },
        "duplication": {"ladder": [3, 5, 10, 20]},
        "coupling": {"ladder": [10, 20, 30, 45]},
        "cycles": {"ladder": [0, 3, 8, 15]},
        "cohesion": {"ladder": [10, 20, 35, 50]},
        "change_coupling": {"ladder": [2, 5, 10, 20], "min_commits": 20},
        "knowledge": {"owner_share": 0.25},
    },
}


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path: Path | None) -> dict[str, Any]:
    if path is None:
        return copy.deepcopy(DEFAULTS)
    with path.open("rb") as fh:
        return _merge(DEFAULTS, tomllib.load(fh))


@lru_cache(maxsize=512)
def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Glob mit `**`-Unterstützung (Pfade immer mit `/`)."""
    i, out = 0, []
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def matches_any(path: str, patterns: list[str]) -> bool:
    return any(glob_to_regex(p).match(path) for p in patterns)
