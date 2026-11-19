"""Erzeugt docs/repo-radar-handbuch.pdf: Handbuch der Kennzahlen.

Die Codeausschnitte werden beim Bauen aus den Quelldateien gelesen (über Start-/Endmarker), Zeilennummern
stimmen daher immer mit dem aktuellen Stand überein. Aufruf: `uv run python docs/handbuch.py`
(braucht google-chrome für den PDF-Export).
"""

from __future__ import annotations

import html
import re
import subprocess
import sys
import tempfile
import textwrap
from datetime import date
from pathlib import Path

from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "repo_radar"
OUT = ROOT / "docs" / "repo-radar-handbuch.pdf"
sys.path.insert(0, str(ROOT / "src"))
from repo_radar import __version__  # noqa: E402

MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"]

# --------------------------------------------------------------------------------------------- Bausteine

parts: list[str] = []
toc: list[tuple[int, str, str]] = []
_counter = [0, 0]


def h1(title: str) -> None:
    _counter[0] += 1
    _counter[1] = 0
    anchor = f"k{_counter[0]}"
    toc.append((1, f"{_counter[0]}", title))
    parts.append(f'<h1 id="{anchor}"><span class="num">{_counter[0]}</span>{title}</h1>')


def h2(title: str) -> None:
    _counter[1] += 1
    num = f"{_counter[0]}.{_counter[1]}"
    toc.append((2, num, title))
    parts.append(f'<h2 id="k{num.replace(".", "-")}"><span class="num">{num}</span>{title}</h2>')


def h1_anhang(letter: str, title: str) -> None:
    toc.append((1, letter, title))
    parts.append(f'<h1 id="a{letter}"><span class="num">{letter}</span>{title}</h1>')


def p(text: str) -> None:
    parts.append(f"<p>{text}</p>")


def raw(text: str) -> None:
    parts.append(text)


def bedeutung(text: str) -> None:
    parts.append(f'<div class="meaning"><div class="label">Bedeutung</div><p>{text}</p></div>')


def berechnung(*paras: str) -> None:
    parts.append('<h3>Berechnung</h3>' + "".join(f"<p>{x}</p>" for x in paras))


def im_code() -> None:
    parts.append("<h3>Im Code</h3>")


def beispiel(body: str) -> None:
    parts.append(f'<div class="example"><div class="label">Beispiel</div>{body}</div>')


def noten(head: list[str], rows: list[list[str]], note: str = "") -> None:
    th = "".join(f"<th>{h}</th>" for h in head)
    tr = "".join(
        "<tr>" + "".join(f'<td class="grade g{r[0]}">{r[0]}</td>' if i == 0 else f"<td>{c}</td>" for i, c in enumerate(r)) + "</tr>"
        for r in rows
    )
    extra = f'<p class="small">{note}</p>' if note else ""
    parts.append(f'<h3>Notengrenzen</h3><table class="grades"><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table>{extra}')


_FORMATTER_CSS = HtmlFormatter(style="friendly").get_style_defs(".hl")


def code_block(code: str, lang: str = "python", caption: str = "", start: int | None = None) -> str:
    fmt = HtmlFormatter(style="friendly", cssclass="hl", linenos="inline" if start else False, linenostart=start or 1, wrapcode=True)
    body = highlight(code, get_lexer_by_name(lang), fmt)
    cap = f'<div class="caption">{caption}</div>' if caption else ""
    keep = " keep" if code.count("\n") < 30 else ""
    return f'<figure class="code{keep}">{cap}{body}</figure>'


def snip(rel: str, start: str, end: str | None = None, *, until: str | None = None, after: str | None = None, note: str = "") -> None:
    """Ausschnitt aus src/repo_radar/<rel>: ab der ersten Zeile mit `start` (optional erst nach `after`)
    bis einschließlich der ersten Zeile mit `end` bzw. ausschließlich der ersten mit `until`."""
    lines = (SRC / rel).read_text(encoding="utf-8").splitlines()
    i0 = 0
    if after is not None:
        i0 = next(i for i, ln in enumerate(lines) if after in ln)
    i = next(k for k in range(i0, len(lines)) if start in lines[k])
    if end is not None:
        j = next(k for k in range(i, len(lines)) if end in lines[k])
    elif until is not None:
        j = next(k for k in range(i + 1, len(lines)) if until in lines[k]) - 1
    else:
        j = i
    while j > i and not lines[j].strip():
        j -= 1
    code = textwrap.dedent("\n".join(lines[i : j + 1]))
    rng = f"Zeile {i + 1}" if i == j else f"Zeilen {i + 1}–{j + 1}"
    caption = f'<span class="file">src/repo_radar/{rel}</span> · {rng}'
    block = code_block(code, "python", caption, start=i + 1)
    parts.append(block + (f'<p class="codenote">{note}</p>' if note else ""))


def example_code(code: str, lang: str, caption: str = "") -> str:
    return code_block(textwrap.dedent(code).strip("\n"), lang, caption)


def table(head: list[str], rows: list[list[str]], cls: str = "") -> str:
    th = "".join(f"<th>{h}</th>" for h in head)
    tr = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<table class="{cls}"><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table>'


# --------------------------------------------------------------------------------------------- Inhalt

h1("Einführung")
p(
    "repo-radar ist ein Kommandozeilenwerkzeug, das ein beliebiges Git-Repository analysiert und einen interaktiven "
    "HTML-Report schreibt. Es beantwortet drei Fragen: <strong>Wie gut ist der Code?</strong> "
    "<strong>Wie stark hängen die Teile voneinander ab?</strong> <strong>Wo lohnt sich Arbeit?</strong>"
)
p(
    "Dieses Handbuch erklärt jede Kennzahl, die repo-radar erhebt. Zu jeder Kennzahl gibt es drei Teile: was sie "
    "bedeutet, wie sie berechnet wird und an welcher Stelle im Quellcode das passiert. Die Codeausschnitte sind "
    f"unverändert aus repo-radar {__version__} übernommen, die Zeilennummern entsprechen den Dateien im Repository. "
    "Wo es dem Verständnis hilft, rechnet ein kleines Beispiel die Kennzahl von Hand nach; alle Beispielwerte wurden "
    "mit dem echten Code von repo-radar überprüft."
)
raw(
    '<div class="principle"><strong>Grundsatz:</strong> Kennzahlen sind Indikatoren, keine Urteile. Komplexer Code, '
    "der nie angefasst wird, ist harmlos. Komplexer Code, der ständig geändert wird und von dem viele andere Dateien "
    "abhängen, ist das eigentliche Risiko. Belastbar wird eine Aussage erst dort, wo mehrere Signale zusammenfallen.</div>"
)

h2("Benutzung in Kürze")
raw(
    example_code(
        """
        repo-radar analyze ~/projects/my-app --open        # lokales Repo, Report danach öffnen
        repo-radar analyze ~/projects/my-app/libs          # nur ein Teilbaum
        repo-radar analyze https://github.com/org/repo     # wird nach ~/.cache/repo-radar geklont
        repo-radar analyze . --since 6m -x 'sample/**' -t 'integration/**'
        """,
        "bash",
    )
)
raw(
    table(
        ["Option", "Wirkung"],
        [
            ["<code>--since 6m</code>", "Zeitfenster der Historie (Default <code>12 months</code>; auch <code>2y</code>, <code>2025-01-01</code>, <code>all</code>)"],
            ["<code>-x, --exclude GLOB</code>", "zusätzliche Excludes, mehrfach möglich"],
            ["<code>-t, --tests GLOB</code>", "zusätzlich als Testcode werten"],
            ["<code>-u, --untracked</code>", "auch ungetrackte, nicht ignorierte Dateien analysieren"],
            ["<code>--no-dup</code>", "Duplikationsanalyse überspringen (kein Node.js nötig)"],
            ["<code>-c, --config FILE</code>", "Schwellwerte und Excludes aus einer <code>radar.toml</code> (Anhang A)"],
        ],
    )
)
p(
    "Ergebnis sind zwei Dateien in <code>radar-out/&lt;name&gt;/</code>: <code>report.html</code>, eine einzelne Datei, "
    "die offline läuft, und <code>analysis.json</code> mit allen Rohdaten."
)

