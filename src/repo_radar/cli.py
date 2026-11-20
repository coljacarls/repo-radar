"""Kommandozeile: `repo-radar analyze <pfad|url>`, `grades <report>`, `task <report> <metrik>`.

Fortschritt und Fehler gehen nach stderr, Ergebnisse (Notentabelle, Pfade) nach stdout, damit Agenten und Skripte
nur das Ergebnis auswerten müssen.
"""

from __future__ import annotations

import json
import re
import sys
import time
import webbrowser
from pathlib import Path
from typing import Annotated, Optional

import typer

from . import __version__, prompts
from .config import load_config
from .pipeline import SCHEMA_VERSION, run
from .report.build import build_report
from .source import SourceError, open_source

app = typer.Typer(add_completion=False, help="Codequalität und Kopplung von Git-Repos analysieren.")


def _log(msg: str) -> None:
    print(msg, file=sys.stderr)


def _fail(msg: str, code: int = 2) -> typer.Exit:
    _log(f"Fehler: {msg}")
    return typer.Exit(code)


def _print_summary(data: dict, out_dir: Path) -> None:
    print(prompts.summary_markdown(data))
    print()
    print(f"Report: {(out_dir / 'report.html').resolve()}")
    print(f"Daten:  {(out_dir / 'analysis.json').resolve()}")


def _load(report: Path) -> tuple[dict, Path]:
    """Analyse laden: Ausgabeordner, analysis.json oder report.html daneben."""
    path = report / "analysis.json" if report.is_dir() else report.with_name("analysis.json") if report.suffix == ".html" else report
    if not path.is_file():
        raise _fail(f"{path} nicht gefunden. Erst `repo-radar analyze` ausführen.")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema", 1) < SCHEMA_VERSION:
        raise _fail(f"{path} stammt von einer älteren repo-radar-Version. Bitte neu analysieren.")
    return data, path.parent


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
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Keine Fortschrittsmeldungen, nur das Ergebnis")] = False,
) -> None:
    """Analysiert ein Repository, schreibt report.html und analysis.json und gibt die Noten aus."""
    log = (lambda _m: None) if quiet else _log
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
        raise _fail(str(exc)) from exc

    rev = src.head[:10] if src.has_commits else "noch keine Commits"
    extra = " · inkl. ungetrackter Dateien" if src.untracked else ""
    log(f"repo-radar {__version__} · {src.name} @ {rev} ({src.branch}){extra}")
    t0 = time.time()
    data = run(src, cfg, log, workers)
    out_dir = out or Path("radar-out") / re.sub(r"[^A-Za-z0-9._-]+", "_", src.name)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "analysis.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    report = out_dir / "report.html"
    build_report(data, report)
    log(f"Fertig in {time.time() - t0:.1f} s\n")
    _print_summary(data, out_dir)
    if open_report:
        webbrowser.open(report.resolve().as_uri())


@app.command()
def grades(
    report: Annotated[Path, typer.Argument(help="Ausgabeordner von `analyze` (oder dessen analysis.json)")],
) -> None:
    """Noten einer vorhandenen Analyse ausgeben, ohne neu zu analysieren."""
    data, out_dir = _load(report)
    _print_summary(data, out_dir)


@app.command()
def task(
    report: Annotated[Path, typer.Argument(help="Ausgabeordner von `analyze` (oder dessen analysis.json)")],
    metric: Annotated[str, typer.Argument(help="Schlüssel der Metrik aus der Notentabelle, z. B. complexity")],
    count: Annotated[int, typer.Option("--count", "-n", min=1, help="Anzahl der Fundstellen, wichtigste zuerst")] = 3,
    out: Annotated[Optional[Path], typer.Option("--out", "-o", help="Zieldatei (Default: <report>/auftrag-<metrik>.md)")] = None,
    force: Annotated[bool, typer.Option("--force", "-f", help="Vorhandene Datei überschreiben")] = False,
) -> None:
    """Arbeitsauftrag mit Checkliste als Markdown aus einer vorhandenen Analyse erzeugen."""
    data, out_dir = _load(report)
    grade = prompts.find_grade(data, metric)
    if grade is None:
        raise _fail(f"Unbekannte Metrik „{metric}“. Gültig: {', '.join(g['key'] for g in data['grades'])}")
    try:
        text = prompts.task_markdown(grade, data, count)
    except ValueError as exc:
        available = [g["key"] for g in data["grades"] if g.get("prompt")]
        raise _fail(f"{exc} Metriken mit Fundstellen: {', '.join(available) or 'keine'}", 1) from exc
    target = out or out_dir / f"auftrag-{grade['key']}.md"
    if target.exists() and not force:
        raise _fail(f"{target} existiert schon (evtl. mit abgehakten Punkten). Mit --force überschreiben.")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    print(target.resolve())


@app.command()
def version() -> None:
    """Version ausgeben."""
    print(__version__)


def main() -> None:
    app()
