/* Hotspot-Karte: Treemap über die Verzeichnisstruktur, Fläche und Farbe wählbar, Zoom per Klick */
(function () {
  'use strict';
  const { data: D, fmt, esc } = RR;

  const SIZE = {
    nloc: { label: 'NLOC', v: (f) => f.nloc },
    ccn_sum: { label: 'CCN-Summe', v: (f) => f.ccn_sum },
    churn: { label: 'Churn (Zeilen)', v: (f) => f.churn },
  };
  const COLOR = {
    hotspot: { label: 'Hotspot-Score', v: (f) => f.hotspot, domain: () => [0, 1], fmt: fmt.dec2 },
    ccn_max: { label: 'max. CCN', v: (f) => f.ccn_max, log: true, fmt: fmt.int },
    commits: { label: 'Commits (Fenster)', v: (f) => f.commits, log: true, fmt: fmt.int },
    churn: { label: 'Churn (Fenster)', v: (f) => f.churn, log: true, fmt: fmt.int },
    impact: { label: 'Änderungsreichweite', v: (f) => f.impact, log: true, fmt: fmt.int },
    age_days: { label: 'Tage seit letzter Änderung', v: (f) => f.age_days, fmt: fmt.days },
    fixes: { label: 'Fix-Commits', v: (f) => f.fixes, log: true, fmt: fmt.int },
    lcom_max: { label: 'max. LCOM4', v: (f) => f.lcom_max, fmt: fmt.int },
    dup_pct: { label: 'Duplikation %', v: (f) => f.dup_pct, domain: () => [0, 50], fmt: fmt.pctRaw },
    main_author: { label: 'Hauptautor', categorical: true },
    cycle: { label: 'In Zyklus', flag: true },
  };

  function buildTree(files, base) {
    const root = { name: base || D.meta.name, path: base, kids: new Map() };
    for (const f of files) {
      const rel = base ? f.path.slice(base.length + 1) : f.path;
      const parts = rel.split('/');
      let node = root;
      for (let i = 0; i < parts.length - 1; i++) {
        if (!node.kids.has(parts[i])) {
          node.kids.set(parts[i], { name: parts[i], path: (node.path ? node.path + '/' : '') + parts[i], kids: new Map() });
        }
        node = node.kids.get(parts[i]);
      }
      node.kids.set(f.name, { name: f.name, file: f });
    }
    function finish(n, isRoot) {
      if (n.file) return n;
      let kids = [...n.kids.values()].map((k) => finish(k, false));
      // Ketten aus Ein-Kind-Verzeichnissen zusammenziehen (a/b/c)
      while (!isRoot && kids.length === 1 && !kids[0].file) {
        n = { name: n.name + '/' + kids[0].name, path: kids[0].path, children: kids[0].children };
        kids = n.children;
      }
      return { name: n.name, path: n.path, children: kids };
    }
    return finish(root, true);
  }

  RR.register('hotspots', 'Hotspot-Karte', (root, params) => {
    const sizeKey = SIZE[params.size] ? params.size : 'nloc';
    const colorKey = COLOR[params.color] ? params.color : 'hotspot';
    const base = params.dir || '';
    const files = D.files.filter((f) => RR.visible(f) && (!base || f.path.startsWith(base + '/')));
    const color = COLOR[colorKey];

    const crumbs = [['', D.meta.name]];
    if (base) base.split('/').forEach((p, i, arr) => crumbs.push([arr.slice(0, i + 1).join('/'), p]));

    root.innerHTML = `
      <div class="toolbar">
        <label>Fläche <select id="tm-size">${Object.entries(SIZE).map(([k, s]) => `<option value="${k}" ${k === sizeKey ? 'selected' : ''}>${s.label}</option>`).join('')}</select></label>
        <label>Farbe <select id="tm-color">${Object.entries(COLOR).map(([k, s]) => `<option value="${k}" ${k === colorKey ? 'selected' : ''}>${s.label}</option>`).join('')}</select></label>
        <label><input type="checkbox" id="tm-tests" ${RR.prefs.showTests ? 'checked' : ''}> Testdateien</label>
      </div>
      <div class="crumbs">${crumbs.map(([p, n], i) => (i === crumbs.length - 1 ? `<strong class="mono">${esc(n)}</strong>` : `<a href="#" data-dir="${esc(p)}">${esc(n)}</a><span class="sep">/</span>`)).join('')}</div>
      <div class="split">
        <div class="card" style="padding:8px"><div class="treemap-wrap" id="tm"></div><div class="legend" id="tm-legend"></div></div>
        <div class="card"><h3>Top-Dateien nach ${esc(color.label)}</h3><div id="tm-top"></div></div>
      </div>`;

    root.querySelector('#tm-size').addEventListener('change', (e) => RR.setParams({ size: e.target.value }));
    root.querySelector('#tm-color').addEventListener('change', (e) => RR.setParams({ color: e.target.value }));
    root.querySelector('#tm-tests').addEventListener('change', (e) => {
      RR.prefs.showTests = e.target.checked;
      RR.savePrefs();
      RR.rerender();
    });
    root.querySelectorAll('[data-dir]').forEach((a) => a.addEventListener('click', (e) => {
      e.preventDefault();
      RR.setParams({ dir: a.dataset.dir || null }, false);
    }));

    if (!files.length) {
      root.querySelector('#tm').innerHTML = '<div class="empty">Keine Dateien in dieser Auswahl</div>';
      return;
    }

    // Farbskala
    let colorOf;
    const legend = root.querySelector('#tm-legend');
    if (color.categorical) {
      const counts = d3.rollups(files.filter((f) => f.main_author), (v) => v.length, (f) => f.main_author).sort((a, b) => b[1] - a[1]);
      const cat = RR.categorical(counts.map((c) => c[0]));
      colorOf = (f) => (f.main_author ? cat(f.main_author) : RR.css('--null'));
      legend.innerHTML = cat.entries().map(([k, c]) => `<span><span class="sw" style="background:${c}"></span>${esc(k)}</span>`).join('') +
        (cat.hasOther ? `<span><span class="sw" style="background:${RR.css('--other')}"></span>Andere</span>` : '');
    } else if (color.flag) {
      colorOf = (f) => (f.cycle != null ? RR.css('--critical') : RR.css('--null'));
      legend.innerHTML = `<span><span class="sw" style="background:var(--critical)"></span>Teil eines Import-Zyklus</span><span><span class="sw" style="background:var(--null)"></span>kein Zyklus / nicht analysiert</span>`;
    } else {
      const vals = files.map(color.v).filter((v) => v != null);
      const domain = color.domain ? color.domain() : [d3.min(vals) ?? 0, Math.max(1, d3.max(vals) ?? 1)];
      const seq = RR.seqScale(domain, color.log);
      colorOf = (f) => seq(color.v(f));
      legend.innerHTML = `<span>${esc(color.label)}: ${color.fmt(domain[0])}<span class="ramp" style="background:${seq.gradient()}"></span>${color.fmt(domain[1])}${color.log ? ' (log)' : ''}</span><span><span class="sw" style="background:var(--null)"></span>kein Wert</span>`;
    }

    // Layout
    const wrap = root.querySelector('#tm');
    const w = wrap.clientWidth;
    const h = wrap.clientHeight;
    const hier = d3.hierarchy(buildTree(files, base), (d) => d.children)
      .sum((d) => (d.file ? Math.max(1, SIZE[sizeKey].v(d.file)) : 0))
      .sort((a, b) => b.value - a.value);
    // paddingOuter setzt auch paddingTop, deshalb zuerst aufrufen
    d3.treemap().size([w, h]).tile(d3.treemapSquarify.ratio(1.2))
      .paddingOuter((d) => (d.depth === 0 ? 0 : 2))
      .paddingTop((d) => (d.depth > 0 && d.depth <= 3 ? 17 : d.depth === 0 ? 0 : 2))
      .paddingInner(1).round(true)(hier);

    const svg = d3.select(wrap).append('svg').attr('viewBox', `0 0 ${w} ${h}`).attr('role', 'img')
      .attr('aria-label', `Treemap: Fläche ${SIZE[sizeKey].label}, Farbe ${color.label}`);
    const dirs = hier.descendants().filter((d) => d.children && d.depth > 0);
    const dirG = svg.append('g').selectAll('g').data(dirs).join('g');
    dirG.append('rect').attr('x', (d) => d.x0).attr('y', (d) => d.y0).attr('width', (d) => d.x1 - d.x0).attr('height', (d) => d.y1 - d.y0)
      .attr('fill', 'var(--surface-2)').attr('stroke', 'var(--border)').attr('rx', 3)
      .style('cursor', 'zoom-in')
      .on('click', (ev, d) => RR.setParams({ dir: d.data.path }, false))
      .on('mousemove', (ev, d) => RR.tip.show(RR.tipTable(esc(d.data.path) + '/', [
        ['Dateien', fmt.int(d.leaves().length)],
        [SIZE[sizeKey].label, fmt.int(d.value)],
        ['Klick', 'hineinzoomen'],
      ]), ev))
      .on('mouseleave', RR.tip.hide);
    dirG.filter((d) => d.depth <= 3 && d.x1 - d.x0 > 36)
      .append('text').attr('class', 'tm-dir-label').attr('x', (d) => d.x0 + 5).attr('y', (d) => d.y0 + 12)
      .text((d) => d.data.name)
      .each(function (d) {
        const max = d.x1 - d.x0 - 10;
        let t = d.data.name;
        while (this.getComputedTextLength() > max && t.length > 2) {
          t = t.slice(0, -2);
          this.textContent = t + '…';
        }
      });

    const leaves = hier.leaves();
    const leafG = svg.append('g').selectAll('g').data(leaves).join('g').style('cursor', 'pointer');
    leafG.append('rect').attr('x', (d) => d.x0).attr('y', (d) => d.y0)
      .attr('width', (d) => Math.max(0, d.x1 - d.x0)).attr('height', (d) => Math.max(0, d.y1 - d.y0))
      .attr('rx', 2).attr('fill', (d) => colorOf(d.data.file))
      .on('click', (ev, d) => RR.openFile(d.data.file.path))
      .on('mousemove', (ev, d) => {
        const f = d.data.file;
        const extra = color.categorical || color.flag ? '' : `<div class="small secondary" style="margin-top:4px">${esc(color.label)}: <strong>${color.fmt(color.v(f))}</strong></div>`;
        RR.tip.show(RR.fileTip(f) + extra, ev);
      })
      .on('mouseleave', RR.tip.hide);
    leafG.filter((d) => d.x1 - d.x0 > 46 && d.y1 - d.y0 > 15)
      .append('text').attr('class', 'tm-file-label').attr('x', (d) => d.x0 + 4).attr('y', (d) => d.y0 + 12)
      .attr('fill', (d) => (d3.lab(colorOf(d.data.file)).l > 58 ? '#0b0b0b' : '#ffffff'))
      .text((d) => d.data.name)
      .each(function (d) {
        const max = d.x1 - d.x0 - 8;
        let t = d.data.name;
        while (this.getComputedTextLength() > max && t.length > 2) {
          t = t.slice(0, -2);
          this.textContent = t + '…';
        }
      });

    // Top-Liste rechts
    const topRows = color.categorical
      ? d3.rollups(files.filter((f) => f.main_author), (v) => ({ n: v.length, nloc: d3.sum(v, (f) => f.nloc) }), (f) => f.main_author)
          .sort((a, b) => b[1].nloc - a[1].nloc).slice(0, 15)
          .map(([a, v]) => `<li><span>${esc(a)}</span><span class="nowrap">${fmt.int(v.n)} Dateien · ${fmt.int(v.nloc)} NLOC</span></li>`)
      : files.filter((f) => (color.flag ? f.cycle != null : color.v(f) != null))
          .sort((a, b) => (color.flag ? b.nloc - a.nloc : color.v(b) - color.v(a))).slice(0, 15)
          .map((f) => `<li><span class="path">${RR.fileLink(f.path)}</span><span class="nowrap">${color.flag ? '#' + (f.cycle + 1) : color.fmt(color.v(f))}</span></li>`);
    root.querySelector('#tm-top').innerHTML = topRows.length ? `<ul class="list">${topRows.join('')}</ul>` : '<div class="empty">–</div>';
  });
})();
