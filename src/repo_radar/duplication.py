"""Duplikation über jscpd (per npx). Fehlt Node, wird die Dimension als „nicht gemessen“ markiert."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .config import DEFAULT_EXCLUDES

JSCPD_VERSION = "4.0.5"


@dataclass
class Duplication:
    measured: bool
    reason: str = ""
    clones: list[dict] = field(default_factory=list)
    dup_lines: dict[str, int] = field(default_factory=dict)


def _merge_ranges(ranges: list[tuple[int, int]]) -> int:
    total, cur_s, cur_e = 0, None, None
    for s, e in sorted(ranges):
        if cur_e is None or s > cur_e + 1:
            if cur_e is not None:
                total += cur_e - cur_s + 1
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    if cur_e is not None:
        total += cur_e - cur_s + 1
    return total


def analyze(root: Path, analyzed: set[str], cfg: dict) -> Duplication:
    if not cfg["analysis"]["duplication"]:
        return Duplication(False, "per Konfiguration deaktiviert")
    npx = shutil.which("npx")
    if npx is None:
        return Duplication(False, "npx nicht gefunden (Node.js fehlt)")
    ignore = ",".join(DEFAULT_EXCLUDES + list(cfg["analysis"]["exclude"]))
    # Eigenes, leeres Arbeitsverzeichnis: npx soll keine .npmrc/node_modules des analysierten Repos nutzen
    with tempfile.TemporaryDirectory(prefix="repo-radar-") as tmp:
        cmd = [
            npx, "--yes", f"jscpd@{JSCPD_VERSION}", "--silent", "--gitignore",
            "--min-tokens", str(cfg["analysis"]["min_dup_tokens"]),
            "--reporters", "json", "--output", tmp, "--ignore", ignore, str(root),
        ]  # fmt: skip
        try:
            subprocess.run(cmd, cwd=tmp, capture_output=True, text=True, timeout=900)
            data = json.loads((Path(tmp) / "jscpd-report.json").read_text(encoding="utf-8"))
        except (subprocess.TimeoutExpired, OSError, ValueError) as exc:
            return Duplication(False, f"jscpd fehlgeschlagen: {type(exc).__name__}")
        base = os.path.realpath(tmp)

    prefix = os.path.realpath(root).rstrip("/") + "/"

    def rel(name: str) -> str:
        # jscpd meldet Pfade relativ zu seinem Arbeitsverzeichnis
        full = os.path.normpath(os.path.join(base, name))
        return full[len(prefix) :] if full.startswith(prefix) else name

    ranges: dict[str, list[tuple[int, int]]] = {}
    clones = []
    for d in data.get("duplicates", []):
        a, b = d["firstFile"], d["secondFile"]
        pa, pb = rel(a["name"]), rel(b["name"])
        if pa not in analyzed or pb not in analyzed:
            continue
        clones.append(
            {"a": pa, "a_start": a["start"], "a_end": a["end"], "b": pb, "b_start": b["start"], "b_end": b["end"], "lines": d["lines"]}
        )
        ranges.setdefault(pa, []).append((a["start"], a["end"]))
        ranges.setdefault(pb, []).append((b["start"], b["end"]))
    clones.sort(key=lambda c: -c["lines"])
    return Duplication(True, "", clones[:3000], {p: _merge_ranges(r) for p, r in ranges.items()})