h2("Ablauf der Analyse")
raw(
    """<ol class="pipeline">
<li><strong>Quelle</strong>: <code>git ls-files</code> listet die Dateien, mit <code>--untracked</code> auch ungetrackte.</li>
<li><strong>Inventar</strong>: Sprache, Testcode, Projekt und Verzeichnis je Datei; Default-Excludes greifen.</li>
<li><strong>Parsing</strong>: lizard misst Funktionen (Komplexität, Länge), tree-sitter liest Imports, Klassen und Felder.</li>
<li><strong>Abhängigkeiten</strong>: Imports werden zu Dateien aufgelöst (TS/JS, Java, Python). Ergebnis ist der Import-Graph.</li>
<li><strong>Graph-Metriken</strong>: Fan-in/-out, Instabilität, Zyklen, Reichweite, PageRank, Propagation Cost.</li>
<li><strong>Historie</strong>: <code>git log</code> liefert Commits, Churn, Autoren und Change-Kopplung.</li>
<li><strong>Duplikation</strong>: jscpd sucht Klone.</li>
<li><strong>Noten</strong>: acht Dimensionen werden mit A bis E bewertet.</li>
</ol>"""
)

# ------------------------------------------------------------------------------------------------ Kapitel 2
h1("Grundlagen der Messung")

h2("Welche Dateien zählen")
p(
    "Grundlage ist <code>git ls-files</code>: Es zählen die getrackten Dateien, alles aus der <code>.gitignore</code> "
    "ist damit automatisch außen vor. Zusätzlich schließen Default-Excludes eingecheckte Dateien aus, die das Ergebnis "
    "verfälschen würden: Build-Output, <code>vendor/</code>, <code>*.min.js</code>, <code>*.d.ts</code>, generierter "
    "Code und Datenbank-Migrationen."
)
p(
    "<strong>Testcode</strong> wird über Namen und Ordner erkannt (<code>*.spec.ts</code>, <code>test_*.py</code>, "
    "<code>*Test.java</code>, <code>tests/</code>, <code>e2e/</code> …). Er erscheint im Report, zählt aber nicht in den "
    "Noten, der Hotspot-Rangliste und den Graph-Metriken. Sonst würde zum Beispiel ein langer Test die Note für die "
    "Funktionsgröße drücken, obwohl lange Testfunktionen unkritisch sind."
)

h2("Grundgrößen")
raw(
    """<dl class="terms">
<dt>Zeilen</dt><dd>Physische Zeilen einer Datei, einschließlich Leerzeilen und Kommentaren.</dd>
<dt>NLOC</dt><dd><em>Non-comment lines of code</em>: Zeilen ohne Leerzeilen und reine Kommentarzeilen. lizard misst sie je Datei und je Funktion.</dd>
<dt>Funktion</dt><dd>Alles, was lizard als Funktion oder Methode erkennt, je nach Sprache auch anonyme Funktionen.</dd>
<dt>Import-Graph</dt><dd>Knoten sind die Produktivdateien mit Import-Auflösung (TS/JS, Java, Python). Eine gerichtete Kante A → B heißt: A importiert B. Mehrere Imports von A aus B ergeben eine Kante.</dd>
<dt>Schwache Kante</dt><dd>Lazy-Import (<code>import()</code>, Import innerhalb einer Funktion) oder reiner Typ-Import (<code>import type</code>, <code>if TYPE_CHECKING:</code>). Sie erzeugt beim Laden keine Abhängigkeit und zählt daher für Fan-in/-out und PageRank, nicht aber für Zyklen, Reichweite und Propagation Cost.</dd>
<dt>Zeitfenster</dt><dd>Über <code>--since</code> gewählt, Default 12 Monate, gerechnet ab dem letzten Commit. Commits, Churn, Fix-Commits und Change-Kopplung beziehen sich auf das Fenster; Autoren und Alter auf die gesamte Historie.</dd>
</dl>"""
)
p("Die Trennung in alle Kanten und statische Kanten geschieht zu Beginn der Graph-Berechnung:")
snip(
    "graph_metrics.py",
    "prod = set(prod_files)",
    "g.add_edges_from(static_e)",
    note="<code>edges</code> bildet jedes Dateipaar auf ein Flag ab: <code>True</code> = schwache Kante. "
    "<code>all_e</code> enthält alle Kanten, <code>static_e</code> nur die starken; nur diese kommen in den Graphen <code>g</code>, "
    "auf dem Zyklen und Reichweiten berechnet werden.",
)

h2("Wie aus Kennzahlen Noten werden")
p(
    "Acht Dimensionen erhalten eine Note von <strong>A</strong> (sehr gut) bis <strong>E</strong> (kritisch). "
    "Eine Gesamtnote gibt es bewusst nicht: Die Dimensionen messen Verschiedenes, ein Mittelwert würde gerade die "
    "Schwachstelle verdecken. Ist eine Dimension nicht messbar, etwa weil es zu wenige Dateien, keine Historie oder "
    "kein Node.js gibt, erscheint „–“ mit der Begründung."
)
p("Es gibt zwei Bewertungsverfahren:")
raw(
    """<ul>
<li><strong>Stufenleiter</strong> (<em>ladder</em>): vier Obergrenzen für A, B, C und D. Die Note ist die erste Stufe, deren Grenze der Wert nicht überschreitet; liegt er über allen Grenzen, gibt es ein E.</li>
<li><strong>Risikoprofil</strong> (<em>profile</em>): für Komplexität und Funktionsgröße. Der Code wird in drei Risikoklassen (moderat, hoch, sehr hoch) aufgeteilt. Die Note ist die beste, bei der <em>alle drei</em> Anteile innerhalb ihrer Grenzen liegen.</li>
</ul>"""
)
p(
    "Die Grenzen stammen entweder aus der Literatur, dem Wartbarkeitsmodell der Software Improvement Group (SIG), das an "
    "Industrie-Benchmarks kalibriert ist, oder sind eigene, offen dokumentierte Heuristiken. Alle lassen sich in einer "
    "<code>radar.toml</code> anpassen (Anhang A)."
)
snip("scoring.py", "def ladder_grade", until="def risk_profile", note="<code>GRADES</code> ist die Zeichenkette <code>\"ABCD\"</code>. "
     "Beide Funktionen probieren die Noten von A abwärts und geben die erste zutreffende zurück.")
beispiel(
    "<p>Das Komplexitätsprofil eines Repos lautet 28 % moderat, 4 % hoch, 0 % sehr hoch. Für A sind höchstens "
    "25 / 0 / 0 % erlaubt: 28 % überschreitet die erste Grenze. Für B sind es 30 / 5 / 0 %: Alle drei Anteile passen. "
    "Ergebnis: <strong>B</strong>.</p>"
)

# ------------------------------------------------------------------------------------------------ Kapitel 3
h1("Die acht Noten")
p(
    "Die Noten erscheinen im Report als Karten auf der Überblicksseite. Ein Klick auf eine Karte zeigt die Herleitung, "
    "die Herkunft der Schwellwerte und die größten Beiträge, also die Funktionen, Dateien oder Klassen, die den Wert "
    "am stärksten treiben."
)

