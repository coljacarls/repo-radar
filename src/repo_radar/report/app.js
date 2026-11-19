/* repo-radar Report – Kern: Daten, Router, Hilfsfunktionen. Views registrieren sich über RR.register(). */
(function () {
  'use strict';
  const RR = (window.RR = {});
  const D = (RR.data = JSON.parse(document.getElementById('rr-data').textContent));

  // ---------- abgeleitete Strukturen ----------
  D.files.forEach((f, i) => {
    f.i = i;
    f.name = f.path.split('/').pop();
    f.dir = f.path.includes('/') ? f.path.slice(0, f.path.lastIndexOf('/')) : '';
    f.churn = f.added + f.deleted;
  });
  RR.byPath = new Map(D.files.map((f) => [f.path, f]));
  RR.out = D.files.map(() => []);
  RR.in = D.files.map(() => []);
  for (const [a, b, weak] of D.edges) {
    RR.out[a].push([b, weak]);
    RR.in[b].push([a, weak]);
  }
  RR.couplingOf = D.files.map(() => []);
  for (const c of D.coupling) {
    RR.couplingOf[c.a].push({ other: c.b, ...c });
    RR.couplingOf[c.b].push({ other: c.a, ...c });
  }
  RR.clonesOf = D.files.map(() => []);
  for (const c of D.clones) {
    RR.clonesOf[c.a].push({ other: c.b, start: c.a_start, end: c.a_end, oStart: c.b_start, oEnd: c.b_end, lines: c.lines });
    if (c.a !== c.b) RR.clonesOf[c.b].push({ other: c.a, start: c.b_start, end: c.b_end, oStart: c.a_start, oEnd: c.a_end, lines: c.lines });
  }
  RR.cycleOfFile = new Map();
  D.cycles.forEach((c, i) => c.forEach((fi) => RR.cycleOfFile.set(fi, i)));

  // ---------- Formatierung ----------
  const nf = new Intl.NumberFormat('de-DE');
  const nf1 = new Intl.NumberFormat('de-DE', { maximumFractionDigits: 1 });
  const nf2 = new Intl.NumberFormat('de-DE', { maximumFractionDigits: 2 });
  RR.fmt = {
    int: (v) => (v == null ? '–' : nf.format(v)),
    dec: (v) => (v == null ? '–' : nf1.format(v)),
    dec2: (v) => (v == null ? '–' : nf2.format(v)),
    pct: (v) => (v == null ? '–' : nf1.format(v * 100) + ' %'),
    pctRaw: (v) => (v == null ? '–' : nf1.format(v) + ' %'),
    date: (ts) => (ts ? new Date(ts * 1000).toLocaleDateString('de-DE', { year: 'numeric', month: 'short', day: 'numeric' }) : '–'),
    days: (d) => (d == null ? '–' : d < 60 ? `${d} T` : d < 730 ? `${Math.round(d / 30.4)} Mon.` : `${nf1.format(d / 365.25)} J.`),
  };
  RR.esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  RR.pathHtml = (p) => {
    const i = p.lastIndexOf('/');
    return i < 0 ? RR.esc(p) : `<span class="path-dir">${RR.esc(p.slice(0, i + 1))}</span>${RR.esc(p.slice(i + 1))}`;
  };
  RR.fileLink = (path, label) => `<a href="#" data-file="${RR.esc(path)}">${label ?? RR.pathHtml(path)}</a>`;

  // ---------- Farben (aus CSS-Tokens, damit Hell/Dunkel stimmt) ----------
  RR.css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  RR.series = () => [1, 2, 3, 4, 5, 6, 7, 8].map((i) => RR.css(`--series-${i}`));
  RR.seqScale = (domain, log = false) => {
    const lo = RR.css('--seq-0');
    const hi = RR.css('--seq-1');
    const s = (log ? d3.scaleSymlog() : d3.scaleLinear()).domain(domain).range([0, 1]).clamp(true);
    const interp = d3.interpolateLab(lo, hi);
    const f = (v) => (v == null ? RR.css('--null') : interp(s(v)));
    f.gradient = () => `linear-gradient(90deg, ${d3.range(0, 1.01, 0.1).map((t) => interp(t)).join(',')})`;
    return f;
  };
  /** Kategorien in fester Reihenfolge; ab dem 9. Wert „Andere“ (grau). */
  RR.categorical = (keysByWeight) => {
    const pal = RR.series();
    const map = new Map(keysByWeight.slice(0, 8).map((k, i) => [k, pal[i]]));
    const other = RR.css('--other');
    const f = (k) => map.get(k) ?? other;
    f.entries = () => [...map.entries()];
    f.hasOther = keysByWeight.length > 8;
    return f;
  };

  // ---------- Filter: Testdateien ----------
  RR.prefs = { showTests: false };
  try {
    Object.assign(RR.prefs, JSON.parse(localStorage.getItem('rr-prefs') || '{}'));
  } catch (_) { /* kein Storage verfügbar */ }
  RR.savePrefs = () => {
    try { localStorage.setItem('rr-prefs', JSON.stringify(RR.prefs)); } catch (_) { /* egal */ }
  };
  RR.visible = (f) => RR.prefs.showTests || !f.test;

  // ---------- Tooltip ----------
  const tip = document.getElementById('tooltip');
  RR.tip = {
    show(html, ev) {
      tip.innerHTML = html;
      tip.hidden = false;
      RR.tip.move(ev);
    },
    move(ev) {
      if (tip.hidden || !ev) return;
      const pad = 14;
      const r = tip.getBoundingClientRect();
      let x = ev.clientX + pad;
      let y = ev.clientY + pad;
      if (x + r.width > window.innerWidth - 8) x = ev.clientX - r.width - pad;
      if (y + r.height > window.innerHeight - 8) y = ev.clientY - r.height - pad;
      tip.style.left = Math.max(8, x) + 'px';
      tip.style.top = Math.max(8, y) + 'px';
    },
    hide() { tip.hidden = true; },
  };
  RR.tipTable = (title, rows) =>
    `<div class="t-title">${title}</div><table>${rows
      .filter((r) => r)
      .map(([k, v]) => `<tr><td class="secondary">${k}</td><td>${v}</td></tr>`)
      .join('')}</table>`;
  RR.fileTip = (f) =>
    RR.tipTable(RR.esc(f.path), [
      ['NLOC', RR.fmt.int(f.nloc)],
      ['CCN max / Σ', `${f.ccn_max} / ${f.ccn_sum}`],
      ['Commits (Fenster)', RR.fmt.int(f.commits)],
      ['Hotspot', RR.fmt.dec2(f.hotspot)],
      f.ca != null && ['Fan-in / Fan-out', `${f.ca} / ${f.ce}`],
      f.impact != null && ['Änderungsreichweite', `${f.impact} Dateien`],
      f.main_author && ['Hauptautor', `${RR.esc(f.main_author)} (${RR.fmt.pct(f.main_share)})`],
      f.cycle != null && ['Zyklus', `#${f.cycle + 1}`],
    ]);

  // ---------- Sortierbare Tabelle ----------
  /**
   * columns: [{key, label, num, fmt(row), value(row), title, cls}]
   * opts: {pageSize, sortKey, sortDir, onRow}
   */
  RR.table = (columns, rows, opts = {}) => {
    const el = document.createElement('div');
    let sortKey = opts.sortKey ?? null;
    let sortDir = opts.sortDir ?? -1;
    let limit = opts.pageSize ?? 100;
    const val = (c, r) => (c.value ? c.value(r) : r[c.key]);
    function draw() {
      let data = rows.slice();
      const col = columns.find((c) => c.key === sortKey);
      if (col) {
        data.sort((a, b) => {
          const x = val(col, a);
          const y = val(col, b);
          if (x == null && y == null) return 0;
          if (x == null) return 1;
          if (y == null) return -1;
          return (x < y ? -1 : x > y ? 1 : 0) * sortDir;
        });
      }
      const shown = data.slice(0, limit);
      el.innerHTML = `<div class="table-wrap"><table class="data"><thead><tr>${columns
        .map(
          (c) =>
            `<th class="sortable ${c.num ? 'num' : ''}" data-k="${c.key}" title="${RR.esc(c.title || '')}">${c.label}${
              c.key === sortKey ? `<span class="arrow"> ${sortDir < 0 ? '↓' : '↑'}</span>` : ''
            }</th>`,
        )
        .join('')}</tr></thead><tbody>${shown
        .map(
          (r) =>
            `<tr>${columns
              .map((c) => `<td class="${c.num ? 'num' : ''} ${c.cls || ''}">${c.fmt ? c.fmt(r) : RR.esc(val(c, r) ?? '–')}</td>`)
              .join('')}</tr>`,
        )
        .join('')}</tbody></table></div>${
        data.length > shown.length
          ? `<div class="more"><button class="btn" data-more>Weitere ${Math.min(opts.pageSize ?? 100, data.length - shown.length)} anzeigen</button><span class="muted small">${shown.length} von ${data.length}</span></div>`
          : data.length === 0
            ? '<div class="empty">Keine Einträge</div>'
            : ''
      }`;
      el.querySelectorAll('th.sortable').forEach((th) =>
        th.addEventListener('click', () => {
          const k = th.dataset.k;
          if (k === sortKey) sortDir = -sortDir;
          else {
            sortKey = k;
            sortDir = columns.find((c) => c.key === k).num ? -1 : 1;
          }
          draw();
        }),
      );
      const more = el.querySelector('[data-more]');
      if (more) more.addEventListener('click', () => { limit += opts.pageSize ?? 100; draw(); });
    }
    draw();
    el.sorted = () => {
      const col = columns.find((c) => c.key === sortKey);
      return col ? rows.slice().sort((a, b) => ((val(col, a) ?? -Infinity) < (val(col, b) ?? -Infinity) ? -1 : 1) * sortDir) : rows;
    };
    return el;
  };

  // ---------- Mini-Balken für Zeitverlauf ----------
  RR.monthRange = (fromTs, toTs) => {
    const out = [];
    const d = new Date(fromTs * 1000);
    d.setUTCDate(1);
    const end = new Date(toTs * 1000);
    while (d <= end && out.length < 240) {
      out.push(`${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`);
      d.setUTCMonth(d.getUTCMonth() + 1);
    }
    return out;
  };
  RR.sparkBars = (counts, months, w = 520, h = 56) => {
    const max = Math.max(1, ...months.map((m) => counts[m] || 0));
    const bw = w / months.length;
    const bars = months
      .map((m, i) => {
        const v = counts[m] || 0;
        const bh = v ? Math.max(2, (v / max) * (h - 14)) : 0;
        return `<rect x="${i * bw + 1}" y="${h - 12 - bh}" width="${Math.max(1, bw - 2)}" height="${bh}" rx="2" fill="var(--series-1)"><title>${m}: ${v} Commits</title></rect>`;
      })
      .join('');
    const first = months[0] || '';
    const last = months[months.length - 1] || '';
    return `<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" preserveAspectRatio="none" role="img" aria-label="Commits je Monat">
      <line x1="0" x2="${w}" y1="${h - 12}" y2="${h - 12}" stroke="var(--grid)"/>${bars}
      <text x="0" y="${h - 1}" font-size="10" fill="var(--text-muted)">${first}</text>
      <text x="${w}" y="${h - 1}" font-size="10" fill="var(--text-muted)" text-anchor="end">${last}</text></svg>`;
  };

  // ---------- Graph-Helfer ----------
  /** Tarjan: stark zusammenhängende Komponenten. adj: Map<key, Set<key>> */
  RR.scc = (nodes, adj) => {
    let index = 0;
    const idx = new Map();
    const low = new Map();
    const onStack = new Set();
    const stack = [];
    const comps = [];
    function strong(v) {
      idx.set(v, index);
      low.set(v, index++);
      stack.push(v);
      onStack.add(v);
      for (const w of adj.get(v) || []) {
        if (!idx.has(w)) {
          strong(w);
          low.set(v, Math.min(low.get(v), low.get(w)));
        } else if (onStack.has(w)) low.set(v, Math.min(low.get(v), idx.get(w)));
      }
      if (low.get(v) === idx.get(v)) {
        const comp = [];
        let w;
        do {
          w = stack.pop();
          onStack.delete(w);
          comp.push(w);
        } while (w !== v);
        comps.push(comp);
      }
    }
    for (const v of nodes) if (!idx.has(v)) strong(v);
    return comps; // in umgekehrter topologischer Reihenfolge (Senken zuerst)
  };

  // ---------- Router ----------
  RR.views = [];
  RR.register = (id, title, render) => RR.views.push({ id, title, render });

  RR.parseHash = () => {
    const h = location.hash.replace(/^#\/?/, '');
    const [view, query] = h.split('?');
    const params = Object.fromEntries(new URLSearchParams(query || ''));
    return { view: view || 'overview', params };
  };
  RR.hrefFor = (view, params = {}) => {
    const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v != null && v !== ''));
    const s = q.toString();
    return `#${view}${s ? '?' + s : ''}`;
  };
  RR.go = (view, params = {}, replace = false) => {
    const href = RR.hrefFor(view, params);
    if (replace) history.replaceState(null, '', href);
    else history.pushState(null, '', href);
    route();
  };
  /** Parameter der aktuellen View ändern (Datei-Schublade bleibt erhalten). */
  RR.setParams = (patch, replace = true) => {
    const { view, params } = RR.parseHash();
    RR.go(view, { ...params, ...patch }, replace);
  };
  RR.openFile = (path) => RR.setParams({ file: path }, false);

  let lastKey = null;
  const main = document.getElementById('view');
  function route(force = false) {
    const { view, params } = RR.parseHash();
    const v = RR.views.find((x) => x.id === view) || RR.views[0];
    const { file, ...viewParams } = params;
    const key = v.id + '|' + JSON.stringify(viewParams);
    document.querySelectorAll('#tabs a').forEach((a) => a.setAttribute('aria-current', a.dataset.view === v.id ? 'page' : 'false'));
    if (force || key !== lastKey) {
      lastKey = key;
      RR.tip.hide();
      main.innerHTML = '';
      v.render(main, viewParams);
    }
    RR.renderDrawer(file ? RR.byPath.get(file) : null);
  }
  RR.rerender = () => route(true);

  // ---------- Theme ----------
  const themeBtn = document.getElementById('theme-toggle');
  const themes = ['auto', 'light', 'dark'];
  const themeLabel = { auto: 'Auto', light: 'Hell', dark: 'Dunkel' };
  function applyTheme(t) {
    if (t === 'auto') delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = t;
    themeBtn.textContent = `Theme: ${themeLabel[t]}`;
  }
  let theme = 'auto';
  try { theme = localStorage.getItem('rr-theme') || 'auto'; } catch (_) { /* egal */ }
  applyTheme(theme);
  themeBtn.addEventListener('click', () => {
    theme = themes[(themes.indexOf(theme) + 1) % themes.length];
    try { localStorage.setItem('rr-theme', theme); } catch (_) { /* egal */ }
    applyTheme(theme);
    RR.rerender();
  });
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => theme === 'auto' && RR.rerender());

  // ---------- Start ----------
  RR.start = () => {
    const m = D.meta;
    document.getElementById('repo-name').textContent = m.name;
    const since = m.since ? RR.fmt.date(m.since) : 'Beginn';
    document.getElementById('repo-meta').innerHTML = [
      m.head ? `${RR.esc(m.branch)} @ <code>${RR.esc(m.head.slice(0, 10))}</code>` : `${RR.esc(m.branch)} · noch keine Commits`,
      `analysiert ${RR.esc(new Date(m.analyzed_at).toLocaleString('de-DE'))}`,
      m.head ? `Historie seit ${since} (${RR.esc(m.since_label)})` : '',
      m.untracked ? 'inkl. ungetrackter Dateien' : '',
      m.url ? `<span class="muted">${RR.esc(m.url)}</span>` : '',
    ]
      .filter(Boolean)
      .join(' · ');
    document.getElementById('tabs').innerHTML = RR.views
      .map((v) => `<a href="#${v.id}" data-view="${v.id}">${v.title}</a>`)
      .join('');
    document.addEventListener('click', (ev) => {
      const a = ev.target.closest('[data-file]');
      if (a) {
        ev.preventDefault();
        RR.openFile(a.dataset.file);
        return;
      }
      const g = ev.target.closest('[data-go]');
      if (g) {
        ev.preventDefault();
        RR.go(g.dataset.go, JSON.parse(g.dataset.params || '{}'));
      }
    });
    document.addEventListener('keydown', (ev) => {
      if (ev.key === 'Escape' && RR.parseHash().params.file) RR.setParams({ file: null }, false);
    });
    let resizeTimer;
    window.addEventListener('resize', () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => RR.rerender(), 200);
    });
    window.addEventListener('hashchange', () => route());
    window.addEventListener('popstate', () => route());
    route(true);
  };
})();
