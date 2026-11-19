# repo-radar

Analysiert beliebige Git-Repositories auf **Codequalität** und **Kopplung** und erzeugt einen **interaktiven
HTML-Report**, der beim Verstehen und Verbessern einer Codebasis hilft.

## Zusammenfassung

repo-radar beantwortet drei Fragen zu einem Repository:

1. **Wie gut ist der Code?** Komplexität, Funktionsgröße, Duplikation und Kohäsion, bewertet mit Noten A–E je Dimension.
2. **Wie stark hängen die Teile voneinander ab?** Import-Graph auf Datei-, Verzeichnis- und Projektebene mit
   Fan-in/-out, Instabilität, Änderungsreichweite, Zyklen und Propagation Cost.
3. **Wo lohnt sich Arbeit?** Die Git-Historie zeigt Hotspots (komplexer Code, der oft geändert wird), versteckte
   Kopplung (Dateien, die immer gemeinsam geändert werden, ohne sich zu importieren) und die Wissensverteilung
   (Truck-Factor).

Die Kombination ist der Kern: Komplexer Code, der nie angefasst wird, ist harmlos. Komplexer Code, der ständig
geändert wird und von dem viele andere Dateien abhängen, ist das eigentliche Risiko.

Technisch ist repo-radar ein Python-CLI. Es führt keinen Code des analysierten Repos aus, braucht keinen Server und
schreibt den Report als **eine einzelne HTML-Datei**, die offline läuft und sich weitergeben lässt. Daneben entsteht
`analysis.json` mit allen Rohdaten (stabiles Schema, z. B. für Auswertungen mit Claude).

