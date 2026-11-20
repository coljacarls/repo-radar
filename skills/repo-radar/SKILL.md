---
name: repo-radar
description: Codequalität eines Git-Repos mit repo-radar messen (Noten A–E je Metrik) und per Interview einen Arbeitsauftrag mit Checkliste daraus machen und abarbeiten. Use when the user asks how good a repo's code is, wants a quality check, technical debt or refactoring priorities, or names repo-radar.
allowed-tools: Bash(repo-radar:*)
---

# repo-radar

repo-radar analysiert ein Git-Repo statisch und aus der Historie. Fortschritt geht nach stderr, Ergebnisse nach stdout.
Es führt keinen Code des Repos aus und schreibt nur in den Ausgabeordner.

## Ablauf

1. **Tool prüfen:** `repo-radar version`. Fehlt der Befehl, schlag die Installation vor
   (`uv tool install git+https://github.com/coljacarls/repo-radar`) und warte auf die Zustimmung.

2. **Analysieren.** Leg die Ausgabe außerhalb des Repos ab, damit der Arbeitsbaum sauber bleibt:

   ```bash
   repo-radar analyze <repo-pfad> -q -o ~/.cache/repo-radar/<repo-name>
   ```

   Bei großen Repos dauert das Minuten. Ohne Node/npx: `--no-dup`. Weitere Optionen (Zeitfenster, Excludes) zeigt
   `repo-radar analyze --help`. Liegt für den aktuellen Stand schon eine Analyse vor, reicht `repo-radar grades <ordner>`.
   Fertig, sobald die Notentabelle vorliegt.

3. **Berichten.** Gib die Tabelle wieder (Note, Metrik, Kennwert) und fasse in zwei bis vier Sätzen zusammen: wo der
   Code gut dasteht, wo die schwächsten Noten liegen und welche Metriken nicht bewertet wurden (Grund steht im
   Kennwert). A ist sehr gut, E kritisch. Nenn den Pfad zu `report.html` zum Selbst-Ansehen.

4. **Interview.** Frag, ob der Nutzer in einer Kategorie tätig werden will, mit dem Frage-Werkzeug des Agenten
   (Claude Code: AskUserQuestion), sonst als nummerierte Auswahl im Chat. Warte auf die Antwort.
   - Kategorie: nur Zeilen mit Fundstellen > 0, schwächste Note zuerst, die schwächste als Empfehlung markiert,
     dazu die Option „nichts tun“ (dann endet der Ablauf hier).
   - Anzahl: wie viele der Top-Fundstellen, 1 bis zur Zahl in der Spalte Fundstellen, Default 3.

5. **Auftrag erzeugen:**

   ```bash
   repo-radar task ~/.cache/repo-radar/<repo-name> <schlüssel> -n <anzahl>
   ```

   Ausgabe ist der Pfad einer Markdown-Datei mit Auftrag und Checkliste. Exit-Code 2 mit Hinweis auf `--force` heißt:
   Es gibt schon eine Checkliste, womöglich mit Fortschritt. Frag, ob sie ersetzt oder weitergeführt werden soll.

6. **Abarbeiten.** Lies die Datei ganz; der Abschnitt „Auftrag“ ist dein Arbeitsauftrag. Arbeite die Checkliste
   von oben nach unten ab. Nach jeder Fundstelle: Tests des Projekts laufen lassen, den Punkt in der Datei abhaken
   (`- [x]`, bewusst ausgelassene mit Grund). Zeilennummern gelten für den analysierten Stand; nach eigenen
   Änderungen an derselben Datei findest du die Stelle über Funktions-, Klassen- oder Dateinamen.
   Fertig, wenn jeder Punkt abgehakt ist, die Tests grün sind und `repo-radar analyze` mit denselben Optionen erneut
   gelaufen ist. Berichte die Note vorher und nachher.

## Was eine erneute Analyse zeigt

Komplexität, Funktionsgröße, Duplikation, Kopplung, Zyklen und Kohäsion messen den Arbeitsbaum und reagieren sofort.
Versteckte Kopplung und Wissensverteilung kommen aus der Git-Historie: Ihre Noten bewegen sich erst über viele
Commits. Berichte bei diesen beiden stattdessen, was konkret erledigt wurde.
