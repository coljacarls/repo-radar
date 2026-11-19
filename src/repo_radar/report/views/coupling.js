/* Change-Kopplung: Netzwerk gemeinsam geänderter Dateien + filterbare Paarliste */
(function () {
  'use strict';
  const { data: D, fmt, esc } = RR;

  RR.register('coupling', 'Change-Kopplung', (root, params) => {
    const cfg = D.meta.config.history;
    const minDeg = params.deg != null ? +params.deg : Math.round(cfg.min_degree * 100);
    const onlyHidden = params.hidden === '1';
    const q = (params.q || '').toLowerCase();
    const pairs = D.coupling.filter((c) => {
      const a = D.files[c.a], b = D.files[c.b];
      if (!RR.visible(a) || !RR.visible(b)) return false;
      if (c.degree * 100 < minDeg) return false;
      if (onlyHidden && c.structural !== false) return false;
      if (q && !a.path.toLowerCase().includes(q) && !b.path.toLowerCase().includes(q)) return false;
      return true;
    });

    root.innerHTML = `
      <p class="small secondary" style="margin-top:0">Dateipaare, die im Analysefenster in mindestens ${cfg.min_shared_commits} Commits gemeinsam geändert wurden.
        Kopplungsgrad = gemeinsame Commits ÷ Ø Commits beider Dateien. <strong>Versteckt</strong> = keine direkte Import-Beziehung: oft ein impliziter Vertrag
        (z. B. Frontend ↔ Backend, Konfiguration ↔ Code) oder kopierte Logik. Commits mit mehr als ${cfg.max_files_per_commit} Dateien zählen nicht.</p>
      <div class="toolbar">
        <label>min. Kopplungsgrad <input type="range" id="cc-deg" min="${Math.round(cfg.min_degree * 100)}" max="100" step="5" value="${minDeg}"> <strong id="cc-deg-v">${minDeg} %</strong></label>
        <label><input type="checkbox" id="cc-hidden" ${onlyHidden ? 'checked' : ''}> nur versteckte</label>
        <label><input type="checkbox" id="cc-tests" ${RR.prefs.showTests ? 'checked' : ''}> Testdateien</label>
        <input type="search" id="cc-q" placeholder="Pfad filtern…" value="${esc(params.q || '')}">
        <span class="muted small">${fmt.int(pairs.length)} Paare</span>
      </div>
      <div class="split">
        <div><div class="graph-wrap" id="cc-graph"></div><div class="legend" id="cc-legend"></div></div>
        <div class="card"><h3>Stärkste Paare</h3><div id="cc-side"></div></div>
      </div>
      <section class="card" style="margin-top:16px"><h2>Alle Paare</h2><div id="cc-table"></div></section>`;

    const deg = root.querySelector('#cc-deg');
    deg.addEventListener('input', () => { root.querySelector('#cc-deg-v').textContent = deg.value + ' %'; });
    deg.addEventListener('change', () => RR.setParams({ deg: deg.value }));
    root.querySelector('#cc-hidden').addEventListener('change', (e) => RR.setParams({ hidden: e.target.checked ? '1' : null }));
    root.querySelector('#cc-tests').addEventListener('change', (e) => { RR.prefs.showTests = e.target.checked; RR.savePrefs(); RR.rerender(); });
    let qt;
    root.querySelector('#cc-q').addEventListener('input', (e) => { clearTimeout(qt); qt = setTimeout(() => RR.setParams({ q: e.target.value || null }), 350); });

    const structLabel = (c) => (c.structural === true ? 'ja' : c.structural === false ? '<span style="color:var(--critical);font-weight:600">nein, versteckt</span>' : '<span class="muted">unbekannt</span>');
    root.querySelector('#cc-side').innerHTML = pairs.length
      ? `<ul class="list">${pairs.slice(0, 12).map((c) => `<li><span class="path">${RR.fileLink(D.files[c.a].path)}<br>↔ ${RR.fileLink(D.files[c.b].path)}<br><span class="small">${structLabel(c)}</span></span><span class="nowrap">${fmt.pct(c.degree)} · ${c.shared}×</span></li>`).join('')}</ul>`
      : '<div class="empty">Keine Paare mit diesen Filtern</div>';

    root.querySelector('#cc-table').appendChild(RR.table([
      { key: 'a', label: 'Datei A', cls: 'path', value: (c) => D.files[c.a].path, fmt: (c) => RR.fileLink(D.files[c.a].path) },
      { key: 'b', label: 'Datei B', cls: 'path', value: (c) => D.files[c.b].path, fmt: (c) => RR.fileLink(D.files[c.b].path) },
      { key: 'shared', label: 'gemeinsam', num: true, title: 'gemeinsame Commits' },
      { key: 'degree', label: 'Grad', num: true, fmt: (c) => fmt.pct(c.degree) },
      { key: 'structural', label: 'Import-Beziehung', value: (c) => (c.structural === false ? 0 : c.structural ? 2 : 1), fmt: structLabel },
    ], pairs, { sortKey: 'degree', pageSize: 50 }));

    // Netzwerk (Top 150 Paare)
    const host = root.querySelector('#cc-graph');
    const shown = pairs.slice(0, 150);
    if (!shown.length) {
      host.innerHTML = '<div class="empty">Keine Paare mit diesen Filtern</div>';
      return;
    }
    const ids = [...new Set(shown.flatMap((c) => [c.a, c.b]))];
    const topDir = (f) => (f.path.includes('/') ? f.path.split('/').slice(0, f.project !== '.' ? f.project.split('/').length : 1).join('/') : '(Wurzel)');
    const dirCounts = d3.rollups(ids, (v) => v.length, (i) => topDir(D.files[i])).sort((a, b) => b[1] - a[1]);
    const cat = RR.categorical(dirCounts.map((d) => d[0]));
    const nodes = ids.map((i) => ({ id: i, f: D.files[i], color: cat(topDir(D.files[i])) }));
    RR.labelTop(nodes, (d) => d.f.commits, 14);
    const crit = RR.css('--critical'), neutral = RR.css('--text-muted'), unknown = RR.css('--other');
    const links = shown.map((c) => ({
      source: c.a, target: c.b, c,
      color: c.structural === false ? crit : c.structural ? neutral : unknown,
      width: 1 + Math.min(5, c.shared / 4),
    }));
    root.querySelector('#cc-legend').innerHTML =
      cat.entries().map(([k, c]) => `<span><span class="sw" style="background:${c}"></span>${esc(k)}</span>`).join('') +
      (cat.hasOther ? `<span><span class="sw" style="background:${RR.css('--other')}"></span>Andere</span>` : '') +
      `<span><span class="line" style="border-color:${crit}"></span>versteckt</span><span><span class="line" style="border-color:${neutral}"></span>mit Import</span><span><span class="line" style="border-color:${unknown}"></span>unbekannt</span><span class="muted">Linienstärke = gemeinsame Commits${pairs.length > 150 ? ' · Top 150 Paare' : ''}</span>`;

    RR.forceGraph(host, nodes, links, {
      label: 'Netzwerk gemeinsam geänderter Dateien',
      distance: 60,
      charge: -140,
      linkStrength: (l) => 0.2 + l.c.degree * 0.6,
      radius: (d) => 4 + Math.sqrt(d.f.commits || 1) * 1.2,
      onClick: (d) => RR.openFile(d.f.path),
      linkTip: (d) => RR.tipTable(`${esc(D.files[d.c.a].name)} ↔ ${esc(D.files[d.c.b].name)}`, [
        ['gemeinsame Commits', d.c.shared], ['Kopplungsgrad', fmt.pct(d.c.degree)], ['Import-Beziehung', structLabel(d.c)]]),
    });
  });
})();
