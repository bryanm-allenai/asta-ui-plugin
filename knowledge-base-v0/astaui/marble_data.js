/* The knowledge base's own content, read from the files `astaui marble-ops`
   writes beside it (marble_data.py) instead of kept in this page. The page
   holds what people do here; the files hold what the knowledge base says, so
   the page stays small however many builds are filed.

   Each data slot on the page is an empty, data-marble-transient element.
   current.json names the generation to read and which slots each view needs.
   A view's slots are drawn the first time it opens; the inspector's and Agent
   Runs' per-build slots hold only what is picked, read when it is picked.
   Nothing drawn here is filed. When a refresh writes a new generation, an open
   page draws it again the next time it is looked at. */
(() => {
  const DIR = '__DATA_DIR__';
  const file = (rel) => `/drive/file?path=${encodeURIComponent(`${DIR}/${rel}`)}`;
  const byId = (id) => document.querySelector(`[data-marble-id="${id}"]`);
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
  const D = (window.kbData = window.kbData || {});

  let man = null;          // current.json as last read
  const drawn = new Set(); // groups drawn from man.gen
  let pickNow = null;      // the pick the per-pick slots show
  const picks = new Map(); // pick -> Promise of its slots, newest last

  const get = (rel) => fetch(file(rel), { cache: 'no-store' }).then((r) => {
    if (r.status === 404) return null;
    if (!r.ok) throw new Error(`the drive answered ${r.status}`);
    return r.json();
  });

  // The name marble_data.py's pick_file gives a pick's file.
  const pickFile = (pick) => {
    const at = pick.indexOf(':');
    const name = pick.slice(at + 1).replace(/[^A-Za-z0-9-]/g, (c) => `_${c.charCodeAt(0).toString(16)}`);
    return `picks/${pick.slice(0, at)}/${name}.json`;
  };

  const settle = () => {
    dispatchEvent(new Event('resize'));
    document.dispatchEvent(new CustomEvent('kb:data'));
  };

  function fill(map, sids) {
    for (const sid of sids) {
      const el = byId(sid);
      const html = map?.[sid] ?? '';
      if (el && el.innerHTML !== html) el.innerHTML = html;
    }
  }

  function fault(sids, why) {
    const el = sids.map(byId).find(Boolean);
    if (el) el.innerHTML = `<p class="muted small kbd-fault">This part of the console could not be read: ${esc(why)}. Refresh writes it again.</p>`;
  }

  function manifest() {
    return get('current.json').then((m) => {
      if (!m) throw new Error('its files have not been written yet');
      D.err = '';
      return m;
    });
  }

  function group(g) {
    if (!man?.groups[g] || drawn.has(g)) return Promise.resolve();
    drawn.add(g);
    const gen = man.gen;
    const sids = man.groups[g];
    return get(`${gen}/groups/${g}.json`)
      .then((map) => { if (man.gen === gen) { fill(map || {}, sids); settle(); } })
      .catch((e) => { drawn.delete(g); fault(sids, e.message || e); });
  }

  const viewNow = () => byId('kb-lens')?.getAttribute('data-view') || 'home';
  const selNow = () => byId('kb-sel')?.getAttribute('data-sel') || '';

  function forView() {
    if (!man) return;
    const v = viewNow();
    for (const [g, view] of Object.entries(man.views || {})) if (view === v) group(g);
  }

  function slotsOf(pick) {
    const rel = pickFile(pick);
    if (!picks.has(pick)) {
      const p = get(`${man.gen}/${rel}`).catch((e) => { picks.delete(pick); throw e; });
      picks.set(pick, p);
      if (picks.size > 60) picks.delete(picks.keys().next().value);
    }
    return picks.get(pick);
  }

  function forPick() {
    if (!man) return;
    const sel = selNow();
    const need = man.needs?.[sel.split(':')[0]];
    if (need) group(need);
    const pick = /^[bpq]:/.test(sel) ? sel : '';
    if (pick === pickNow) return;
    pickNow = pick;
    const sids = man.picks || [];
    if (!pick) { fill({}, sids); settle(); return; }
    slotsOf(pick)
      .then((map) => { if (pickNow === pick) { fill(map || {}, sids); settle(); } })
      .catch((e) => { if (pickNow === pick) fault(['kb-insp-b'], e.message || e); });
  }

  // Read current.json; when it names a new generation, draw again what was drawn.
  let checking = null;
  function check() {
    if (checking) return checking;
    checking = manifest().then((m) => {
      if (man && m.gen === man.gen) return;
      const again = man ? [...drawn] : ['boot'];
      man = m;
      D.manifest = m;
      drawn.clear();
      picks.clear();
      pickNow = null;
      for (const g of again) group(g);
      group('boot');
      forView();
      forPick();
    }).catch((e) => {
      D.err = String(e.message || e);
      if (!man) fault(['kb-cat-builds'], D.err);
    }).finally(() => { checking = null; });
    return checking;
  }
  D.check = check;

  let watched = null;
  function watch() {
    const lens = byId('kb-lens');
    const sel = byId('kb-sel');
    if (!lens || !sel || watched === lens) return;
    watched = lens;
    new MutationObserver(forView).observe(lens, { attributes: true, attributeFilter: ['data-view'] });
    new MutationObserver(forPick).observe(sel, { attributes: true, attributeFilter: ['data-sel'] });
  }

  watch();
  check();
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') check(); });
  setInterval(() => { if (document.visibilityState === 'visible') check(); }, 120000);
  const ready = (m) => m.register?.(() => { watch(); forView(); forPick(); });
  if (window.marble) ready(window.marble);
  else addEventListener('marble:ready', (e) => ready(e.detail), { once: true });
})();
