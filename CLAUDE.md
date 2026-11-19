# repo-radar

Python-CLI (uv, Python 3.12), analysiert Git-Repos und schreibt einen Offline-HTML-Report. Nutzung und Metriken: `README.md`.

## Pipeline (`src/repo_radar/pipeline.py`)

`source` (Repo/Klon, `git ls-files`) → `inventory` (Sprache, Test, Projekt, Package) → `parsing` (pro Datei lizard +
tree-sitter, parallel) → `deps` (Import-Auflösung → Dateigraph) → `graph_metrics` (networkx: Ca/Ce/I, SCC, Reichweite,
Propagation Cost; Datei-, Verzeichnis-, Projektebene) → `git_history` (Churn, Autoren, Change-Kopplung) → `duplication`
(jscpd) → `scoring` (Noten) → JSON → `report/build.py` (Template + CSS + JS + Daten in eine HTML-Datei).

## Erweiterungspunkte

- **Neue Sprache mit Import-Auflösung:** Extraktor in `langs/<sprache>.py` (`extract(root) -> Parsed`), Resolver in
  `deps/<sprache>.py`, Eintrag in `inventory.DEP_FAMILY`, `parsing._GRAMMAR`/`_EXTRACT` und `deps.build_graph`.
- **Neue Note:** in `scoring.compute` anhängen, Defaults in `config.DEFAULTS["grades"]`. Jede Note liefert Wert,
  Erklärung, Quelle der Schwellwerte und Top-Befunde, der Report rendert das generisch.
- **Neue Report-Ansicht:** `report/views/<name>.js` mit `RR.register(id, titel, render)`, in `report/build.SCRIPTS`
  eintragen (Reihenfolge: `app.js` zuerst, `detail.js` zuletzt, weil es `RR.start()` aufruft).

## Konventionen

- Kanten-Flag „schwach“ (Lazy- oder Typ-Import) zählt nicht für Zyklen/Propagation Cost. Wer neue Importarten
  einführt, entscheidet das bewusst (`Import.kind`).
- Graph-Metriken und Noten nur über Produktivcode (`is_test` ist False). Tests bleiben als Kanten im JSON.
- Report: Farben nur über CSS-Tokens (`--series-*`, `--seq-*`, Status `--good`…`--critical`), Palette nach dem
  dataviz-Referenzsatz; Noten immer mit Buchstabe, nie nur Farbe. D3 v7.9.0 liegt in `report/vendor/`.
- Kein Code des analysierten Repos wird ausgeführt; `npx` läuft in einem leeren Temp-Verzeichnis.
- Nach Änderungen: `uv run pytest`, dann einen Report bauen und im Browser ansehen (Headless-Screenshot:
  `google-chrome --headless=new --screenshot=x.png --window-size=1440,1100 --virtual-time-budget=4000 <url>`;
  `file://` funktioniert dafür nicht zuverlässig, Ausgabeordner per `python3 -m http.server` servieren).
