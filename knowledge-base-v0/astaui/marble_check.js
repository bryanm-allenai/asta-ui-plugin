/* Check Runs, part 1 of 4: the runs, read from the files `python3 -m
   astaui.checkruns` writes beside the run records, and the bar that filters
   and sorts them. What is drawn here is transient; the one thing filed is the
   owner's verdict on a run, an item each in kb-ck-marks (part 2). Where the
   lens stands (filters, the picked run) is kept for the tab only. */
(() => {
  const K = (window.kbCheck = window.kbCheck || {});
  const byId = (id) => document.querySelector(`[data-marble-id="${id}"]`);
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  K.byId = byId;
  K.esc = esc;
  K.DIR = 'Ai2/AstaUI/knowledge-base-v0/pilot/public';
  K.file = (path) => `/drive/file?path=${encodeURIComponent(path)}`;
  K.money = (c) => (c == null ? '–' : `$${Number(c).toFixed(2)}`);
  K.band = (n) => (n == null ? '' : n <= 2 ? 'lo' : n === 3 ? 'mid' : 'hi');

  const STATUS = [['all', 'All'], ['explored', 'Explored'], ['unusable', 'Not usable'], ['code', 'From code only'], ['other', 'Failed or refused']];
  const COV = [['any', 'Any'], ['lo', '1–2'], ['mid', '3'], ['hi', '4–5']];
  const MINE = [['any', 'Any'], ['none', 'Not checked'], ['right', 'Looks right'], ['partial', 'Partial'], ['wrong', 'Wrong']];
  const SORTS = [['cov', 'Coverage, lowest first'], ['point', 'Fit to purpose, lowest first'], ['cost', 'Cost, highest first'],
    ['new', 'Newest first'], ['name', 'Name'], ['field', 'Field']];
  K.STATUS_WORD = { explored: 'Explored', unusable: 'Not usable', code: 'From code only', failed: 'Failed', refused: 'Refused', running: 'Still running', unknown: 'Unknown' };
  K.VERDICT_WORD = { right: 'Looks right', partial: 'Partial', wrong: 'Wrong' };

  const saved = (() => { try { return JSON.parse(sessionStorage.getItem('kbCheck') || '{}'); } catch { return {}; } })();
  K.st = Object.assign({ status: 'all', cov: 'any', mine: 'any', q: '', sort: 'cov', pick: '', part: 'steps', all: false }, saved);
  K.keep = () => { try { sessionStorage.setItem('kbCheck', JSON.stringify(K.st)); } catch { /* a tab without storage just forgets */ } };

  // The owner's verdicts, as the page holds them.
  K.marks = () => {
    const out = new Map();
    for (const li of byId('kb-ck-marks')?.children ?? []) {
      const slug = (li.getAttribute('data-marble-id') || '').replace(/^kb-ck-m-/, '');
      if (slug) out.set(slug, { li, v: li.getAttribute('data-v') || '', note: li.textContent.trim(), at: li.getAttribute('data-at') || '', run: li.getAttribute('data-run') || '' });
    }
    return out;
  };

  let loading = null;
  let loadedAt = 0;
  K.load = (force) => {
    if (loading) return loading;
    if (K.index && !force && Date.now() - loadedAt < 60000) return Promise.resolve(K.index);
    loading = fetch(K.file(`${K.DIR}/inspect/index.json`), { cache: 'no-store' })
      .then((r) => { if (!r.ok) throw new Error(`the drive answered ${r.status}`); return r.json(); })
      .then((j) => { K.index = j; K.err = ''; loadedAt = Date.now(); return j; })
      .catch((e) => { K.err = String(e.message || e); return K.index; })
      .finally(() => { loading = null; });
    return loading;
  };
  const apps = new Map();
  K.app = (slug) => {
    if (apps.has(slug)) return apps.get(slug);
    const p = fetch(K.file(`${K.DIR}/inspect/apps/${slug}.json`), { cache: 'no-store' })
      .then((r) => { if (!r.ok) throw new Error(`the drive answered ${r.status}`); return r.json(); });
    p.catch(() => apps.delete(slug));
    apps.set(slug, p);
    return p;
  };
  K.forget = () => apps.clear();

  function pass(r, m, skip) {
    const st = K.st;
    if (skip !== 'status' && st.status !== 'all') {
      if (st.status === 'other' ? ['explored', 'unusable', 'code'].includes(r.status) : r.status !== st.status) return false;
    }
    if (skip !== 'cov' && st.cov !== 'any' && K.band(r.cov) !== st.cov) return false;
    if (skip !== 'mine' && st.mine !== 'any') {
      const v = m.get(r.slug)?.v || '';
      if (st.mine === 'none' ? v : v !== st.mine) return false;
    }
    if (st.q) {
      const hay = `${r.title} ${r.slug} ${r.field} ${r.framework} ${r.repo}`.toLowerCase();
      if (!st.q.toLowerCase().split(/\s+/).every((w) => hay.includes(w))) return false;
    }
    return true;
  }
  const num = (v, none) => (v == null ? none : v);
  const ORDER = {
    cov: (a, b) => num(a.cov, 9) - num(b.cov, 9) || num(a.point, 9) - num(b.point, 9),
    point: (a, b) => num(a.point, 9) - num(b.point, 9) || num(a.cov, 9) - num(b.cov, 9),
    cost: (a, b) => num(b.cost, 0) - num(a.cost, 0),
    new: (a, b) => String(b.when).localeCompare(String(a.when)),
    name: (a, b) => String(a.title).localeCompare(String(b.title)),
    field: (a, b) => String(a.field).localeCompare(String(b.field)) || String(a.title).localeCompare(String(b.title)),
  };
  K.shown = () => {
    const m = K.marks();
    const rows = (K.index?.apps ?? []).filter((r) => pass(r, m));
    return rows.sort((a, b) => ORDER[K.st.sort](a, b) || String(a.slug).localeCompare(String(b.slug)));
  };

  function seg(key, opts, counts) {
    return `<div class="ckseg" role="group" data-ck="${key}">${opts.map(([k, w]) =>
      `<button type="button" data-k="${k}" aria-pressed="${K.st[key] === k}">${esc(w)}${counts ? `<span class="n">${counts[k] ?? 0}</span>` : ''}</button>`).join('')}</div>`;
  }
  function counts(key, of) {
    const m = K.marks();
    const out = {};
    for (const r of K.index?.apps ?? []) {
      if (!pass(r, m, key)) continue;
      out.any = (out.any || 0) + 1;
      out.all = (out.all || 0) + 1;
      const k = of(r, m);
      out[k] = (out[k] || 0) + 1;
    }
    return out;
  }
  function tools() {
    const host = byId('kb-ck-tools');
    if (!host) return;
    const box = host.querySelector(':scope > .cktb') || host.appendChild(Object.assign(document.createElement('div'), { className: 'cktb' }));
    box.setAttribute('data-marble-transient', '');
    const had = document.activeElement?.classList.contains('ckq');
    box.innerHTML =
      `<div class="ckg"><span class="tl">Status</span>${seg('status', STATUS, counts('status', (r) => (['explored', 'unusable', 'code'].includes(r.status) ? r.status : 'other')))}</div>` +
      `<div class="ckg"><span class="tl">Workflow coverage</span>${seg('cov', COV, counts('cov', (r) => K.band(r.cov) || 'none'))}</div>` +
      `<div class="ckg"><span class="tl">My verdict</span>${seg('mine', MINE, counts('mine', (r, m) => m.get(r.slug)?.v || 'none'))}</div>` +
      `<div class="ckg"><input class="ckq" type="search" placeholder="Name, field or repository" aria-label="Find a run" value="${esc(K.st.q)}" autocomplete="off" spellcheck="false">` +
      `<select class="cksort" aria-label="Sort">${SORTS.map(([k, w]) => `<option value="${k}"${K.st.sort === k ? ' selected' : ''}>${esc(w)}</option>`).join('')}</select></div>`;
    if (had) { const q = box.querySelector('.ckq'); q.focus(); q.setSelectionRange(q.value.length, q.value.length); }
  }

  function row(r, m) {
    const v = m.get(r.slug)?.v;
    const cov = r.cov == null ? '<span>no review</span>' : `<span class="${K.band(r.cov)}">coverage ${r.cov}/5</span>`;
    const status = r.status === 'explored' ? '' : `${esc(K.STATUS_WORD[r.status] || r.status)} · `;
    return `<button type="button" class="ckrow" data-slug="${esc(r.slug)}" aria-current="${K.st.pick === r.slug}">` +
      `<span class="ckrt">${esc(r.title)}</span>` +
      `<span class="ckrs">${cov}<span>${v ? `<span class="ckv" data-v="${v}">${esc(K.VERDICT_WORD[v])}</span> · ` : ''}${K.money(r.cost)}</span></span>` +
      `<span class="ckrf">${status}${esc(r.field || '')}${r.framework ? ` · ${esc(r.framework)}` : ''}${r.depth && r.depth !== 'right' ? ` · ${esc(r.depth)}` : ''}</span></button>`;
  }
  K.drawList = () => {
    const host = byId('kb-ck-list');
    if (!host) return;
    let box = host.querySelector(':scope > .ckl');
    if (!box) { box = document.createElement('div'); box.className = 'ckl'; box.setAttribute('data-marble-transient', ''); host.append(box); }
    tools();
    if (!K.index) {
      box.innerHTML = `<p class="cknone">${K.err ? `Could not read the runs: ${esc(K.err)}. Run <code>python3 -m astaui.checkruns</code> in knowledge-base-v0, then open this view again.` : 'Reading the runs…'}</p>`;
      return;
    }
    const m = K.marks();
    const rows = K.shown();
    const total = K.index.apps.length;
    box.innerHTML = `<p class="ckcount">${rows.length === total ? `${total} runs` : `${rows.length} of ${total} runs`}</p>` +
      (rows.length ? rows.map((r) => row(r, m)).join('') : '<p class="cknone">No run matches these filters.</p>');
  };

  K.pick = (slug) => {
    K.st.pick = slug;
    K.keep();
    for (const b of document.querySelectorAll('#kb-ck-list .ckrow')) b.setAttribute('aria-current', String(b.dataset.slug === slug));
    K.drawOne?.();
  };

  document.addEventListener('click', (e) => {
    const b = e.target.closest('#kb-v-check .ckseg[data-ck] > button');
    if (b) {
      K.st[b.parentElement.dataset.ck] = b.dataset.k;
      K.keep();
      K.drawList();
      return;
    }
    const r = e.target.closest('#kb-ck-list .ckrow');
    if (r) K.pick(r.dataset.slug);
  });
  document.addEventListener('input', (e) => {
    if (!e.target.matches?.('#kb-v-check .ckq')) return;
    K.st.q = e.target.value;
    K.keep();
    K.drawList();
  });
  document.addEventListener('change', (e) => {
    if (!e.target.matches?.('#kb-v-check .cksort')) return;
    K.st.sort = e.target.value;
    K.keep();
    K.drawList();
  });
  // Up and down walk the runs while one has the focus.
  document.addEventListener('keydown', (e) => {
    const r = e.target.closest?.('#kb-ck-list .ckrow');
    if (!r || (e.key !== 'ArrowDown' && e.key !== 'ArrowUp')) return;
    e.preventDefault();
    const sib = e.key === 'ArrowDown' ? r.nextElementSibling : r.previousElementSibling;
    if (sib?.classList.contains('ckrow')) { sib.focus(); K.pick(sib.dataset.slug); }
  });

  const open = () => byId('kb-lens')?.getAttribute('data-view') === 'check';
  let wasOpen = false;
  K.show = () => {
    const now = open();
    const opened = now && !wasOpen;
    wasOpen = now;
    if (!opened) return;
    K.forget();
    K.drawList();
    K.load(true).then(() => { K.drawList(); if (K.st.pick) K.pick(K.st.pick); });
  };
  K.start = () => {
    if (K.started) return;
    K.started = true;
    const lens = byId('kb-lens');
    if (lens) new MutationObserver(K.show).observe(lens, { attributes: true, attributeFilter: ['data-view'] });
    const marks = byId('kb-ck-marks');
    if (marks) new MutationObserver(() => { if (open()) { K.drawList(); K.drawMine?.(); } }).observe(marks, { childList: true, subtree: true, attributes: true, characterData: true });
    K.show();
  };
  K.ready = () => { if (K.drawOne && K.drawSteps && K.drawReview) K.start(); };
  K.ready();
})();