# 3.1 Komplexität
h2("Komplexität")
bedeutung(
    "Die zyklomatische Komplexität (CCN, McCabe 1976) zählt die unabhängigen Ausführungspfade durch eine Funktion. "
    "Je höher sie ist, desto mehr Fälle muss man beim Lesen im Kopf behalten und beim Testen abdecken."
)
berechnung(
    "lizard zerlegt jede Datei in Funktionen und zählt deren Entscheidungspunkte: <strong>CCN = 1 + Anzahl der "
    "Verzweigungen</strong>. Gezählt werden <code>if</code>, <code>for</code>, <code>while</code>, <code>catch</code>, "
    "<code>case</code>, der Ternär-Operator <code>?</code> und die logischen Operatoren <code>&amp;&amp;</code> und "
    "<code>||</code>; TypeScript zusätzlich <code>??</code>, Python stattdessen <code>elif</code>, <code>except</code>, "
    "<code>finally</code>, <code>and</code> und <code>or</code>. Jede Funktion des Produktivcodes fällt in eine "
    "Risikoklasse: gering (CCN ≤ 10), moderat (11–20), hoch (21–50) oder sehr hoch (&gt; 50). Für die Note zählt nicht "
    "die Zahl der Funktionen, sondern wie viel Code in jeder Klasse steckt: die NLOC der Funktionen einer Klasse geteilt "
    "durch die NLOC aller Funktionen. So wiegt eine lange, verschachtelte Funktion schwerer als ein kurzer Einzeiler mit "
    "gleicher CCN. Die drei Anteile gehen in das Risikoprofil (Abschnitt 2.3). Als Wert zeigt der Report ihre Summe: "
    "„x % des Codes in Funktionen mit CCN &gt; 10“."
)
im_code()
snip("parsing.py", "info = lizard.analyze_file", until="family = DEP_FAMILY",
     note="Je Datei liefert lizard eine Liste von Funktionen mit Name, Position, CCN, NLOC und Parameterzahl.")
snip("scoring.py", "def risk_profile", until="def _na",
     note="<code>risk</code> ist <code>[10, 20, 50]</code>. Die Schleife prüft von der höchsten Klasse abwärts und schlägt "
     "die NLOC der Funktion genau einer Klasse zu. Funktionen mit CCN ≤ 10 landen in keinem Eimer, sie zählen nur in "
     "<code>total</code>.")
beispiel(
    "<p>Die folgende Funktion hat die CCN 6: Basiswert 1 plus fünf Entscheidungspunkte.</p>"
    + example_code(
        """
        function versandkosten(warenkorb: Artikel[], land: string): number {   // Basis      1
          if (warenkorb.length === 0) return 0;                                 // if       + 1 = 2
          let summe = 0;
          for (const a of warenkorb) {                                          // for      + 1 = 3
            summe += a.preis * a.menge;
          }
          if (land !== 'DE' && summe < 50) return 9.9;                          // if, &&   + 2 = 5
          return summe >= 100 ? 0 : 4.9;                                        // ?        + 1 = 6
        }
        """,
        "typescript",
    )
    + "<p>Mit CCN 6 liegt sie in der Klasse „gering“ und trägt nur zum Nenner des Profils bei.</p>"
)
noten(
    ["Note", "moderat (11–20)", "hoch (21–50)", "sehr hoch (&gt; 50)"],
    [["A", "≤ 25 %", "0 %", "0 %"], ["B", "≤ 30 %", "≤ 5 %", "0 %"], ["C", "≤ 40 %", "≤ 10 %", "0 %"], ["D", "≤ 50 %", "≤ 15 %", "≤ 5 %"], ["E", "darüber", "", ""]],
    "Quelle: SIG-Wartbarkeitsmodell (Heitlager, Kuipers &amp; Visser 2007). Anteil = NLOC in Funktionen der Klasse / NLOC aller Funktionen.",
)

# 3.2 Funktionsgröße
h2("Funktionsgröße")
bedeutung(
    "Wie lang die Funktionen sind, gemessen in Codezeilen ohne Leerzeilen und Kommentare (NLOC). Lange Funktionen "
    "erledigen meist mehrere Aufgaben auf einmal und sind schwer zu testen, zu benennen und wiederzuverwenden."
)
berechnung(
    "Das Verfahren ist dasselbe wie bei der Komplexität, nur mit der NLOC je Funktion als Maß. Die Risikoklassen sind "
    "moderat (16–30 NLOC), hoch (31–60) und sehr hoch (&gt; 60). Wieder wird der Code gewichtet: Eine Funktion mit 80 "
    "NLOC schlägt 80 Zeilen der Klasse „sehr hoch“ zu, und der Anteil bezieht sich auf alle NLOC in Funktionen des "
    "Produktivcodes. Die Profilgrenzen stammen aus dem SIG-Benchmark von 2012 (Baggen et al.) und sind deshalb "
    "krumme Werte. Der Report zeigt „x % des Codes in Funktionen &gt; 15 NLOC“."
)
im_code()
snip("scoring.py", "# 2) Funktionsgröße", '"grade": profile_grade(shares, g["unit_size"]["profile"])',
     note="Derselbe <code>risk_profile</code>-Aufruf wie bei der Komplexität, nur mit dem Schlüssel <code>\"nloc\"</code> statt <code>\"ccn\"</code>.")
snip("config.py", '"unit_size": {', until='"duplication": {"ladder"', after='"grades": {')
noten(
    ["Note", "moderat (16–30)", "hoch (31–60)", "sehr hoch (&gt; 60)"],
    [["A", "≤ 19,5 %", "≤ 10,9 %", "≤ 3,9 %"], ["B", "≤ 26,0 %", "≤ 15,5 %", "≤ 6,5 %"], ["C", "≤ 34,1 %", "≤ 22,2 %", "≤ 11,0 %"], ["D", "≤ 45,9 %", "≤ 31,4 %", "≤ 18,1 %"], ["E", "darüber", "", ""]],
    "Quelle: SIG-Modell, Kalibrierung nach Baggen, Correia, Schill &amp; Visser 2012.",
)

# 3.3 Duplikation
h2("Duplikation")
bedeutung(
    "Der Anteil der Codezeilen, die in gleicher Form an anderer Stelle noch einmal vorkommen. Duplikate müssen bei "
    "jeder Änderung mitgepflegt werden; wird eine Kopie vergessen, entsteht ein Fehler."
)
berechnung(
    "repo-radar startet jscpd 4.0.5 über <code>npx</code> in einem leeren temporären Verzeichnis, damit keine "
    "Konfiguration des analysierten Repos greift. jscpd zerlegt den Code in Tokens und meldet jede übereinstimmende "
    "Tokenfolge von mindestens 50 Tokens als <em>Klonpaar</em> mit je einem Zeilenbereich in beiden Dateien. Paare "
    "zählen nur, wenn beide Dateien zur Analyse gehören. Je Datei werden alle Zeilenbereiche, an denen sie beteiligt ist, "
    "zusammengeführt: Überlappende oder direkt aneinandergrenzende Bereiche verschmelzen, damit jede Zeile nur einmal "
    "zählt. Original und Kopie zählen beide als dupliziert. Die Note bezieht die Summe der duplizierten Zeilen aller "
    "Produktivdateien auf die Summe ihrer physischen Zeilen. Fehlt Node.js oder wird <code>--no-dup</code> gesetzt, "
    "erscheint „–“."
)
im_code()
snip("duplication.py", "cmd = [", "]  # fmt: skip")
snip("duplication.py", "def _merge_ranges", "return total", after="def _merge_ranges",
     note="Die Bereiche werden sortiert und nacheinander verschmolzen, solange der nächste Bereich spätestens eine Zeile "
     "nach dem aktuellen Ende beginnt (<code>s &gt; cur_e + 1</code> beendet einen Block).")
snip("scoring.py", "dup = ctx[\"duplication\"]", "pct = 100 * dl / lines if lines else 0.0")
beispiel(
    "<p>Eine Datei mit 200 Zeilen ist an zwei Klonpaaren beteiligt, mit den Bereichen 10–30 und 25–40. Verschmolzen "
    "ergibt das den Block 10–40, also <strong>31</strong> duplizierte Zeilen (nicht 21 + 16 = 37). Die Datei ist zu "
    "15,5 % dupliziert.</p>"
)
noten(["Note", "duplizierte Zeilen"], [["A", "≤ 3 %"], ["B", "≤ 5 %"], ["C", "≤ 10 %"], ["D", "≤ 20 %"], ["E", "&gt; 20 %"]], "Quelle: SIG-Modell.")

