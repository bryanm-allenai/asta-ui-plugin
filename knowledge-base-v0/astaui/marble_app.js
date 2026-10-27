// AstaUI console: what a press does.
//
// Looking is not changing. Which lens is open, what is picked, what the builds
// are filtered by, how the map is placed: each is one attribute on one small
// element, set here and filed as a look, so the owner's page opens where they
// left it and a visitor's looking stays in their tab. A missing attribute means
// the default, so the page reads right before anything is set.
//
// One selection holds across the page. Anything with a data-pick attribute
// (a row in the list, a point on the map, a cell in the grid, a name in the
// inspector) picks the object it names, and every view follows. Back walks the
// picks made in this tab.
//
// Changing is a queued change. A press that would change the knowledge base adds
// a row to the changes under the inspector, filed as an insert, with an inverse so
// Mod+Z takes it back. Nothing reaches the knowledge base until Apply runs them.
// A row is never removed here: dropping it marks it, and Apply clears it.
(() => {
  const M = () => window.marble;
  const byId = (id) => document.querySelector(`[data-marble-id="${id}"]`);
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  // One pane at a time below 46rem, as the stylesheet's container query says.
  const narrow = () => document.documentElement.clientWidth <= 46 * 16;

  // ---- looks
  function look(el, name, value) {
    if (!el) return;
    const v = value === null || value === undefined || value === '' ? null : String(value);
    if (el.getAttribute(name) === v) return;
    if (v === null) el.removeAttribute(name);
    else el.setAttribute(name, v);
    const m = M();
    const id = m?.id(el);
    if (id) m.op({ type: 'setAttr', id, name, value: v }, { immediate: true, look: true });
  }

  function go(view, to) {
    look(byId('kb-lens'), 'data-view', view === 'home' ? null : view);
    if (narrow()) look(byId('kb-thumb'), 'data-pane', null);
    const target = to && byId(to);
    if (target) requestAnimationFrame(() => target.scrollIntoView({ behavior: 'smooth', block: 'start' }));
    else byId('kb-lens-body')?.scrollTo({ top: 0 });
  }

  // ---- the one selection, and the way back through it
  const history = [];
  const selEl = () => byId('kb-sel');
  function showBack() {
    const back = byId('kb-back');
    if (back && back.classList.contains('marble-hasback') !== history.length > 0) back.classList.toggle('marble-hasback', history.length > 0);
  }
  function pick(next) {
    const now = selEl()?.getAttribute('data-sel') || null;
    if (now === (next || null)) return;
    if (now && next) history.push(now);
    if (!next) history.length = 0;
    look(selEl(), 'data-sel', next);
    showBack();
  }
  function back() {
    const prev = history.pop() || null;
    look(selEl(), 'data-sel', prev);
    showBack();
  }

  // ---- popovers: a menu stays by its button, and one is open at a time
  function closePops(except) {
    for (const w of document.querySelectorAll('.popwrap.marble-open')) if (w !== except) w.classList.remove('marble-open');
  }
  function togglePop(wrap) {
    const open = !wrap.classList.contains('marble-open');
    closePops(wrap);
    wrap.classList.toggle('marble-open', open);
    const btn = wrap.querySelector(':scope > button');
    if (btn) btn.setAttribute('aria-expanded', String(open));
  }

  // ---- Find: every build, word, request, pair and view, by name
  let finder = null;
  function entries() {
    const out = [];
    const kindOf = { b: 'Build', t: 'Word', q: 'Test request', p: 'Two builds' };
    const seen = new Set();
    for (const r of document.querySelectorAll('.list .row[data-pick]')) {
      const p = r.dataset.pick;
      if (seen.has(p)) continue;
      seen.add(p);
      const list = r.closest('.wlist')?.dataset.l;
      const listName = list ? document.querySelector(`.wpick [data-to="${list}"]`)?.textContent : '';
      out.push({ pick: p, kind: listName ? `Word · ${listName}` : kindOf[p[0]] || '', title: r.querySelector('.t')?.textContent || p, meta: r.querySelector('.m')?.textContent || '' });
    }
    for (const b of document.querySelectorAll('#kb-lens [data-set="view"]')) out.push({ view: b.dataset.to, kind: 'View', title: b.textContent, meta: '' });
    return out;
  }
  function openFinder() {
    if (finder) return finder.input.focus();
    const all = entries();
    const backdrop = document.createElement('div');
    backdrop.className = 'finder-back';
    backdrop.setAttribute('data-marble-transient', '');
    const box = document.createElement('div');
    box.className = 'finder';
    box.setAttribute('data-marble-transient', '');
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-label', 'Find');
    box.innerHTML = '<input type="search" placeholder="Find a build, a word, a test request or a view" aria-label="Find" enterkeyhint="go" autocomplete="off" spellcheck="false"><ol role="listbox"></ol>';
    document.body.append(backdrop, box);
    const input = box.querySelector('input');
    const list = box.querySelector('ol');
    let shown = [];
    let at = 0;
    const draw = () => {
      const words = input.value.toLowerCase().split(/\s+/).filter(Boolean);
      shown = all.filter((e) => words.every((w) => `${e.title} ${e.meta} ${e.kind}`.toLowerCase().includes(w))).slice(0, 12);
      at = Math.min(at, Math.max(0, shown.length - 1));
      list.innerHTML = shown.length
        ? shown.map((e, n) => `<li role="option" data-n="${n}" aria-selected="${n === at}"><span class="fk">${esc(e.kind)}</span><span class="ft">${esc(e.title)}</span>${e.meta ? `<span class="fm">${esc(e.meta)}</span>` : ''}</li>`).join('')
        : '<p class="none">Nothing by that name.</p>';
    };
    const choose = (e) => {
      closeFinder();
      if (!e) return;
      if (e.view) return go(e.view);
      pick(e.pick);
      revealIn(e.pick);
    };
    input.addEventListener('input', () => { at = 0; draw(); });
    input.addEventListener('keydown', (ev) => {
      if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
        ev.preventDefault();
        at = (at + (ev.key === 'ArrowDown' ? 1 : shown.length - 1)) % Math.max(1, shown.length);
        draw();
        list.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: 'nearest' });
      } else if (ev.key === 'Enter') {
        ev.preventDefault();
        choose(shown[at]);
      } else if (ev.key === 'Escape') {
        ev.preventDefault();
        closeFinder();
      }
    });
    list.addEventListener('pointerdown', (ev) => {
      const li = ev.target.closest('li[data-n]');
      if (li) { ev.preventDefault(); choose(shown[Number(li.dataset.n)]); }
    });
    backdrop.addEventListener('pointerdown', () => closeFinder());
    finder = { box, backdrop, input, opener: document.activeElement };
    draw();
    input.focus();
  }
  function closeFinder() {
    if (!finder) return;
    const { box, backdrop, opener } = finder;
    finder = null;
    box.remove();
    backdrop.remove();
    if (opener?.focus) opener.focus();
  }

  // Make what was found visible in the list beside it: its kind of list, and its row.
  function revealIn(sel) {
    const cat = byId('kb-cat');
    const kind = { b: 'builds', t: 'words', q: 'reqs', p: 'pairs' }[sel[0]];
    if (kind) look(cat, 'data-cat', kind === 'builds' ? null : kind);
    if (sel[0] === 't') {
      const list = sel.slice(2).split(':')[0];
      look(cat, 'data-list', list === 'data-shapes' ? null : list);
    }
    requestAnimationFrame(() => document.querySelector(`.list .row[data-pick="${CSS.escape(sel)}"]`)?.scrollIntoView({ block: 'nearest' }));
  }

  // ---- the queue
  const WORD = {
    'data-shapes': 'data shape', 'task-verbs': 'task', 'stage-terms': 'stage', 'mechanism-views': 'view',
    'mechanism-interactions': 'interaction', 'mechanism-patterns': 'pattern', 'field-disciplines': 'discipline',
  };
  const WHY = ['because', 'Why', 'a reason, for the ontology’s change log'];
  const titleOf = (b) => byId(`kb-pt-${b}`)?.dataset.title || b;
  const word = (f) => WORD[`${f.facet}-${f.list}`] || 'word';
  const TERM = ['facet', 'list', 'term'];
  const ACTIONS = {
    'add-term': { fixed: TERM, what: (f, b) => `Add the ${word(f)} ${b(f.term)} to the list`, args: [['means', 'Meaning', 'what the word means, in a sentence'], WHY] },
    'rename-term': { fixed: TERM, what: (f, b) => `Rename the ${word(f)} ${b(f.term)}`, args: [['to', 'New name', 'the word to use instead'], WHY] },
    'merge-term': { fixed: TERM, what: (f, b) => `Merge the ${word(f)} ${b(f.term)} into another`, args: [['into', 'Into', 'the word it should count as'], WHY] },
    'add-word': { fixed: TERM, what: (f, b) => `Let another word count as the ${word(f)} ${b(f.term)}`, args: [['word', 'Word', 'a word that means the same'], WHY] },
    'set-meaning': { fixed: TERM, what: (f, b) => `Say what the ${word(f)} ${b(f.term)} means`, args: [['means', 'Meaning', 'what the word means, in a sentence'], WHY] },
    'retire-term': { fixed: TERM, what: (f, b) => `Retire the ${word(f)} ${b(f.term)}`, args: [WHY] },
    tag: { fixed: ['build', ...TERM], what: (f, b) => `Give ${b(titleOf(f.build))} the ${word(f)} ${b(f.term)}`, args: [] },
    untag: { fixed: ['build', ...TERM], what: (f, b) => `Take the ${word(f)} ${b(f.term)} off ${b(titleOf(f.build))}`, args: [] },
    judge: { fixed: ['a', 'b', 'judgment'], what: (f, b) => `Judge ${b(titleOf(f.a))} and ${b(titleOf(f.b))} ${f.judgment === 'same' ? 'the same' : f.judgment}`, args: [['note', 'Note', 'what makes them alike, or not']] },
    unjudge: { fixed: ['a', 'b'], what: (f, b) => `Take back the judgment on ${b(titleOf(f.a))} and ${b(titleOf(f.b))}`, args: [] },
    'set-weight': { fixed: ['facet'], what: (f, b) => `Change how much ${b(f.facet)} counts in search`, args: [['weight', 'Weight', 'a number from 0 to 1'], WHY] },
  };

  const openTray = () => look(byId('kb-tray-bar'), 'data-open', 'yes');

  function focusRow(li) {
    if (!li) return;
    const args = [...li.querySelectorAll('.arg')];
    const field = args.find((a) => !a.textContent.trim()) || args[0];
    requestAnimationFrame(() => {
      li.scrollIntoView({ block: 'nearest' });
      if (!field) return;
      field.focus();
      const range = document.createRange();
      range.selectNodeContents(field);
      range.collapse(false);
      const s = getSelection();
      s.removeAllRanges();
      s.addRange(range);
    });
  }

  function queue(t) {
    const m = M();
    const spec = ACTIONS[t.dataset.queue];
    const q = byId('kb-queue');
    if (!m || !spec || !q) return;
    const f = {};
    for (const k of spec.fixed) f[k] = t.dataset[k] ?? '';
    // The same change already waiting is shown, not added twice.
    const same = [...q.children].find((li) => !li.hasAttribute('data-dropped') && li.dataset.action === t.dataset.queue
      && spec.fixed.every((k) => (li.dataset[k] ?? '') === f[k]));
    if (same) {
      openTray();
      focusRow(same);
      return;
    }
    const id = m.newId();
    const b = (s) => `<b data-marble-id="${m.newId()}">${esc(s)}</b>`;
    const pre = (name) => t.dataset[`pre${name[0].toUpperCase()}${name.slice(1)}`] ?? '';
    const fixed = spec.fixed.map((k) => ` data-${k}="${esc(f[k])}"`).join('');
    const args = spec.args.map(([name, label, ph]) => `<span class="af" data-marble-id="${m.newId()}"><span class="al" data-marble-id="${m.newId()}">${esc(label)}</span>`
      + `<span class="arg" data-marble-id="${m.newId()}" data-arg="${name}" data-marble-editable="write" data-ph="${esc(ph)}">${esc(pre(name))}</span></span>`).join('');
    const html = `<li class="chg" data-marble-id="${id}" data-action="${esc(t.dataset.queue)}"${fixed}>`
      + `<span class="what" data-marble-id="${m.newId()}">${spec.what(f, b)}</span>${args}`
      + `<span class="problem" data-marble-id="${m.newId()}"></span>`
      + `<button type="button" class="drop" data-marble-id="${m.newId()}">Drop</button>`
      + `<button type="button" class="back" data-marble-id="${m.newId()}">Bring back</button></li>`;
    const op = { type: 'insert', parentId: 'kb-queue', beforeId: null, html };
    m.apply(op);
    m.op(op, { immediate: true });
    // Undo takes the change out of the queue by dropping it; redo brings it back.
    m.record({ redo: [{ type: 'setAttr', id, name: 'data-dropped', value: null }], undo: [{ type: 'setAttr', id, name: 'data-dropped', value: '' }] });
    openTray();
    // A merge picked from the list of words needs no typing, so the reason is what waits.
    focusRow(byId(id));
  }

  function drop(li, on) {
    const m = M();
    const id = m?.id(li);
    if (!id) return;
    if (on) li.setAttribute('data-dropped', '');
    else li.removeAttribute('data-dropped');
    const op = { type: 'setAttr', id, name: 'data-dropped', value: on ? '' : null };
    m.op(op, { immediate: true });
    m.record({ redo: [op], undo: [{ type: 'setAttr', id, name: 'data-dropped', value: on ? null : '' }] });
  }

  function clearNote() {
    const m = M();
    const note = byId('kb-apply-note');
    if (!m || !note) return;
    const prior = note.textContent;
    note.textContent = '';
    const op = { type: 'setText', id: 'kb-apply-note', text: '' };
    m.op(op, { immediate: true });
    m.record({ redo: [op], undo: [{ type: 'setText', id: 'kb-apply-note', text: prior }] });
  }

  // ---- presses
  document.addEventListener('click', (e) => {
    const t = e.target.closest('button');
    if (!e.target.closest('.popwrap')) closePops();
    if (!t) {
      if (e.target.closest('.plot')) pick(null);
      return;
    }
    const d = t.dataset;
    if (t.id === 'kb-lens-btn' || t.id === 'kb-filter-btn') return togglePop(t.closest('.popwrap'));
    if (t.id === 'kb-find') return openFinder();
    if (t.id === 'kb-back') return back();
    if (t.id === 'kb-close') return pick(null);
    if (t.id === 'kb-tray-toggle') {
      const bar = byId('kb-tray-bar');
      return look(bar, 'data-open', bar.hasAttribute('data-open') ? null : 'yes');
    }
    if (t.id === 'kb-note-done') return clearNote();
    if (d.set) {
      const tools = d.toolsId ? byId(d.toolsId) : t.closest('[data-tools]');
      const name = `data-${d.set}`;
      if (d.set === 'view') { closePops(); return go(d.to); }
      if (t.hasAttribute('data-toggle')) return look(tools, name, tools.getAttribute(name) === d.to ? null : d.to);
      return look(tools, name, t.hasAttribute('data-default') ? null : d.to);
    }
    if (d.queue) return queue(t);
    if (t.classList.contains('drop')) return drop(t.closest('.chg'), true);
    if (t.classList.contains('back') && t.closest('.chg')) return drop(t.closest('.chg'), false);
    if ('filter' in d) {
      // In a legend or the filter menu a second press lets the filter go.
      const fb = byId('kb-filter-btn');
      const again = d.filter && fb.getAttribute('data-filter') === d.filter && !t.classList.contains('bar');
      look(fb, 'data-filter', again ? null : d.filter);
      closePops();
    }
    if (d.catTo) {
      look(byId('kb-cat'), 'data-cat', d.catTo === 'builds' ? null : d.catTo);
      if (narrow()) look(byId('kb-thumb'), 'data-pane', 'list');
    }
    if (d.pick) pick(d.pick);
    if (d.go || d.goTo) go(d.go || byId('kb-lens').getAttribute('data-view') || 'home', d.goTo);
  });

  // The list filters as you type; what is typed is the tab's own, not the page's.
  document.addEventListener('input', (e) => {
    if (e.target.id !== 'kb-cat-q') return;
    const words = e.target.value.toLowerCase().split(/\s+/).filter(Boolean);
    for (const item of document.querySelectorAll('.list .item')) {
      const hit = words.every((w) => item.textContent.toLowerCase().includes(w));
      if (item.classList.contains('marble-hide') === hit) item.classList.toggle('marble-hide', !hit);
    }
  });

  // ---- keys: Find, Escape, and arrows along the list, the grid and the switches.
  document.addEventListener('keydown', (e) => {
    const typing = e.target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName);
    if ((e.key === 'k' || e.key === 'K') && (e.metaKey || e.ctrlKey) && !e.altKey) {
      e.preventDefault();
      return openFinder();
    }
    if (typing) return;
    if (e.key === '/') {
      e.preventDefault();
      return openFinder();
    }
    if (e.key === 'Escape') {
      if (document.querySelector('.popwrap.marble-open')) { e.preventDefault(); return closePops(); }
      if (selEl()?.hasAttribute('data-sel')) { e.preventDefault(); return pick(null); }
      return;
    }
    if (!/^Arrow(Left|Right|Up|Down)$/.test(e.key)) return;
    const t = e.target;
    const row = t.closest?.('.list .row');
    if (row && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
      const rows = [...row.closest('.list').querySelectorAll('.item:not(.marble-hide) .row')].filter((r) => r.offsetParent);
      const next = rows[rows.indexOf(row) + (e.key === 'ArrowDown' ? 1 : -1)];
      if (next) {
        e.preventDefault();
        next.focus();
        pick(next.dataset.pick);
      }
      return;
    }
    const seg = t.closest?.('.seg, .wpick, .chips, .thumb');
    if (seg && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) {
      const buttons = [...seg.querySelectorAll('button')];
      const next = buttons[(buttons.indexOf(t) + (e.key === 'ArrowRight' ? 1 : buttons.length - 1)) % buttons.length];
      e.preventDefault();
      next.focus();
      next.click();
      return;
    }
    if (t.classList?.contains('cell')) {
      // The diagonal keeps the grid square; it is not a stop for the keyboard.
      const rows = [...byId('kb-mx-grid').querySelectorAll('.mrow:not(.mhead)')];
      const cells = (r) => [...r.querySelectorAll('.cell')];
      let r = rows.indexOf(t.closest('.mrow'));
      let c = cells(rows[r]).indexOf(t);
      const [dr, dc] = { ArrowLeft: [0, -1], ArrowRight: [0, 1], ArrowUp: [-1, 0], ArrowDown: [1, 0] }[e.key];
      do { r += dr; c += dc; } while (rows[r] && cells(rows[r])[c]?.classList.contains('self'));
      const target = rows[r] && cells(rows[r])[c];
      if (target) {
        e.preventDefault();
        target.focus();
      }
    }
  });

  // The key that opens Find, said the way this machine says it.
  const findBtn = byId('kb-find');
  if (findBtn && !findBtn.querySelector('kbd') && matchMedia('(hover: hover)').matches) {
    const k = document.createElement('kbd');
    k.setAttribute('data-marble-transient', '');
    k.textContent = /Mac|iPhone|iPad/.test(navigator.platform) ? '⌘K' : 'Ctrl K';
    findBtn.append(k);
  }

  // Pressed states, open menus and keyboard stops are the page's own, never filed.
  const ready = (m) => m.pageOnly('aria-pressed', 'aria-expanded', 'tabindex');
  if (window.marble) ready(window.marble);
  else addEventListener('marble:ready', (e) => ready(e.detail), { once: true });
})();
