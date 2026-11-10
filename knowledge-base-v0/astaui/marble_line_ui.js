/* The map's Line up, part 2 of 4: the presses, and what they say. Picking a
   build puts a press by its dot, and one in the inspector, that lines the map
   up by its workflow (part 1 draws it); the side panes fold away. While
   lined up, the bar keeps one row: the build, Steps or Phases, Map settings
   (the bar's other rows) and the way back; a caption says what the picture
   means, and the inspector how a picked build's tasks meet the line's. It
   also darkens a build's shading when it is pointed at or picked. Which build
   is a look, filed like the bar's others; Cluster by puts the map back. */
(() => {
  const L = (window.kbLine = window.kbLine || {});
  L.ui = 2; // which copy the tab runs
  const byId = (id) => document.querySelector(`[data-marble-id="${id}"]`);
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const short = (t) => {
    const s = String(t || '');
    for (const cut of [' — ', ' – ', ' - ', ': ', ' (']) { const i = s.indexOf(cut); if (i >= 3) return s.slice(0, i); }
    return s;
  };
  const title = (b) => short(byId(`kb-pt-${b}`)?.dataset.title || b);
  const picked = () => { const s = byId('kb-sel')?.getAttribute('data-sel') || ''; return s.startsWith('b:') ? s.slice(2) : ''; };
  const line = () => byId('kb-map-tools')?.getAttribute('data-line') || '';
  const mapOpen = () => byId('kb-lens')?.getAttribute('data-view') === 'map';
  const C = () => window.kbCompare;
  const has = (b) => !C()?.rows || C().rows.has(b);
  const made = (tag, cls) => { const el = document.createElement(tag); el.className = cls; el.setAttribute('data-marble-transient', ''); return el; };

  // The look: which build the map is lined up by, or none.
  function set(id) {
    const tools = byId('kb-map-tools');
    const value = id || null;
    if (!tools || (tools.getAttribute('data-line') || null) === value) return;
    if (value === null) tools.removeAttribute('data-line');
    else tools.setAttribute('data-line', value);
    window.marble?.op?.({ type: 'setAttr', id: 'kb-map-tools', name: 'data-line', value }, { immediate: true, look: true });
  }
  let more = false; // the bar's other rows, shown while lined up

  // While lined up: a row on the map's bar naming the build, with the way
  // back, and a caption under the map saying what the picture means.
  function bar() {
    const tools = byId('kb-map-tools');
    const chan = byId('kb-map-chan');
    const id = line();
    let row = tools?.querySelector(':scope > .lngrp');
    let cap = chan?.querySelector(':scope > .lncap');
    if (!tools || !id) { row?.remove(); cap?.remove(); return; }
    if (!row) {
      row = made('div', 'grp lngrp');
      const at = byId('kb-map-g3');
      if (at?.parentElement === tools) at.after(row);
      else tools.prepend(row);
    }
    const D = L.D;
    const steps = L.steps ? L.steps() : true;
    const mode = (k, label, on) => `<button type="button" data-ln-mode="${k}" aria-pressed="${on}">${label}</button>`;
    const rowHtml = `<span class="tl">Lined up by</span><div class="lnnow"><b>${esc(D?.id === id ? short(D.title) : title(id))}</b>`
      + `<div class="seg" aria-label="Show down the column">${mode('steps', 'Steps', steps)}${mode('phases', 'Phases', !steps)}</div>`
      + `<button type="button" class="link lnmore" aria-expanded="${more}">Map settings</button>`
      + '<button type="button" class="link lnback">Back to the map</button></div>';
    if (row.dataset.key !== rowHtml) { row.dataset.key = rowHtml; row.innerHTML = rowHtml; }
    if (!chan) return;
    if (!cap) { cap = made('p', 'cap lncap'); cap.setAttribute('aria-live', 'polite'); chan.prepend(cap); }
    let text;
    if (L.missing === id) text = `${title(id)} has no workflow tree yet, so the map can't be lined up by it.`;
    else if (!D || D.id !== id) text = `Lining up by ${title(id)}’s workflow…`;
    else {
      text = `The ${D.near.length} closest workflows sit level with the steps they match, nearer the middle the closer they are`
        + (L.disc ? `; ${L.disc} on the left, other disciplines on the right` : '') + '. Pick one to see the steps it shares.';
    }
    if (cap.textContent !== text) cap.textContent = text;
  }

  let following = 0;
  function pill() {
    const plot = byId('kb-map-pts');
    const b = picked();
    const pt = plot && b && mapOpen() && b !== line() && has(b) ? plot.querySelector(`.pt[data-pick="b:${CSS.escape(b)}"]`) : null;
    let p = plot?.querySelector(':scope > .lnpill');
    if (!pt) { p?.remove(); return; }
    if (!p) { p = made('button', 'lnpill'); p.type = 'button'; plot.append(p); }
    p.dataset.b = b;
    if (p.textContent !== 'Line up by its workflow') p.textContent = 'Line up by its workflow';
    const until = performance.now() + 700;
    const place = (now) => {
      const half = p.offsetWidth / 2 + 4;
      // While its shared steps show, the press sits under them, not on them.
      const last = plot.querySelector(':scope > .lnshare > .lnsh:last-child');
      const x = last ? last.offsetLeft + last.offsetWidth / 2 : pt.offsetLeft;
      const y = last ? last.offsetTop + last.offsetHeight : pt.offsetTop;
      p.style.left = `${Math.min(plot.clientWidth - half, Math.max(half, x))}px`;
      p.style.top = `${y}px`;
      p.classList.toggle('marble-below', y < 44 || !!line());
      if (now < until) following = requestAnimationFrame(place);
    };
    cancelAnimationFrame(following);
    following = requestAnimationFrame(place);
  }

  function inspector() {
    const box = byId('kb-insp-b');
    const body = byId('kb-insp-body');
    if (!box || !body) return;
    const b = picked();
    const acts = b ? box.querySelector(`[data-for="b:${CSS.escape(b)}"] .acts`) : null;
    let btn = acts?.querySelector('.lnact');
    if (acts && has(b) && !btn) {
      btn = made('button', 'link lnact');
      btn.type = 'button';
      btn.dataset.go = 'map';
      btn.textContent = 'Line up the map by its workflow';
      const at = acts.querySelector('[data-go="map"]');
      if (at) at.after(btn);
      else acts.prepend(btn);
    }
    if (btn) { btn.dataset.b = b; btn.hidden = b === line(); }

    const D = L.D;
    const r = D && line() && b && b !== D.id ? D.near.find((x) => x.b === b) : null;
    let p = body.querySelector(':scope > .lnpanel');
    if (!r) { p?.remove(); return; }
    if (!p) { p = made('section', 'lnpanel'); body.insertBefore(p, box); }
    const tasks = L.tasks || D.stations.flatMap((st, i) => st.tasks.map((t) => ({ ...t, st: i })));
    const name = esc(short(D.title));
    const rank = D.near.indexOf(r) + 1;
    const hits = r.hits.slice().sort((x, y) => x[0] - y[0]);
    const html = `<h3>How it meets ${name}’s workflow</h3>`
      + `<p class="small muted">${rank === 1 ? 'The closest workflow' : `Number ${rank} by how close its workflow is`}, of ${D.n}. `
      + (hits.length ? `${hits.length} of its tasks match steps of ${name}’s.` : `None of its tasks is close enough to one of ${name}’s to count as a match, so it sits where its nearest ones fall.`) + '</p>'
      + (hits.length ? `<ol>${hits.map(([ti, v, theirs]) => {
        const t = tasks[ti] || {};
        return `<li><span class="st">${t.n ? `Step ${t.n}` : `Phase ${(t.st ?? 0) + 1}`} · ${v >= D.same ? 'the same move' : 'alike'}</span><span class="mine">${esc(t.g)}</span><span class="theirs">Its task: ${esc(theirs)}</span></li>`;
      }).join('')}</ol>` : '')
      + (C()?.st ? `<button type="button" class="link lncompare" data-go="compare" data-a="${esc(D.id)}" data-b="${esc(b)}">Compare the two side by side</button>` : '');
    if (p.dataset.key !== html) { p.dataset.key = html; p.innerHTML = html; }
  }

  // Rays and tasks lit: every ray of the builds in `ids`, or onto the tasks in `tasks`.
  L.mark = (ids, tasks) => {
    L.lit = ids;
    const over = byId('kb-map-pts')?.querySelector(':scope > .lnover');
    if (!over) return;
    const on = new Set(tasks || []);
    let any = false;
    for (const r of over.querySelectorAll('svg.lnlines .ray')) {
      const ts = r.dataset.t.split(' ').map(Number);
      const lit = ids.has(r.dataset.b) || ts.some((t) => tasks?.has(t));
      r.classList.toggle('marble-on', lit);
      if (lit) { any = true; if (!tasks) ts.forEach((t) => on.add(t)); }
    }
    over.querySelector('svg.lnlines')?.classList.toggle('marble-lit', any);
    for (const t of over.querySelectorAll('.lntick, .lnstep')) t.classList.toggle('marble-on', on.has(+t.dataset.t));
  };

  function sync() {
    bar();
    pill();
    inspector();
    L.mark?.(new Set([picked()]));
    L.share?.();
  }
  L.onDraw = sync;

  document.addEventListener('click', (e) => {
    const t = e.target.closest?.('.lnpill, .lnact, .lnback, .lnmore, .lncompare, #kb-map-tools button[data-by], #kb-map-tools [data-set="channel"], #kb-map-tools [data-set="cards"]');
    if (!t) return;
    // The inspector's two carry data-go, so the page's own press opens the lens (and, on a phone, shows it).
    if (t.matches('.lnpill, .lnact')) { set(t.dataset.b || picked()); return; }
    if (t.matches('.lnback')) { set(null); return; }
    if (t.matches('.lnmore')) { more = !more; bar(); return; }
    if (t.matches('.lncompare')) {
      const c = C();
      Object.assign(c.st, { a: t.dataset.a, b: t.dataset.b, focus: null, arm: '' });
      c.keep?.();
      if (byId('kb-lens')?.getAttribute('data-view') === 'compare') c.compare?.();
      return;
    }
    if (line()) set(null);
  });
  // Pointing at a build lights its matches; pointing at a phase lights every match of its tasks.
  const hover = (e) => {
    if (!L.D) return;
    const ids = new Set([picked()]);
    const pt = e.type !== 'pointerout' && e.target.closest?.('#kb-map-pts .pt');
    if (pt) ids.add(pt.dataset.pick.slice(2));
    const band = e.type !== 'pointerout' && e.target.closest?.('#kb-map-pts .lnband');
    const tick = e.type !== 'pointerout' && e.target.closest?.('#kb-map-pts :is(.lntick, .lnstep)');
    let tasks = null;
    if (tick) tasks = new Set([+tick.dataset.t]);
    else if (band) tasks = new Set((L.tasks || []).map((t, i) => (t.st === +band.dataset.i ? i : -1)).filter((i) => i >= 0));
    L.mark?.(ids, tasks);
  };
  for (const type of ['pointerover', 'pointerout', 'focusin']) document.addEventListener(type, hover);

  const watched = new WeakSet();
  function watch() {
    for (const [id, opts] of [['kb-sel', { attributes: true, attributeFilter: ['data-sel'] }], ['kb-lens', { attributes: true, attributeFilter: ['data-view'] }],
      ['kb-map-tools', { attributes: true, attributeFilter: ['data-line', 'data-lnphases'] }], ['kb-insp-b', { childList: true }]]) {
      const el = byId(id);
      if (el && !watched.has(el)) { watched.add(el); new MutationObserver(() => requestAnimationFrame(sync)).observe(el, opts); }
    }
    C()?.load?.().then(sync);
    sync();
  }
  watch();
  const ready = (m) => m.register?.(watch);
  if (window.marble) ready(window.marble);
  else addEventListener('marble:ready', (e) => ready(e.detail), { once: true });
})();