# 3.4 Strukturelle Kopplung
h2("Strukturelle Kopplung (Propagation Cost)")
bedeutung(
    "Wie weit sich eine Änderung über Imports im Mittel ausbreiten kann. Eine Propagation Cost von 20 % heißt: "
    "Eine Datei hängt im Durchschnitt direkt oder über Umwege von einem Fünftel aller Dateien ab, und eine Änderung "
    "erreicht im Durchschnitt ebenso viele."
)
berechnung(
    "Grundlage ist der Import-Graph des Produktivcodes ohne schwache Kanten. Für jede Datei wird gezählt, wie viele "
    "andere Dateien sie direkt oder transitiv erreicht. Die Propagation Cost (MacCormack, Rusnak &amp; Baldwin 2006) "
    "ist die Dichte der daraus entstehenden Erreichbarkeitsmatrix: <strong>PC = (Σ erreichbare Dateien + n) / n²</strong>. "
    "Das „+ n“ zählt die Diagonale mit, denn jede Datei erreicht sich selbst; so steht es auch in der Originaldefinition.",
    "Damit das auch bei Tausenden Dateien schnell geht, wird der Graph zuerst kondensiert: Jeder Zyklus wird zu einem "
    "Knoten, das Ergebnis ist zyklenfrei. In umgekehrter topologischer Reihenfolge erhält jeder Knoten eine Bitmaske der "
    "erreichbaren Dateien: seine eigenen Mitglieder, verodert mit den Masken seiner Nachfolger. Die Zahl der gesetzten "
    "Bits minus eins (die Datei selbst) ist die Reichweite. Die Note gibt es ab 5 Dateien; bei kleinen Systemen "
    "(&lt; 50 Dateien) fällt der Wert naturgemäß höher aus.",
)
im_code()
snip("graph_metrics.py", "def _reach_counts", until="def _sccs",
     note="<code>nx.condensation</code> fasst stark zusammenhängende Komponenten zusammen; <code>mapping</code> ordnet jede "
     "Datei ihrer Komponente zu. <code>bit_count()</code> zählt die gesetzten Bits.")
snip("graph_metrics.py", "deps_t = _reach_counts(g)", "pc = pc / (n * n) if n else 0.0")
beispiel(
    "<p>Vier Dateien: <code>app</code> importiert <code>service</code> und <code>util</code>, <code>service</code> "
    "importiert <code>repo</code>.</p>"
    + table(
        ["Datei", "erreicht", "Anzahl"],
        [["app", "service, repo, util", "3"], ["service", "repo", "1"], ["repo", "–", "0"], ["util", "–", "0"]],
        "compact",
    )
    + "<p>PC = (3 + 1 + 0 + 0 + 4) / 4² = 8 / 16 = <strong>50 %</strong>.</p>"
)
noten(["Note", "Propagation Cost"], [["A", "≤ 10 %"], ["B", "≤ 20 %"], ["C", "≤ 30 %"], ["D", "≤ 45 %"], ["E", "&gt; 45 %"]], "Heuristik, in <code>radar.toml</code> anpassbar.")

# 3.5 Zyklen
h2("Zyklische Abhängigkeiten")
bedeutung(
    "Dateien, die sich über Imports gegenseitig erreichen, bilden einen Zyklus. Sie lassen sich nur gemeinsam "
    "verstehen, testen und ändern, und keine von ihnen kann ohne die anderen wiederverwendet werden."
)
berechnung(
    "Ein Zyklus ist eine stark zusammenhängende Komponente (SCC) des Import-Graphen mit mehr als einer Datei: eine "
    "maximale Menge von Dateien, in der jede jede andere über Imports erreicht. networkx ermittelt die Komponenten. "
    "Schwache Kanten zählen nicht: Ein Lazy-Import zurück zur Elternkomponente, etwa bei Angular-Routen, oder ein reiner "
    "Typ-Import erzeugt beim Laden keine Abhängigkeit. Die Note bewertet den Anteil der Produktivdateien mit "
    "Import-Auflösung, die in irgendeinem Zyklus liegen. Zusätzlich, aber ohne Note, sucht repo-radar Zyklen zwischen "
    "Verzeichnissen und Projekten: Dort entsteht eine Kante, sobald eine Datei der einen Gruppe eine Datei der anderen importiert."
)
im_code()
snip("graph_metrics.py", "def _sccs", until="def _level")
snip("scoring.py", "in_cycles = sum(", "pct = 100 * in_cycles / len(covered)",
     note="<code>covered</code> sind die Produktivdateien mit Import-Auflösung; <code>cycle</code> ist der Index des Zyklus oder <code>None</code>.")
noten(["Note", "Dateien in Zyklen"], [["A", "0 %"], ["B", "≤ 3 %"], ["C", "≤ 8 %"], ["D", "≤ 15 %"], ["E", "&gt; 15 %"]], "Heuristik: Ein A gibt es nur ganz ohne Zyklen.")

# 3.6 Kohäsion
h2("Kohäsion (LCOM4)")
bedeutung(
    "LCOM4 (<em>Lack of Cohesion of Methods</em>, Hitz &amp; Montazeri 1995) zählt, in wie viele unabhängige Teile eine "
    "Klasse zerfällt. LCOM4 = 1 heißt, alles hängt zusammen; LCOM4 = 3 heißt, die Klasse bündelt drei Aufgaben, die "
    "man in drei Klassen trennen könnte."
)
berechnung(
    "tree-sitter liest je Klasse die Felder und Methoden und für jede Methode, welche Felder und Methoden sie über "
    "<code>this</code> bzw. <code>self</code> benutzt. Methoden und Felder werden zu Knoten eines Graphen: Eine Kante "
    "verbindet eine Methode mit jedem Feld, das sie nutzt, und mit jeder Methode, die sie aufruft. Felder, deren "
    "Initialisierer andere Member nutzen (etwa Angular <code>computed()</code>), werden mit diesen verbunden. "
    "<strong>LCOM4 ist die Zahl der Zusammenhangskomponenten, die mindestens eine Methode enthalten</strong>; "
    "berechnet wird sie mit einer Union-Find-Struktur.",
    "repo-radar weicht an vier Stellen bewusst vom Lehrbuch ab, um bekannte Fehlalarme zu vermeiden: Klassen mit "
    "weniger als zwei Methoden oder ohne Felder werden nicht bewertet, weil zustandslose Klassen keine Kohäsion im "
    "Sinne von LCOM haben. Konstruktoren zählen nicht als Methode, da sie jedes Feld berühren und sonst alles verbinden "
    "würden. Getter und Setter bilden keine eigene Gruppe: In TypeScript und Python werden Accessoren übergangen, in "
    "Java zählt der Aufruf von <code>getX()</code>/<code>setX()</code> als Zugriff auf das Feld <code>x</code>. Methoden "
    "ganz ohne Instanzbezug (Framework-Hooks, Helfer) werden als „isoliert“ ausgewiesen und bilden keine eigene Gruppe. "
    "Die Note bewertet den Anteil der Klassen mit LCOM4 &gt; 1; sie gibt es ab 5 bewertbaren Klassen.",
)
im_code()
snip("langs/base.py", "parent: dict[str, str] = {}", "return max(len(result), 1), result, sorted(isolated)", after="def lcom4",
     note="Knoten tragen ein Präfix (<code>m:</code> Methode, <code>f:</code> Feld). Gruppen ohne Methode, also unbenutzte "
     "Felder, werden übersprungen, Einzelgänger-Methoden landen in <code>isolated</code>.")
