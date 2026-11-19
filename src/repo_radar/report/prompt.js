/* Arbeitsauftrag für einen KI-Agenten je Note: kurze Anweisung + Fundstellen (wichtigste zuerst).
 * Die Reihenfolge der Fundstellen ist die von scoring.py („Größte Beiträge“), hier wird nur gefiltert und formatiert. */
(function () {
  'use strict';
  const { data: D, fmt, esc } = RR;
  const G = D.meta.config.grades;

  const range = (t) => (t.line ? `:${t.line}${t.end && t.end !== t.line ? `-${t.end}` : ''}` : '');
  const strongEdges = new Map(); // Datei-Index → Ziele (nur starke Kanten, wie bei der Zyklenmessung)
  for (const [a, b, weak] of D.edges) if (!weak) (strongEdges.get(a) || strongEdges.set(a, []).get(a)).push(b);

  /** Je Note: Arbeitsanweisung, Filter auf echte Befunde und Formatierung einer Fundstelle. */
  const SPECS = {
    complexity: {
      task: () =>
        `Senke die zyklomatische Komplexität (McCabe-CCN) der folgenden Funktionen auf möglichst ≤ ${G.complexity.risk[0]}, ohne ihr Verhalten zu ändern. ` +
        'Zerlege sie in kleine, sprechend benannte Hilfsfunktionen, ersetze tiefe Verschachtelung durch Guard Clauses und lange if/else- oder switch-Ketten durch Lookup-Tabellen oder Polymorphie. ' +
        'Sichere das Verhalten vorher mit Tests ab, falls keine vorhanden sind.',
      keep: (t) => t.value > G.complexity.risk[0],
      ref: (t) => `${t.file}${range(t)} · ${t.label} (CCN ${t.value}, ${t.nloc} NLOC)`,
    },
    unit_size: {
      task: () =>
        `Kürze die folgenden Funktionen auf möglichst ≤ ${G.unit_size.risk[0]} NLOC, ohne ihr Verhalten zu ändern. ` +
        'Extrahiere zusammenhängende Abschnitte in eigene, sprechend benannte Funktionen mit klaren Parametern und Rückgabewerten, statt den Code nur umzubrechen. ' +
        'Sichere das Verhalten vorher mit Tests ab, falls keine vorhanden sind.',
      keep: (t) => t.value > G.unit_size.risk[0],
      ref: (t) => `${t.file}${range(t)} · ${t.label} (${t.value} NLOC, CCN ${t.ccn})`,
    },
    duplication: {
      task: () =>
        'Beseitige die folgenden Code-Duplikate. Prüfe je Paar, ob beide Stellen fachlich dasselbe tun; wenn ja, extrahiere die gemeinsame Logik ' +
        'in eine Funktion oder ein Modul an passender Stelle und nutze sie an beiden Stellen. ' +
        'Bewusst getrennte Varianten, die sich fachlich auseinanderentwickeln werden, lässt du stehen und begründest das kurz.',
      keep: () => true,
      ref: (t) => `${t.file}:${t.line}-${t.end} <-> ${t.other}:${t.other_line}-${t.other_end} (${t.value} Zeilen)`,
    },
    coupling: {
      task: () =>
        'Senke die strukturelle Kopplung rund um die folgenden Dateien: Von ihnen hängen viele Dateien direkt oder transitiv ab, eine Änderung dort strahlt also weit aus. ' +
        'Prüfe, welche Imports nur einzelne Hilfsfunktionen oder Typen nutzen, teile zu breite Module nach Verantwortung auf und führe Abhängigkeiten über schmale Schnittstellen. ' +
        'Bewusst zentrale, stabile Basistypen bleiben, wie sie sind.',
      keep: (t) => t.value > 0,
      ref: (t) => `${t.file} (Änderungsreichweite ${t.value} Dateien, Fan-in ${t.ca}, Fan-out ${t.ce})`,
    },
    cycles: {
      task: () =>
        'Löse die folgenden zyklischen Import-Abhängigkeiten auf. Suche je Zyklus die Kante, die gegen die gewünschte Schichtung zeigt, und kehre sie um: ' +
        'gemeinsam genutzten Code in ein eigenes Modul verschieben, eine Schnittstelle in die untere Schicht legen (Dependency Inversion) oder Callbacks/Events statt direkter Imports nutzen. ' +
        'Weiche nicht auf Lazy- oder reine Typ-Imports aus, nur damit der Zyklus aus der Messung fällt.',
      keep: () => true,
      ref: (t) => {
        const members = D.cycles[t.cycle];
        const inCycle = new Set(members);
        const lines = members.map((fi) => {
          const targets = (strongEdges.get(fi) || []).filter((b) => inCycle.has(b)).map((b) => D.files[b].path);
          return `   - ${D.files[fi].path} -> ${targets.join(', ')}`;
        });
        return `Zyklus #${t.cycle + 1} (${members.length} Dateien, Imports innerhalb des Zyklus):\n${lines.join('\n')}`;
      },
    },
    cohesion: {
      task: () =>
        'Prüfe die folgenden Klassen mit LCOM4 > 1: Sie zerfallen in Gruppen von Methoden, die weder gemeinsame Felder nutzen noch sich gegenseitig aufrufen. ' +
        'Gehören die Gruppen fachlich nicht zusammen, extrahiere sie in eigene Klassen und passe die Aufrufer an. ' +
        'Ist die Trennung nur ein Messartefakt (z. B. Delegation über ein anderes Objekt), lass die Klasse stehen und begründe das kurz.',
      keep: () => true,
      ref: (t) => {
        const groups = (t.groups || []).map((g) => `[${g.join(', ')}]`).join(' | ');
        const iso = t.isolated && t.isolated.length ? `; ohne Instanzbezug: ${t.isolated.join(', ')}` : '';
        return `${t.file}${range(t)} · Klasse ${t.label} (LCOM4 ${t.value}; Gruppen aus Methoden und Feldern: ${groups}${iso})`;
      },
    },
    change_coupling: {
      task: () =>
        'Untersuche die folgenden Dateipaare: Sie werden laut Git-Historie oft gemeinsam geändert, importieren sich aber nicht direkt. ' +
        'Finde je Paar den gemeinsamen Änderungsgrund (git log -- <a> <b>), etwa geteilte Annahmen, Formate, Konstanten oder kopierte Logik, ' +
        'und mache die Abhängigkeit explizit: gemeinsamen Typ, gemeinsame Konstante oder gemeinsames Modul einführen oder Logik zusammenlegen. ' +
        'Ist die Kopplung gewollt (z. B. Code und zugehörige Doku), notiere das kurz.',
      keep: () => true,
      ref: (t) => `${t.file} <-> ${t.other} (Kopplungsgrad ${fmt.pct(t.degree)}, ${t.shared} gemeinsame Commits)`,
    },
    knowledge: {
      task: () =>
        `Die folgenden Dateien wurden fast ausschließlich von einer Person geändert (Truck-Factor ${D.meta.truck_factor}). ` +
        'Verringere das Wissensrisiko, ohne Verhalten zu ändern: Halte Absicht, Randfälle und Zusammenspiel in Docstrings oder einer kurzen Modul-README fest, ' +
        'kommentiere nicht offensichtliche Stellen und ergänze Tests, die das erwartete Verhalten dokumentieren.',
      keep: () => true,
      ref: (t) => `${t.file} (${fmt.pct(t.share)} der Commits von einer Person, ${t.commits} Commits, ${t.nloc} NLOC)`,
    },
  };

  /** Fundstellen einer Note, die in einen Arbeitsauftrag gehören (bereits nach Wichtigkeit sortiert). */
  RR.promptRefs = (g) => {
    const spec = SPECS[g.key];
    return spec && g.grade ? (g.top || []).filter(spec.keep) : [];
  };

  RR.agentPrompt = (g, n) => {
    const spec = SPECS[g.key];
    const refs = RR.promptRefs(g).slice(0, n);
    const m = D.meta;
    const where = m.head ? `Commit ${m.head.slice(0, 10)}` : 'dem analysierten Arbeitsstand';
    return [
      spec.task(),
      `Arbeite die Fundstellen der Reihe nach ab, halte jede Änderung klein und lass danach die bestehenden Tests laufen.`,
      `Ausgangslage: repo-radar bewertet „${g.label}“ mit ${g.grade} (${g.value}).`,
      '',
      `Fundstellen, wichtigste zuerst (Pfade relativ zur Repository-Wurzel, Zeilen laut ${where}):`,
      ...refs.map((t, i) => `${i + 1}. ${spec.ref(t)}`),
    ].join('\n');
  };

  // ---------- Dialog ----------
  const dlg = document.getElementById('prompt-dialog');
  const countEl = dlg.querySelector('#prompt-count');
  const textEl = dlg.querySelector('#prompt-text');
  const copyBtn = dlg.querySelector('#prompt-copy');
  const status = dlg.querySelector('#prompt-status');
  let current = null;

  const defaultCount = () => Math.max(1, +RR.prefs.promptRefs || 3);
  function update() {
    const total = RR.promptRefs(current).length;
    const n = Math.min(total, Math.max(1, Math.round(+countEl.value) || 1));
    textEl.value = RR.agentPrompt(current, n);
    status.textContent = '';
  }

  RR.openPrompt = (g) => {
    current = g;
    const total = RR.promptRefs(g).length;
    dlg.querySelector('#prompt-title').textContent = `KI-Prompt: ${g.label}`;
    countEl.max = total;
    countEl.value = Math.min(total, defaultCount());
    dlg.querySelector('#prompt-total').textContent = `von ${total}`;
    update();
    dlg.showModal();
    textEl.scrollTop = 0;
  };

  countEl.addEventListener('input', () => {
    update();
    const v = Math.round(+countEl.value);
    if (v >= 1) {
      RR.prefs.promptRefs = v;
      RR.savePrefs();
    }
  });
  copyBtn.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(textEl.value);
    } catch (_) {
      textEl.select();
      document.execCommand('copy'); // Fallback, falls die Clipboard-API nicht erlaubt ist
    }
    status.textContent = 'Kopiert';
  });
  dlg.querySelector('#prompt-close').addEventListener('click', () => dlg.close());
  dlg.addEventListener('click', (ev) => ev.target === dlg && dlg.close()); // Klick auf den Hintergrund

  RR.promptButton = (g) =>
    RR.promptRefs(g).length
      ? `<button type="button" class="btn" data-prompt="${esc(g.key)}" title="Arbeitsauftrag mit den wichtigsten Fundstellen für einen KI-Agenten">KI-Prompt</button>`
      : '';
})();
