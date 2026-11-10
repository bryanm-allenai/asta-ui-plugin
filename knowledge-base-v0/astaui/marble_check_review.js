/* Check Runs, part 4 of 4: the reviewer's judgement beside what the repository
   says the interface is for, and what each stage of the run cost. */
(() => {
  const K = (window.kbCheck = window.kbCheck || {});
  const { esc } = K;
  const list = (xs) => (xs?.length ? `<ul class="ckul">${xs.map((x) => `<li>${esc(typeof x === 'string' ? x : JSON.stringify(x))}</li>`).join('')}</ul>` : '');
  K.drawReview = (d) => {
    const rv = d.review || {};
    const pl = d.plan || {};
    if (!Object.keys(rv).length) return '<p class="ckp m">This run has no review.</p>';
    const sec = (h, body) => (body ? `<section class="cksec"><h4>${h}</h4>${body}</section>` : '');
    const goals = Array.isArray(pl.goals) ? pl.goals : pl.goals ? [pl.goals] : [];
    return sec('What the repository says it is for', list(goals) + (pl.workflow_stated ? `<p class="ckp m">${esc(typeof pl.workflow_stated === 'string' ? pl.workflow_stated : JSON.stringify(pl.workflow_stated))}</p>` : '')) +
      sec(`Workflow coverage ${rv.coverage?.score ?? '–'}/5`, rv.coverage?.missing?.length ? `<h5>Missing from the tree</h5>${list(rv.coverage.missing)}` : '<p class="ckp m">Nothing named as missing.</p>') +
      sec(`Depth: ${esc(rv.depth?.verdict || '–')}`, `<p class="ckp">${esc(rv.depth?.note || '')}</p>`) +
      sec(`Features ${rv.features?.score ?? '–'}/5`, (rv.features?.note ? `<p class="ckp">${esc(rv.features.note)}</p>` : '') + (rv.features?.missing?.length ? `<h5>Missing</h5>${list(rv.features.missing)}` : '')) +
      sec(`Screens checked: ${rv.evidence?.checked ?? '–'}`, (rv.evidence?.wrong?.length ? `<h5>Wrong</h5>${list(rv.evidence.wrong)}` : '') + `<p class="ckp">${esc(rv.evidence?.note || '')}</p>`) +
      sec(`Labels ${rv.words?.score ?? '–'}/5`, `<p class="ckp">${esc(rv.words?.note || '')}</p>`) +
      sec('Fixes it asked for', list(rv.fixes) + (d.fixed ? '<p class="ckp m">A corrected tree was written from these (tree.fixed.json); the tree shown here is the agent’s own.</p>' : ''));
  }
  K.drawCost = (d) => {
    const rows = Object.entries(d.stages || {});
    if (!rows.length) return '<p class="ckp m">No stages were recorded.</p>';
    const extra = (s) => Object.entries(s).filter(([k, v]) => !['seconds', 'cost', 'account'].includes(k) && v !== null && v !== '' && typeof v !== 'object')
      .map(([k, v]) => `${esc(k.replace(/_/g, ' '))} ${esc(v)}`).join(' · ');
    return `<table class="cktable"><thead><tr><th>Stage</th><th class="r">Time</th><th class="r">Cost</th><th>Login</th><th>Details</th></tr></thead><tbody>` +
      rows.map(([k, s]) => `<tr><td>${esc(k)}</td><td class="r">${s.seconds != null ? `${Math.round(s.seconds)} s` : ''}</td><td class="r">${s.cost ? K.money(s.cost) : ''}</td><td>${esc(s.account || '')}</td><td>${extra(s)}</td></tr>`).join('') +
      `<tr><th>Total</th><th class="r">${d.minutes != null ? `${d.minutes} min` : ''}</th><th class="r">${K.money(d.cost)}</th><th></th><th>${esc(d.model || '')}</th></tr></tbody></table>` +
      '<p class="ckp m">Costs are list prices as claude -p reports them; the runs were billed to the subscription logins.</p>';
  }

  K.ready?.();
})();