snip("langs/typescript.py", "if len(methods) < 2 or not fields:", note="Die Mindestbedingung für eine Bewertung, gleich in allen drei Sprachen.")
snip("scoring.py", "classes = [(f[\"path\"], c) for f in prod", "pct = 100 * len(bad) / len(classes)", after="# 6) Kohäsion")
beispiel(
    example_code(
        """
        export class Bestellung {
          private positionen: Position[] = [];
          private kunde: Kunde;

          hinzufuegen(p: Position) { this.positionen.push(p); }
          summe() { return this.positionen.reduce((s, p) => s + p.preis, 0); }
          rabatt() { return this.summe() * 0.1; }
          kundenMail() { return this.kunde.mail; }
          adresse() { return this.kunde.adresse; }
        }
        """,
        "typescript",
    )
    + "<p><code>hinzufuegen</code> und <code>summe</code> teilen <code>positionen</code>, <code>rabatt</code> ruft "
    "<code>summe</code> auf: Das ist Gruppe 1. <code>kundenMail</code> und <code>adresse</code> teilen <code>kunde</code>: "
    "Das ist Gruppe 2. Zwischen den Gruppen gibt es keine Verbindung, also <strong>LCOM4 = 2</strong>. Die Kundendaten "
    "wären ein Kandidat für eine eigene Klasse.</p>"
)
noten(["Note", "Klassen mit LCOM4 &gt; 1"], [["A", "≤ 10 %"], ["B", "≤ 20 %"], ["C", "≤ 35 %"], ["D", "≤ 50 %"], ["E", "&gt; 50 %"]], "Heuristik.")

# 3.7 Versteckte Kopplung
h2("Versteckte Kopplung")
bedeutung(
    "Dateien, die immer wieder im selben Commit geändert werden, obwohl keine die andere importiert. Das deutet auf "
    "eine unsichtbare Abhängigkeit hin: kopierte Logik, ein gemeinsames Datenformat oder eine fehlende Abstraktion."
)
berechnung(
    "repo-radar liest die Historie mit <code>git log --no-merges --numstat -M</code>. Umbenennungen werden verfolgt, "
    "sodass Commits unter einem alten Pfad der Datei unter ihrem heutigen Namen zugerechnet werden. Für jeden Commit im "
    "Zeitfenster, der 2 bis 50 analysierte Dateien ändert, wird jedes Dateipaar gezählt; größere Commits sind meist "
    "Formatierungen oder Massenumbenennungen und würden alles mit allem koppeln.",
    "Ein Paar gilt als <strong>gekoppelt</strong>, wenn es mindestens 5 gemeinsame Commits hat und der "
    "<strong>Kopplungsgrad = gemeinsame Commits / Durchschnitt der Commits beider Dateien</strong> mindestens 30 % "
    "beträgt. <strong>Versteckt</strong> ist ein gekoppeltes Paar zweier Produktivdateien, wenn keine direkte Import-Kante "
    "zwischen ihnen besteht, in keiner Richtung, und der Grad mindestens 50 % erreicht. Paare mit Dateien ohne "
    "Import-Auflösung (etwa HTML-Templates) gelten als „unbekannt“ und zählen nicht. Die Note bewertet den Anteil der "
    "Produktivdateien mit Import-Auflösung, die an mindestens einem versteckten Paar beteiligt sind. Sie gibt es erst "
    "ab 20 Commits im Zeitfenster.",
)
im_code()
snip("git_history.py", "if in_window and 2 <= len(touched) <= max_files:", "pair_counts[(a, b)] += 1",
     note="<code>touched</code> enthält die analysierten Dateien des Commits, schon auf ihre heutigen Pfade umgeschrieben.")
snip("git_history.py", "for (a, b), shared in pair_counts.items():", 'coupling.append({"a": a, "b": b, "shared": shared, "degree": round(degree, 3)})')
snip("pipeline.py", "for c in hist.coupling:", 'coupling.append({**c, "structural": structural})',
     note="<code>structural</code> ist <code>True</code> bei einer Import-Kante, <code>False</code> ohne, <code>None</code>, wenn eine der Dateien keine Import-Auflösung hat.")
snip("scoring.py", "hidden = [", "pct = 100 * len(involved) / len(covered)", after="# 7) Change-Kopplung")
beispiel(
    "<p><code>order.service.ts</code> hat im Fenster 8 Commits, <code>invoice.mapper.ts</code> 10. Sechs davon "
    "betreffen beide. Kopplungsgrad = 6 / ((8 + 10) / 2) = 6 / 9 = <strong>67 %</strong>. Das Paar hat ≥ 5 gemeinsame "
    "Commits und einen Grad ≥ 50 %. Importiert keine der beiden Dateien die andere, ist es versteckt gekoppelt.</p>"
)
noten(["Note", "versteckt gekoppelte Dateien"], [["A", "≤ 2 %"], ["B", "≤ 5 %"], ["C", "≤ 10 %"], ["D", "≤ 20 %"], ["E", "&gt; 20 %"]], "Methode nach Tornhill, „Your Code as a Crime Scene“; Grenzen heuristisch.")

# 3.8 Wissensverteilung
h2("Wissensverteilung (Truck-Factor)")
bedeutung(
    "Der Truck-Factor gibt an, wie viele Personen das Projekt verlassen müssten, bis für mehr als die Hälfte der "
    "Dateien niemand mehr da ist, der sie kennt. Ein Wert von 1 heißt: Das Wissen hängt an einer Person."
)
berechnung(
    "Das Verfahren ist eine vereinfachte Form von Avelino et al. (2016). Für jede Produktivdatei gilt als "
    "<em>Kenner</em>, wer mindestens 25 % ihrer Commits verfasst hat, über die gesamte Historie (<code>owner_share</code>). "
    "Vorher werden Autoren-Identitäten zusammengeführt (Abschnitt 4.6). Dann wird gierig vorgegangen: Es wird "
    "wiederholt die Person entfernt, die gerade die meisten Dateien kennt, bis mehr als die Hälfte der Dateien keinen "
    "Kenner mehr hat. Die Zahl der entfernten Personen ist der Truck-Factor. Die Note ergibt sich direkt aus ihm; "
    "zusätzlich gibt es ein E, wenn der Truck-Factor höchstens 1 ist und über 80 % der Dateien zu mindestens 90 % von "
    "einer Person stammen. Mit nur einem Autor gibt es keine Note.",
)
im_code()
snip("git_history.py", "def truck_factor", "o.discard(top)")
snip("scoring.py", 'solo = [f for f in prod if f["main_share"]', "grade = \"E\"", after="# 8) Wissensverteilung")
beispiel(
    table(
        ["Datei", "Commits", "Kenner (≥ 25 %)"],
        [["f1", "Ada 10", "Ada"], ["f2", "Ada 6, Ben 4", "Ada, Ben"], ["f3", "Ben 5", "Ben"], ["f4", "Ada 3, Cem 1", "Ada, Cem"]],
        "compact",
    )
    + "<p>Ada kennt die meisten Dateien (3) und wird zuerst entfernt: Nur f1 ist danach verwaist, 1 von 4 ist nicht "
    "mehr als die Hälfte. Als Nächstes geht Ben (kennt noch f2 und f3): Jetzt sind f1, f2 und f3 verwaist, 3 von 4. "
    "<strong>Truck-Factor = 2</strong>, Schlüsselpersonen Ada und Ben, Note C.</p>"
)
noten(
    ["Note", "Truck-Factor"],
    [["A", "≥ 4"], ["B", "3"], ["C", "2"], ["D", "1"], ["E", "0, oder ≤ 1 und &gt; 80 % Ein-Personen-Dateien"]],
    "Heuristik. „Ein-Personen-Datei“: Hauptautor-Anteil ≥ 90 %.",
)

# ------------------------------------------------------------------------------------------------ Kapitel 4
h1("Kennzahlen je Datei und Verzeichnis")
p(
    "Die folgenden Kennzahlen ergeben keine eigene Note. Sie stehen in der Tabelle „Dateien“, in der Detailansicht jeder "
    "Datei und als Farbe oder Fläche in der Hotspot-Karte, und einige fließen in die Noten ein."
)

h2("Fan-in und Fan-out")
bedeutung(
    "Fan-in (afferente Kopplung, Ca) ist die Zahl der Dateien, die diese Datei importieren; Fan-out (efferente "
    "Kopplung, Ce) die Zahl der Dateien, die sie selbst importiert. Hoher Fan-in kennzeichnet zentrale Dateien, deren "
    "Änderung viele trifft; hoher Fan-out Dateien, die von vielem abhängen."
)
berechnung(
    "Für jede Kante A → B im Import-Graph des Produktivcodes, schwache Kanten eingeschlossen, steigt Ce(A) und Ca(B) "
    "um eins. Weil mehrere Imports zwischen zwei Dateien eine Kante bilden, zählt jede Nachbardatei einmal. Benannte "
    "Imports aus einer Barrel-Datei (<code>index.ts</code>) löst repo-radar bis zur definierenden Datei auf; das Barrel "
    "sammelt also keinen künstlichen Fan-in."
)
im_code()
snip("graph_metrics.py", "ca: dict[str, int] = dict.fromkeys(prod_files, 0)", "ca[b] += 1")

