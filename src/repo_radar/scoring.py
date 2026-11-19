"""Noten A–E je Dimension. Jede Note bringt Wert, Herkunft der Schwellwerte und Top-Befunde mit."""

from __future__ import annotations

GRADES = "ABCD"

SIG = "Literatur: SIG-Wartbarkeitsmodell (Heitlager, Kuipers & Visser 2007; Baggen et al. 2012)"
HEURISTIC = "Heuristik: eigene Setzung, in radar.toml anpassbar"


def ladder_grade(value: float, ladder: list[float]) -> str:
    for g, limit in zip(GRADES, ladder):
        if value <= limit:
            return g
    return "E"


def profile_grade(shares: list[float], table: dict[str, list[float]]) -> str:
    for g in GRADES:
        if all(s <= lim for s, lim in zip(shares, table[g])):
            return g
    return "E"


def risk_profile(functions: list[tuple[str, dict]], key: str, risk: list[int]) -> tuple[list[float], int]:
    """NLOC-Anteile (in %) der Kategorien moderat/hoch/sehr hoch."""
    total = sum(f["nloc"] for _, f in functions)
    buckets = [0, 0, 0]
    for _, f in functions:
        v = f[key]
        for i in (2, 1, 0):
            if v > risk[i]:
                buckets[i] += f["nloc"]
                break
    return ([100 * b / total for b in buckets] if total else [0.0, 0.0, 0.0]), total


def _na(key: str, label: str, reason: str) -> dict:
    return {"key": key, "label": label, "grade": None, "value": reason, "source": "", "explanation": reason, "details": [], "top": []}


def _fmt(x: float, digits: int = 1) -> str:
    return f"{x:.{digits}f}".replace(".", ",")


