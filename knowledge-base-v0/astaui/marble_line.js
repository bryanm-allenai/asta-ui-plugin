/* The map's Line up, part 1 of 4: the layout. With data-line on kb-map-tools
   set to a build's id, its workflow is written down the middle of the map,
   phases in order from the top with their steps in words, and the builds
   with the closest workflows gather on either side (`python3 -m
   astaui.compare` writes them to compare/gather). A build sits level with
   the steps it matches, pulled hardest by its closest match, and shades
   them in its colour; the closer its whole workflow, the nearer the middle.
   Builds sharing the line build's discipline sit on the left, the rest on
   the right. All of it is data-marble-transient, places are rules in a
   transient <style>; part 2 files the look, part 3 writes the column and
   the names, part 4 lays out what a picked build shares. */
(() => {
  const L = (window.kbLine = window.kbLine || {});
  L.v = 5; // which copy the tab runs: a newer page reloads a tab on an older one
  const byId = (id) => document.querySelector(`[data-marble-id="${id}"]`);
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  L.byId = byId;
  L.esc = esc;
  L.DIR = 'Ai2/AstaUI/knowledge-base-v0/console-data/compare/gather';
  // Where things sit, in pixels: the column's top, the line build's own dot
  // above it, and how far from the column the closest builds sit.
  const TOP = 64, FOCUS = 34, OFF0 = 26;
  // The column: about a third of the map, in the middle.
  L.cols = (W) => {
    const cw = W < 560 ? Math.max(150, W * .54) : Math.min(440, Math.max(250, W * .4));
    return [Math.round((W - cw) / 2), Math.round((W + cw) / 2)];
  };

  const cache = new Map();
  L.get = (id) => {
    if (!cache.has(id)) {
      const name = String(id).replace(/[^A-Za-z0-9-]/g, (c) => `_${c.charCodeAt(0).toString(16)}`);
      cache.set(id, fetch(`/drive/file?path=${encodeURIComponent(`${L.DIR}/${name}.json`)}`, { cache: 'no-store' })
        .then((r) => (r.ok ? r.json() : null)).catch(() => null));
    }
    return cache.get(id);
  };
  L.line = () => byId('kb-map-tools')?.getAttribute('data-line') || '';
  L.mapOpen = () => byId('kb-lens')?.getAttribute('data-view') === 'map';
  const discs = (pt) => ((pt?.dataset.tags || '').match(/\|d:[^|]+/g) || []).map((t) => t.slice(3));
  const ptOf = (plot, b) => plot.querySelector(`.pt[data-pick="b:${CSS.escape(b)}"]`);

  // Each step's top, middle and foot, read off the column as drawn.
  function measure(plot, over) {
    const top = plot.getBoundingClientRect().top + plot.clientTop;
    const G = { tt: [], tb: [], ty: [] };
    for (const r of over.querySelectorAll('.lnstep')) {
      const b = r.getBoundingClientRect(), i = +r.dataset.t;
      G.tt[i] = b.top - top; G.tb[i] = b.bottom - top; G.ty[i] = (G.tt[i] + G.tb[i]) / 2;
    }
    G.end = (over.querySelector('.lncol')?.getBoundingClientRect().bottom ?? top) - top;
    return G;
  }
  // A place along the line (0 to 1, as compare.py gives it) as a height.
  const yAt = (D, G, s) => {
    const S = D.spots;
    if (s <= S[0]) return G.ty[0];
    for (let i = 1; i < S.length; i++) if (s <= S[i]) return G.ty[i - 1] + ((G.ty[i] - G.ty[i - 1]) * (s - S[i - 1])) / (S[i] - S[i - 1] || 1);
    return G.ty[S.length - 1];
  };

  // Where each gathered build goes.
  function places(D, plot, G, mine) {
    const { W, H, c0, c1 } = G;
    const cs = D.near.map((r) => r.c);
    const top = Math.max(...cs), low = Math.min(...cs);
    const off1 = Math.max(OFF0 + 8, Math.min(c0, W - c1) - 16);
    const P = [];
    D.near.forEach((r, i) => {
      const pt = ptOf(plot, r.b);
      if (!pt) return;
      let y = yAt(D, G, r.x);
      if (r.hits.length) {
        const vmax = r.hits[0][1];
        let sw = 0, sy = 0;
        for (const [ti, v] of r.hits) { const w = Math.exp((v - vmax) / .04); sw += w; sy += w * G.ty[ti]; }
        y = sy / sw;
      }
      const t = top > low ? (top - r.c) / (top - low) : 0;
      const off = OFF0 + (off1 - OFF0) * Math.pow(t, .85);
      const up = mine.size ? discs(pt).some((d) => mine.has(d)) : i % 2 === 0;
      P.push({ r, up, x: up ? c0 - off : c1 + off, y });
    });
    // Dots that would sit on each other move apart, more along the column
    // than away from it, each staying on its own side.
    const R = 15;
    for (let k = 0; k < 90; k++) {
      let moved = false;
      for (let i = 0; i < P.length; i++) {
        for (let j = i + 1; j < P.length; j++) {
          const a = P[i], b = P[j];
          const dx = b.x - a.x, dy = b.y - a.y;
          const d = Math.hypot(dx, dy);
          if (d >= R) continue;
          moved = true;
          const ux = d > .01 ? dx / d : 0, uy = d > .01 ? dy / d : (j % 2 ? 1 : -1);
          const o = (R - d) / 2 + .2;
          a.x -= ux * o * .6; b.x += ux * o * .6;
          a.y -= uy * o; b.y += uy * o;
        }
      }
      for (const p of P) {
        p.x = p.up ? Math.min(c0 - 14, Math.max(10, p.x)) : Math.max(c1 + 14, Math.min(W - 10, p.x));
        p.y = Math.min(H - 12, Math.max(TOP, p.y));
      }
      if (!moved) break;
    }
    return P.map((p) => ({ ...p, px: p.x, py: p.y, x: p.x / W, y: p.y / H }));
  }

  function clear(plot) {
    plot?.querySelector(':scope > .lnover')?.remove();
    plot?.querySelector(':scope > .lnshare')?.remove();
    for (const p of plot?.querySelectorAll('.pt[data-lnfocus], .pt.marble-lnlab') || []) {
      p.removeAttribute('data-lnfocus');
      p.classList.remove('marble-lnlab');
    }
    L.P = L.G = null;
  }

  let shown = '';
  function render(plot, D) {
    const W = plot.clientWidth;
    L.tasks = D.stations.flatMap((st, i) => st.tasks.map((t, j) => ({ ...t, st: i, n: `${i + 1}.${j + 1}` })));
    if (!W) return; // the map is hidden; drawn when it shows
    const mine = new Set(discs(ptOf(plot, D.id)));
    L.disc = [...mine].join(', ');
    const [c0, c1] = L.cols(W);
    let over = plot.querySelector(':scope > .lnover');
    if (!over) {
      over = document.createElement('div');
      over.className = 'lnover';
      over.setAttribute('data-marble-transient', '');
      plot.insertBefore(over, plot.firstChild);
    }
    const key = `${D.id}|${W}|${L.disc}|${L.steps?.()}`;
    if (over.dataset.key !== key) {
      over.dataset.key = key;
      over.style.cssText = `--c0:${c0}px;--c1:${c1}px;--cw:${c1 - c0}px;--top:${TOP}px`;
      over.toggleAttribute('data-narrow', W < 560);
      over.innerHTML = (L.disc ? `<span class="lnside up">${esc(L.disc)}</span><span class="lnside down">Other disciplines</span>` : '')
        + `<div class="lncol">${L.col?.(D) || ''}</div>`
        + '<svg class="lnlines" aria-hidden="true"></svg><style data-marble-transient></style><style class="lnla" data-marble-transient></style>';
    }
    // The map grows to hold the whole column, then the places follow its height.
    const style = over.querySelector(':scope > style');
    const G = measure(plot, over);
    const tall = `#kb-map-tools[data-line] ~ .plotwrap .plot:has(> .lnover) { height: max(26rem, 100cqh, ${Math.ceil(G.end + 28)}px); }`;
    if (!style.textContent.startsWith(tall)) style.textContent = tall;
    const H = plot.clientHeight || 600;
    Object.assign(G, { W, H, c0, c1, top: TOP, key: `${key}|${H}` });
    L.G = G;
    const P = places(D, plot, G, mine);
    L.P = new Map(P.map((p) => [p.r.b, p]));
    const q = (b) => `#kb-map-tools[data-line] ~ .plotwrap .plot .pt[data-pick="b:${CSS.escape(b)}"]`;
    const css = [tall, `${q(D.id)} { --x: .5; --y: ${(FOCUS / H).toFixed(4)}; --lnop: 1; --lnpe: auto; }`]
      .concat(P.map((p) => `${q(p.r.b)} { --x: ${p.x.toFixed(4)}; --y: ${p.y.toFixed(4)}; --lnop: 1; --lnpe: auto; }`)).join('\n');
    if (style.textContent !== css) style.textContent = css;

    L.name?.(plot, D, P, W, H, .5, FOCUS / H);

    // Rays: each gathered build shades, in its dot's colour, the run of steps
    // its matched tasks cover (neighbouring steps make one run), reaching the
    // column's edge on its own side.
    const svg = over.querySelector('svg.lnlines');
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    const f = (n) => n.toFixed(1);
    let rays = '';
    for (const p of P) {
      const hits = p.r.hits.slice().sort((a, b) => a[0] - b[0]);
      const ex = p.up ? c0 : c1;
      for (let k = 0, j; k < hits.length; k = j + 1) {
        for (j = k; j + 1 < hits.length && hits[j + 1][0] === hits[j][0] + 1;) j++;
        const a = G.tt[hits[k][0]], z = G.tb[hits[j][0]], pad = Math.min(6, (z - a) * .15);
        rays += `<polygon class="ray" data-b="${esc(p.r.b)}" data-t="${hits.slice(k, j + 1).map((h) => h[0]).join(' ')}" `
          + `points="${f(p.px)},${f(p.py - 1.2)} ${f(p.px)},${f(p.py + 1.2)} ${f(ex)},${f(z - pad)} ${f(ex)},${f(a + pad)}"/>`;
      }
    }
    svg.innerHTML = rays;
    if (shown !== D.id) {
      shown = D.id;
      svg.classList.add('marble-moving');
      setTimeout(() => svg.classList.remove('marble-moving'), 480);
    }
    L.mark?.(L.lit || new Set());
    tint();
  }

  // A ray takes its dot's colour, read once the dot has settled there (a dot
  // coloured by place changes colour as it moves).
  let tinting = 0;
  function tint() {
    clearTimeout(tinting);
    tinting = setTimeout(() => {
      const plot = byId('kb-map-pts');
      const seen = new Map();
      for (const r of plot?.querySelectorAll('.lnover .ray') || []) {
        const b = r.dataset.b;
        if (!seen.has(b)) seen.set(b, getComputedStyle(ptOf(plot, b)?.querySelector('.dot') || plot).backgroundColor);
        r.style.fill = seen.get(b);
      }
    }, 520);
  }

  let seq = 0;
  L.draw = () => {
    const plot = byId('kb-map-pts');
    if (!plot) return;
    const id = L.line();
    if (!id || !plot.querySelector('.pt')) {
      clear(plot);
      L.D = null;
      L.onDraw?.();
      return;
    }
    const n = ++seq;
    L.get(id).then((D) => {
      if (n !== seq || id !== L.line()) return;
      L.missing = D ? '' : id;
      L.D = D;
      if (D) render(plot, D);
      else clear(plot);
      L.onDraw?.();
    });
  };

  let frame = 0;
  const soon = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(L.draw); };
  const watched = new WeakSet();
  function watch() {
    const tools = byId('kb-map-tools');
    const plot = byId('kb-map-pts');
    if (tools && !watched.has(tools)) {
      watched.add(tools);
      new MutationObserver(soon).observe(tools, { attributes: true, attributeFilter: ['data-line', 'data-colour', 'data-lnphases'] });
    }
    if (plot && !watched.has(plot)) {
      watched.add(plot);
      // The dots arrive (or come again with new data): only those changes, not this script's own.
      new MutationObserver((ms) => {
        if (ms.some((m) => [...m.addedNodes, ...m.removedNodes].some((n) => n.nodeType === 1 && n.classList.contains('pt')))) soon();
      }).observe(plot, { childList: true });
      let size = '';
      new ResizeObserver(() => {
        const s = `${plot.clientWidth}x${plot.clientHeight}`;
        if (s !== size && plot.clientWidth) { size = s; if (L.line()) soon(); }
      }).observe(plot);
    }
    soon();
  }
  watch();
  const ready = (m) => m.register?.(watch);
  if (window.marble) ready(window.marble);
  else addEventListener('marble:ready', (e) => ready(e.detail), { once: true });
})();