h2("Instabilität")
bedeutung(
    "Die Instabilität I nach Robert C. Martin liegt zwischen 0 und 1. Bei 0 ist eine Datei maximal stabil: Sie wird "
    "genutzt, hängt aber selbst von nichts ab. Bei 1 ist sie maximal instabil: Sie hängt von anderen ab, niemand nutzt "
    "sie. Stabile Dateien sollten selten geändert werden müssen, weil jede Änderung viele trifft."
)
berechnung(
    "<strong>I = Ce / (Ca + Ce)</strong>. Für Dateien ganz ohne Kanten ist der Wert undefiniert und erscheint als „–“. "
    "Auf Verzeichnis- und Projektebene gilt dieselbe Formel, mit Ca und Ce über die Gruppengrenze gezählt (Abschnitt 4.8)."
)
im_code()
snip("graph_metrics.py", "for f in prod_files:", '"impact": impact[f],', after="pr = _pagerank(",
     note="Hier entstehen alle Graph-Kennzahlen einer Datei auf einmal.")

h2("Änderungsreichweite und transitive Abhängigkeiten")
bedeutung(
    "Die Änderungsreichweite (<em>impact</em>) zählt, wie viele Dateien direkt oder über Umwege von dieser Datei "
    "abhängen und damit potenziell von einer Änderung betroffen sind. Die transitiven Abhängigkeiten zählen die "
    "Gegenrichtung: wie viele Dateien diese Datei selbst braucht."
)
berechnung(
    "Beide Werte entstehen mit demselben Reichweiten-Algorithmus wie die Propagation Cost (Abschnitt 3.4), ohne "
    "schwache Kanten. Die transitiven Abhängigkeiten werden auf dem Import-Graphen gezählt, die Änderungsreichweite auf "
    "dem umgedrehten Graphen, in dem jede Kante von der importierten zur importierenden Datei zeigt. Die Dateien mit der "
    "größten Änderungsreichweite erscheinen bei der Note „Strukturelle Kopplung“ als größte Beiträge."
)
im_code()
snip("graph_metrics.py", "deps_t = _reach_counts(g)", "impact = _reach_counts(g.reverse(copy=False))")
beispiel(
    "<p>Im Beispiel aus Abschnitt 3.4 hat <code>repo</code> die Änderungsreichweite 2 (<code>service</code> direkt, "
    "<code>app</code> über <code>service</code>) und 0 transitive Abhängigkeiten. Bei <code>app</code> ist es umgekehrt: "
    "Reichweite 0, transitive Abhängigkeiten 3.</p>"
)

h2("PageRank")
bedeutung(
    "Wie zentral eine Datei im Import-Graphen ist. Anders als der Fan-in berücksichtigt PageRank, ob die importierenden "
    "Dateien selbst zentral sind. 1,0 ist der Durchschnitt, 3,0 heißt dreimal so zentral."
)
berechnung(
    "repo-radar nutzt eine eigene Umsetzung des PageRank-Verfahrens (Page, Brin et al. 1999) mit Dämpfungsfaktor 0,85 "
    "und 60 Iterationen. Alle Dateien starten mit dem Rang 1/n. In jeder Runde gibt jede Datei 85 % ihres Rangs zu "
    "gleichen Teilen an die Dateien weiter, die sie importiert. Dateien ohne Imports (Senken) verteilen ihren Rang auf "
    "alle, und jede Datei erhält zusätzlich einen Grundanteil von 15 % / n. Am Ende wird mit n multipliziert, sodass der "
    "Mittelwert 1 ist. Schwache Kanten zählen mit."
)
im_code()
snip("graph_metrics.py", "def _pagerank", until="def _reach_counts")
beispiel(
    "<p>Im Beispiel aus Abschnitt 3.4 ergibt sich: <code>repo</code> 1,46, <code>service</code> 0,94, "
    "<code>util</code> 0,94, <code>app</code> 0,66. <code>repo</code> und <code>util</code> haben beide den Fan-in 1, "
    "aber <code>repo</code> wird von <code>service</code> importiert, das selbst Rang erhält.</p>"
)

h2("Commits, Churn, Fix-Commits und Alter")
bedeutung(
    "Wie oft und wie stark eine Datei geändert wird. Häufig geänderte Dateien zeigen, wo die Entwicklung tatsächlich "
    "stattfindet und wo sich Qualitätsprobleme am stärksten auswirken."
)
berechnung(
    "Alle Werte stammen aus <code>git log --no-merges --numstat -M</code> über die gesamte Historie bis zum aktuellen "
    "Commit. Je Datei gibt es: <strong>Commits</strong> im Zeitfenster und insgesamt; <strong>Churn</strong>, die im "
    "Fenster hinzugefügten und gelöschten Zeilen (getrennt ausgewiesen); <strong>Fix-Commits</strong>, die Commits im "
    "Fenster, deren Betreff auf ein Muster wie <code>fix</code>, <code>bug</code>, <code>hotfix</code>, "
    "<code>fehler</code>, <code>behoben</code> passt (ohne Groß-/Kleinschreibung); und das <strong>Alter</strong>, also "
    "die Tage zwischen dem letzten Commit der Datei und dem letzten Commit des Repos. Wurde eine Datei umbenannt, werden "
    "ältere Commits unter dem alten Namen dem heutigen zugeordnet. Merge-Commits zählen nicht, Binärdateien zählen als "
    "Commit ohne Zeilen.",
)
im_code()
snip("git_history.py", "fh = files.get(path)", "fh.fixes += 1", after="def analyze",
     note="<code>current</code> bildet historische Pfade auf heutige ab; Dateien, die heute nicht mehr existieren, fallen bei <code>fh is None</code> heraus.")
snip("config.py", '"fix_pattern":', after='"history": {')
snip("pipeline.py", '"age_days":',
     note="<code>head</code> ist der Zeitstempel des letzten Commits im Repo, nicht das heutige Datum. So bleibt ein Report reproduzierbar.")

h2("Autoren und Hauptautor-Anteil")
bedeutung(
    "Wer an einer Datei gearbeitet hat und wie sehr sie in einer Hand liegt. Ein Hauptautor-Anteil von 100 % heißt: "
    "Es hat nur eine Person je daran committet."
)
berechnung(
    "Je Datei werden die Commits je Autor über die gesamte Historie gezählt. Vorher werden Identitäten zusammengeführt: "
    "zusätzlich zur <code>.mailmap</code> gelten zwei Einträge als dieselbe Person, wenn sie dieselbe E-Mail-Adresse "
    "oder denselben normalisierten Namen tragen (Kleinbuchstaben, nur a–z und 0–9, mindestens 3 Zeichen) oder wenn eine "
    "GitHub-noreply-Adresse auf diesen Namen zeigt. „Ada Lovelace“, „adalovelace“ und "
    "<code>123+adalovelace@users.noreply.github.com</code> werden so eine Person. <strong>Hauptautor</strong> ist der Autor "
    "mit den meisten Commits, der <strong>Anteil</strong> sind dessen Commits geteilt durch alle Commits der Datei. "
    "Dateien mit mindestens 90 % gelten beim Truck-Factor als Ein-Personen-Dateien."
)
im_code()
snip("git_history.py", "def tokens(name: str, email: str)", "return out or [\"r:\" + name]",
     note="Jede Identität erzeugt Schlüssel; Identitäten mit einem gemeinsamen Schlüssel werden per Union-Find vereint. "
     "Angezeigt wird der häufigste Name einer Gruppe.")
snip("pipeline.py", "auth_total = sum(h.authors.values())", "main_author, main_count =")
snip("pipeline.py", '"main_share":')

