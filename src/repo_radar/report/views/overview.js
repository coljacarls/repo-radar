/* Überblick: Noten, Kennzahlen, Aktivität, Top-Befunde */
(function () {
  'use strict';
  const { data: D, fmt, esc } = RR;

  function gradeCard(g) {
    const cls = g.grade ? `g-${g.grade}` : 'g-na';
    return `<button type="button" class="grade-card" data-grade="${g.key}" aria-expanded="false">
      <span class="grade-letter ${cls}" aria-label="Note ${g.grade || 'nicht bewertet'}">${g.grade || '–'}</span>
      <span><span class="label">${esc(g.label)}</span><div class="value">${esc(g.value)}</div></span></button>`;
  }

  function gradeDetail(g) {
    const top = (g.top || [])
      .map((t) => {
        const target = t.cycle != null
          ? `<a href="#" data-go="deps" data-params='${esc(JSON.stringify({ mode: 'graph', cycle: t.cycle }))}'>${esc(t.label)}</a> <span class="muted">(${RR.pathHtml(t.file)} …)</span>`
          : `${RR.fileLink(t.file)}${t.line ? `<span class="muted">:${t.line}</span>` : ''} <span class="secondary">${esc(t.label)}</span>`;
        return `<li><span class="path">${target}</span><span class="num nowrap">${esc(t.value)}</span></li>`;
      })
      .join('');
    let thresholds = '';
    if (g.thresholds && Array.isArray(g.thresholds)) {
      thresholds = `<p class="small secondary">Notengrenzen (≤): ${['A', 'B', 'C', 'D'].map((l, i) => `${l} ${g.thresholds[i]}`).join(' · ')} · sonst E</p>`;
    } else if (g.thresholds) {
      thresholds = `<p class="small secondary">Notengrenzen (max. Anteil moderat / hoch / sehr hoch in %): ${Object.entries(g.thresholds)
        .map(([l, v]) => `${l} ${v.join(' / ')}`)
        .join(' · ')} · sonst E</p>`;
    }
    return `<div class="card grade-detail">
      <div class="section-title"><h3>${esc(g.label)}: ${g.grade ? 'Note ' + g.grade : 'nicht bewertet'}</h3>${RR.promptButton(g)}</div>
      <p>${esc(g.explanation)}</p>
      ${g.details && g.details.length ? `<dl class="kv">${g.details.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>` : ''}
      ${thresholds}
      ${top ? `<h3 style="margin-top:12px">Größte Beiträge</h3><ul class="list">${top}</ul>` : ''}
      ${g.source ? `<div class="src">${esc(g.source)}</div>` : ''}
    </div>`;
  }

  function kpi(k, v, s) {
    return `<div class="kpi"><div class="k">${k}</div><div class="v">${v}</div>${s ? `<div class="s">${s}</div>` : ''}</div>`;
  }

  function activityChart(el) {
    const months = D.meta.monthly;
    if (!months.length) {
      el.innerHTML = '<div class="empty">Keine Commits</div>';
      return;
    }
    const all = RR.monthRange(
      Date.UTC(+months[0][0].slice(0, 4), +months[0][0].slice(5) - 1, 1) / 1000,
      D.meta.head_time,
    );
    const counts = Object.fromEntries(months);
    const w = el.clientWidth || 800;
    const h = 160;
    const m = { t: 10, r: 8, b: 22, l: 36 };
    const x = d3.scaleBand().domain(all).range([m.l, w - m.r]).paddingInner(all.length > 60 ? 0.1 : 0.25);
    const y = d3.scaleLinear().domain([0, d3.max(all, (k) => counts[k] || 0) || 1]).nice().range([h - m.b, m.t]);
    const svg = d3.select(el).append('svg').attr('width', w).attr('height', h).attr('role', 'img').attr('aria-label', 'Commits je Monat');
    svg.append('g').attr('class', 'axis').attr('transform', `translate(${m.l},0)`)
      .call(d3.axisLeft(y).ticks(4).tickSize(-(w - m.l - m.r)).tickFormat(d3.format('d')))
      .call((g) => g.select('.domain').remove())
      .call((g) => g.selectAll('line').attr('stroke', 'var(--grid)'));
    const step = Math.ceil(all.length / Math.max(1, Math.floor((w - 60) / 64)));
    svg.append('g').attr('class', 'axis').attr('transform', `translate(0,${h - m.b})`)
      .call(d3.axisBottom(x).tickValues(all.filter((_, i) => i % step === 0)).tickSize(0).tickPadding(6))
      .call((g) => g.select('.domain').attr('stroke', 'var(--grid)'));
    const sinceKey = D.meta.since ? new Date(D.meta.since * 1000).toISOString().slice(0, 7) : null;
    if (sinceKey && x(sinceKey) != null) {
      svg.append('rect').attr('x', x(sinceKey)).attr('y', m.t).attr('width', w - m.r - x(sinceKey)).attr('height', h - m.b - m.t)
        .attr('fill', 'var(--accent-soft)').attr('opacity', 0.5);
      svg.append('text').attr('x', x(sinceKey) + 4).attr('y', m.t + 11).attr('font-size', 11).attr('fill', 'var(--text-secondary)')
        .text('Analysefenster');
    }
    const bw = x.bandwidth();
    svg.append('g').selectAll('path').data(all.filter((k) => counts[k])).join('path')
      .attr('d', (k) => {
        const x0 = x(k), y0 = y(counts[k]), y1 = y(0), r = Math.min(4, bw / 2, y1 - y0);
        return `M${x0},${y1}V${y0 + r}Q${x0},${y0} ${x0 + r},${y0}H${x0 + bw - r}Q${x0 + bw},${y0} ${x0 + bw},${y0 + r}V${y1}Z`;
      })
      .attr('fill', 'var(--series-1)');
    svg.append('g').selectAll('rect').data(all).join('rect')
      .attr('x', (k) => x(k) - x.step() * x.paddingInner() / 2).attr('width', x.step()).attr('y', m.t).attr('height', h - m.b - m.t)
      .attr('fill', 'transparent')
      .on('mousemove', (ev, k) => RR.tip.show(RR.tipTable(k, [['Commits', fmt.int(counts[k] || 0)]]), ev))
      .on('mouseleave', RR.tip.hide);
  }

  RR.register('overview', 'Überblick', (root) => {
    const m = D.meta;
    const prod = D.files.filter((f) => !f.test);
    const tests = D.files.length - prod.length;
    const nloc = d3.sum(prod, (f) => f.nloc);
    const funcs = d3.sum(prod, (f) => f.fn);
    const hot = prod.filter((f) => f.hotspot > 0).sort((a, b) => b.hotspot - a.hotspot).slice(0, 10);
    const hidden = D.coupling.filter((c) => c.structural === false && !D.files[c.a].test && !D.files[c.b].test).slice(0, 10);
    const langs = Object.entries(m.languages).sort((a, b) => b[1].nloc - a[1].nloc);
    const maxLang = d3.max(langs, (l) => l[1].nloc) || 1;
    const covered = D.files.filter((f) => f.deps).length;
    const unresolved = d3.sum(D.files, (f) => f.unresolved);

    const notes = [];
    if (covered < D.files.length)
      notes.push(`${fmt.int(D.files.length - covered)} Dateien ohne Import-Auflösung (nur TS/JS, Java und Python werden strukturell analysiert). Sie fehlen in Graph, Zyklen und versteckter Kopplung.`);
    if (unresolved) notes.push(`${fmt.int(unresolved)} Imports ließen sich keiner Datei zuordnen (z. B. generierter Code oder unbekannte Aliase).`);
    if (!m.duplication.measured) notes.push(`Duplikation nicht gemessen: ${esc(m.duplication.reason)}.`);
    if (m.parse_errors) notes.push(`${m.parse_errors} Dateien konnten nicht vollständig geparst werden.`);
    notes.push(`Ausgeschlossen: ${fmt.int(m.skipped.excluded)} Dateien über Excludes, ${fmt.int(m.skipped.too_large)} zu groß, ${fmt.int(m.skipped.other_language)} ohne unterstützte Sprache (Markup, Konfiguration, Assets).`);

    root.innerHTML = `
      <div class="stack">
        <section>
          <div class="section-title"><h2>Bewertung je Dimension</h2><span class="muted small">Karte anklicken für Herleitung und größte Beiträge</span></div>
          <div class="grades">${D.grades.map(gradeCard).join('')}</div>
          <div id="grade-detail"></div>
        </section>
        <section class="kpis">
          ${kpi('Quelldateien', fmt.int(prod.length), `+ ${fmt.int(tests)} Testdateien`)}
          ${kpi('Code (NLOC)', fmt.int(nloc), 'ohne Tests, Kommentare, Leerzeilen')}
          ${kpi('Funktionen', fmt.int(funcs), `Ø CCN ${fmt.dec(d3.mean(prod.flatMap((f) => f.functions.map((x) => x.ccn))))}`)}
          ${kpi('Commits', fmt.int(m.commits_window), `im Fenster · ${fmt.int(m.commits_total)} gesamt`)}
          ${kpi('Autoren', fmt.int(m.authors_window), `im Fenster · ${fmt.int(m.authors_total)} gesamt`)}
          ${kpi('Import-Kanten', fmt.int(D.edges.length), `${D.cycles.length} Datei-Zyklen`)}
          ${kpi('Externe Pakete', fmt.int(D.externals.length), 'direkt importiert')}
        </section>
        <section class="card">
          <div class="section-title"><h2>Aktivität</h2><span class="muted small">Commits je Monat, gesamte Historie</span></div>
          <div class="chart" id="activity"></div>
        </section>
        <div class="grid cols-2">
          <section class="card">
            <div class="section-title"><h2>Top-Hotspots</h2><a href="#hotspots" class="small">Karte öffnen</a></div>
            <p class="small secondary" style="margin-top:0">Komplexer Code, der oft geändert wird: hier lohnt Refactoring am meisten. Score = log. normierte Commits × log. normierte CCN-Summe.</p>
            <div id="hot-table"></div>
          </section>
          <section class="card">
            <div class="section-title"><h2>Versteckte Kopplung</h2><a href="#coupling?hidden=1" class="small">Alle anzeigen</a></div>
            <p class="small secondary" style="margin-top:0">Werden oft gemeinsam geändert, importieren sich aber nicht direkt.</p>
            ${hidden.length ? `<ul class="list">${hidden
              .map((c) => `<li><span class="path">${RR.fileLink(D.files[c.a].path)}<br>↔ ${RR.fileLink(D.files[c.b].path)}</span><span class="nowrap">${fmt.pct(c.degree)} · ${c.shared}×</span></li>`)
              .join('')}</ul>` : '<div class="empty">Keine gefunden</div>'}
          </section>
          <section class="card">
            <div class="section-title"><h2>Zyklische Abhängigkeiten</h2><a href="#deps" class="small">Matrix öffnen</a></div>
            ${D.cycles.length ? `<ul class="list">${D.cycles.slice(0, 10)
              .map((c, i) => `<li><span class="path"><a href="#" data-go="deps" data-params='${esc(JSON.stringify({ mode: 'graph', cycle: i }))}'>Zyklus #${i + 1}</a>: ${c.slice(0, 4).map((fi) => RR.fileLink(D.files[fi].path, esc(D.files[fi].name))).join(', ')}${c.length > 4 ? ` … +${c.length - 4}` : ''}</span><span class="nowrap">${c.length} Dateien</span></li>`)
              .join('')}</ul>` : '<div class="empty">Keine Zyklen auf Dateiebene</div>'}
            ${D.packages.cycles.length ? `<p class="small secondary">Zusätzlich ${D.packages.cycles.length} Zyklen zwischen Verzeichnissen, z. B. ${D.packages.cycles[0].slice(0, 3).map((p) => `<code>${esc(p)}</code>`).join(' ↔ ')}${D.packages.cycles[0].length > 3 ? ' …' : ''}</p>` : ''}
          </section>
          <section class="card">
            <h2>Sprachen</h2>
            <div class="table-wrap"><table class="data"><thead><tr><th>Sprache</th><th class="num">Dateien</th><th class="num">NLOC</th></tr></thead><tbody>
            ${langs.map(([l, v]) => `<tr><td>${esc(l)}</td><td class="num">${fmt.int(v.files)}</td><td class="num"><div class="bar-cell"><span class="bar" style="width:${Math.max(2, (v.nloc / maxLang) * 120)}px"></span>${fmt.int(v.nloc)}</div></td></tr>`).join('')}
            </tbody></table></div>
            <h3 style="margin-top:16px">Meistgenutzte externe Pakete</h3>
            <div>${D.externals.slice(0, 30).map(([n, c]) => `<span class="chip" title="${c} Dateien">${esc(n)} <span class="muted">${c}</span></span>`).join('') || '<span class="muted">keine</span>'}</div>
          </section>
        </div>
        <section class="card">
          <h2>Hinweise zur Messung</h2>
          <ul class="small secondary" style="margin:0;padding-left:18px">${notes.map((n) => `<li>${n}</li>`).join('')}
            <li>Metriken sind Indikatoren, keine Urteile. Aussagekräftig wird es, wo mehrere zusammenfallen, etwa hohe Komplexität, viele Änderungen und hohe Änderungsreichweite.</li>
            <li>Laufzeit: ${Object.entries(m.timings).map(([k, v]) => `${k} ${fmt.dec(v)} s`).join(' · ')} · repo-radar ${esc(m.tool_version)}</li>
          </ul>
        </section>
      </div>`;

    const detail = root.querySelector('#grade-detail');
    root.querySelectorAll('.grade-card').forEach((btn) =>
      btn.addEventListener('click', () => {
        const open = btn.getAttribute('aria-expanded') === 'true';
        root.querySelectorAll('.grade-card').forEach((b) => b.setAttribute('aria-expanded', 'false'));
        if (open) {
          detail.innerHTML = '';
          return;
        }
        btn.setAttribute('aria-expanded', 'true');
        const g = D.grades.find((x) => x.key === btn.dataset.grade);
        detail.innerHTML = gradeDetail(g);
        const promptBtn = detail.querySelector('[data-prompt]');
        if (promptBtn) promptBtn.addEventListener('click', () => RR.openPrompt(g));
      }),
    );

    activityChart(root.querySelector('#activity'));

    root.querySelector('#hot-table').appendChild(
      RR.table(
        [
          { key: 'path', label: 'Datei', cls: 'path', fmt: (f) => RR.fileLink(f.path) },
          { key: 'hotspot', label: 'Score', num: true, fmt: (f) => fmt.dec2(f.hotspot) },
          { key: 'commits', label: 'Commits', num: true },
          { key: 'ccn_sum', label: 'CCN Σ', num: true },
          { key: 'main_share', label: 'Hauptautor', num: true, fmt: (f) => (f.main_share == null ? '–' : fmt.pct(f.main_share)) },
        ],
        hot,
        { sortKey: 'hotspot', pageSize: 10 },
      ),
    );
  });
})();
