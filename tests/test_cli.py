"""Agenten-Ablauf über die Kommandozeile: analyze → grades → task."""

import json

from typer.testing import CliRunner

from repo_radar.cli import app

from test_analysis import TS_FILES

runner = CliRunner()


def test_analyze_grades_and_task(repo, tmp_path):
    repo.commit(TS_FILES)
    out = tmp_path / "out"
    res = runner.invoke(app, ["analyze", str(repo.root), "-q", "--no-dup", "-o", str(out)])
    assert res.exit_code == 0, res.output
    assert res.stderr == ""  # -q: nur das Ergebnis
    assert "| Note | Metrik | Schlüssel | Kennwert | Fundstellen |" in res.stdout
    assert "`cycles`" in res.stdout and str((out / "report.html").resolve()) in res.stdout

    res = runner.invoke(app, ["grades", str(out)])
    assert res.exit_code == 0 and "`complexity`" in res.stdout

    res = runner.invoke(app, ["task", str(out), "cycles", "-n", "1"])
    assert res.exit_code == 0, res.output
    md = (out / "auftrag-cycles.md").read_text(encoding="utf-8")
    assert md.startswith("# Arbeitsauftrag: Zyklische Abhängigkeiten verbessern")
    assert "- [ ] 1. Zyklus #1 (3 Dateien" in md
    assert "  - apps/web/src/cyc/x.ts -> apps/web/src/cyc/y.ts" in md
    assert "- [ ] Alle bestehenden Tests laufen grün" in md

    # vorhandene Checkliste (evtl. mit Fortschritt) bleibt ohne --force erhalten
    res = runner.invoke(app, ["task", str(out), "cycles"])
    assert res.exit_code == 2 and "--force" in res.stderr
    assert runner.invoke(app, ["task", str(out), "cycles", "--force", "-o", str(tmp_path / "a.md")]).exit_code == 0


def test_task_errors_name_valid_metrics(repo, tmp_path):
    repo.commit(TS_FILES)
    out = tmp_path / "out"
    assert runner.invoke(app, ["analyze", str(repo.root), "-q", "--no-dup", "-o", str(out)]).exit_code == 0

    res = runner.invoke(app, ["task", str(out), "gibtsnicht"])
    assert res.exit_code == 2 and "complexity" in res.stderr

    res = runner.invoke(app, ["task", str(out), "duplication"])  # nicht gemessen → keine Fundstellen
    assert res.exit_code == 1 and "Metriken mit Fundstellen" in res.stderr

    data = json.loads((out / "analysis.json").read_text(encoding="utf-8"))
    data["schema"] = 1
    (out / "analysis.json").write_text(json.dumps(data), encoding="utf-8")
    res = runner.invoke(app, ["grades", str(out)])
    assert res.exit_code == 2 and "neu analysieren" in res.stderr