def compute(files: list[dict], ctx: dict, cfg: dict) -> list[dict]:
    g = cfg["grades"]
    prod = [f for f in files if not f["test"]]
    funcs = [(f["path"], fn) for f in prod for fn in f["functions"]]
    out: list[dict] = []

    # 1) Komplexität
    risk = g["complexity"]["risk"]
    shares, total = risk_profile(funcs, "ccn", risk)
    if total:
        worst = sorted(funcs, key=lambda x: -x[1]["ccn"])[:15]
        out.append(
            {
                "key": "complexity",
                "label": "Komplexität",
                "grade": profile_grade(shares, g["complexity"]["profile"]),
                "value": f"{_fmt(sum(shares))} % des Codes in Funktionen mit CCN > {risk[0]}",
                "source": SIG,
                "explanation": (
                    "Zyklomatische Komplexität (McCabe) je Funktion, eingeteilt in Risikoklassen "
                    f"moderat ({risk[0] + 1}–{risk[1]}), hoch ({risk[1] + 1}–{risk[2]}) und sehr hoch (> {risk[2]}). "
                    "Bewertet wird, welcher Anteil der Funktions-NLOC in jeder Klasse liegt. Testcode ist ausgenommen."
                ),
                "details": [
                    ["moderat", f"{_fmt(shares[0])} %"],
                    ["hoch", f"{_fmt(shares[1])} %"],
                    ["sehr hoch", f"{_fmt(shares[2])} %"],
                ],
                "thresholds": g["complexity"]["profile"],
                "top": [
                    {"file": p, "line": fn["line"], "end": fn["end"], "label": fn["name"], "value": fn["ccn"], "nloc": fn["nloc"]}
                    for p, fn in worst
                ],
            }
        )
    else:
        out.append(_na("complexity", "Komplexität", "Keine Funktionen gefunden"))

    # 2) Funktionsgröße
    risk = g["unit_size"]["risk"]
    shares, total = risk_profile(funcs, "nloc", risk)
    if total:
        worst = sorted(funcs, key=lambda x: -x[1]["nloc"])[:15]
        out.append(
            {
                "key": "unit_size",
                "label": "Funktionsgröße",
                "grade": profile_grade(shares, g["unit_size"]["profile"]),
                "value": f"{_fmt(sum(shares))} % des Codes in Funktionen > {risk[0]} NLOC",
                "source": SIG,
                "explanation": (
                    f"Länge je Funktion in NLOC, Risikoklassen moderat ({risk[0] + 1}–{risk[1]}), "
                    f"hoch ({risk[1] + 1}–{risk[2]}), sehr hoch (> {risk[2]}). Lange Funktionen sind schwer zu testen und wiederzuverwenden."
                ),
                "details": [
                    ["moderat", f"{_fmt(shares[0])} %"],
                    ["hoch", f"{_fmt(shares[1])} %"],
                    ["sehr hoch", f"{_fmt(shares[2])} %"],
                ],
                "thresholds": g["unit_size"]["profile"],
                "top": [
                    {"file": p, "line": fn["line"], "end": fn["end"], "label": fn["name"], "value": fn["nloc"], "ccn": fn["ccn"]}
                    for p, fn in worst
                ],
            }
        )
    else:
        out.append(_na("unit_size", "Funktionsgröße", "Keine Funktionen gefunden"))

    # 3) Duplikation
    dup = ctx["duplication"]
    if dup.measured:
        lines = sum(f["lines"] for f in prod)
        dl = sum(f["dup_lines"] for f in prod)
        pct = 100 * dl / lines if lines else 0.0
        out.append(
            {
                "key": "duplication",
                "label": "Duplikation",
                "grade": ladder_grade(pct, g["duplication"]["ladder"]),
                "value": f"{_fmt(pct)} % duplizierte Zeilen",
                "source": SIG,
                "explanation": (
                    f"Tokenbasierte Klonerkennung (jscpd, mindestens {cfg['analysis']['min_dup_tokens']} Tokens). "
                    "Gezählt werden Zeilen, die in mindestens einem Klonpaar vorkommen, bezogen auf alle Zeilen im Produktivcode."
                ),
                "details": [["Klonpaare", str(len(dup.clones))], ["duplizierte Zeilen", str(dl)]],
                "thresholds": g["duplication"]["ladder"],
                "top": [
                    {
                        "file": c["a"],
                        "line": c["a_start"],
                        "end": c["a_end"],
                        "label": f"↔ {c['b']}:{c['b_start']}",
                        "value": c["lines"],
                        "other": c["b"],
                        "other_line": c["b_start"],
                        "other_end": c["b_end"],
                    }
                    for c in dup.clones[:15]
                ],
            }
        )
    else:
        out.append(_na("duplication", "Duplikation", f"Nicht gemessen ({dup.reason})"))

    covered = [f for f in prod if f["ca"] is not None]
    gm = ctx["graph"]

    # 4) Strukturelle Kopplung
    if len(covered) >= 5:
        pc = 100 * gm.propagation_cost
        top = sorted(covered, key=lambda f: -f["impact"])[:15]
        note = " Bei kleinen Systemen (< 50 Dateien) fällt der Wert naturgemäß höher aus." if len(covered) < 50 else ""
        out.append(
            {
                "key": "coupling",
                "label": "Strukturelle Kopplung",
                "grade": ladder_grade(pc, g["coupling"]["ladder"]),
                "value": f"Propagation Cost {_fmt(pc)} %",
                "source": "Metrik: MacCormack, Rusnak & Baldwin 2006. " + HEURISTIC,
                "explanation": (
                    "Propagation Cost = Anteil aller Dateipaare (A, B), bei denen A direkt oder transitiv von B abhängt. "
                    "Er misst, wie weit sich eine Änderung im Mittel ausbreiten kann." + note
                ),
                "details": [
                    ["Dateien im Graph", str(len(covered))],
                    ["Import-Kanten", str(sum(f["ce"] for f in covered))],
                    ["Ø Fan-out", _fmt(sum(f["ce"] for f in covered) / len(covered))],
                    ["max. Fan-out", str(max(f["ce"] for f in covered))],
                ],
                "thresholds": g["coupling"]["ladder"],
                "top": [
                    {"file": f["path"], "label": "transitiv abhängige Dateien", "value": f["impact"], "ca": f["ca"], "ce": f["ce"]}
                    for f in top
                ],
            }
        )
    else:
        out.append(_na("coupling", "Strukturelle Kopplung", "Zu wenige Dateien mit Import-Auflösung (TS/JS, Java, Python)"))

    # 5) Zyklen
    if len(covered) >= 5:
        in_cycles = sum(1 for f in covered if f["cycle"] is not None)
        pct = 100 * in_cycles / len(covered)
        out.append(
            {
                "key": "cycles",
                "label": "Zyklische Abhängigkeiten",
                "grade": ladder_grade(pct, g["cycles"]["ladder"]),
                "value": f"{_fmt(pct)} % der Dateien in Zyklen",
                "source": HEURISTIC,
                "explanation": (
                    "Dateien, die über statische Imports gegenseitig (direkt oder über Umwege) voneinander abhängen, "
                    "bilden einen Zyklus (stark zusammenhängende Komponente). Sie lassen sich nur gemeinsam verstehen, testen und ändern. "
                    "Schwache Kanten zählen nicht: Lazy-Imports (import(), Imports in Funktionen) und reine Typ-Imports "
                    "(import type, if TYPE_CHECKING)."
                ),
                "details": [
                    ["Datei-Zyklen", str(len(gm.cycles))],
                    ["größter Zyklus", f"{len(gm.cycles[0]) if gm.cycles else 0} Dateien"],
                    ["Verzeichnis-Zyklen", str(len(gm.packages.cycles))],
                    ["Projekt-Zyklen", str(len(gm.projects.cycles))],
                ],
                "thresholds": g["cycles"]["ladder"],
                "top": [
                    {"file": c[0], "label": f"Zyklus #{i + 1}", "value": len(c), "cycle": i} for i, c in enumerate(gm.cycles[:15])
                ],
            }
        )
    else:
        out.append(_na("cycles", "Zyklische Abhängigkeiten", "Zu wenige Dateien mit Import-Auflösung"))

    # 6) Kohäsion
    classes = [(f["path"], c) for f in prod for c in f["classes"]]
    if len(classes) >= 5:
        bad = [x for x in classes if x[1]["lcom"] > 1]
        pct = 100 * len(bad) / len(classes)
        out.append(
            {
                "key": "cohesion",
                "label": "Kohäsion",
                "grade": ladder_grade(pct, g["cohesion"]["ladder"]),
                "value": f"{_fmt(pct)} % der Klassen mit LCOM4 > 1",
                "source": "Metrik: Hitz & Montazeri 1995. " + HEURISTIC,
                "explanation": (
                    "LCOM4 zählt die Gruppen von Methoden, die weder gemeinsame Felder nutzen noch sich gegenseitig aufrufen. "
                    "LCOM4 > 1 heißt, die Klasse ließe sich in so viele unabhängige Teile zerlegen. "
                    "Betrachtet werden Klassen mit mindestens zwei Methoden und mindestens einem Feld (Java, TS/JS, Python). "
                    "Zustandslose Klassen (z. B. Repositories, die nur Funktionen bündeln) bleiben außen vor. "
                    "Getter/Setter zählen als Feldzugriff, Methoden ganz ohne Instanzbezug (Framework-Hooks, Helfer) "
                    "werden separat ausgewiesen und bilden keine eigene Gruppe."
                ),
                "details": [["Klassen", str(len(classes))], ["mit LCOM4 > 1", str(len(bad))]],
                "thresholds": g["cohesion"]["ladder"],
                "top": [
                    {
                        "file": p,
                        "line": c["line"],
                        "label": c["name"],
                        "value": c["lcom"],
                        "groups": c["groups"],
                        "isolated": c.get("isolated", []),
                    }
                    for p, c in sorted(bad, key=lambda x: -x[1]["lcom"])[:15]
                ],
            }
        )
    else:
        out.append(_na("cohesion", "Kohäsion", "Zu wenige Klassen mit mindestens zwei Methoden"))

    # 7) Change-Kopplung
    hist = ctx["history"]
    min_commits = g["change_coupling"]["min_commits"]
    if hist.commits_window >= min_commits and covered:
        hidden_min = cfg["history"]["hidden_min_degree"]
        prod_paths = {f["path"] for f in covered}
        hidden = [
            c for c in ctx["coupling"]
            if c["structural"] is False and c["degree"] >= hidden_min and c["a"] in prod_paths and c["b"] in prod_paths
        ]  # fmt: skip
        involved = {c["a"] for c in hidden} | {c["b"] for c in hidden}
        pct = 100 * len(involved) / len(covered)
        out.append(
            {
                "key": "change_coupling",
                "label": "Versteckte Kopplung",
                "grade": ladder_grade(pct, g["change_coupling"]["ladder"]),
                "value": f"{_fmt(pct)} % der Dateien versteckt gekoppelt",
                "source": "Methode: Tornhill, „Your Code as a Crime Scene“. " + HEURISTIC,
                "explanation": (
                    f"Dateipaare, die in ≥ {cfg['history']['min_shared_commits']} Commits gemeinsam geändert wurden "
                    f"(Kopplungsgrad ≥ {int(hidden_min * 100)} %), aber keine direkte Import-Beziehung haben. "
                    "Das deutet auf implizite Verträge, kopierte Logik oder eine fehlende Abstraktion hin. "
                    "Commits mit mehr als " + str(cfg["history"]["max_files_per_commit"]) + " Dateien werden ignoriert."
                ),
                "details": [
                    ["gekoppelte Paare gesamt", str(len(ctx["coupling"]))],
                    ["davon versteckt", str(len(hidden))],
                    ["Commits im Zeitfenster", str(hist.commits_window)],
                ],
                "thresholds": g["change_coupling"]["ladder"],
                "top": [
                    {
                        "file": c["a"],
                        "label": f"↔ {c['b']}",
                        "value": f"{round(c['degree'] * 100)} % · {c['shared']}×",
                        "other": c["b"],
                        "degree": c["degree"],
                        "shared": c["shared"],
                    }
                    for c in hidden[:15]
                ],
            }
        )
    else:
        out.append(
            _na("change_coupling", "Versteckte Kopplung", f"Zu wenig Historie ({hist.commits_window} Commits im Zeitfenster, mind. {min_commits})")
        )

    # 8) Wissensverteilung
    tf, tf_authors = ctx["truck_factor"]
    if not hist.authors_all:
        out.append(_na("knowledge", "Wissensverteilung", "Keine Commits in der Historie"))
    elif len(hist.authors_all) == 1:
        out.append(_na("knowledge", "Wissensverteilung", "Nur ein Autor in der Historie"))
    else:
        solo = [f for f in prod if f["main_share"] is not None and f["main_share"] >= 0.9]
        solo_pct = 100 * len(solo) / len(prod) if prod else 0.0
        grade = {0: "E", 1: "D", 2: "C", 3: "B"}.get(tf, "A")
        if tf <= 1 and solo_pct > 80:
            grade = "E"
        out.append(
            {
                "key": "knowledge",
                "label": "Wissensverteilung",
                "grade": grade,
                "value": f"Truck-Factor {tf}",
                "source": "Methode: Avelino et al. 2016 (vereinfacht). " + HEURISTIC,
                "explanation": (
                    "Truck-Factor = Anzahl der Personen, deren Weggang mehr als die Hälfte der Dateien ohne Kenner zurücklässt. "
                    f"Als Kenner gilt, wer mindestens {int(g['knowledge']['owner_share'] * 100)} % der Commits einer Datei verfasst hat. "
                    "Noten: ≥ 4 → A, 3 → B, 2 → C, 1 → D; 1 und > 80 % Ein-Personen-Dateien → E."
                ),
                "details": [
                    ["Autoren gesamt", str(len(hist.authors_all))],
                    ["Autoren im Zeitfenster", str(len(hist.authors_window))],
                    ["Dateien mit ≥ 90 % eines Autors", f"{_fmt(solo_pct)} %"],
                    ["Schlüsselpersonen", ", ".join(tf_authors) or "–"],
                ],
                "thresholds": None,
                # Wissensinseln: Dateien fast nur einer Person, die am häufigsten geändert werden, zuerst
                "top": [
                    {
                        "file": f["path"],
                        "label": f"{round(f['main_share'] * 100)} % eines Autors",
                        "value": f"{f['commits_all']} Commits",
                        "share": f["main_share"],
                        "commits": f["commits_all"],
                        "nloc": f["nloc"],
                    }
                    for f in sorted(solo, key=lambda f: (-f["commits_all"], -f["nloc"]))[:15]
                ],
            }
        )
    return out
