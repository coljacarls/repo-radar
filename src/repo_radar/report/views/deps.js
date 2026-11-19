/* Abhängigkeiten: Dependency Structure Matrix (DSM) mit Drill-down und Ego-/Zyklus-Graph */
(function () {
  'use strict';
  const { data: D, fmt, esc } = RR;

  // ======================= DSM =======================
  function groupKey(f, level, prefix, depth) {
    if (level === 'project') return f.project;
    const rel = prefix ? f.path.slice(prefix.length + 1) : f.path;
    const parts = rel.split('/');
    return parts.length <= depth ? rel : parts.slice(0, depth).join('/');
  }

  function renderDsm(root, params) {
    const level = params.level === 'project' ? 'project' : 'dir';
    const prefix = level === 'dir' ? params.prefix || '' : '';
    const depth = Math.max(1, Math.min(8, +params.depth || 1));
    const showWeak = params.weak !== '0';
    const files = D.files.filter((f) => f.deps && RR.visible(f) && (!prefix || f.path.startsWith(prefix + '/')));
    const keyOf = new Map(files.map((f) => [f.i, groupKey(f, level, prefix, depth)]));
    const groups = [...new Set(keyOf.values())];
    const isFile = new Set(files.map((f) => groupKey(f, level, prefix, depth)).filter((k) => {
      const f = RR.byPath.get(prefix ? prefix + '/' + k : k);
      return level === 'dir' && f && keyOf.get(f.i) === k;
    }));

    // aggregierte Kanten
    const cells = new Map(); // "a\u0000b" -> [ [fromIdx,toIdx,weak], ... ]
    const adj = new Map(groups.map((g) => [g, new Set()]));
    for (const [a, b, weak] of D.edges) {
      if (!keyOf.has(a) || !keyOf.has(b)) continue;
      if (weak && !showWeak) continue;
      const ga = keyOf.get(a), gb = keyOf.get(b);
      if (ga === gb) continue;
      const k = ga + '\u0000' + gb;
      if (!cells.has(k)) cells.set(k, []);
      cells.get(k).push([a, b, weak]);
      if (!weak) adj.get(ga).add(gb);
    }
    // Ordnung: SCCs, Anbieter (Abhängigkeiten) zuerst → Rückwärtsabhängigkeiten liegen über der Diagonale
    const comps = RR.scc(groups.sort(), adj);
    const order = comps.flatMap((c) => c.sort());
    const compOf = new Map();
    comps.forEach((c, i) => c.forEach((g) => compOf.set(g, c.length > 1 ? i : -1)));
    const pos = new Map(order.map((g, i) => [g, i]));
    const n = order.length;
    const cyclic = comps.filter((c) => c.length > 1);

    const crumbs = [['', D.meta.name]];
    if (prefix) prefix.split('/').forEach((p, i, arr) => crumbs.push([arr.slice(0, i + 1).join('/'), p]));

    root.insertAdjacentHTML('beforeend', `
      <div class="toolbar">
        <label>Ebene <span class="seg" id="dsm-level">
          <button type="button" data-v="dir" aria-pressed="${level === 'dir'}">Verzeichnisse</button>
          <button type="button" data-v="project" aria-pressed="${level === 'project'}">Projekte</button></span></label>
        ${level === 'dir' ? `<label>Tiefe <input type="number" id="dsm-depth" min="1" max="8" value="${depth}" style="width:56px"></label>` : ''}
        <label><input type="checkbox" id="dsm-weak" ${showWeak ? 'checked' : ''}> schwache Kanten (Lazy/Typ)</label>
        <label><input type="checkbox" id="dsm-tests" ${RR.prefs.showTests ? 'checked' : ''}> Testdateien</label>
      </div>
      ${level === 'dir' ? `<div class="crumbs">${crumbs.map(([p, nm], i) => (i === crumbs.length - 1 ? `<strong class="mono">${esc(nm)}</strong>` : `<a href="#" data-prefix="${esc(p)}">${esc(nm)}</a><span class="sep">/</span>`)).join('')}</div>` : ''}
      <p class="small secondary">Zeile <em>nutzt</em> Spalte, Zahl = Anzahl Datei-Imports. Sortiert so, dass genutzte Bausteine oben links stehen: Einträge <strong>über der Diagonale</strong> sind Rückwärtsabhängigkeiten und gehören zu Zyklen (rot umrahmt). Zeilenname anklicken = hineinzoomen, Zelle anklicken = Datei-Imports anzeigen.</p>
      <div class="split">
        <div class="dsm-wrap" id="dsm"></div>
        <div class="card" id="dsm-side"><h3>Auswahl</h3><p class="muted small">Zelle oder Zeile anklicken.</p>
          ${cyclic.length ? `<h3 style="margin-top:12px">Zyklen auf dieser Ebene</h3><ul class="list">${cyclic.map((c) => `<li><span class="mono">${c.map(esc).join(' ↔ ')}</span><span>${c.length}</span></li>`).join('')}</ul>` : '<p class="small secondary">Keine Zyklen auf dieser Ebene.</p>'}
        </div>
      </div>`);

    root.querySelectorAll('#dsm-level button').forEach((b) => b.addEventListener('click', () => RR.setParams({ level: b.dataset.v === 'dir' ? null : b.dataset.v, prefix: null })));
    const depthIn = root.querySelector('#dsm-depth');
    if (depthIn) depthIn.addEventListener('change', (e) => RR.setParams({ depth: e.target.value }));
    root.querySelector('#dsm-weak').addEventListener('change', (e) => RR.setParams({ weak: e.target.checked ? null : '0' }));
    root.querySelector('#dsm-tests').addEventListener('change', (e) => { RR.prefs.showTests = e.target.checked; RR.savePrefs(); RR.rerender(); });
    root.querySelectorAll('[data-prefix]').forEach((a) => a.addEventListener('click', (e) => { e.preventDefault(); RR.setParams({ prefix: a.dataset.prefix || null }, false); }));

    const host = root.querySelector('#dsm');
    if (!n) {
      host.innerHTML = '<div class="empty">Keine Dateien mit Import-Auflösung in dieser Auswahl</div>';
      return;
    }
    if (n > 300) {
      host.innerHTML = `<div class="empty">${n} Gruppen sind zu viele für eine lesbare Matrix. Tiefe verringern oder in ein Verzeichnis hineinzoomen.</div>`;
      return;
    }
    const labelW = Math.min(320, 40 + d3.max(order, (g) => g.length) * 6.6);
    const avail = Math.max(300, host.clientWidth - labelW - 16);
    const cs = Math.max(10, Math.min(30, Math.floor(avail / n)));
    const top = 34;
    const W = labelW + n * cs + 8;
    const H = top + n * cs + 8;
    const maxCount = d3.max([...cells.values()], (v) => v.length) || 1;
    const seq = RR.seqScale([1, maxCount], true);
    const svg = d3.select(host).append('svg').attr('width', W).attr('height', H).attr('role', 'img').attr('aria-label', 'Abhängigkeitsmatrix');

    // Hintergrund-Raster
    const g = svg.append('g').attr('transform', `translate(${labelW},${top})`);
    g.append('rect').attr('width', n * cs).attr('height', n * cs).attr('fill', 'var(--surface-1)').attr('stroke', 'var(--grid)');
    if (cs >= 12) {
      g.append('g').selectAll('line').data(d3.range(1, n)).join('line')
        .attr('x1', 0).attr('x2', n * cs).attr('y1', (i) => i * cs).attr('y2', (i) => i * cs).attr('stroke', 'var(--grid)');
      g.append('g').selectAll('line').data(d3.range(1, n)).join('line')
        .attr('y1', 0).attr('y2', n * cs).attr('x1', (i) => i * cs).attr('x2', (i) => i * cs).attr('stroke', 'var(--grid)');
    }
    g.append('g').selectAll('rect').data(order).join('rect')
      .attr('x', (d, i) => i * cs).attr('y', (d, i) => i * cs).attr('width', cs).attr('height', cs).attr('fill', 'var(--surface-2)');

    const cellData = [...cells.entries()].map(([k, list]) => {
      const [a, b] = k.split('\u0000');
      return { a, b, list, r: pos.get(a), c: pos.get(b), cyc: compOf.get(a) >= 0 && compOf.get(a) === compOf.get(b) };
    });
    const cell = g.append('g').selectAll('g').data(cellData).join('g').attr('transform', (d) => `translate(${d.c * cs},${d.r * cs})`).style('cursor', 'pointer');
    cell.append('rect').attr('x', 1).attr('y', 1).attr('width', cs - 2).attr('height', cs - 2).attr('rx', 2)
      .attr('fill', (d) => (d.cyc ? RR.css('--critical') : seq(d.list.length)));
    if (cs >= 18) {
      cell.append('text').attr('x', cs / 2).attr('y', cs / 2 + 4).attr('text-anchor', 'middle').attr('font-size', cs >= 24 ? 11 : 9.5)
        .style('fill', (d) => (d.cyc || d3.lab(seq(d.list.length)).l < 58 ? '#fff' : '#0b0b0b'))
        .style('pointer-events', 'none')
        .text((d) => (d.list.length > 999 ? '999+' : d.list.length));
    }
    cell.on('mousemove', (ev, d) => RR.tip.show(RR.tipTable(`${esc(d.a)} → ${esc(d.b)}`, [
      ['Datei-Imports', fmt.int(d.list.length)],
      ['davon schwach', fmt.int(d.list.filter((x) => x[2]).length)],
      d.cyc && ['', '<span style="color:var(--critical)">Teil eines Zyklus</span>'],
    ]), ev)).on('mouseleave', RR.tip.hide)
      .on('click', (ev, d) => {
        const side = root.querySelector('#dsm-side');
        side.innerHTML = `<h3><span class="mono">${esc(d.a)}</span> → <span class="mono">${esc(d.b)}</span></h3>
          <p class="small secondary">${d.list.length} Import(e)${d.cyc ? ' · <span style="color:var(--critical)">Teil eines Zyklus</span>' : ''}</p>
          <ul class="list">${d.list.slice(0, 200).map(([a, b, w]) => `<li><span class="path">${RR.fileLink(D.files[a].path)}<br>→ ${RR.fileLink(D.files[b].path)}</span>${w ? '<span class="badge">schwach</span>' : ''}</li>`).join('')}</ul>`;
      });

    // SCC-Rahmen
    for (const c of cyclic) {
      const ps = c.map((x) => pos.get(x));
      const lo = d3.min(ps), hi = d3.max(ps);
      g.append('rect').attr('x', lo * cs).attr('y', lo * cs).attr('width', (hi - lo + 1) * cs).attr('height', (hi - lo + 1) * cs)
        .attr('fill', 'none').attr('stroke', 'var(--critical)').attr('stroke-width', 2).attr('rx', 2).style('pointer-events', 'none');
    }

    // Spaltennummern
    if (cs >= 12) {
      svg.append('g').attr('transform', `translate(${labelW},${top - 6})`).selectAll('text').data(order).join('text')
        .attr('x', (d, i) => i * cs + cs / 2).attr('text-anchor', 'middle').attr('font-size', 10).text((d, i) => i + 1);
    }
    // Zeilenbeschriftung
    const metrics = new Map(groups.map((gk) => [gk, { files: 0, nloc: 0 }]));
    files.forEach((f) => { const m = metrics.get(keyOf.get(f.i)); m.files++; m.nloc += f.nloc; });
    svg.append('g').attr('transform', `translate(0,${top})`).selectAll('text').data(order).join('text')
      .attr('class', 'dsm-row-label').attr('x', labelW - 6).attr('y', (d, i) => i * cs + cs / 2 + 4).attr('text-anchor', 'end')
      .attr('font-size', Math.min(12, Math.max(9, cs - 3)))
      .style('fill', (d) => (compOf.get(d) >= 0 ? 'var(--critical)' : null))
      .text((d, i) => {
        const label = `${d}${isFile.has(d) ? '' : '/'}`;
        const max = Math.floor((labelW - 30) / 6.4);
        return `${i + 1}  ${label.length > max ? '…' + label.slice(-max + 1) : label}`;
      })
      .on('mousemove', (ev, d) => {
        const m = metrics.get(d);
        const outN = d3.sum(order, (o) => (cells.get(d + '\u0000' + o) || []).length);
        const inN = d3.sum(order, (o) => (cells.get(o + '\u0000' + d) || []).length);
        RR.tip.show(RR.tipTable(esc(d), [['Dateien', fmt.int(m.files)], ['NLOC', fmt.int(m.nloc)], ['nutzt (ausgehend)', fmt.int(outN)], ['wird genutzt (eingehend)', fmt.int(inN)],
          ['Klick', isFile.has(d) ? 'Datei öffnen' : level === 'dir' ? 'hineinzoomen' : '']]), ev);
      })
      .on('mouseleave', RR.tip.hide)
      .on('click', (ev, d) => {
        if (level === 'project') return;
        const full = prefix ? prefix + '/' + d : d;
        if (isFile.has(d)) RR.openFile(full);
        else RR.setParams({ prefix: full }, false);
      });
  }

  // ======================= Graph =======================
  function bfs(start, depth, dir, includeTests) {
    const seen = new Map([[start, 0]]);
    let frontier = [start];
    for (let d = 1; d <= depth; d++) {
      const next = [];
      for (const v of frontier) {
        for (const [w] of dir === 'out' ? RR.out[v] : RR.in[v]) {
          if (seen.has(w) || (!includeTests && D.files[w].test)) continue;
          seen.set(w, d);
          next.push(w);
        }
      }
      frontier = next;
    }
    return seen;
  }

  /**
   * Kraftbasierter Graph. Das Layout wird vorab synchron berechnet und in die Fläche eingepasst,
   * damit nichts nachwackelt; Ziehen startet die Simulation kurz neu.
   * nodes: {id, f, color, ring?, label?}  links: {source, target, color, width?, weak?}
   * opts: {label, arrows, distance, charge, layerX(d,w), radius(d), onClick(d), linkTip(d)}
   */
  RR.forceGraph = function forceGraph(host, nodes, links, opts) {
    const w = host.clientWidth;
    const h = host.clientHeight;
    const svg = d3.select(host).append('svg').attr('viewBox', `0 0 ${w} ${h}`).attr('role', 'img').attr('aria-label', opts.label);
    const defs = svg.append('defs');
    const markers = [...new Set(links.map((l) => l.color))];
    const uid = Math.random().toString(36).slice(2, 7);
    markers.forEach((c, i) => {
      defs.append('marker').attr('id', `arr-${uid}-${i}`).attr('viewBox', '0 -4 8 8').attr('refX', 8).attr('refY', 0)
        .attr('markerWidth', 7).attr('markerHeight', 7).attr('orient', 'auto')
        .append('path').attr('d', 'M0,-4L8,0L0,4').attr('fill', c);
    });
    const markerId = new Map(markers.map((c, i) => [c, `arr-${uid}-${i}`]));
    const g = svg.append('g');
    let label = null;
    // Schrift bleibt beim Zoomen gleich groß lesbar
    const zoom = d3.zoom().scaleExtent([0.15, 4]).on('zoom', (ev) => {
      g.attr('transform', ev.transform);
      if (label) label.style('font-size', `${11 / ev.transform.k}px`).style('stroke-width', `${3 / ev.transform.k}px`)
        .attr('dy', (d) => -r(d) - 4 / ev.transform.k);
    });
    svg.call(zoom);
    const r = opts.radius || ((d) => 4 + Math.sqrt(d.f.nloc || 1) / 3);
    const link = g.append('g').selectAll('line').data(links).join('line')
      .attr('stroke', (d) => d.color).attr('stroke-width', (d) => d.width || 1.2).attr('stroke-opacity', 0.75)
      .attr('stroke-linecap', 'round')
      .attr('stroke-dasharray', (d) => (d.weak ? '4 3' : null))
      .attr('marker-end', (d) => (opts.arrows ? `url(#${markerId.get(d.color)})` : null));
    if (opts.linkTip) link.on('mousemove', (ev, d) => RR.tip.show(opts.linkTip(d), ev)).on('mouseleave', RR.tip.hide);
    const node = g.append('g').selectAll('circle').data(nodes).join('circle')
      .attr('r', r).attr('fill', (d) => d.color).attr('stroke', (d) => d.ring || 'var(--surface-1)').attr('stroke-width', (d) => (d.ring ? 3 : 2))
      .style('cursor', 'pointer')
      .on('mousemove', (ev, d) => RR.tip.show(RR.fileTip(d.f), ev))
      .on('mouseleave', RR.tip.hide)
      .on('click', (ev, d) => opts.onClick(d));
    label = g.append('g').selectAll('text').data(nodes.filter((d) => d.label)).join('text')
      .attr('class', 'node-label').attr('dy', (d) => -r(d) - 4).attr('text-anchor', 'middle').text((d) => d.label);
    const sim = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(links).id((d) => d.id).distance(opts.distance || 70).strength(opts.linkStrength || 0.4))
      .force('charge', d3.forceManyBody().strength(opts.charge || -220))
      .force('collide', d3.forceCollide().radius((d) => r(d) + 6))
      .force('x', d3.forceX(w / 2).strength(0.04))
      .force('y', d3.forceY(h / 2).strength(0.06))
      .stop();
    if (opts.layerX) sim.force('lx', d3.forceX((d) => opts.layerX(d, w)).strength(0.25));
    function ticked() {
      link.each(function (d) {
        const dx = d.target.x - d.source.x, dy = d.target.y - d.source.y;
        const len = Math.hypot(dx, dy) || 1;
        const rt = opts.arrows ? r(d.target) + 3 : 0;
        d3.select(this).attr('x1', d.source.x).attr('y1', d.source.y)
          .attr('x2', d.target.x - (dx / len) * rt).attr('y2', d.target.y - (dy / len) * rt);
      });
      node.attr('cx', (d) => d.x).attr('cy', (d) => d.y);
      label.attr('x', (d) => d.x).attr('y', (d) => d.y);
    }
    const n = Math.ceil(Math.log(sim.alphaMin()) / Math.log(1 - sim.alphaDecay()));
    for (let i = 0; i < n; i++) sim.tick();
    ticked();
    // in die Fläche einpassen
    const [x0, x1] = d3.extent(nodes, (d) => d.x);
    const [y0, y1] = d3.extent(nodes, (d) => d.y);
    const pad = 40;
    const k = Math.min(1.6, (w - 2 * pad) / Math.max(1, x1 - x0), (h - 2 * pad) / Math.max(1, y1 - y0));
    svg.call(zoom.transform, d3.zoomIdentity.translate(w / 2, h / 2).scale(k).translate(-(x0 + x1) / 2, -(y0 + y1) / 2));
    sim.on('tick', ticked);
    node.call(d3.drag()
      .on('start', (ev, d) => { if (!ev.active) sim.alphaTarget(0.15).restart(); d.fx = d.x; d.fy = d.y; })
      .on('drag', (ev, d) => { d.fx = ev.x; d.fy = ev.y; })
      .on('end', (ev, d) => { if (!ev.active) sim.alphaTarget(0); d.fx = null; d.fy = null; }));
    return sim;
  };
  const forceGraph = RR.forceGraph;

  /** Beschriftung nur für die wichtigsten Knoten, sonst wird es unlesbar. */
  RR.labelTop = (nodes, weight, max = 14, always = () => false) => {
    const top = new Set(nodes.slice().sort((a, b) => weight(b) - weight(a)).slice(0, max).map((d) => d.id));
    nodes.forEach((d) => { d.label = always(d) || top.has(d.id) ? d.f.name : null; });
  };

  function renderGraph(root, params) {
    const depth = Math.max(1, Math.min(4, +params.depth || 1));
    const includeTests = RR.prefs.showTests;
    const cycleIdx = params.cycle != null ? +params.cycle : null;
    let center = params.focus ? RR.byPath.get(params.focus) : null;
    if (!center && cycleIdx == null) {
      // Startpunkt: meistgenutzte Datei (höchster direkter Fan-in)
      center = D.files.filter((f) => f.deps && !f.test).sort((a, b) => (b.ca ?? 0) - (a.ca ?? 0))[0];
    }
    const options = D.files.filter((f) => f.deps).map((f) => `<option value="${esc(f.path)}">`).join('');
    root.insertAdjacentHTML('beforeend', `
      <div class="toolbar">
        <label>Datei <input type="search" id="g-file" list="g-files" placeholder="Pfad eingeben…" value="${center ? esc(center.path) : ''}" style="min-width:min(100%,420px)"></label>
        <datalist id="g-files">${options}</datalist>
        <label>Tiefe <input type="number" id="g-depth" min="1" max="4" value="${depth}" style="width:56px"></label>
        <label><input type="checkbox" id="g-tests" ${includeTests ? 'checked' : ''}> Testdateien</label>
        ${D.cycles.length ? `<label>Zyklus <select id="g-cycle"><option value="">–</option>${D.cycles.map((c, i) => `<option value="${i}" ${i === cycleIdx ? 'selected' : ''}>#${i + 1} (${c.length} Dateien)</option>`).join('')}</select></label>` : ''}
      </div>
      <div class="split">
        <div class="graph-wrap" id="graph"></div>
        <div class="card" id="g-side"></div>
      </div>`);
    const fileIn = root.querySelector('#g-file');
    fileIn.addEventListener('change', () => { if (RR.byPath.has(fileIn.value)) RR.setParams({ focus: fileIn.value, cycle: null }, false); });
    root.querySelector('#g-depth').addEventListener('change', (e) => RR.setParams({ depth: e.target.value }));
    root.querySelector('#g-tests').addEventListener('change', (e) => { RR.prefs.showTests = e.target.checked; RR.savePrefs(); RR.rerender(); });
    const cyc = root.querySelector('#g-cycle');
    if (cyc) cyc.addEventListener('change', (e) => RR.setParams({ cycle: e.target.value || null, focus: null }, false));

    const host = root.querySelector('#graph');
    const side = root.querySelector('#g-side');
    const c1 = RR.css('--series-1'), c2 = RR.css('--series-2'), crit = RR.css('--critical'), muted = RR.css('--text-muted');

    if (cycleIdx != null && D.cycles[cycleIdx]) {
      const members = new Set(D.cycles[cycleIdx]);
      const nodes = [...members].map((i) => ({ id: i, f: D.files[i], color: c1 }));
      RR.labelTop(nodes, (d) => d.f.nloc, 30);
      const links = D.edges.filter(([a, b]) => members.has(a) && members.has(b))
        .map(([a, b, weak]) => ({ source: a, target: b, weak: !!weak, color: weak ? muted : crit }));
      side.innerHTML = `<h3>Zyklus #${cycleIdx + 1}</h3><p class="small secondary">${members.size} Dateien hängen über statische Imports gegenseitig voneinander ab. Um den Zyklus aufzulösen, eine der roten Kanten entfernen, z. B. durch ein gemeinsames Interface oder durch das Verschieben geteilter Teile in eine eigene Datei.</p>
        <h3>Kanten im Zyklus</h3><ul class="list">${links.filter((l) => !l.weak).map((l) => `<li><span class="path">${RR.fileLink(D.files[l.source].path, esc(D.files[l.source].name))} → ${RR.fileLink(D.files[l.target].path, esc(D.files[l.target].name))}</span></li>`).join('')}</ul>`;
      forceGraph(host, nodes, links, { arrows: true, label: 'Zyklus-Graph', distance: 110, onClick: (d) => RR.setParams({ focus: d.f.path, cycle: null }, false) });
      return;
    }
    if (!center) {
      host.innerHTML = '<div class="empty">Keine Datei mit Import-Auflösung</div>';
      return;
    }
    const outs = bfs(center.i, depth, 'out', includeTests);
    const ins = bfs(center.i, depth, 'in', includeTests);
    let ids = new Set([...outs.keys(), ...ins.keys()]);
    let truncated = false;
    if (ids.size > 220) {
      truncated = true;
      const ranked = [...ids].sort((a, b) => Math.min(outs.get(a) ?? 9, ins.get(a) ?? 9) - Math.min(outs.get(b) ?? 9, ins.get(b) ?? 9));
      ids = new Set(ranked.slice(0, 220));
    }
    const sameCycle = (i) => center.cycle != null && D.files[i].cycle === center.cycle;
    const nodes = [...ids].map((i) => {
      const isOut = outs.has(i) && i !== center.i, isIn = ins.has(i) && i !== center.i;
      return {
        id: i, f: D.files[i],
        color: i === center.i ? RR.css('--text-primary') : isOut && !isIn ? c1 : isIn && !isOut ? c2 : RR.css('--series-7'),
        ring: i !== center.i && sameCycle(i) ? crit : null,
        side: i === center.i ? 0 : isOut && !isIn ? 1 : isIn && !isOut ? -1 : 0,
      };
    });
    RR.labelTop(nodes, (d) => d.f.nloc, 10, (d) => d.id === center.i);
    const links = D.edges.filter(([a, b]) => ids.has(a) && ids.has(b) && ((outs.has(a) && outs.has(b)) || (ins.has(a) && ins.has(b))))
      .map(([a, b, weak]) => ({ source: a, target: b, weak: !!weak, color: sameCycle(a) && sameCycle(b) ? crit : muted }));
    const f = center;
    side.innerHTML = `<h3 class="mono" style="overflow-wrap:anywhere">${esc(f.path)}</h3>
      <div class="mini-kpis"><div><div class="k">nutzt direkt</div><div class="v">${f.ce ?? RR.out[f.i].length}</div></div>
      <div><div class="k">genutzt von</div><div class="v">${f.ca ?? RR.in[f.i].length}</div></div>
      <div><div class="k">transitiv abhängig</div><div class="v">${f.impact ?? '–'}</div></div></div>
      <div class="legend" style="margin-top:12px"><span><span class="sw" style="background:${c1}"></span>Abhängigkeiten (nutzt)</span><span><span class="sw" style="background:${c2}"></span>Abhängige (wird genutzt von)</span><span><span class="sw" style="background:var(--series-7)"></span>beides</span><span><span class="sw" style="background:transparent;border:2px solid ${crit}"></span>gleicher Zyklus</span><span><span class="line" style="border-top-style:dashed;border-color:${muted}"></span>schwache Kante</span></div>
      ${truncated ? '<p class="note">Graph auf 220 Knoten gekürzt (nächste zuerst). Tiefe verringern für Vollständigkeit.</p>' : ''}
      <p class="small secondary">Knoten anklicken = neu zentrieren. Ziehen verschiebt, Mausrad zoomt.</p>
      <div class="actions"><button class="btn" data-file="${esc(f.path)}">Details öffnen</button></div>`;
    forceGraph(host, nodes, links, {
      arrows: true,
      label: `Abhängigkeitsgraph um ${f.path}`,
      layerX: (d, w) => w / 2 + d.side * w * 0.22,
      onClick: (d) => RR.setParams({ focus: d.f.path, cycle: null }, false),
    });
  }

  RR.register('deps', 'Abhängigkeiten', (root, params) => {
    const mode = params.mode === 'graph' || params.focus || params.cycle != null ? 'graph' : 'dsm';
    root.innerHTML = `<div class="toolbar"><span class="seg" id="deps-mode">
        <button type="button" data-v="dsm" aria-pressed="${mode === 'dsm'}">Matrix (DSM)</button>
        <button type="button" data-v="graph" aria-pressed="${mode === 'graph'}">Graph um Datei / Zyklus</button></span></div>`;
    root.querySelectorAll('#deps-mode button').forEach((b) => b.addEventListener('click', () =>
      RR.go('deps', b.dataset.v === 'graph' ? { mode: 'graph' } : {}, false)));
    if (!D.files.some((f) => f.deps)) {
      root.insertAdjacentHTML('beforeend', '<div class="empty">Keine Dateien mit Import-Auflösung (TS/JS, Java, Python) gefunden.</div>');
      return;
    }
    if (mode === 'dsm') renderDsm(root, params);
    else renderGraph(root, params);
  });
})();
