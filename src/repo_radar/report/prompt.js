/* Arbeitsauftrag für einen KI-Agenten je Note. Die Texte entstehen in prompts.py (grades[].prompt),
 * hier wird nur zusammengesetzt; dieselben Bausteine nutzt `repo-radar task` für das Markdown. */
(function () {
  'use strict';
  const { esc } = RR;

  /** Fundstellen einer Note, bereits nach Wichtigkeit sortiert und auf echte Befunde gefiltert. */
  RR.promptRefs = (g) => (g.prompt ? g.prompt.refs : []);

  RR.agentPrompt = (g, n) => {
    const p = g.prompt;
    const refs = p.refs.slice(0, n).map((r, i) => [`${i + 1}. ${r.text}`, ...r.sub.map((s) => `   - ${s}`)].join('\n'));
    return [p.intro, '', p.refs_header, ...refs].join('\n');
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