Unterstützt werden alle Sprachen, die [lizard](https://github.com/terryyin/lizard) kennt (u. a. TypeScript,
JavaScript, Java, Python, Kotlin, Go, C#, Rust). Den Abhängigkeitsgraphen mit echter Import-Auflösung gibt es für
**TypeScript/JavaScript (inkl. Angular und Nx), Java und Python**.

## Installation

Voraussetzungen: Python ≥ 3.12, [uv](https://docs.astral.sh/uv/), git. Optional Node.js (für die Duplikationsanalyse).

```bash
cd repo-radar
uv tool install .        # danach ist `repo-radar` global verfügbar
```

Ohne Installation: `uv run repo-radar …` im Projektordner.

## Benutzung

```bash
repo-radar analyze ~/projects/my-app --open             # lokales Repo, Report danach öffnen
repo-radar analyze ~/projects/my-app/libs               # nur ein Teilbaum
repo-radar analyze https://github.com/spring-projects/spring-petclinic
repo-radar analyze . --since 6m -x 'sample/**' -t 'integration/**'
```

Ausgabe: `radar-out/<name>/report.html` und `radar-out/<name>/analysis.json`.

| Option | Bedeutung |
| --- | --- |
| `--since 6m` | Zeitfenster der Historie für Churn und Change-Kopplung (Default `12 months`; auch `2y`, `2025-01-01`, `all`) |
| `-x, --exclude GLOB` | zusätzliche Excludes, mehrfach möglich |
| `-t, --tests GLOB` | zusätzlich als Testcode werten, mehrfach möglich |
| `-u, --untracked` | auch ungetrackte Dateien analysieren, die nicht per `.gitignore` ausgeschlossen sind |
| `--no-dup` | Duplikationsanalyse überspringen (schneller, kein Node nötig) |
| `-c, --config FILE` | Konfiguration; eine `radar.toml` im Arbeitsverzeichnis wird automatisch gelesen |
| `-o, --out DIR` | Ausgabeordner |
| `--workers N` | parallele Prozesse fürs Parsen |

URLs werden nach `~/.cache/repo-radar/repos/` geklont und bei erneutem Aufruf aktualisiert.

### Welche Dateien analysiert werden

Grundlage ist `git ls-files`: Es zählen nur getrackte Dateien, alles aus der `.gitignore` ist damit automatisch
außen vor. Mit `--untracked` kommen ungetrackte, nicht ignorierte Dateien hinzu. Ein Repo ohne Commits wird
automatisch so analysiert; Historie, Hotspots und die Noten zu versteckter Kopplung und Wissensverteilung entfallen dann. Zusätzlich schließen Default-Excludes eingecheckte Dateien aus, die das Ergebnis verfälschen würden
(Build-Output, `vendor/`, `*.min.js`, `*.d.ts`, generierter Code, Migrationen; Liste in `src/repo_radar/config.py`).
Testcode wird über Namen und Ordner erkannt (`*.spec.ts`, `test_*.py`, `*Test.java`, `tests/`, `e2e/` …). Er erscheint
im Report, zählt aber nicht in Noten, Hotspot-Rangliste und Graph-Metriken.

## Was gemessen wird

| Dimension | Metrik | Notengrenzen |
| --- | --- | --- |
| Komplexität | zyklomatische Komplexität (McCabe) je Funktion; Anteil des Codes in Funktionen mit CCN 11–20 / 21–50 / > 50 | SIG-Modell |
| Funktionsgröße | NLOC je Funktion; Anteil des Codes in Funktionen mit 16–30 / 31–60 / > 60 NLOC | SIG-Modell |
| Duplikation | Anteil duplizierter Zeilen (tokenbasiert, jscpd) | SIG-Modell |
| Strukturelle Kopplung | Propagation Cost: Anteil aller Dateipaare mit direkter oder transitiver Abhängigkeit | Heuristik |
| Zyklen | Anteil der Dateien in Import-Zyklen (stark zusammenhängende Komponenten) | Heuristik |
| Kohäsion | Anteil der Klassen mit LCOM4 > 1 | Heuristik |
| Versteckte Kopplung | Anteil der Dateien in Paaren, die oft gemeinsam committet werden, ohne sich zu importieren | Heuristik |
| Wissensverteilung | Truck-Factor: wie viele Personen gehen müssten, bis die Hälfte der Dateien keinen Kenner mehr hat | Heuristik |

„SIG-Modell“ bezieht sich auf das Wartbarkeitsmodell der Software Improvement Group (Heitlager, Kuipers & Visser 2007;
Baggen et al. 2012). Alle Grenzen sind in `radar.toml` anpassbar (Vorlage: `radar.toml.example`).

Je Datei kommen hinzu: Fan-in/Fan-out, Instabilität `Ce/(Ca+Ce)`, Änderungsreichweite (wie viele Dateien transitiv
abhängen), PageRank, Commits, Churn, Fix-Commits, Alter, Autoren, Anteil des Hauptautors, Duplikate und der
**Hotspot-Score** (log-normierte Commits × log-normierte CCN-Summe). Je Verzeichnis zusätzlich Abstraktheit und
Abstand zur Main Sequence nach Robert C. Martin (aussagekräftig vor allem bei Java).

### Import-Auflösung

- **TypeScript/JavaScript:** relative Pfade, `tsconfig`-`paths`/`baseUrl` inklusive `extends`-Ketten (Nx), Workspace-Pakete
  über den `package.json`-Namen, `.js`-Specifier auf `.ts`-Dateien. Benannte Importe aus Barrels (`index.ts`) werden bis
  zur Datei durchgereicht, die das Symbol definiert.
- **Java:** Index aller Typen nach Package, Einzel-, Wildcard- und statische Imports sowie Referenzen auf Klassen im
  selben Package ohne Import.
- **Python:** Paketwurzeln über `__init__.py` und `src`-Layout, absolute und relative Imports; Standardbibliothek wird
  nicht als externe Abhängigkeit gezählt.

**Schwache Kanten:** Lazy-Imports (`import()`, Imports innerhalb von Funktionen) und reine Typ-Importe (`import type`,
`if TYPE_CHECKING:`) zählen für Fan-in/-out, nicht aber für Zyklen und Propagation Cost. Sie erzeugen zur Laufzeit
keine Abhängigkeit beim Laden.

## Der Report

| Ansicht | Inhalt |
| --- | --- |
| Überblick | Notenkarten mit Herleitung, größten Beiträgen und KI-Prompt, Kennzahlen, Commit-Aktivität, Top-Hotspots, versteckte Kopplung, Zyklen, Sprachen, externe Pakete, Hinweise zur Messung |
| Hotspot-Karte | Treemap über die Verzeichnisstruktur, Fläche und Farbe wählbar (Hotspot, Komplexität, Churn, Alter, Hauptautor, LCOM4, Duplikation, Zyklen), Zoom per Klick |
| Abhängigkeiten | Dependency Structure Matrix auf Verzeichnis- oder Projektebene mit Drill-down; Graph um eine Datei oder einen Zyklus |
| Change-Kopplung | Netzwerk und filterbare Liste gemeinsam geänderter Dateipaare, versteckte Paare hervorgehoben |
| Dateien | alle Metriken je Datei, sortier- und filterbar (auch per Regex), CSV-Export |

Jede Datei hat eine Detailansicht mit Funktionen, Klassen und LCOM4-Gruppen, Imports in beide Richtungen,
gemeinsam geänderten Dateien, Duplikaten und Autoren. Ansichten und Filter stehen in der URL (`#deps?mode=graph&focus=…`)
und lassen sich teilen. Hell- und Dunkelmodus folgen dem System oder werden über den Schalter oben rechts gewählt.

Zu jeder bewerteten Note öffnet der Button **KI-Prompt** in der Detailkarte einen Arbeitsauftrag für einen KI-Agenten
(z. B. Claude Code): eine kurze Anweisung, was zu tun ist, gefolgt von den Fundstellen mit Datei und Zeilenbereich,
wichtigste zuerst. Wie viele Fundstellen der Auftrag enthält, ist einstellbar (Default 3, höchstens die 15 größten
Beiträge) und wird im Browser gemerkt. Aufgenommen werden nur echte Befunde, also z. B. nur Funktionen über der
Komplexitätsschwelle.

## Bekannte Grenzen

**Grundsätzlich**

- Metriken sind Indikatoren, keine Urteile. Belastbar wird eine Aussage erst, wo mehrere Signale zusammenfallen.
- Die SIG-Grenzen wurden an Industrie-Benchmarks kalibriert, die übrigen Grenzen sind eigene Setzungen. Noten
  vergleichen Repos daher nur grob; aussagekräftiger sind Ranglisten innerhalb eines Repos und der Verlauf über die Zeit.
- Die Propagation Cost fällt bei kleinen Systemen (< 50 Dateien) naturgemäß höher aus.

**Dateiauswahl**

- Dateien, die committet wurden, bevor sie in die `.gitignore` kamen, sind weiterhin getrackt und werden mitanalysiert.
- Bei lokalen Pfaden wird der Inhalt im Arbeitsverzeichnis gelesen; nicht committete Änderungen fließen in die
  Code-Metriken ein, aber nicht in die Historie. Ungetrackte Dateien fehlen, außer mit `--untracked`; sie haben
  keine Historie.
- Testcode wird über Namensmuster erkannt. Ordner wie `integration/`, `sample/` oder `examples/` gelten als
  Produktivcode, solange sie nicht per `-t` oder `-x` zugeordnet werden.

**Abhängigkeitsgraph**

- Import-Auflösung nur für TS/JS, Java und Python. Dateien anderer Sprachen fehlen in Graph, Zyklen, versteckter
  Kopplung und LCOM4.
- Angular-Templates (`.html`) und Single-File-Components (`.vue`, `.svelte`) werden nicht auf Imports geparst.
  Bei Standalone-Komponenten ist die Nutzung über deren `imports` trotzdem sichtbar.
- TS: `exports`-Maps in `package.json`, Specifier aus Variablen oder Template-Strings mit Platzhaltern sowie
  Webpack-/Vite-Aliase außerhalb der `tsconfig` werden nicht aufgelöst. Namespace-Importe (`import * as`) aus
  Barrels bleiben am Barrel hängen.
- Java: Same-Package- und Wildcard-Referenzen werden über Typnamen erkannt; eine zufällige Namensgleichheit kann eine
  falsche Kante erzeugen. Voll qualifizierte Typnamen im Code ohne Import werden nicht erkannt.
- Python: dynamische Imports (`importlib`, `__import__`) bleiben unsichtbar; die Standardbibliothek richtet sich nach
  der Python-Version, mit der repo-radar läuft.

**Kohäsion (LCOM4)**

- Bewusste Variante: Klassen ohne Felder werden nicht bewertet, Getter/Setter zählen als Feldzugriff, Methoden ohne
  jeden Instanzbezug bilden keine eigene Gruppe.
- Geerbte Felder und von Lombok oder Dekoratoren erzeugte Member sind unsichtbar.

**Historie**

- Umbenennungen werden über die Ähnlichkeitserkennung von git (`-M`) verfolgt; stark umgebaute Dateien verlieren dabei
  ihre ältere Historie.
- Merge-Commits werden ignoriert. Squash-Merges fassen viele Änderungen zusammen und können Change-Kopplung erzeugen,
  die es im Entwicklungsalltag nicht gab. Commits mit mehr als 50 Dateien zählen für die Kopplung nicht.
- Autoren werden über E-Mail und normalisierten Namen zusammengeführt (zusätzlich zu `.mailmap`). Das kann
  verschiedene Personen mit gleichem Namen vereinen oder Aliase übersehen.
- Fix-Commits werden über ein Muster in der Commit-Nachricht erkannt (`fix`, `bug`, `fehler` …), nicht über einen
  Issue-Tracker. Der Truck-Factor ist eine vereinfachte, commit-basierte Variante.

**Duplikation und Laufzeit**

- Die Duplikationsanalyse braucht Node.js und lädt beim ersten Lauf `jscpd@4.0.5` per `npx` aus dem npm-Registry.
  Sie läuft in einem leeren Temp-Verzeichnis, damit keine `.npmrc` des analysierten Repos greift.
- Die tree-sitter-Grammatiken werden beim ersten Lauf nach `~/.cache/tree-sitter-language-pack/` geladen. Für den
  Offline-Betrieb muss also mindestens ein Lauf mit Netz vorausgehen.
- Private Repos per URL brauchen funktionierende git-Zugangsdaten.

**Report**

- Große Repos erzeugen große Reports (nest mit ~2.400 Dateien: 4,7 MB); das Laden dauert trotzdem unter einer Sekunde.
- Die Matrix zeigt höchstens 300 Gruppen, Graphen höchstens 220 Knoten, das Kopplungsnetz die 150 stärksten Paare.
  Im JSON stehen höchstens 5.000 Kopplungspaare und 3.000 Klonpaare.
- Der Report enthält Autorennamen aus der Git-Historie. Das ist vor dem Weitergeben zu bedenken.

## Entwicklung

```bash
uv run pytest                       # Tests gegen im Test erzeugte Mini-Repos
uv run repo-radar analyze <pfad>
```

Aufbau der Pipeline, Erweiterungspunkte (neue Sprache, neue Note, neue Report-Ansicht) und Konventionen stehen in
[`CLAUDE.md`](CLAUDE.md).

## Lizenz

MIT, siehe [`LICENSE`](LICENSE). Mitgeliefert wird [D3](https://d3js.org) v7.9.0 (ISC-Lizenz, Copyright Mike Bostock)
in `src/repo_radar/report/vendor/`.
