"""Arbeitsaufträge für KI-Agenten je Note: kurze Anweisung + Fundstellen (wichtigste zuerst).

Einzige Quelle der Prompt-Texte. Die Pipeline hängt das Ergebnis von `build` an jede Note (`grade["prompt"]`),
der Report (report/prompt.js) setzt daraus den Prompt im Dialog zusammen, `repo-radar task` schreibt daraus
ein Markdown mit Checkliste. Die Reihenfolge der Fundstellen ist die von scoring.py („Größte Beiträge“),
hier wird nur auf echte Befunde gefiltert und formatiert.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable

Ref = dict  # {"text": str, "sub": list[str]}


def _pct(x: float) -> str:
    return f"{x * 100:.1f}".replace(".", ",").removesuffix(",0") + " %"


def _range(t: dict) -> str:
    if not t.get("line"):
        return ""
    end = t.get("end")
    return f":{t['line']}-{end}" if end and end != t["line"] else f":{t['line']}"


def _ref(text: str, sub: list[str] | None = None) -> Ref:
    return {"text": text, "sub": sub or []}


def _cycle_ref(t: dict, data: dict) -> Ref:
    files = data["files"]
    members = data["cycles"][t["cycle"]]
    in_cycle = set(members)
    targets: dict[int, list[str]] = {}
    for a, b, weak in data["edges"]:  # nur starke Kanten, wie bei der Zyklenmessung
        if not weak and a in in_cycle and b in in_cycle:
            targets.setdefault(a, []).append(files[b]["path"])
    sub = [f"{files[fi]['path']} -> {', '.join(targets.get(fi, []))}" for fi in members]
    return _ref(f"Zyklus #{t['cycle'] + 1} ({len(members)} Dateien, Imports innerhalb des Zyklus)", sub)


def _cohesion_ref(t: dict) -> Ref:
    groups = " | ".join(f"[{', '.join(g)}]" for g in t.get("groups", []))
    iso = f"; ohne Instanzbezug: {', '.join(t['isolated'])}" if t.get("isolated") else ""
    return _ref(f"{t['file']}{_range(t)} · Klasse {t['label']} (LCOM4 {t['value']}; Gruppen aus Methoden und Feldern: {groups}{iso})")


class _Spec:
    def __init__(self, task: Callable[[dict, dict], str], ref: Callable[[dict, dict], Ref], keep: Callable[[dict, dict], bool] = lambda t, g: True):
        self.task, self.ref, self.keep = task, ref, keep


SPECS: dict[str, _Spec] = {
    "complexity": _Spec(
        lambda c, m: (
            f"Senke die zyklomatische Komplexität (McCabe-CCN) der folgenden Funktionen auf möglichst ≤ {c['complexity']['risk'][0]}, "
            "ohne ihr Verhalten zu ändern. Zerlege sie in kleine, sprechend benannte Hilfsfunktionen, ersetze tiefe Verschachtelung "
            "durch Guard Clauses und lange if/else- oder switch-Ketten durch Lookup-Tabellen oder Polymorphie. "
            "Sichere das Verhalten vorher mit Tests ab, falls keine vorhanden sind."
        ),
        lambda t, d: _ref(f"{t['file']}{_range(t)} · {t['label']} (CCN {t['value']}, {t['nloc']} NLOC)"),
        lambda t, c: t["value"] > c["complexity"]["risk"][0],
    ),
    "unit_size": _Spec(
        lambda c, m: (
            f"Kürze die folgenden Funktionen auf möglichst ≤ {c['unit_size']['risk'][0]} NLOC, ohne ihr Verhalten zu ändern. "
            "Extrahiere zusammenhängende Abschnitte in eigene, sprechend benannte Funktionen mit klaren Parametern und "
            "Rückgabewerten, statt den Code nur umzubrechen. Sichere das Verhalten vorher mit Tests ab, falls keine vorhanden sind."
        ),
        lambda t, d: _ref(f"{t['file']}{_range(t)} · {t['label']} ({t['value']} NLOC, CCN {t['ccn']})"),
        lambda t, c: t["value"] > c["unit_size"]["risk"][0],
    ),
    "duplication": _Spec(
        lambda c, m: (
            "Beseitige die folgenden Code-Duplikate. Prüfe je Paar, ob beide Stellen fachlich dasselbe tun; wenn ja, extrahiere "
            "die gemeinsame Logik in eine Funktion oder ein Modul an passender Stelle und nutze sie an beiden Stellen. "
            "Bewusst getrennte Varianten, die sich fachlich auseinanderentwickeln werden, lässt du stehen und begründest das kurz."
        ),
        lambda t, d: _ref(f"{t['file']}:{t['line']}-{t['end']} <-> {t['other']}:{t['other_line']}-{t['other_end']} ({t['value']} Zeilen)"),
    ),
    "coupling": _Spec(
        lambda c, m: (
            "Senke die strukturelle Kopplung rund um die folgenden Dateien: Von ihnen hängen viele Dateien direkt oder transitiv ab, "
            "eine Änderung dort strahlt also weit aus. Prüfe, welche Imports nur einzelne Hilfsfunktionen oder Typen nutzen, "
            "teile zu breite Module nach Verantwortung auf und führe Abhängigkeiten über schmale Schnittstellen. "
            "Bewusst zentrale, stabile Basistypen bleiben, wie sie sind."
        ),
        lambda t, d: _ref(f"{t['file']} (Änderungsreichweite {t['value']} Dateien, Fan-in {t['ca']}, Fan-out {t['ce']})"),
        lambda t, c: t["value"] > 0,
    ),
    "cycles": _Spec(
        lambda c, m: (
            "Löse die folgenden zyklischen Import-Abhängigkeiten auf. Suche je Zyklus die Kante, die gegen die gewünschte "
            "Schichtung zeigt, und kehre sie um: gemeinsam genutzten Code in ein eigenes Modul verschieben, eine Schnittstelle "
            "in die untere Schicht legen (Dependency Inversion) oder Callbacks/Events statt direkter Imports nutzen. "
            "Weiche nicht auf Lazy- oder reine Typ-Imports aus, nur damit der Zyklus aus der Messung fällt."
        ),
        _cycle_ref,
    ),
    "cohesion": _Spec(
        lambda c, m: (
            "Prüfe die folgenden Klassen mit LCOM4 > 1: Sie zerfallen in Gruppen von Methoden, die weder gemeinsame Felder nutzen "
            "noch sich gegenseitig aufrufen. Gehören die Gruppen fachlich nicht zusammen, extrahiere sie in eigene Klassen und "
            "passe die Aufrufer an. Ist die Trennung nur ein Messartefakt (z. B. Delegation über ein anderes Objekt), lass die "
            "Klasse stehen und begründe das kurz."
        ),
        lambda t, d: _cohesion_ref(t),
    ),
    "change_coupling": _Spec(
        lambda c, m: (
            "Untersuche die folgenden Dateipaare: Sie werden laut Git-Historie oft gemeinsam geändert, importieren sich aber nicht "
            "direkt. Finde je Paar den gemeinsamen Änderungsgrund (git log -- <a> <b>), etwa geteilte Annahmen, Formate, "
            "Konstanten oder kopierte Logik, und mache die Abhängigkeit explizit: gemeinsamen Typ, gemeinsame Konstante oder "
            "gemeinsames Modul einführen oder Logik zusammenlegen. Ist die Kopplung gewollt (z. B. Code und zugehörige Doku), "
            "notiere das kurz."
        ),
        lambda t, d: _ref(f"{t['file']} <-> {t['other']} (Kopplungsgrad {_pct(t['degree'])}, {t['shared']} gemeinsame Commits)"),
    ),
    "knowledge": _Spec(
        lambda c, m: (
            f"Die folgenden Dateien wurden fast ausschließlich von einer Person geändert (Truck-Factor {m['truck_factor']}). Verringere das "
            "Wissensrisiko, ohne Verhalten zu ändern: Halte Absicht, Randfälle und Zusammenspiel in Docstrings oder einer kurzen "
            "Modul-README fest, kommentiere nicht offensichtliche Stellen und ergänze Tests, die das erwartete Verhalten dokumentieren."
        ),
        lambda t, d: _ref(f"{t['file']} ({_pct(t['share'])} der Commits von einer Person, {t['commits']} Commits, {t['nloc']} NLOC)"),
    ),
}


def _where(meta: dict) -> str:
    return f"Commit {meta['head'][:10]}" if meta.get("head") else "dem analysierten Arbeitsstand"


def build(grade: dict, data: dict) -> dict | None:
    """Prompt-Bausteine einer Note oder None, wenn es nichts zu tun gibt (nicht bewertet, keine Befunde)."""
    spec = SPECS.get(grade["key"])
    if spec is None or grade["grade"] is None:
        return None
    cfg = data["meta"]["config"]["grades"]
    refs = [spec.ref(t, data) for t in grade.get("top", []) if spec.keep(t, cfg)]
    if not refs:
        return None
    task = spec.task(cfg, data["meta"])
    situation = f"Ausgangslage: repo-radar bewertet „{grade['label']}“ mit {grade['grade']} ({grade['value']})."
    return {
        "task": task,
        "situation": situation,
        # Für den Prompt im Report: Anweisung + Ausgangslage, danach folgen Kopfzeile und nummerierte Fundstellen
        "intro": "\n".join([task, "Arbeite die Fundstellen der Reihe nach ab, halte jede Änderung klein und lass danach die bestehenden Tests laufen.", situation]),
        "refs_header": f"Fundstellen, wichtigste zuerst (Pfade relativ zur Repository-Wurzel, Zeilen laut {_where(data['meta'])}):",
        "refs": refs,
    }


def attach(data: dict) -> None:
    for g in data["grades"]:
        g["prompt"] = build(g, data)


def find_grade(data: dict, key: str) -> dict | None:
    key = key.strip().lower()
    return next((g for g in data["grades"] if key in (g["key"], g["label"].lower())), None)


# ---------------------------------------------------------------------------- Ausgaben für die Kommandozeile


def summary_markdown(data: dict) -> str:
    """Notentabelle für Mensch und Agent: Note, Metrik, Schlüssel für `repo-radar task`, Kennwert, Fundstellen."""
    m = data["meta"]
    rev = f"{m['head'][:10]} ({m['branch']})" if m.get("head") else f"{m['branch']}, noch keine Commits"
    rows = [
        "| Note | Metrik | Schlüssel | Kennwert | Fundstellen |",
        "| --- | --- | --- | --- | ---: |",
    ]
    for g in data["grades"]:
        p = g.get("prompt") if "prompt" in g else build(g, data)
        rows.append(f"| {g['grade'] or '–'} | {g['label']} | `{g['key']}` | {g['value']} | {len(p['refs']) if p else 0} |")
    return f"repo-radar {m['tool_version']} · {m['name']} @ {rev}\n\n" + "\n".join(rows)


def task_markdown(grade: dict, data: dict, count: int) -> str:
    """Arbeitsauftrag als Markdown: Auftrag, Hintergrund der Metrik und Checkliste der Fundstellen."""
    p = build(grade, data)
    if p is None:
        raise ValueError(f"Für „{grade['label']}“ gibt es keine Fundstellen ({grade['value']}).")
    m = data["meta"]
    refs = p["refs"][:count]
    analyzed = datetime.fromisoformat(m["analyzed_at"]).strftime("%d.%m.%Y")
    rev = f"{m['head'][:10]} ({m['branch']})" if m.get("head") else f"{m['branch']}, noch keine Commits"
    lines = [
        f"# Arbeitsauftrag: {grade['label']} verbessern",
        "",
        f"repo-radar {m['tool_version']} · {m['name']} @ {rev} · analysiert am {analyzed} · {len(refs)} von {len(p['refs'])} Fundstellen",
        "",
        "## Auftrag",
        "",
        p["task"],
        "",
        "Arbeite die Checkliste von oben nach unten ab und halte jede Änderung klein. Lass nach jeder Fundstelle die bestehenden "
        "Tests laufen und hake sie hier ab (`- [x]`). Lässt du eine Fundstelle bewusst aus, hake sie trotzdem ab und schreib den "
        "Grund dahinter.",
        "",
        p["situation"],
        "",
        f"Pfade sind relativ zur Repository-Wurzel, Zeilennummern gelten für {_where(m)}. Sobald du eine Datei änderst, verschieben "
        "sich ihre Zeilen; orientiere dich dann am Funktions-, Klassen- oder Dateinamen.",
        "",
        f"## Hintergrund: {grade['label']}",
        "",
        grade["explanation"],
        "",
        "## Checkliste",
        "",
    ]
    for i, r in enumerate(refs, 1):
        lines.append(f"- [ ] {i}. {r['text']}")
        lines.extend(f"  - {s}" for s in r["sub"])
    lines += [
        "- [ ] Alle bestehenden Tests laufen grün",
        f"- [ ] repo-radar erneut ausführen und die neue Note für „{grade['label']}“ notieren (vorher: {grade['grade']})",
        "",
    ]
    return "\n".join(lines)
