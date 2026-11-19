"""Kommandozeile: `repo-radar analyze <pfad|url>`."""

from __future__ import annotations

import json
import re
import sys
import time
import webbrowser
from pathlib import Path
from typing import Annotated, Optional

import typer

from . import __version__
from .config import load_config
from .pipeline import run
from .report.build import build_report
from .source import SourceError, open_source

app = typer.Typer(add_completion=False, help="Codequalität und Kopplung von Git-Repos analysieren.")


def _log(msg: str) -> None:
    print(msg, file=sys.stderr)


@app.command()
def analyze(
    target: Annotated[str, typer.Argument(help="Lokaler Pfad (Repo oder Unterordner) oder Git-URL")],
    out: Annotated[Optional[Path], typer.Option("--out", "-o", help="Ausgabeordner (Default: ./radar-out/<name>)")] = None,
    since: Annotated[Optional[str], typer.Option(help="Zeitfenster der Historie: '12 months', '6m', '2y', '2025-01-01', 'all'")] = None,
    config: Annotated[Optional[Path], typer.Option("--config", "-c", help="radar.toml mit Schwellwerten/Excludes")] = None,
    exclude: Annotated[Optional[list[str]], typer.Option("--exclude", "-x", help="Zusätzliche Glob-Excludes (mehrfach)")] = None,
    tests: Annotated[Optional[list[str]], typer.Option("--tests", "-t", help="Zusätzliche Globs für Testcode, z. B. 'integration/**' (mehrfach)")] = None,
    untracked: Annotated[bool, typer.Option("--untracked", "-u", help="Auch ungetrackte, nicht ignorierte Dateien analysieren")] = False,
    no_dup: Annotated[bool, typer.Option("--no-dup", help="Duplikationsanalyse (jscpd/npx) überspringen")] = False,
    workers: Annotated[Optional[int], typer.Option(help="Parallele Prozesse fürs Parsen")] = None,
    open_report: Annotated[bool, typer.Option("--open", help="Report danach im Browser öffnen")] = False,
) -> None:
    """Analysiert ein Repository und schreibt report.html und analysis.json."""
    if config is None and Path("radar.toml").exists():
        config = Path("radar.toml")
    cfg = load_config(config)
    if since:
        cfg["history"]["since"] = since
    if exclude:
        cfg["analysis"]["exclude"] = list(cfg["analysis"]["exclude"]) + exclude
    if tests:
        cfg["analysis"]["test_globs"] = list(cfg["analysis"]["test_globs"]) + tests
    if no_dup:
        cfg["analysis"]["duplication"] = False
    try:
        src = open_source(target, untracked=untracked)
    except SourceError as exc:
        _log(f"Fehler: {exc}")
        raise typer.Exit(2) from exc

    rev = src.head[:10] if src.has_commits else "noch keine Commits"
    extra = " · inkl. ungetrackter Dateien" if src.untracked else ""
    _log(f"repo-radar {__version__} · {src.name} @ {rev} ({src.branch}){extra}")
    t0 = time.time()
    data = run(src, cfg, _log, workers)
    out_dir = out or Path("radar-out") / re.sub(r"[^A-Za-z0-9._-]+", "_", src.name)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "analysis.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    report = out_dir / "report.html"
    build_report(data, report)
    _log(f"Fertig in {time.time() - t0:.1f} s")
    for g in data["grades"]:
        _log(f"  {g['grade'] or '–'}  {g['label']}: {g['value']}")
    print(report.resolve())
    if open_report:
        webbrowser.open(report.resolve().as_uri())


@app.command()
def version() -> None:
    """Version ausgeben."""
    print(__version__)


def main() -> None:
    app()
