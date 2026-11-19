/* Dateitabelle: alle Metriken, sortier- und filterbar, CSV-Export */
(function () {
  'use strict';
  const { data: D, fmt, esc } = RR;

  const COLUMNS = [
    { key: 'path', label: 'Datei', cls: 'path', fmt: (f) => RR.fileLink(f.path) + (f.test ? ' <span class="badge">Test</span>' : '') + (f.barrel ? ' <span class="badge">Barrel</span>' : '') },
    { key: 'lang', label: 'Sprache' },
    { key: 'nloc', label: 'NLOC', num: true, fmt: (f) => fmt.int(f.nloc) },
    { key: 'fn', label: 'Fkt.', num: true, title: 'Anzahl Funktionen' },
    { key: 'ccn_max', label: 'CCN max', num: true, title: 'höchste zyklomatische Komplexität einer Funktion' },
    { key: 'ccn_sum', label: 'CCN Σ', num: true, title: 'Summe der Komplexität aller Funktionen' },
    { key: 'ca', label: 'Fan-in', num: true, title: 'Ca: Anzahl Dateien, die diese Datei importieren', fmt: (f) => fmt.int(f.ca) },
    { key: 'ce', label: 'Fan-out', num: true, title: 'Ce: Anzahl importierter Repo-Dateien', fmt: (f) => fmt.int(f.ce) },
    { key: 'instability', label: 'I', num: true, title: 'Instabilität Ce/(Ca+Ce): 0 = stabil, 1 = instabil', fmt: (f) => fmt.dec2(f.instability) },
    { key: 'impact', label: 'Reichweite', num: true, title: 'Dateien, die transitiv von dieser Datei abhängen', fmt: (f) => fmt.int(f.impact) },
    { key: 'commits', label: 'Commits', num: true, title: 'Commits im Analysefenster' },
    { key: 'churn', label: 'Churn', num: true, title: 'hinzugefügte + gelöschte Zeilen im Fenster', fmt: (f) => fmt.int(f.churn) },
    { key: 'fixes', label: 'Fixes', num: true, title: 'Fix-Commits im Fenster' },
    { key: 'author_count', label: 'Autoren', num: true },
    { key: 'main_share', label: 'Hauptautor', num: true, title: 'Commit-Anteil des Hauptautors (gesamte Historie)', fmt: (f) => (f.main_share == null ? '–' : fmt.pct(f.main_share)) },
    { key: 'age_days', label: 'Alter', num: true, title: 'Zeit seit letzter Änderung', fmt: (f) => fmt.days(f.age_days) },
    { key: 'hotspot', label: 'Hotspot', num: true, fmt: (f) => fmt.dec2(f.hotspot) },
    { key: 'lcom_max', label: 'LCOM4', num: true, title: 'höchstes LCOM4 einer Klasse in der Datei', fmt: (f) => fmt.int(f.lcom_max) },
    { key: 'dup_pct', label: 'Dup.', num: true, title: 'Anteil duplizierter Zeilen', fmt: (f) => fmt.pctRaw(f.dup_pct) },
    { key: 'cycle', label: 'Zyklus', num: true, fmt: (f) => (f.cycle == null ? '' : `<span class="badge crit">#${f.cycle + 1}</span>`) },
  ];

  function toCsv(rows) {
    const keys = COLUMNS.map((c) => c.key);
    const q = (v) => (v == null ? '' : /[",;\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v));
    return [keys.join(';'), ...rows.map((r) => keys.map((k) => q(r[k])).join(';'))].join('\n');
  }

  RR.register('files', 'Dateien', (root, params) => {
    const q = params.q || '';
    const lang = params.lang || '';
    const project = params.project || '';
    const onlyCycles = params.cycles === '1';
    let matcher = (s) => s.toLowerCase().includes(q.toLowerCase());
    let reErr = false;
    if (q.startsWith('/') && q.length > 2 && q.endsWith('/')) {
      try {
        const re = new RegExp(q.slice(1, -1), 'i');
        matcher = (s) => re.test(s);
      } catch (_) { reErr = true; }
    }
    const rows = D.files.filter((f) => RR.visible(f) && (!q || matcher(f.path)) && (!lang || f.lang === lang) &&
      (!project || f.project === project) && (!onlyCycles || f.cycle != null));
    const langs = Object.keys(D.meta.languages).sort();
    const projects = D.meta.projects;

    root.innerHTML = `
      <div class="toolbar">
        <input type="search" id="f-q" placeholder="Pfad filtern (oder /regex/)…" value="${esc(q)}">
        <label>Sprache <select id="f-lang"><option value="">alle</option>${langs.map((l) => `<option ${l === lang ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select></label>
        ${projects.length > 1 ? `<label>Projekt <select id="f-project"><option value="">alle</option>${projects.map((p) => `<option ${p === project ? 'selected' : ''}>${esc(p)}</option>`).join('')}</select></label>` : ''}
        <label><input type="checkbox" id="f-tests" ${RR.prefs.showTests ? 'checked' : ''}> Testdateien</label>
        <label><input type="checkbox" id="f-cycles" ${onlyCycles ? 'checked' : ''}> nur in Zyklen</label>
        <button class="btn" id="f-csv" type="button">CSV exportieren</button>
        <span class="muted small">${fmt.int(rows.length)} Dateien${reErr ? ' · ungültige Regex' : ''}</span>
      </div>
      <div class="card" id="f-table" style="padding:0 0 8px"></div>`;
    const qIn = root.querySelector('#f-q');
    let t;
    qIn.addEventListener('input', () => { clearTimeout(t); t = setTimeout(() => RR.setParams({ q: qIn.value || null }), 300); });
    root.querySelector('#f-lang').addEventListener('change', (e) => RR.setParams({ lang: e.target.value || null }));
    const pSel = root.querySelector('#f-project');
    if (pSel) pSel.addEventListener('change', (e) => RR.setParams({ project: e.target.value || null }));
    root.querySelector('#f-tests').addEventListener('change', (e) => { RR.prefs.showTests = e.target.checked; RR.savePrefs(); RR.rerender(); });
    root.querySelector('#f-cycles').addEventListener('change', (e) => RR.setParams({ cycles: e.target.checked ? '1' : null }));
    const table = RR.table(COLUMNS, rows, { sortKey: params.sort || 'hotspot', pageSize: 100 });
    root.querySelector('#f-table').appendChild(table);
    root.querySelector('#f-csv').addEventListener('click', () => {
      const blob = new Blob(['﻿' + toCsv(table.sorted())], { type: 'text/csv;charset=utf-8' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `${D.meta.name.replace(/[^\w.-]+/g, '_')}-dateien.csv`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    });
    if (q) {
      qIn.focus();
      qIn.setSelectionRange(q.length, q.length);
    }
  });
})();
