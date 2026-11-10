/* Compare Two, part 4 of 4: the bar and the picks. Two slots name the
   builds; pressing one opens a list of every build with its screenshot,
   the closest to the other build first, to pick from. The bar also switches
   the stage between the two trees and what could move across. */
(() => {
  const C = (window.kbCompare = window.kbCompare || {});
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const PARTS = [['tree', 'Side by side'], ['move', 'What could move across']];
  const box = (host, cls) => {
    let b = host.querySelector(`:scope > .${cls}`);
    if (!b) { b = document.createElement('div'); b.className = cls; b.setAttribute('data-marble-transient', ''); host.append(b); }
    return b;
  };

  function slot(k) {
    const r = C.rows?.get(C.st[k]);
    return `<button type="button" class="cmslot" data-slot="${k}" aria-expanded="${C.st.arm === k}" aria-haspopup="listbox">` +
      `<span class="cmth">${r?.shot ? C.img(r.shot, '') : ''}</span><span class="cmsl"><span class="cmwho">${k === 'a' ? 'First' : 'Second'}</span>` +
      `<span class="cmst">${r ? esc(r.title) : 'Pick a build'}</span></span><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 6l4 4 4-4"/></svg></button>`;
  }
  function options() {
    const k = C.st.arm, other = C.rows?.get(C.st[k === 'a' ? 'b' : 'a']);
    const q = (C.st.q || '').toLowerCase().split(/\s+/).filter(Boolean);
    const hit = (r) => q.every((w) => `${r.title} ${r.id} ${r.field}`.toLowerCase().includes(w));
    const near = new Map((other?.near || []).map(([id, s]) => [id, s]));
    const row = (r) => `<button type="button" class="cmopt" role="option" data-id="${esc(r.id)}" aria-selected="${r.id === C.st[k]}">` +
      `<span class="cmth">${r.shot ? C.img(r.shot, '') : ''}</span><span class="cmsl"><span class="cmst">${esc(r.title)}</span>` +
      `<span class="cmof">${esc(r.field)}</span></span>${near.has(r.id) ? `<span class="cmcl">${C.two(near.get(r.id))}</span>` : `<span class="cmcl">${C.plural(r.tasks, 'step')}</span>`}</button>`;
    const all = (C.index?.builds || []).filter((r) => r.id !== other?.id && hit(r));
    const close = all.filter((r) => near.has(r.id)).sort((x, y) => near.get(y.id) - near.get(x.id));
    const rest = all.filter((r) => !near.has(r.id)).sort((x, y) => x.title.localeCompare(y.title));
    return (close.length ? `<p class="cmgh">Closest to ${esc(C.short(other.title))} by workflow</p>${close.map(row).join('')}<p class="cmgh">Every other build</p>` : '') +
      (rest.length ? rest.map(row).join('') : close.length ? '' : '<p class="cmquiet">No build matches.</p>');
  }
  C.drawTools = () => {
    const host = C.byId('kb-cm-tools');
    if (!host) return;
    const b = box(host, 'cmtb');
    const had = document.activeElement?.classList.contains('cmq');
    b.innerHTML = `<div class="cmslots">${slot('a')}<button type="button" class="cmswap" aria-label="Swap the two builds" title="Swap">` +
      `<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 5h10M10 2l3 3-3 3M13 11H3M6 8l-3 3 3 3"/></svg></button>${slot('b')}</div>` +
      `<div class="ckseg" role="group" data-cm="part">${PARTS.map(([k, w]) => `<button type="button" data-k="${k}" aria-pressed="${C.st.part === k}">${esc(w)}</button>`).join('')}</div>` +
      (C.R ? C.summary(C.R) : '') +
      (C.st.arm ? `<div class="cmpop" data-for="${C.st.arm}"><input class="cmq" type="search" placeholder="Name or field" aria-label="Find a build" value="${esc(C.st.q || '')}" autocomplete="off" spellcheck="false">` +
        `<div class="cmopts" role="listbox">${options()}</div></div>` : '');
    if (C.st.arm) {
      const q = b.querySelector('.cmq');
      if (had || !C.st.q) { q.focus(); q.setSelectionRange(q.value.length, q.value.length); }
    }
  };

  C.draw = () => {
    C.drawTools();
    const host = C.byId('kb-cm-stage');
    if (!host) return;
    const b = box(host, 'cmbox');
    b.dataset.part = C.st.part;
    if (!C.index) { b.innerHTML = `<p class="cmquiet">${C.err ? `Could not read the comparisons: ${esc(C.err)}. Run <code>python3 -m astaui.compare</code> in knowledge-base-v0, then open this view again.` : 'Reading the builds…'}</p>`; return; }
    if (!C.R) { b.innerHTML = `<p class="cmquiet">${C.loadErr ? `Could not read a build: ${esc(C.loadErr)}.` : C.st.a && C.st.b ? 'Lining up the two workflows…' : 'Pick two builds.'}</p>`; return; }
    const keep = b.querySelector('.cmtrees')?.scrollTop || 0;
    b.innerHTML = C.st.part === 'move' ? C.drawMove(C.R) : C.drawTrees(C.R);
    const t = b.querySelector('.cmtrees');
    if (t) { t.scrollTop = keep; requestAnimationFrame(C.lines); }
  };

  let seq = 0;
  C.compare = () => {
    const { a, b } = C.st;
    C.R = null;
    C.loadErr = '';
    C.draw();
    if (!a || !b) return;
    const n = ++seq;
    Promise.all([C.build(a), C.build(b)]).then(([A, B]) => {
      if (n !== seq) return;
      C.R = C.align(A, B);
      C.draw();
    }).catch((e) => { if (n === seq) { C.loadErr = String(e.message || e); C.draw(); } });
  };
  const defaults = () => {
    const rows = C.index?.builds || [];
    if (!C.rows.has(C.st.a)) C.st.a = '';
    if (!C.rows.has(C.st.b)) C.st.b = '';
    if (!C.st.a) {
      const top = rows.filter((r) => r.near.length).sort((x, y) => y.near[0][1] - x.near[0][1])[0];
      C.st.a = top?.id || '';
    }
    if (!C.st.b && C.st.a) C.st.b = C.rows.get(C.st.a)?.near?.find(([id]) => id !== C.st.a)?.[0] || '';
    C.keep();
  };

  const set = (k, id) => {
    C.st[k] = id;
    C.st.arm = '';
    C.st.q = '';
    C.st.focus = null;
    C.keep();
    C.compare();
  };
  document.addEventListener('click', (e) => {
    const v = e.target.closest?.('#kb-v-compare');
    if (!v) { if (C.st.arm) { C.st.arm = ''; C.drawTools(); } return; }
    const s = e.target.closest('.cmslot');
    if (s) { C.st.arm = C.st.arm === s.dataset.slot ? '' : s.dataset.slot; C.st.q = ''; C.drawTools(); return; }
    const o = e.target.closest('.cmopt');
    if (o) return set(C.st.arm, o.dataset.id);
    if (e.target.closest('.cmswap')) { [C.st.a, C.st.b] = [C.st.b, C.st.a]; return set('a', C.st.a); }
    const p = e.target.closest('[data-cm="part"] > button');
    if (p) { C.st.part = p.dataset.k; C.keep(); C.draw(); return; }
    if (C.st.arm && !e.target.closest('.cmpop')) { C.st.arm = ''; C.drawTools(); }
    const t = e.target.closest('.cmtask');
    if (t) {
      const f = C.st.focus;
      C.st.focus = f && f.side === t.dataset.side && f.id === t.dataset.id ? null : { side: t.dataset.side, id: t.dataset.id };
      C.draw();
    }
  });
  document.addEventListener('input', (e) => {
    if (!e.target.matches?.('#kb-v-compare .cmq')) return;
    C.st.q = e.target.value;
    const list = e.target.parentElement.querySelector('.cmopts');
    if (list) list.innerHTML = options();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && C.st.arm && e.target.closest?.('#kb-v-compare')) { C.st.arm = ''; C.drawTools(); C.byId('kb-cm-tools')?.querySelector('.cmslot')?.focus(); }
    if (e.key === 'Enter' && e.target.matches?.('#kb-v-compare .cmq')) {
      const first = e.target.parentElement.querySelector('.cmopt');
      if (first) set(C.st.arm, first.dataset.id);
    }
  });

  const open = () => C.byId('kb-lens')?.getAttribute('data-view') === 'compare';
  let wasOpen = false;
  C.show = () => {
    const now = open();
    const opened = now && !wasOpen;
    wasOpen = now;
    if (!opened) return;
    C.draw();
    C.load(true).then(() => {
      if (!C.index) return C.draw();
      defaults();
      C.compare();
    });
  };
  C.start = () => {
    if (C.started) return;
    C.started = true;
    const lens = C.byId('kb-lens');
    if (lens) new MutationObserver(C.show).observe(lens, { attributes: true, attributeFilter: ['data-view'] });
    const stage = C.byId('kb-cm-stage');
    if (stage && 'ResizeObserver' in window) new ResizeObserver(() => { if (open()) C.lines(); }).observe(stage);
    C.show();
  };
  C.ready?.();
})();
