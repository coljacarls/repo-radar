/* Detail-Schublade für eine Datei; startet am Ende die App. */
(function () {
  'use strict';
  const { data: D, fmt, esc } = RR;
  const drawer = document.getElementById('drawer');
  const risk = D.meta.config.grades.complexity.risk;

  function k(label, value) {
    return `<div><div class="k">${label}</div><div class="v">${value}</div></div>`;
  }

  function depList(entries, empty) {
    if (!entries.length) return `<p class="muted small">${empty}</p>`;
    return `<ul class="list">${entries
      .sort((a, b) => D.files[a[0]].path.localeCompare(D.files[b[0]].path))
      .map(([i, weak]) => `<li><span class="path">${RR.fileLink(D.files[i].path)}</span>${weak ? '<span class="badge" title="Lazy- oder Typ-Import">schwach</span>' : ''}</li>`)
      .join('')}</ul>`;
  }

  RR.renderDrawer = (f) => {
    if (!f) {
      drawer.classList.remove('open');
      drawer.setAttribute('aria-hidden', 'true');
      return;
    }
    const months = RR.monthRange(D.meta.since || f.first || D.meta.head_time, D.meta.head_time);
    const badges = [
      `<span class="badge">${esc(f.lang)}</span>`,
      f.project !== '.' ? `<span class="badge" title="Projekt">${esc(f.project)}</span>` : '',
      f.test ? '<span class="badge">Testdatei</span>' : '',
      f.barrel ? '<span class="badge" title="Datei re-exportiert nur (index.ts)">Barrel</span>' : '',
      f.cycle != null ? `<a href="#" class="badge crit" data-go="deps" data-params='${esc(JSON.stringify({ mode: 'graph', cycle: f.cycle }))}'>Zyklus #${f.cycle + 1}</a>` : '',
      !f.deps ? '<span class="badge" title="Für diese Sprache gibt es keine Import-Auflösung">ohne Abhängigkeitsanalyse</span>' : '',
      f.error ? `<span class="badge crit" title="${esc(f.error)}">Parserfehler</span>` : '',
    ].join('');

    const fnRows = f.functions.slice(0, 30).map((fn) => `<tr>
        <td class="mono" style="overflow-wrap:anywhere">${esc(fn.name)}</td><td class="num">${fn.line}</td>
        <td class="num">${fn.ccn > risk[1] ? `<span class="badge crit">${fn.ccn}</span>` : fn.ccn > risk[0] ? `<strong>${fn.ccn}</strong>` : fn.ccn}</td>
        <td class="num">${fn.nloc}</td><td class="num">${fn.params}</td></tr>`).join('');

    const classes = f.classes.map((c) => `<div class="group-box">
        <div style="display:flex;justify-content:space-between;gap:8px"><strong class="mono">${esc(c.name)}</strong>
        <span class="${c.lcom > 1 ? 'badge crit' : 'badge'}">LCOM4 ${c.lcom}</span></div>
        <div class="small secondary">${c.methods} Methoden · ${c.fields} Felder · Zeile ${c.line}</div>
        ${c.lcom > 1 ? c.groups.map((g, i) => `<div class="small" style="margin-top:4px"><span class="secondary">Gruppe ${i + 1}:</span> ${g.map((m) => `<span class="chip">${esc(m)}</span>`).join('')}</div>`).join('') : ''}
        ${c.isolated && c.isolated.length ? `<div class="small" style="margin-top:4px"><span class="secondary">ohne Instanzbezug:</span> ${c.isolated.map((m) => `<span class="chip">${esc(m)}</span>`).join('')}</div>` : ''}
      </div>`).join('');

    const coupled = RR.couplingOf[f.i].slice().sort((a, b) => b.degree - a.degree);
    const clones = RR.clonesOf[f.i];
    const authorsTotal = d3.sum(f.authors, (a) => a[1]) || 1;

    drawer.innerHTML = `
      <div class="drawer-head">
        <div class="row"><h2>${esc(f.path)}</h2><button class="btn ghost" id="drawer-close" type="button" aria-label="Schließen">✕</button></div>
        <div class="badges">${badges}</div>
        <div class="actions">
          ${f.deps ? `<a class="btn" href="${RR.hrefFor('deps', { mode: 'graph', focus: f.path })}">Abhängigkeitsgraph</a>` : ''}
          <a class="btn" href="${RR.hrefFor('hotspots', { dir: f.dir || null })}">In Hotspot-Karte</a>
        </div>
      </div>
      <section class="mini-kpis">
        ${k('NLOC', fmt.int(f.nloc))}${k('Funktionen', fmt.int(f.fn))}${k('CCN max / Σ', `${f.ccn_max} / ${f.ccn_sum}`)}
        ${k('Fan-in / -out', f.ca == null ? '–' : `${f.ca} / ${f.ce}`)}${k('Instabilität', fmt.dec2(f.instability))}${k('Reichweite', f.impact == null ? '–' : `${f.impact} Dat.`)}
        ${k('Commits', `${f.commits} <span class="small muted">/ ${f.commits_all}</span>`)}${k('Churn', `+${fmt.int(f.added)} −${fmt.int(f.deleted)}`)}${k('Fix-Commits', fmt.int(f.fixes))}
        ${k('Letzte Änderung', fmt.days(f.age_days))}${k('Hotspot', fmt.dec2(f.hotspot))}${k('Duplikation', fmt.pctRaw(f.dup_pct))}
      </section>
      <section><h3>Änderungen im Analysefenster</h3>${f.commits ? RR.sparkBars(f.months, months) : '<p class="muted small">Keine Commits im Fenster.</p>'}
        <p class="small muted">Erste Änderung ${fmt.date(f.first)} · letzte ${fmt.date(f.last)}</p></section>
      <section><h3>Autoren (gesamte Historie)</h3>${f.authors.length ? `<ul class="list">${f.authors.map(([a, n]) => `<li><span>${esc(a)}</span><span class="bar-cell"><span class="bar" style="width:${Math.max(2, (n / authorsTotal) * 120)}px"></span>${n}</span></li>`).join('')}</ul>` : '<p class="muted small">–</p>'}</section>
      ${f.functions.length ? `<section><h3>Funktionen nach Komplexität</h3><div class="table-wrap"><table class="data"><thead><tr><th>Name</th><th class="num">Zeile</th><th class="num">CCN</th><th class="num">NLOC</th><th class="num">Param.</th></tr></thead><tbody>${fnRows}</tbody></table></div>${f.functions.length > 30 ? `<p class="small muted">+ ${f.functions.length - 30} weitere</p>` : ''}</section>` : ''}
      ${classes ? `<section><h3>Klassen & Kohäsion</h3>${classes}</section>` : ''}
      ${coupled.length ? `<section><h3>Wird gemeinsam geändert mit</h3><ul class="list">${coupled.slice(0, 25).map((c) => `<li><span class="path">${RR.fileLink(D.files[c.other].path)}${c.structural === false ? ' <span class="badge crit">versteckt</span>' : ''}</span><span class="nowrap">${fmt.pct(c.degree)} · ${c.shared}×</span></li>`).join('')}</ul></section>` : ''}
      ${f.deps ? `<section><h3>Importiert (${RR.out[f.i].length})</h3>${depList(RR.out[f.i].slice(), 'Keine Repo-internen Imports.')}</section>
      <section><h3>Wird importiert von (${RR.in[f.i].length})</h3>${depList(RR.in[f.i].slice(), 'Wird von keiner Repo-Datei importiert.')}</section>` : ''}
      ${f.ext.length ? `<section><h3>Externe Pakete</h3>${f.ext.map((e) => `<span class="chip">${esc(e)}</span>`).join('')}</section>` : ''}
      ${clones.length ? `<section><h3>Duplikate</h3><ul class="list">${clones.slice(0, 25).map((c) => `<li><span class="path">Z. ${c.start}–${c.end} ↔ ${RR.fileLink(D.files[c.other].path)}<span class="muted">:${c.oStart}–${c.oEnd}</span></span><span class="nowrap">${c.lines} Zeilen</span></li>`).join('')}</ul></section>` : ''}
      ${f.unresolved ? `<p class="note">${f.unresolved} Import(e) konnten keiner Datei zugeordnet werden.</p>` : ''}
    `;
    drawer.classList.add('open');
    drawer.setAttribute('aria-hidden', 'false');
    drawer.scrollTop = 0;
    drawer.querySelector('#drawer-close').addEventListener('click', () => RR.setParams({ file: null }, false));
  };

  RR.start();
})();
