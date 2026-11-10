/* Check Runs, part 2 of 4: the picked run. Its head and the reviewer's scores,
   the owner's verdict (the one thing filed: an item per run in kb-ck-marks,
   data-v right, partial or wrong, the note as its text), and the switch
   between what the agent did and the tree it wrote (part 3) and the review
   and the cost (part 4). */
(() => {
  const K = (window.kbCheck = window.kbCheck || {});
  const { byId, esc } = K;
  const PARTS = [['steps', 'What it did'], ['tree', 'What it wrote'], ['replay', 'Replay'], ['review', 'Review'], ['cost', 'Cost']];
  const FILE_WORD = { yes: 'File as is', fix: 'Fix, then file', no: 'Redo' };
  const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };
  // Each verdict edit is sent on its own: on a page this size the drive reads the
  // whole file once per edit, and two in one call can run it out of memory.
  const NOW = { immediate: true };

  function host() {
    const h = byId('kb-ck-one');
    if (!h) return null;
    let box = h.querySelector(':scope > .ck1');
    if (!box) { box = document.createElement('div'); box.className = 'ck1'; box.setAttribute('data-marble-transient', ''); h.append(box); }
    return box;
  }

  const fact = (dt, dd, cls = '') => `<div><dt>${esc(dt)}</dt><dd class="${cls}">${dd}</dd></div>`;
  const score = (n) => (n == null ? '–' : `${n}<small>/5</small>`);
  function head(d) {
    const r = d.row || {};
    const rv = d.review || {};
    const iface = d.tree?.interface || {};
    const ex = d.stages?.explore || d.stages?.codeonly || {};
    const repo = d.repo ? `<a href="https://github.com/${esc(d.repo)}${d.commit ? `/tree/${esc(d.commit)}` : ''}${d.subdir ? `/${esc(d.subdir)}` : ''}" target="_blank" rel="noopener">${esc(d.repo)}</a>` : '';
    const when = d.run ? `${d.run.slice(0, 4)}-${d.run.slice(4, 6)}-${d.run.slice(6, 8)} ${d.run.slice(9, 11)}:${d.run.slice(11, 13)}` : '';
    const ev = rv.evidence || {};
    return `<button type="button" class="link ckback">All runs</button>` +
      `<div class="ckhead"><h3>${esc(r.title || d.slug)}</h3>` +
      `<p class="ckmeta">${[repo, esc(d.field || ''), esc(d.framework || ''), `run ${esc(when)}`, r.filed ? 'in the knowledge base' : 'not filed'].filter(Boolean).join(' · ')}</p>` +
      (iface.what_it_is_for ? `<p class="ckfor">${esc(iface.what_it_is_for)}</p>` : '') + `</div>` +
      `<dl class="ckfacts">` +
      fact('Status', esc(K.STATUS_WORD[r.status] || r.status || '–')) +
      fact('Reviewer says', esc(FILE_WORD[rv.file] || '–')) +
      fact('Workflow coverage', score(rv.coverage?.score), K.band(rv.coverage?.score)) +
      fact('Depth', esc(rv.depth?.verdict || '–'), rv.depth?.verdict && rv.depth.verdict !== 'right' ? 'mid' : '') +
      fact('Fit to purpose', score(rv.point), K.band(rv.point)) +
      fact('Features', score(rv.features?.score), K.band(rv.features?.score)) +
      fact('Tree', ex.phases != null ? `${ex.phases} <small>phases</small> ${ex.tasks ?? 0} <small>tasks</small>` : '–') +
      fact('Replayed', esc(r.replayed || '–')) +
      fact('Browser calls', `${r.steps || 0} <small>${r.clicks || 0} clicks${r.errors ? `, ${r.errors} error${r.errors === 1 ? '' : 's'}` : ''}</small>`, r.errors ? 'mid' : '') +
      fact('Screens checked', ev.checked != null ? `${ev.checked} <small>${(ev.wrong || []).length} wrong</small>` : '–', (ev.wrong || []).length ? 'lo' : '') +
      fact('Cost', `${K.money(d.cost)} <small>${d.minutes != null ? `${d.minutes} min` : ''}</small>`) +
      `</dl>` +
      (d.failed ? `<p class="ckp"><b>Why it stopped:</b> ${esc(d.failed)}</p>` : '') +
      (rv.summary ? `<p class="cksum"><b>Reviewer:</b> ${esc(rv.summary)}</p>` : '');
  }

  // ---- the owner's verdict
  function mine(slug) {
    const m = K.marks().get(slug) || {};
    return `<div class="ckmine" data-slug="${esc(slug)}"><span class="tl">My verdict</span>` +
      `<div class="ckpick" role="group" aria-label="My verdict">${Object.entries(K.VERDICT_WORD).map(([v, w]) =>
        `<button type="button" data-v="${v}" aria-pressed="${m.v === v}">${esc(w)}</button>`).join('')}</div>` +
      `<textarea class="cknote" rows="2" placeholder="What it got right, what it missed or clicked wrongly" aria-label="Note on this run">${esc(m.note || '')}</textarea>` +
      `<p class="ckwhen" aria-live="polite">${m.at ? `Saved ${esc(m.at)}` : 'Saved with the page when you pick or leave the note.'}</p></div>`;
  }
  K.drawMine = () => {
    const box = document.querySelector('#kb-ck-one .ckmine');
    if (!box) return;
    const m = K.marks().get(box.dataset.slug) || {};
    for (const b of box.querySelectorAll('.ckpick button')) b.setAttribute('aria-pressed', String(m.v === b.dataset.v));
    const note = box.querySelector('.cknote');
    if (note && document.activeElement !== note && note.value !== (m.note || '')) note.value = m.note || '';
  };
  // One op per gesture: a new run's verdict is an insert, a changed one a setAttr
  // or a setText. The page moves first, then the op is filed.
  function save(slug, change) {
    const M = window.marble;
    const box = document.querySelector('#kb-ck-one .ckmine');
    const said = (t) => { const w = box?.querySelector('.ckwhen'); if (w) w.textContent = t; };
    const have = K.marks().get(slug);
    const run = K.current?.run || '';
    if (!have) {
      const v = change.v ? ` data-v="${esc(change.v)}"` : '';
      const op = { type: 'insert', parentId: 'kb-ck-marks', beforeId: null,
        html: `<li data-marble-${'id'}="kb-ck-m-${esc(slug)}" data-run="${esc(run)}" data-at="${today()}"${v}>${esc(change.note ?? '')}</li>` };
      if (M?.apply) { M.apply(op); M.op(op, NOW); } else byId('kb-ck-marks')?.insertAdjacentHTML('beforeend', op.html);
    } else if ('v' in change) {
      const value = change.v || null;
      if (value) have.li.setAttribute('data-v', value); else have.li.removeAttribute('data-v');
      M?.op?.({ type: 'setAttr', id: `kb-ck-m-${slug}`, name: 'data-v', value }, NOW);
    } else {
      have.li.textContent = change.note;
      M?.op?.({ type: 'setText', id: `kb-ck-m-${slug}`, text: change.note }, NOW);
    }
    said(M ? `Saved ${new Date().toTimeString().slice(0, 5)}` : 'Not saved: this copy is not open in the drive.');
    K.drawList();
    K.drawMine();
  }
  document.addEventListener('click', (e) => {
    const b = e.target.closest('#kb-ck-one .ckpick button');
    if (b) {
      const slug = b.closest('.ckmine').dataset.slug;
      const now = K.marks().get(slug)?.v;
      save(slug, { v: now === b.dataset.v ? '' : b.dataset.v });
      return;
    }
    if (e.target.closest('#kb-ck-one .ckback')) { K.pick(''); return; }
    const p = e.target.closest('#kb-ck-one .ckparts > button');
    if (p) { K.st.part = p.dataset.k; K.keep(); drawPart(); }
  });
  document.addEventListener('focusout', (e) => {
    if (!e.target.matches?.('#kb-ck-one .cknote')) return;
    const slug = e.target.closest('.ckmine').dataset.slug;
    const note = e.target.value.trim();
    if (note !== (K.marks().get(slug)?.note || '')) save(slug, { note });
  });

  // ---- the parts
  function drawPart() {
    const d = K.current;
    const box = document.querySelector('#kb-ck-one .ckpart');
    if (!d || !box) return;
    for (const b of document.querySelectorAll('#kb-ck-one .ckparts > button')) b.setAttribute('aria-pressed', String(b.dataset.k === K.st.part));
    const part = K.st.part;
    box.innerHTML = part === 'tree' ? K.drawTree(d) : part === 'replay' ? K.drawReplay(d) : part === 'review' ? K.drawReview(d) : part === 'cost' ? K.drawCost(d) : K.drawSteps(d, d.explore, 'explore');
  }

  let asked = '';
  K.drawOne = () => {
    const box = host();
    if (!box) return;
    const slug = K.st.pick;
    if (!slug) {
      K.current = null;
      box.innerHTML = '<p class="ckempty">Pick a run to see the tree the agent wrote, every browser call it made with the screens it kept, the replay, the reviewer’s judgement and the cost, and to give your own verdict.</p>';
      return;
    }
    asked = slug;
    if (K.current?.slug !== slug) box.innerHTML = '<p class="ckempty">Reading this run…</p>';
    K.app(slug).then((d) => {
      if (asked !== slug) return;
      const keepScroll = K.current?.slug === slug ? byId('kb-ck-one')?.scrollTop : 0;
      K.current = d;
      box.innerHTML = `<div class="ckin">${head(d)}${mine(slug)}` +
        `<div class="ckseg ckparts" role="group" aria-label="Show">${PARTS.map(([k, w]) => `<button type="button" data-k="${k}">${esc(w)}</button>`).join('')}</div>` +
        `<div class="ckpart"></div></div>`;
      drawPart();
      const one = byId('kb-ck-one');
      if (one) one.scrollTop = keepScroll || 0;
    }).catch((e) => {
      if (asked === slug) box.innerHTML = `<p class="ckempty">Could not read this run: ${esc(e.message || e)}.</p>`;
    });
  };
  K.redrawPart = drawPart;
  K.ready?.();
})();