h2("Hotspot-Score")
bedeutung(
    "Der Hotspot-Score verbindet Änderungshäufigkeit und Komplexität, nach Adam Tornhill. Hoch ist er nur, wenn eine "
    "Datei sowohl komplex ist als auch oft geändert wird. Dort lohnt sich Refactoring am meisten, weil jede Verbesserung "
    "bei jeder künftigen Änderung wirkt."
)
berechnung(
    "Je Datei gehen zwei Größen ein: die Commits im Zeitfenster und die Summe der CCN aller Funktionen. Beide werden "
    "logarithmisch auf 0 bis 1 normiert: <strong>log(1 + x) / log(1 + Maximum)</strong>, das Maximum über alle "
    "analysierten Dateien. Der Logarithmus dämpft Ausreißer, damit eine einzige riesige Datei nicht alle anderen auf "
    "null drückt. Der <strong>Score ist das Produkt</strong> der beiden normierten Werte. Er liegt zwischen 0 und 1 und "
    "ist nur dann hoch, wenn beide Faktoren hoch sind. Die Rangliste im Report blendet Testdateien aus."
)
im_code()
snip("pipeline.py", "def _log_norm", until="def run")
snip("pipeline.py", "hot_c = _log_norm(", "hot_x = _log_norm(")
snip("pipeline.py", '"hotspot":')
beispiel(
    "<p>Die meistgeänderte Datei hat 40 Commits, die höchste CCN-Summe liegt bei 120. Eine Datei mit 10 Commits und "
    "CCN-Summe 60 erhält: log(11) / log(41) = 0,646 und log(61) / log(121) = 0,857, Score = 0,646 × 0,857 = "
    "<strong>0,553</strong>. Linear normiert wären es nur 0,25 × 0,5 = 0,125.</p>"
)

h2("Abstraktheit und Abstand zur Main Sequence")
bedeutung(
    "Nach Robert C. Martin sollten stabile Pakete abstrakt sein (Schnittstellen, abstrakte Klassen), instabile dürfen "
    "konkret sein. Der Abstand D misst je Verzeichnis, wie weit es von diesem Gleichgewicht entfernt ist: 0 liegt auf "
    "der „Main Sequence“, 1 maximal daneben."
)
berechnung(
    "Gerechnet wird auf Verzeichnisebene. <strong>Ca</strong> ist die Zahl verschiedener Dateien außerhalb, die "
    "Dateien des Verzeichnisses importieren, <strong>Ce</strong> die Zahl verschiedener Dateien außerhalb, die es "
    "importiert; daraus folgt die Instabilität I = Ce / (Ca + Ce). Die <strong>Abstraktheit A</strong> ist der Anteil "
    "abstrakter Typen an allen Typen: in Java Interfaces und abstrakte Klassen, in TypeScript Interfaces und "
    "<code>abstract class</code>, in Python Klassen mit Basis <code>ABC</code>, <code>ABCMeta</code> oder "
    "<code>Protocol</code> oder mit einer <code>@abstractmethod</code>. Der <strong>Abstand D = |A + I − 1|</strong>. "
    "Ein großes D bei kleinem A und kleinem I heißt „Zone of Pain“ (konkret und von vielen genutzt, also schwer zu "
    "ändern), bei großem A und großem I „Zone of Uselessness“ (Abstraktionen, die niemand nutzt). Aussagekräftig ist "
    "das vor allem bei Java; in TypeScript- und Python-Projekten ist A oft nahe 0."
)
im_code()
snip("graph_metrics.py", "ca, ce = len(ca_files[n]), len(ce_files[n])", '"distance": abs(abstr + inst - 1)', after="def _level")
snip("langs/java.py", "parsed.type_count += 1", "parsed.abstract_count += 1")
beispiel("<p>Ein Verzeichnis mit A = 0,2 und I = 0,3 hat den Abstand D = |0,2 + 0,3 − 1| = <strong>0,5</strong>: "
         "eher stabil, aber kaum abstrakt, also auf dem Weg in die Zone of Pain.</p>")

# ------------------------------------------------------------------------------------------------ Anhang
h1_anhang("A", "Konfiguration")
p(
    "Alle Schwellwerte lassen sich überschreiben. Eine <code>radar.toml</code> im Arbeitsverzeichnis wird automatisch "
    "gelesen, sonst per <code>--config</code> übergeben; nicht gesetzte Werte behalten ihren Default. Die Vorlage "
    "<code>radar.toml.example</code> im Repository:"
)
raw(code_block((ROOT / "radar.toml.example").read_text(encoding="utf-8").rstrip("\n"), "toml", '<span class="file">radar.toml.example</span>'))
raw(
    table(
        ["Schlüssel", "Default", "Wirkung"],
        [
            ["<code>history.since</code>", "12 months", "Zeitfenster für Commits, Churn, Fix-Commits, Change-Kopplung"],
            ["<code>history.max_files_per_commit</code>", "50", "größere Commits zählen nicht für Change-Kopplung"],
            ["<code>history.min_shared_commits</code>", "5", "Mindestzahl gemeinsamer Commits eines Paares"],
            ["<code>history.min_degree</code>", "0,3", "ab diesem Kopplungsgrad wird ein Paar gelistet"],
            ["<code>history.hidden_min_degree</code>", "0,5", "ab diesem Grad zählt ein Paar ohne Import als versteckt"],
            ["<code>grades.knowledge.owner_share</code>", "0,25", "Commit-Anteil, ab dem jemand als Kenner einer Datei gilt"],
            ["<code>grades.change_coupling.min_commits</code>", "20", "Mindestzahl Commits im Fenster für die Note"],
            ["<code>analysis.min_dup_tokens</code>", "50", "Mindestlänge eines Klons in Tokens"],
        ],
    )
)

h1_anhang("B", "Literatur")
raw(
    """<ul class="refs">
<li>Avelino, G., Passos, L., Hora, A., Valente, M. T. (2016): <em>A Novel Approach for Estimating Truck Factors.</em> ICPC 2016.</li>
<li>Baggen, R., Correia, J. P., Schill, K., Visser, J. (2012): <em>Standardized code quality benchmarking for improving software maintainability.</em> Software Quality Journal 20.</li>
<li>Heitlager, I., Kuipers, T., Visser, J. (2007): <em>A Practical Model for Measuring Maintainability.</em> QUATIC 2007.</li>
<li>Hitz, M., Montazeri, B. (1995): <em>Measuring Coupling and Cohesion in Object-Oriented Systems.</em> Proc. Int. Symposium on Applied Corporate Computing.</li>
<li>MacCormack, A., Rusnak, J., Baldwin, C. Y. (2006): <em>Exploring the Structure of Complex Software Designs: An Empirical Study of Open Source and Proprietary Code.</em> Management Science 52(7).</li>
<li>Martin, R. C. (2002): <em>Agile Software Development: Principles, Patterns, and Practices.</em> Prentice Hall.</li>
<li>McCabe, T. J. (1976): <em>A Complexity Measure.</em> IEEE Transactions on Software Engineering SE-2(4).</li>
<li>Page, L., Brin, S., Motwani, R., Winograd, T. (1999): <em>The PageRank Citation Ranking: Bringing Order to the Web.</em> Stanford InfoLab.</li>
<li>Tornhill, A. (2015): <em>Your Code as a Crime Scene.</em> The Pragmatic Bookshelf.</li>
</ul>"""
)

# --------------------------------------------------------------------------------------------- Seite

