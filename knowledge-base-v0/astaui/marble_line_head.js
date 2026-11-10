/* The map's Line up, part 3 of 4: the column and the names. Down the middle
   runs the line build's workflow: each phase's name, where in the interface
   it happens, and under it every step in words, numbered 1.1, 1.2 and so on.
   With Phases chosen on the bar's Lined up row, a phase keeps only its name
   and its steps become marks along the column's edges. Phases is a look,
   data-lnphases on kb-map-tools, filed like the bar's others; with none set
   the steps show. This part also says which gathered builds are named at
   rest. Everything it draws is inside part 1's transient overlay. */
(() => {
  const L = (window.kbLine = window.kbLine || {});
  const byId = (id) => document.querySelector(`[data-marble-id="${id}"]`);
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const tools = () => byId('kb-map-tools');
  L.steps = () => !tools()?.hasAttribute('data-lnphases');

  // One band a phase: its name and place, then its steps.
  L.col = (D) => {
    const steps = L.steps();
    let t = 0;
    return D.stations.map((st, i) => {
      const m = st.tasks.length;
      const rows = st.tasks.map((k, j) => `<li class="lnstep" data-t="${t + j}"${steps ? '' : ` title="${esc(`${i + 1}.${j + 1} ${k.g}`)}"`}>`
        + `<span class="n">${i + 1}.${j + 1}</span><span class="t">${esc(k.g)}</span></li>`).join('');
      t += m;
      return `<div class="lnband" data-i="${i}" style="--m:${m}"><p class="lnhead"><span class="n">${i + 1}</span><span class="t">${esc(st.g)}</span>`
        + `${st.s ? `<span class="w">${esc(st.s)}</span>` : ''}</p><ol class="lnsteps">${rows}</ol></div>`;
    }).join('');
  };

  // Names shown at rest: the line build's, then the closest few whose names
  // would not cover one already shown or the column (a name sits above its
  // dot, running away from the column).
  L.name = (plot, D, P, W, H, fx, fy) => {
    const at = (b) => plot.querySelector(`.pt[data-pick="b:${CSS.escape(b)}"]`);
    const named = new Set([D.id]);
    const G = L.G;
    const boxes = G ? [[G.c0 - 4, G.top - 4, G.c1 + 4, H]] : [];
    const wide = (b) => (at(b)?.querySelector('.lab')?.textContent.length || 10) * 6.4 + 10;
    // Which way a name runs from its dot: away from the column, unless that
    // would run it off the map.
    const way = (p, w) => (p.up ? (p.x * W - w < 2 ? p.x : 1) : (p.x * W + w > W - 2 ? p.x : 0));
    const fits = (p) => {
      const w = wide(p.r.b), la = way(p, w), x = p.x, y = p.y;
      const box = [x * W - w * la, y * H - 30, x * W + w * (1 - la), y * H - 10];
      if (boxes.some((o) => box[0] < o[2] && o[0] < box[2] && box[1] < o[3] && o[1] < box[3])) return false;
      boxes.push(box);
      return true;
    };
    boxes.push([fx * W - 90, fy * H - 30, fx * W + 90, fy * H - 10]);
    for (const p of P.slice().sort((a, b) => b.r.c - a.r.c)) {
      if (named.size > (W < 500 ? 3 : 8)) break;
      if (fits(p)) named.add(p.r.b);
    }
    for (const p of plot.querySelectorAll('.pt')) {
      const b = p.dataset.pick.slice(2);
      p.toggleAttribute('data-lnfocus', b === D.id);
      p.classList.toggle('marble-lnlab', named.has(b));
    }
    const st = plot.querySelector(':scope > .lnover > style.lnla');
    if (!st) return;
    const q = (b) => `#kb-map-tools[data-line] ~ .plotwrap .plot .pt[data-pick="b:${CSS.escape(b)}"]`;
    const css = [`${q(D.id)} { --lnla: .5; }`].concat(P.map((p) => `${q(p.r.b)} { --lnla: ${+way(p, wide(p.r.b)).toFixed(3)}; }`)).join('\n');
    if (st.textContent !== css) st.textContent = css;
  };

  // Steps or Phases, from the bar's Lined up row.
  document.addEventListener('click', (e) => {
    const b = e.target.closest?.('#kb-map-tools [data-ln-mode]');
    const el = tools();
    if (!b || !el) return;
    const value = b.dataset.lnMode === 'phases' ? 'on' : null;
    if ((el.getAttribute('data-lnphases') || null) === value) return;
    if (value) el.setAttribute('data-lnphases', value);
    else el.removeAttribute('data-lnphases');
    window.marble?.op?.({ type: 'setAttr', id: 'kb-map-tools', name: 'data-lnphases', value }, { immediate: true, look: true });
  });
})();
