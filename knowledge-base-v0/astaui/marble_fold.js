/* Folding the side panes away: a press at each end of the top bar folds the
   pane on that side to a rail at the page's edge, and the rail, which names
   what the pane holds, opens it again. Where the list and the details share
   one column (a laptop), the press on the right folds whichever is showing.
   Which panes are folded is a look, data-fold on kb-lens ("cat", "insp"),
   filed like the lens itself. While the map is lined up by a workflow, both
   fold whatever the look says, so the map has the room; a pane opened then
   stays open until the line-up ends, and is not filed. The page shows the
   outcome as marble-fold-cat and marble-fold-insp on kb-console; the presses
   and rails are data-marble-transient. */
(() => {
  const F = (window.kbFold = window.kbFold || {});
  const byId = (id) => document.querySelector(`[data-marble-id="${id}"]`);
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const short = (t) => {
    const s = String(t || '');
    for (const cut of [' — ', ' – ', ' - ', ': ', ' (']) { const i = s.indexOf(cut); if (i >= 3) return s.slice(0, i); }
    return s;
  };
  // A panel with its edge on the left or right, and an arrow: toward that edge to fold, away to open.
  const icon = (side, open) => {
    const d = side === 'left' ? 5.5 : 10.5, c = side === 'left' ? 10 : 6;
    const arrow = (side === 'left') !== open ? `M${c + 1} 5.5 ${c - 1.5} 8l2.5 2.5` : `M${c - 1} 5.5 ${c + 1.5} 8l-2.5 2.5`;
    return '<svg viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round">'
      + `<rect x="1.75" y="2.75" width="12.5" height="10.5" rx="2"/><path d="M${d} 2.75v10.5"/><path d="${arrow}"/></svg>`;
  };
  const made = (cls) => { const el = document.createElement('button'); el.className = cls; el.type = 'button'; el.setAttribute('data-marble-transient', ''); return el; };

  const lined = () => byId('kb-lens')?.getAttribute('data-view') === 'map' && !!byId('kb-map-tools')?.getAttribute('data-line');
  const filed = () => new Set((byId('kb-lens')?.getAttribute('data-fold') || '').split(' ').filter(Boolean));
  let peek = new Set(); // panes opened while lined up
  F.folded = (k) => (lined() ? !peek.has(k) : filed().has(k));
  F.fold = (k, on) => {
    if (lined()) { if (on) peek.delete(k); else peek.add(k); show(); return; }
    const s = filed();
    if (on) s.add(k);
    else s.delete(k);
    const lens = byId('kb-lens');
    const value = ['cat', 'insp'].filter((x) => s.has(x)).join(' ') || null;
    if (!lens || (lens.getAttribute('data-fold') || null) === value) return;
    if (value) lens.setAttribute('data-fold', value);
    else lens.removeAttribute('data-fold');
    window.marble?.op?.({ type: 'setAttr', id: 'kb-lens', name: 'data-fold', value }, { immediate: true, look: true });
    show();
  };

  // What each rail says: the list that is open, and what is picked.
  function says(k) {
    if (k === 'cat') {
      const to = byId('kb-cat')?.getAttribute('data-cat') || 'builds';
      return byId('kb-cat')?.querySelector(`[data-set="cat"][data-to="${CSS.escape(to)}"]`)?.textContent.trim() || 'The list';
    }
    const sel = byId('kb-sel')?.getAttribute('data-sel') || '';
    if (sel.startsWith('b:')) return short(byId(`kb-pt-${sel.slice(2)}`)?.dataset.title || sel.slice(2));
    return sel ? 'Picked' : 'Nothing picked';
  }

  // The column on the right: the details, or on a laptop whichever pane it shows.
  const right = () => {
    const app = byId('kb-console');
    if (!app || !getComputedStyle(app).gridTemplateAreas.includes('side')) return 'insp';
    return byId('kb-sel')?.getAttribute('data-sel') ? 'insp' : 'cat';
  };
  const WHAT = { cat: 'the list', insp: 'the details' };

  let was = false;
  function show() {
    const app = byId('kb-console'), top = byId('kb-top');
    const now = lined();
    if (!now && was) peek = new Set();
    was = now;
    for (const [pane, k, side] of [[byId('kb-catp'), 'cat', 'left'], [byId('kb-inspp'), 'insp', 'right']]) {
      app?.classList.toggle(`marble-fold-${k}`, F.folded(k));
      if (!pane) continue;
      let rail = pane.querySelector(':scope > .foldrail');
      if (!rail) {
        rail = made('foldrail');
        rail.dataset.fold = k;
        rail.title = `Show ${WHAT[k]}`;
        pane.prepend(rail);
      }
      const text = says(k), html = `${icon(side, true)}<span class="t">${esc(text)}</span>`;
      if (rail.dataset.key !== html) { rail.dataset.key = html; rail.innerHTML = html; rail.setAttribute('aria-label', `Show ${WHAT[k]}: ${text}`); }
    }
    if (!top) return;
    for (const side of ['left', 'right']) {
      let b = top.querySelector(`:scope > .foldbtn[data-side="${side}"]`);
      if (!b) {
        b = made('foldbtn');
        b.dataset.side = side;
        if (side === 'left') top.prepend(b);
        else top.append(b);
      }
      const k = side === 'left' ? 'cat' : right(), shut = F.folded(k);
      b.dataset.fold = k;
      const svg = icon(side, shut);
      if (b.dataset.key !== svg) { b.dataset.key = svg; b.innerHTML = svg; }
      b.title = `${shut ? 'Show' : 'Hide'} ${WHAT[k]}`;
      b.setAttribute('aria-label', b.title);
      b.setAttribute('aria-expanded', String(!shut));
    }
  }

  document.addEventListener('click', (e) => {
    const t = e.target.closest?.('.foldbtn, .foldrail');
    if (t) F.fold(t.dataset.fold, t.matches('.foldbtn') && !F.folded(t.dataset.fold));
  });

  const watched = new WeakSet();
  function watch() {
    for (const [id, names] of [['kb-sel', ['data-sel']], ['kb-cat', ['data-cat']], ['kb-lens', ['data-view', 'data-fold']], ['kb-map-tools', ['data-line']]]) {
      const el = byId(id);
      if (el && !watched.has(el)) { watched.add(el); new MutationObserver(() => requestAnimationFrame(show)).observe(el, { attributes: true, attributeFilter: names }); }
    }
    // The map's dots carry the builds' names, and arrive after the page does.
    const pts = byId('kb-map-pts');
    if (pts && !watched.has(pts)) { watched.add(pts); new MutationObserver(() => requestAnimationFrame(show)).observe(pts, { childList: true }); }
    show();
  }
  watch();
  addEventListener('resize', () => requestAnimationFrame(show));
  const ready = (m) => m.register?.(watch);
  if (window.marble) ready(window.marble);
  else addEventListener('marble:ready', (e) => ready(e.detail), { once: true });
})();
