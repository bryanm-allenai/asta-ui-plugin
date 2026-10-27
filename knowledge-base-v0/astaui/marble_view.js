// AstaUI console: what the page shows, derived.
//
// Everything here follows from attributes already in the file (what is picked,
// what the builds are filtered by, which lens and list are open, the rows waiting
// in the queue) and none of it is filed: classes named marble-…, attributes the
// page declared its own, and panels and drawings marked transient. Picking one
// thing marks it in every view: its row in the list, its point and neighbours on
// the map, its row and column in the grid, its column of words, its column in a
// workflow family, and its card in the inspector. It runs again whenever one of
// those attributes changes, and after Marble lands an edit.
(() => {
  const byId = (id) => document.querySelector(`[data-marble-id="${id}"]`);
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const SVG = 'http://www.w3.org/2000/svg';
  const mark = (el, cls, on) => { if (el && el.classList.contains(cls) !== on) el.classList.toggle(cls, on); };
  const split = (s, at) => { const i = (s || '').indexOf(at); return i < 0 ? [s || '', ''] : [s.slice(0, i), s.slice(i + 1)]; };
  const plural = (n, one, many) => `${n} ${n === 1 ? one : many || `${one}s`}`;
  const WORD = {
    'data-shapes': 'data shape', 'task-verbs': 'task', 'stage-terms': 'stage', 'mechanism-views': 'view',
    'mechanism-interactions': 'interaction', 'mechanism-patterns': 'pattern', 'field-disciplines': 'discipline',
  };
  const FACT = { f: 'workflow family', d: 'discipline', k: 'source', c: 'consent', s: 'data shape', t: 'task', g: 'stage', p: 'pattern' };
  const title = (b) => byId(`kb-pt-${b}`)?.dataset.title || b;

  // A panel the script builds: transient, so it never reaches the file.
  function panel(host, before, cls) {
    let p = host.querySelector(`:scope > .${cls}`);
    if (!p) {
      p = document.createElement('div');
      p.className = `${cls} marble-panel`;
      p.setAttribute('data-marble-transient', '');
      p.setAttribute('aria-live', 'polite');
      host.insertBefore(p, before);
    }
    return p;
  }
  const unpanel = (host, cls) => host?.querySelector(`:scope > .${cls}`)?.remove();
  function say(host, cls, text) {
    let s = host.querySelector(`:scope > .${cls}`);
    if (!s) {
      s = document.createElement('span');
      s.className = cls;
      s.setAttribute('data-marble-transient', '');
      host.insertBefore(s, host.firstChild);
    }
    if (s.textContent !== text) s.textContent = text;
  }

  // ---- what is waiting in the queue, by what it is about
  function waiting() {
    const terms = new Map();
    const pairs = new Map();
    let n = 0;
    for (const li of byId('kb-queue')?.children ?? []) {
      if (li.hasAttribute('data-dropped')) continue;
      n += 1;
      const d = li.dataset;
      if (d.term) terms.set(`t:${d.facet}-${d.list}:${d.term}`, (terms.get(`t:${d.facet}-${d.list}:${d.term}`) || 0) + 1);
      if (d.a && d.b) {
        const k = `p:${[d.a, d.b].sort().join('|')}`;
        pairs.set(k, (pairs.get(k) || 0) + 1);
      }
    }
    return { n, terms, pairs };
  }

  // ---- pressed states, for whoever cannot see them
  function pressed() {
    for (const b of document.querySelectorAll('button[data-set]')) {
      const tools = b.dataset.toolsId ? byId(b.dataset.toolsId) : b.closest('[data-tools]');
      if (!tools) continue;
      const now = tools.getAttribute(`data-${b.dataset.set}`);
      const on = b.hasAttribute('data-toggle') ? now === b.dataset.to : now === null ? b.hasAttribute('data-default') : now === b.dataset.to;
      if (b.getAttribute('aria-pressed') !== String(on)) b.setAttribute('aria-pressed', String(on));
    }
  }

  // ---- the filter: which builds are in, said once in words
  function filtering() {
    const f = byId('kb-filter-btn')?.getAttribute('data-filter') || '';
    const inSet = (tags) => !f || (tags || '').includes(`|${f}|`);
    for (const item of document.querySelectorAll('#kb-cat-builds .item')) mark(item, 'marble-out', !inSet(item.dataset.tags));
    const ins = new Set();
    for (const p of document.querySelectorAll('.pt')) {
      const on = inSet(p.dataset.tags);
      mark(p, 'marble-out', !on);
      if (on) ins.add(p.dataset.pick.slice(2));
    }
    for (const r of document.querySelectorAll('#kb-mx-grid .mrow:not(.mhead)')) mark(r, 'marble-out', !!f && !ins.has(r.dataset.b));
    for (const b of document.querySelectorAll('[data-filter]')) if (b.dataset.filter) mark(b, 'marble-on', b.dataset.filter === f);
    const [k, v] = split(f, ':');
    const now = byId('kb-fnow');
    const line = byId('kb-filterline');
    const total = document.querySelectorAll('.pt').length;
    if (now) say(now, 'fsay', f ? `Showing the ${plural(ins.size, 'build')} of ${total} whose ${FACT[k] || k} is ${v}.` : `Every build is shown. Pick a value to show only the builds that have it.`);
    if (line) {
      if (f) {
        const p = panel(line, null, 'fl');
        const html = `<span>Showing the ${plural(ins.size, 'build')} of ${total} whose ${esc(FACT[k] || k)} is <b>${esc(v)}</b>.</span><button type="button" class="link" data-filter="">Show every build</button>`;
        if (p.innerHTML !== html) p.innerHTML = html;
      } else unpanel(line, 'fl');
    }
    return ins;
  }

  // ---- the one selection, in every view
  let drawing = 0;
  function selection(w) {
    const sel = byId('kb-sel')?.getAttribute('data-sel') || '';
    const [kind, rest] = split(sel, ':');
    for (const el of document.querySelectorAll('[data-pick]')) {
      const on = el.dataset.pick === sel;
      mark(el, 'marble-on', on);
      if (el.classList.contains('pt') || el.classList.contains('rq')) el.setAttribute('aria-pressed', String(on));
    }
    for (const el of document.querySelectorAll('[data-for]')) mark(el, 'marble-on', el.dataset.for === sel);

    // Which builds the picked thing is about.
    let builds = [];
    if (kind === 'b') builds = [rest];
    if (kind === 'p') builds = rest.split('|');
    let withWord = new Set();
    let wordRow = null;
    if (kind === 't') {
      const [list, term] = split(rest, ':');
      wordRow = [...document.querySelectorAll(`.tlist[data-l="${CSS.escape(list)}"] .trow:not(.tcols)`)].find((r) => r.dataset.t === term) || null;
      const cols = (byId(`kb-tc-${list}`)?.dataset.bs || '').split(' ');
      const dots = wordRow ? [...wordRow.querySelectorAll('.cells i')] : [];
      withWord = new Set(cols.filter((b, i) => dots[i]?.classList.contains('y')));
    }
    for (const r of document.querySelectorAll('.trow:not(.tcols)')) {
      mark(r, 'marble-sel', r === wordRow);
      mark(r, 'marble-pending', w.terms.has(`t:${r.closest('.tlist')?.dataset.l}:${r.dataset.t}`));
    }
    for (const c of document.querySelectorAll('#kb-mx-grid button.cell')) mark(c, 'marble-pending', w.pairs.has(c.dataset.pick));

    // The grid: the picked build's row and column, or the picked pair's two.
    const hl = new Set(kind === 't' ? withWord : builds);
    for (const r of document.querySelectorAll('#kb-mx-grid .rh')) mark(r, 'marble-hl', hl.has(r.dataset.pick?.slice(2)));
    for (const c of document.querySelectorAll('#kb-mx-grid .ch')) mark(c, 'marble-hl', hl.has(c.id.slice(5)));
    // Coverage: the picked build's column of words.
    for (const tl of document.querySelectorAll('.tlist')) {
      const cols = (byId(`kb-tc-${tl.dataset.l}`)?.dataset.bs || '').split(' ');
      const at = kind === 'b' ? cols.indexOf(rest) : -1;
      for (const r of tl.querySelectorAll('.trow:not(.tcols)')) {
        r.querySelectorAll('.cells i').forEach((d, i) => mark(d, 'marble-col', i === at));
      }
    }
    // Workflows: the picked builds' columns.
    for (const c of document.querySelectorAll('table.align [data-b]')) mark(c, 'marble-col', builds.includes(c.dataset.b));

    // The map: the picked build and its neighbours under this representation; a
    // request and what it should find; a pair and the line between; a word and
    // every build that has it.
    const tools = byId('kb-map-tools');
    const plot = byId('kb-map-pts');
    if (!tools || !plot) return;
    const ch = tools.getAttribute('data-channel') || 'c';
    const pts = [...plot.querySelectorAll('.pt')];
    const at = (b) => pts.find((p) => p.dataset.pick === `b:${b}`);
    let from = null;
    let ends = [];
    const near = new Set(withWord);
    if (kind === 'b' && at(rest)) {
      from = at(rest);
      ends = (from.getAttribute(`data-n${ch}`) || '').split(' ').filter(Boolean).map((j) => [j, false]);
    } else if (kind === 'q') {
      from = plot.querySelector(`.rq[data-pick="${CSS.escape(sel)}"]`);
      if (from) {
        const want = (from.dataset.want || '').split(' ').filter(Boolean);
        const n = from.getAttribute(`data-n${ch}`);
        ends = want.map((j) => [j, true]);
        if (n && !want.includes(n)) ends.push([n, false]);
      }
    } else if (kind === 'p' && at(builds[0]) && at(builds[1])) {
      from = at(builds[0]);
      ends = [[builds[1], false]];
    }
    for (const [j] of ends) near.add(j);
    for (const p of pts) mark(p, 'marble-near', near.has(p.dataset.pick.slice(2)) && p !== from);
    let svg = plot.querySelector(':scope > svg.lines');
    if (!from || !ends.length) { svg?.remove(); return; }
    if (!svg) {
      svg = document.createElementNS(SVG, 'svg');
      svg.setAttribute('class', 'lines');
      svg.setAttribute('data-marble-transient', '');
      svg.setAttribute('aria-hidden', 'true');
      plot.insertBefore(svg, plot.firstChild);
    }
    const until = performance.now() + 700;
    const frame = (now) => {
      const xy = (el) => [el.offsetLeft, el.offsetTop];
      const [x1, y1] = xy(from);
      svg.innerHTML = ends.map(([j, dashed]) => {
        const p = at(j);
        if (!p) return '';
        const [x2, y2] = xy(p);
        return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"${dashed ? ' class="want"' : ''}/>`;
      }).join('');
      if (now < until) drawing = requestAnimationFrame(frame);
    };
    cancelAnimationFrame(drawing);
    drawing = requestAnimationFrame(frame);
  }

  // ---- the inspector's panels for a word and for a pair, built from what the page holds
  function inspector(w) {
    const body = byId('kb-insp-body');
    if (!body) return;
    const sel = byId('kb-sel')?.getAttribute('data-sel') || '';
    const [kind, rest] = split(sel, ':');
    if (kind === 't') wordPanel(body, rest, w);
    else unpanel(body, 'tpanel');
    if (kind === 'p') pairPanel(body, rest, w);
    else unpanel(body, 'ppanel');
  }

  function wordPanel(body, rest, w) {
    const [list, term] = split(rest, ':');
    const [facet, lst] = split(list, '-');
    const row = [...document.querySelectorAll(`.tlist[data-l="${CSS.escape(list)}"] .trow:not(.tcols)`)].find((r) => r.dataset.t === term);
    if (!row) return unpanel(body, 'tpanel');
    const cols = (byId(`kb-tc-${list}`)?.dataset.bs || '').split(' ');
    const dots = [...row.querySelectorAll('.cells i')];
    const have = cols.filter((b, i) => dots[i]?.classList.contains('y'));
    const lack = cols.filter((b) => b && !have.includes(b));
    const st = row.dataset.st;
    const means = st === 'proposed' ? '' : row.querySelector('.tn small')?.textContent || '';
    const also = (row.dataset.also || '').split('|').filter(Boolean);
    const what = WORD[list] || 'word';
    const others = [...document.querySelectorAll(`.tlist[data-l="${CSS.escape(list)}"] .trow:not(.tcols)`)]
      .filter((r) => r !== row && r.dataset.st !== 'proposed').map((r) => r.dataset.t);
    const q = (action, label, extra = '', cls = 'run outline') => `<button type="button" class="${cls}" data-queue="${action}" data-facet="${esc(facet)}" data-list="${esc(lst)}" data-term="${esc(term)}"${extra}>${label}</button>`;
    const status = st === 'proposed' ? `Proposed by ${plural(have.length, 'card')}; the list lacks it.`
      : st === 'unused' ? 'In the list; no build uses it yet.' : `In the list; ${plural(have.length, 'build')} use it.`;
    const merge = `<details><summary>${st === 'proposed' ? 'Merge it into a word the list has' : 'Merge it into another word'}</summary><div class="opts">`
      + others.map((o) => `<button type="button" class="opt" data-queue="merge-term" data-facet="${esc(facet)}" data-list="${esc(lst)}" data-term="${esc(term)}" data-pre-into="${esc(o)}">${esc(o)}</button>`).join('')
      + '</div></details>';
    const acts = st === 'proposed'
      ? q('add-term', 'Add it to the list')
      : q('rename-term', 'Rename') + q('add-word', 'Add another word for it') + q('set-meaning', 'Edit the meaning', ` data-pre-means="${esc(means)}"`)
        + (st === 'unused' ? q('retire-term', 'Retire') : '');
    const n = w.terms.get(`t:${rest}`);
    const html = `<header class="ih"><h2>${esc(term)}</h2><p class="meta">${esc(what[0].toUpperCase() + what.slice(1))} · ${status}</p></header>`
      + `<p>${means ? esc(means) : '<span class="faint">No meaning written yet.</span>'}</p>`
      + `<p class="small muted">${also.length ? `Also counts: ${esc(also.join(', '))}.` : 'No other word counts as it yet.'}</p>`
      + `<div class="tacts">${acts}</div>${merge}`
      + (n ? `<p class="small muted">${plural(n, 'change')} to this word ${n === 1 ? 'is' : 'are'} waiting below.</p>` : '')
      + `<h3>Builds with it</h3>`
      + (have.length ? `<ul>${have.map((b) => `<li><button type="button" class="nb" data-pick="b:${esc(b)}">${esc(title(b))}</button>${q('untag', 'Take it off', ` data-build="${esc(b)}"`, 'link')}</li>`).join('')}</ul>` : '<p class="faint small">None.</p>')
      + (lack.length ? `<details><summary>Give it to another build</summary><ul>${lack.map((b) => `<li><span>${esc(title(b))}</span>${q('tag', 'Give it', ` data-build="${esc(b)}"`, 'link')}</li>`).join('')}</ul></details>` : '');
    const p = panel(body, body.querySelector(':scope > .empty')?.nextSibling || null, 'tpanel');
    const key = `${rest}|${n || 0}`;
    if (p.dataset.key !== key) {
      p.dataset.key = key;
      p.innerHTML = html;
    }
  }

  function pairPanel(body, rest, w) {
    const [x, y] = rest.split('|');
    const cell = document.querySelector(`#kb-mx-grid .cell[data-pick="p:${CSS.escape(rest)}"]`);
    const rows = [];
    const ch = byId('kb-mx-tools')?.getAttribute('data-channel') || 'w';
    if (cell) {
      const values = getComputedStyle(cell);
      for (const lg of byId('kb-mx-legend')?.children ?? []) {
        const k = lg.dataset.k;
        const v = values.getPropertyValue(`--v${k}`).trim();
        if (!v) continue;
        const raw = Number(lg.dataset.lo) + Number(v) * (Number(lg.dataset.hi) - Number(lg.dataset.lo));
        const label = lg.querySelector('span')?.textContent.split(':')[0] || k;
        rows.push(`<span class="bl${k === ch ? ' on' : ''}">${esc(label)}</span><span class="bt"><i style="--v:${Math.max(0, Math.min(1, raw)).toFixed(3)}"></i></span><span class="num">${raw.toFixed(2)}</span>`);
      }
    }
    const j = cell?.dataset.j;
    const said = j ? `Judged ${j === 'same' ? 'the same' : j}${cell.dataset.jn ? `: ${esc(cell.dataset.jn)}` : '.'}` : 'Not judged by eye yet.';
    const n = w.pairs.get(`p:${rest}`);
    const judge = (to, label) => `<button type="button" class="run outline" data-queue="judge" data-a="${esc(x)}" data-b="${esc(y)}" data-judgment="${to}">${label}</button>`;
    const html = `<header class="ih"><h2>${esc(title(x))} and ${esc(title(y))}</h2><p class="meta">Two builds, compared</p></header>`
      + `<div class="acts"><button type="button" class="link" data-pick="b:${esc(x)}">${esc(title(x))}</button><button type="button" class="link" data-pick="b:${esc(y)}">${esc(title(y))}</button></div>`
      + (rows.length ? `<h3>How alike, by each representation</h3><div class="bars8">${rows.join('')}</div><p class="faint small">1 would be the same text.</p>` : '')
      + `<h3>By eye</h3><p class="small">${said}</p>`
      + `<div class="judge">${judge('same', 'The same')}${judge('related', 'Related')}${judge('different', 'Different')}`
      + (j ? `<button type="button" class="run outline" data-queue="unjudge" data-a="${esc(x)}" data-b="${esc(y)}">Take it back</button>` : '') + '</div>'
      + (n ? `<p class="small muted">${plural(n, 'change')} to this pair ${n === 1 ? 'is' : 'are'} waiting below.</p>` : '');
    const p = panel(body, byId('kb-insp-b'), 'ppanel');
    const key = `${rest}|${ch}|${n || 0}`;
    if (p.dataset.key !== key) {
      p.dataset.key = key;
      p.innerHTML = html;
    }
  }

  // ---- the lens menu says which lens is open; the tray says how many changes wait
  function counts(w) {
    const bar = byId('kb-tray-bar');
    if (bar) say(bar, 'count', w.n ? `${plural(w.n, 'change')} waiting` : 'No changes waiting');
  }

  // ---- the grid has one keyboard stop: the picked cell, or the first
  function stops() {
    const cells = [...document.querySelectorAll('#kb-mx-grid button.cell')];
    const on = cells.find((c) => c.classList.contains('marble-on')) || cells[0];
    for (const c of cells) {
      const t = c === on ? '0' : '-1';
      if (c.getAttribute('tabindex') !== t) c.setAttribute('tabindex', t);
    }
  }

  function derive() {
    const w = waiting();
    pressed();
    filtering();
    selection(w);
    inspector(w);
    counts(w);
    stops();
  }

  let soon = 0;
  const schedule = () => { if (!soon) soon = requestAnimationFrame(() => { soon = 0; derive(); }); };
  const watcher = new MutationObserver(schedule);
  function watch() {
    watcher.disconnect();
    for (const el of [byId('kb-sel'), byId('kb-filter-btn'), byId('kb-tray-bar'), ...document.querySelectorAll('[data-tools]')]) {
      if (el) watcher.observe(el, { attributes: true, attributeFilter: ['data-sel', 'data-filter', 'data-open', 'data-view', 'data-cat', 'data-list', 'data-channel', 'data-colour', 'data-req', 'data-common', 'data-pane', 'data-part', 'data-fam', 'data-consent'] });
    }
    const q = byId('kb-queue');
    if (q) watcher.observe(q, { childList: true, subtree: true, attributes: true, attributeFilter: ['data-dropped'] });
    for (const id of ['kb-map-pts', 'kb-mx-grid', 'kb-cat-builds', 'kb-insp-b', 'kb-mx-legend']) {
      const el = byId(id);
      if (el) watcher.observe(el, { childList: true });
    }
  }
  watch();
  derive();
  addEventListener('resize', schedule);
  const ready = (m) => m.register(() => { watch(); schedule(); });
  if (window.marble) ready(window.marble);
  else addEventListener('marble:ready', (e) => ready(e.detail), { once: true });
})();