CSS = """
@page { size: A4; margin: 20mm 18mm 20mm 18mm;
  @bottom-left { content: "repo-radar · Handbuch der Kennzahlen"; font: 8pt 'Ubuntu Sans', sans-serif; color: #7a8290; }
  @bottom-right { content: counter(page); font: 8pt 'Ubuntu Sans', sans-serif; color: #7a8290; } }
@page :first { margin: 0; @bottom-left { content: none; } @bottom-right { content: none; } }
:root { --ink: #1d2330; --muted: #5c6575; --line: #dde1e8; --accent: #1f5fbf; --accent-soft: #eaf1fc; --code-bg: #f6f7f9; }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { margin: 0; font: 9.8pt/1.45 'Ubuntu Sans', 'Noto Sans', sans-serif; color: var(--ink); background: #fff; hyphens: auto; }
p { margin: 0 0 7pt; text-align: left; }
code { font: 8.6pt 'Ubuntu Sans Mono', 'DejaVu Sans Mono', monospace; background: var(--code-bg); padding: 0 2.5pt; border-radius: 2pt; }
strong { font-weight: 600; }

.cover { height: 296.8mm; overflow: hidden; padding: 62mm 24mm 24mm; display: flex; flex-direction: column; break-after: page;
  background: linear-gradient(160deg, #123a75 0%, #1f5fbf 62%, #2f78d6 100%); color: #fff; }
.cover .kicker { font-size: 11pt; letter-spacing: .16em; text-transform: uppercase; opacity: .8; }
.cover h1 { font-size: 40pt; line-height: 1.05; margin: 8mm 0 6mm; font-weight: 700; border: 0; padding: 0; color: #fff; break-before: auto; }
.cover .sub { font-size: 14pt; max-width: 125mm; opacity: .92; line-height: 1.4; }
.cover .meta { margin-top: auto; font-size: 10pt; opacity: .85; line-height: 1.7; }
.cover svg { margin-bottom: 10mm; }

.toc { break-after: page; }
.toc h1 { margin-top: 0; }
.toc ol { list-style: none; padding: 0; margin: 0; }
.toc li.l1 { font-weight: 600; margin-top: 7pt; font-size: 10.5pt; }
.toc li.l2 { padding-left: 9mm; color: var(--muted); }
.toc a { color: inherit; text-decoration: none; }
.toc .n { display: inline-block; width: 9mm; color: var(--accent); font-variant-numeric: tabular-nums; }
.toc li.l2 .n { width: 10mm; }

h1 { font-size: 20pt; line-height: 1.2; margin: 0 0 10pt; padding-bottom: 6pt; border-bottom: 2pt solid var(--accent); break-before: page; break-after: avoid; }
h1 .num, h2 .num { color: var(--accent); margin-right: 8pt; font-variant-numeric: tabular-nums; }
h2 { font-size: 14pt; margin: 20pt 0 8pt; break-after: avoid; }
h3 { font-size: 10.5pt; margin: 12pt 0 5pt; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; break-after: avoid; }

.meaning { background: var(--accent-soft); border-left: 3pt solid var(--accent); padding: 7pt 10pt 1pt; margin: 6pt 0 8pt; break-inside: avoid; }
.meaning .label, .example .label { font-size: 8pt; text-transform: uppercase; letter-spacing: .1em; color: var(--accent); font-weight: 700; margin-bottom: 2pt; }
.meaning p { font-size: 10.5pt; }
.example { border: 1pt solid var(--line); border-radius: 4pt; padding: 7pt 10pt 2pt; margin: 8pt 0; break-inside: avoid; }
.example .label { color: #8a5a00; }
.example figure.code { margin: 4pt 0 6pt; }
.principle { border: 1pt solid var(--line); border-radius: 4pt; padding: 8pt 10pt; margin: 10pt 0; background: #fafbfc; }

figure.code { margin: 6pt 0 4pt; break-inside: auto; }
figure.code.keep { break-inside: avoid; }
figure.code .caption { font-size: 8pt; color: var(--muted); margin-bottom: 2pt; }
figure.code .caption .file { font-family: 'Ubuntu Sans Mono', monospace; color: var(--ink); }
.hl { background: var(--code-bg) !important; border: 1pt solid var(--line); border-radius: 3pt; padding: 5pt 7pt; }
.hl pre { margin: 0; font: 7.7pt/1.42 'Ubuntu Sans Mono', 'DejaVu Sans Mono', monospace; white-space: pre-wrap; overflow-wrap: anywhere; background: none !important; }
.hl pre code { background: none; padding: 0; font: inherit; }
.hl .linenos { color: #9aa2ae; padding-right: 7pt; user-select: none; }
.codenote { font-size: 8.8pt; color: var(--muted); margin: 0 0 8pt; }

table { border-collapse: collapse; width: 100%; margin: 6pt 0 8pt; font-size: 9pt; break-inside: avoid; }
th, td { text-align: left; padding: 3.5pt 6pt; border-bottom: 1pt solid var(--line); vertical-align: top; }
th { font-weight: 600; color: var(--muted); border-bottom: 1.2pt solid #c3c9d3; }
table.compact { width: auto; }
table.grades { width: auto; }
table.grades td { padding-right: 16pt; }
td.grade { font-weight: 700; text-align: center; width: 22pt; color: #fff; padding: 3.5pt 0; }
td.gA { background: #1a7f37; } td.gB { background: #5a9a2a; } td.gC { background: #b58105; } td.gD { background: #c4511a; } td.gE { background: #b42318; }
.small { font-size: 8.5pt; color: var(--muted); }

dl.terms { margin: 4pt 0 8pt; }
dl.terms dt { font-weight: 600; margin-top: 5pt; }
dl.terms dd { margin: 1pt 0 0 0; padding-left: 10pt; border-left: 2pt solid var(--line); }
ol.pipeline { padding-left: 16pt; } ol.pipeline li { margin-bottom: 3pt; }
ul { padding-left: 14pt; } ul li { margin-bottom: 3pt; }
ul.refs li { margin-bottom: 5pt; }
"""

COVER_ICON = """<svg width="64" height="64" viewBox="0 0 64 64" aria-hidden="true">
<circle cx="32" cy="32" r="29" fill="none" stroke="#fff" stroke-width="3" opacity=".9"/>
<circle cx="32" cy="32" r="18" fill="none" stroke="#fff" stroke-width="3" opacity=".7"/>
<circle cx="32" cy="32" r="6" fill="#fff"/>
<path d="M32 32 L54 14" stroke="#fff" stroke-width="3" stroke-linecap="round"/></svg>"""


def build_html() -> str:
    today = date.today()
    stand = f"{today.day}. {MONATE[today.month - 1]} {today.year}"
    cover = f"""<section class="cover">{COVER_ICON}
<div class="kicker">repo-radar</div>
<h1>Handbuch der<br>Kennzahlen</h1>
<div class="sub">Was repo-radar misst, wie es rechnet und wie aus Messwerten Noten werden: mit Codeausschnitten und Rechenbeispielen.</div>
<div class="meta">Version {html.escape(__version__)} · Stand {stand}</div>
</section>"""
    items = []
    for level, num, title in toc:
        anchor = ("a" + num) if num.isalpha() else ("k" + num.replace(".", "-"))
        items.append(f'<li class="l{level}"><a href="#{anchor}"><span class="n">{num}</span>{title}</a></li>')
    toc_html = f'<section class="toc"><h1 style="break-before:auto">Inhalt</h1><ol>{"".join(items)}</ol></section>'
    body = "\n".join(parts)
    # erstes Kapitel folgt direkt auf das Inhaltsverzeichnis, das bereits umbricht
    body = body.replace('<h1 id="k1">', '<h1 id="k1" style="break-before:auto">', 1)
    return f"""<!doctype html><html lang="de"><head><meta charset="utf-8"><title>repo-radar – Handbuch der Kennzahlen</title>
<style>{_FORMATTER_CSS}\n{CSS}</style></head><body>{cover}{toc_html}<main>{body}</main></body></html>"""


def main() -> None:
    doc = build_html()
    with tempfile.TemporaryDirectory(prefix="rr-handbuch-") as tmp:
        src = Path(tmp) / "handbuch.html"
        src.write_text(doc, encoding="utf-8")
        if "--html" in sys.argv:
            (OUT.with_suffix(".html")).write_text(doc, encoding="utf-8")
        subprocess.run(
            ["google-chrome", "--headless=new", "--no-pdf-header-footer", "--virtual-time-budget=3000",
             f"--print-to-pdf={OUT}", src.as_uri()],
            check=True, capture_output=True, timeout=120,
        )  # fmt: skip
    print(OUT)


if __name__ == "__main__":
    main()
