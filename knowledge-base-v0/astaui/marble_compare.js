/* Compare Two, part 1 of 3: the two builds and how their workflows line up.
   `python3 -m astaui.compare` writes, beside the console's other data, every
   build's tree and features with a vector for each goal, phase, task and
   feature, and the thresholds the knowledge base sets for a match. Any two
   builds are lined up here, in the page: each task's closest task in the other
   tree, one to one, strongest first, kept when it clears the threshold. Nothing
   here is filed; which two are open is kept for the tab only. */
(() => {
  const C = (window.kbCompare = window.kbCompare || {});
  const byId = (id) => document.querySelector(`[data-marble-id="${id}"]`);
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  C.byId = byId;
  C.esc = esc;
  C.DIR = 'Ai2/AstaUI/knowledge-base-v0/console-data/compare';
  C.file = (path) => `/drive/file?path=${encodeURIComponent(path)}`;
  C.short = (t) => {
    const s = String(t || '');
    for (const cut of [' — ', ' – ', ' - ', ': ', ' (']) {
      const i = s.indexOf(cut);
      if (i >= 3) return s.slice(0, i);
    }
    return s;
  };

  const saved = (() => { try { return JSON.parse(sessionStorage.getItem('kbCompare') || '{}'); } catch { return {}; } })();
  C.st = Object.assign({ a: '', b: '', part: 'tree', focus: -1, arm: '' }, saved);
  C.keep = () => { try { sessionStorage.setItem('kbCompare', JSON.stringify({ a: C.st.a, b: C.st.b, part: C.st.part })); } catch { /* a tab without storage forgets */ } };

  let loading = null;
  C.load = (force) => {
    if (loading) return loading;
    if (C.index && !force) return Promise.resolve(C.index);
    loading = fetch(C.file(`${C.DIR}/index.json`), { cache: 'no-store' })
      .then((r) => { if (!r.ok) throw new Error(`the drive answered ${r.status}`); return r.json(); })
      .then((j) => { C.index = j; C.err = ''; C.rows = new Map(j.builds.map((r) => [r.id, r])); return j; })
      .catch((e) => { C.err = String(e.message || e); return C.index; })
      .finally(() => { loading = null; });
    return loading;
  };

  const vec = (b64) => {
    const bin = atob(b64);
    const v = new Float32Array(bin.length);
    for (let i = 0; i < bin.length; i++) { const x = bin.charCodeAt(i); v[i] = (x > 127 ? x - 256 : x) / 127; }
    return v;
  };
  const dot = (u, v) => { let s = 0; for (let i = 0; i < u.length; i++) s += u[i] * v[i]; return s; };
  C.dot = dot;

  // One build: its tree with each task's phase, its features, its vectors.
  const builds = new Map();
  C.build = (id) => {
    if (builds.has(id)) return builds.get(id);
    const name = String(id).replace(/[^A-Za-z0-9-]/g, (c) => `_${c.charCodeAt(0).toString(16)}`);
    const p = fetch(C.file(`${C.DIR}/b/${name}.json`), { cache: 'no-store' })
      .then((r) => { if (!r.ok) throw new Error(`the drive answered ${r.status}`); return r.json(); })
      .then((d) => {
        d.vec = {};
        for (const [k, s] of Object.entries(d.v || {})) d.vec[k] = vec(s);
        d.tasks = [];
        d.phases = [];
        d.node = {};
        const walk = (n, phase) => {
          if (n.id) d.node[n.id] = n;
          if (n.k === 'phase') d.phases.push(n);
          if (n.k === 'task') { n.phase = phase; d.tasks.push(n); }
          for (const c of n.kids || []) walk(c, n.k === 'phase' ? n.id : phase);
        };
        walk(d.tree, '');
        for (const f of d.feats || []) f.tasks = f.tasks || [];
        return d;
      });
    p.catch(() => builds.delete(id));
    builds.set(id, p);
    return p;
  };
  C.forget = () => builds.clear();

  // Strongest first, one to one, above a floor.
  function greedy(xs, ys, floor) {
    const all = [];
    for (let i = 0; i < xs.length; i++) for (let j = 0; j < ys.length; j++) {
      if (!xs[i].v || !ys[j].v) continue;
      const s = dot(xs[i].v, ys[j].v);
      if (s >= floor) all.push([s, i, j]);
    }
    all.sort((p, q) => q[0] - p[0]);
    const ui = new Set(), uj = new Set(), out = [];
    for (const [s, i, j] of all) {
      if (ui.has(i) || uj.has(j)) continue;
      ui.add(i); uj.add(j);
      out.push({ i, j, s });
    }
    return out;
  }
  // For each row, its best in the other: how much of a workflow the other covers.
  function best(xs, ys) {
    if (!xs.length || !ys.length) return 0;
    let t = 0;
    for (const x of xs) { let m = -1; for (const y of ys) m = Math.max(m, dot(x, y)); t += m; }
    return t / xs.length;
  }
  C.where = (s) => {
    const q = C.index?.quantiles || [];
    if (!q.length) return null;
    let k = 0;
    while (k < q.length - 1 && q[k + 1] <= s) k++;
    return k;
  };

  C.align = (A, B) => {
    const th = C.index.task, fth = C.index.feat;
    const ta = A.tasks.map((n) => ({ n, v: A.vec[n.id] })), tb = B.tasks.map((n) => ({ n, v: B.vec[n.id] }));
    const order = new Map(A.tasks.map((n, i) => [n.id, i]));
    const matches = greedy(ta, tb, th.alike)
      .map((m) => ({ a: ta[m.i].n.id, b: tb[m.j].n.id, s: m.s, same: m.s >= th.same }))
      .sort((p, q) => order.get(p.a) - order.get(q.a));
    matches.forEach((m, k) => { m.k = k + 1; });
    const ofA = new Map(matches.map((m) => [m.a, m])), ofB = new Map(matches.map((m) => [m.b, m]));

    // Phases: two phases go together when tasks of one match tasks of the other.
    const phase = [];
    for (const pa of A.phases) for (const pb of B.phases) {
      const n = matches.filter((m) => A.node[m.a].phase === pa.id && B.node[m.b].phase === pb.id).length;
      const s = A.vec[pa.id] && B.vec[pb.id] ? dot(A.vec[pa.id], B.vec[pb.id]) : 0;
      if (n || s >= th.same) phase.push({ a: pa.id, b: pb.id, n, s });
    }
    phase.sort((p, q) => q.n - p.n || q.s - p.s);
    const pu = new Set(), phaseOf = new Map();
    for (const p of phase) {
      if (pu.has(p.a) || pu.has(`b:${p.b}`)) continue;
      pu.add(p.a); pu.add(`b:${p.b}`);
      phaseOf.set(p.a, p.b); phaseOf.set(`b:${p.b}`, p.a);
    }

    // Features: those alike in both, then what each could lend the other.
    const fa = A.feats.map((f) => ({ f, v: A.vec[f.id] })), fb = B.feats.map((f) => ({ f, v: B.vec[f.id] }));
    const both = greedy(fa, fb, fth.alike).map((m) => ({ a: fa[m.i].f, b: fb[m.j].f, s: m.s, same: m.s >= fth.same }));
    const inBothA = new Set(both.map((x) => x.a.id)), inBothB = new Set(both.map((x) => x.b.id));
    // A feature lends to the other build when it serves a step they share and
    // nothing alike is in both. It fills a gap when the other build has no
    // feature for that step, and is another way to do it when it has one.
    const lend = (from, to, have, of, toA) => {
      const out = [], beyond = [];
      for (const f of from.feats) {
        if (have.has(f.id)) continue;
        const ms = f.tasks.map((t) => of.get(t)).filter(Boolean);
        if (!ms.length) { beyond.push({ f, ms }); continue; }
        const theirs = to.feats.filter((g) => ms.some((m) => g.tasks.includes(toA ? m.a : m.b)));
        out.push({ f, ms, theirs, gap: !theirs.length });
      }
      out.sort((p, q) => q.gap - p.gap || Math.max(...q.ms.map((m) => m.s)) - Math.max(...p.ms.map((m) => m.s)));
      return { out, beyond, gaps: out.filter((x) => x.gap).length };
    };
    const bToA = lend(B, A, inBothB, ofB, true), aToB = lend(A, B, inBothA, ofA, false);

    const va = ta.map((x) => x.v).filter(Boolean), vb = tb.map((x) => x.v).filter(Boolean);
    const close = (best(va, vb) + best(vb, va)) / 2;
    const goal = A.vec.g && B.vec.g ? dot(A.vec.g, B.vec.g) : null;
    return { A, B, matches, ofA, ofB, phaseOf, both, bToA, aToB, close, at: C.where(close), goal };
  };

  C.ready = () => { if (C.draw && C.start) C.start(); };
  C.ready();
})();
