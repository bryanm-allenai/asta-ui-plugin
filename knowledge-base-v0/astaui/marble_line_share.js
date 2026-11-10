/* The map's Line up, part 4 of 4: what a picked build shares. Picking one of
   the gathered builds lays its own tasks beside the steps of the column they
   match, on its side, each level with its step and saying which step and how
   alike; those steps light, the others fade, and so do the other builds.
   Drawn from the gather file's matches into a transient layer over the dots;
   nothing here is filed. */
(() => {
  const L = (window.kbLine = window.kbLine || {});
  const byId = (id) => document.querySelector(`[data-marble-id="${id}"]`);
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const picked = () => { const s = byId('kb-sel')?.getAttribute('data-sel') || ''; return s.startsWith('b:') ? s.slice(2) : ''; };

  L.share = () => {
    const plot = byId('kb-map-pts');
    if (!plot) return;
    let box = plot.querySelector(':scope > .lnshare');
    const D = L.D, G = L.G, b = picked();
    const p = D && G && L.P && L.line() === D.id && b && b !== D.id ? L.P.get(b) : null;
    const room = p ? (p.up ? G.c0 : G.W - G.c1) - 24 : 0;
    // Nothing to lay out, or no room beside the column (a phone shows the inspector instead).
    if (!p || !p.r.hits.length || room < 120) { box?.remove(); return; }
    if (!box) {
      box = document.createElement('div');
      box.className = 'lnshare';
      box.setAttribute('data-marble-transient', '');
      box.setAttribute('aria-live', 'polite');
      plot.append(box);
    }
    const key = `${G.key}|${b}`;
    if (box.dataset.key === key) return;
    box.dataset.key = key;
    const sw = Math.min(280, room);
    box.style.cssText = `--sx:${p.up ? G.c0 - 12 - sw : G.c1 + 12}px;--sw:${sw}px`;
    const hits = p.r.hits.slice().sort((x, y) => x[0] - y[0]);
    box.innerHTML = hits.map(([ti, v, theirs]) => `<p class="lnsh" data-t="${ti}"><span class="t">${esc(theirs)}</span>`
      + `<span class="h">Step ${esc(L.tasks?.[ti]?.n || ti + 1)} · ${v >= D.same ? 'the same move' : 'alike'}</span></p>`).join('');
    // Each level with its step, pushed down past the one above, then back up
    // from the foot if the last would fall off the map.
    const els = [...box.children], tops = [];
    let last = -Infinity;
    els.forEach((el, i) => {
      const h = el.offsetHeight;
      tops[i] = Math.max(G.ty[+el.dataset.t] - h / 2, last + 4, G.top);
      last = tops[i] + h;
    });
    let floor = G.H - 8;
    for (let i = els.length - 1; i >= 0; i--) {
      tops[i] = Math.min(tops[i], floor - els[i].offsetHeight);
      floor = tops[i] - 4;
    }
    els.forEach((el, i) => { el.style.top = `${Math.round(tops[i])}px`; });
  };
})();
