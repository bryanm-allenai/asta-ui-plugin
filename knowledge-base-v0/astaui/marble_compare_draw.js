/* Compare Two, part 2 of 4: the two builds side by side. Each column is a
   build's screen and the tree an agent wrote of its workflow; a line joins
   each pair of matched tasks, solid for the same move and dashed for alike.
   Picking a task puts its screens at the top and both steps, with the
   features that serve them, at the foot. Everything here is transient. */
(() => {
  const C = (window.kbCompare = window.kbCompare || {});
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const two = (s) => (s == null ? '–' : s.toFixed(2));
  const plural = (n, one, many) => `${n} ${n === 1 ? one : many || `${one}s`}`;
  C.two = two;
  C.plural = plural;

  const img = (path, alt) => (path ? `<img src="${C.file(path)}" alt="${esc(alt)}" loading="lazy" decoding="async">` : '<span class="cmnoshot">No screenshot</span>');
  C.img = img;

  // The task picked, on either side, and what goes with it.
  C.focused = (R) => {
    const f = C.st.focus;
    if (!f || !R) return null;
    const d = f.side === 'a' ? R.A : R.B;
    const n = d.node[f.id];
    if (!n) return null;
    const m = (f.side === 'a' ? R.ofA : R.ofB).get(f.id) || null;
    return { side: f.side, n, m };
  };

  function head(d, side, R) {
    const F = C.focused(R);
    let id = null;
    if (F) id = F.side === side ? F.n.id : F.m ? (side === 'a' ? F.m.a : F.m.b) : null;
    const n = id ? d.node[id] : null;
    const sc = n?.sc?.length ? n.sc : null;
    const cap = sc ? `The screen for ${n.k === 'task' ? 'this step' : 'this part'}${sc.length > 1 ? ` (1 of ${sc.length})` : ''}` : 'The interface';
    const pic = sc ? img(sc[0], `${d.title}: ${n.g}`) : img(d.shot, d.title);
    const href = sc ? sc[0] : d.shot;
    return `<figure class="cmshot" data-side="${side}">` +
      `<a class="cmimg" ${href ? `href="${C.file(href)}" target="_blank" rel="noopener"` : ''}>${pic}</a>` +
      `<figcaption><span class="cmwho">${side === 'a' ? 'First' : 'Second'}</span><b>${esc(d.title)}</b>` +
      `<span class="cmfield">${esc(d.field)}</span><span class="cmcap">${esc(cap)}</span></figcaption>` +
      `<p class="cmfor">${esc(d.for)}</p></figure>`;
  }

  function actions(n) {
    const acts = (n.kids || []).filter((k) => k.k === 'action');
    return acts.length ? `<span class="cmacts">${plural(acts.length, 'action')}</span>` : '';
  }
  function task(n, side, R, depth) {
    const m = (side === 'a' ? R.ofA : R.ofB).get(n.id);
    const F = C.st.focus;
    const cur = F && ((F.side === side && F.id === n.id) || (m && C.focused(R)?.m === m));
    const kids = (n.kids || []).filter((k) => k.k !== 'action').map((k) => node(k, side, R, depth + 1)).join('');
    return `<button type="button" class="cmtask${m ? (m.same ? ' same' : ' alike') : ' lone'}" data-side="${side}" data-id="${n.id}"${m ? ` data-m="${m.k}"` : ''} aria-current="${!!cur}">` +
      `<span class="cmn">${m ? m.k : ''}</span><span class="cmtg">${esc(n.g)}</span>` +
      `<span class="cmts">${esc(n.s)}</span>${actions(n)}</button>${kids ? `<div class="cmsub">${kids}</div>` : ''}`;
  }
  function node(n, side, R, depth) {
    if (n.k === 'task') return task(n, side, R, depth);
    if (n.k === 'action') return '';
    const o = side === 'a' ? R.B : R.A;
    const other = R.phaseOf.get(side === 'a' ? n.id : `b:${n.id}`);
    const with_ = other ? `<span class="cmpm">Goes with ${esc(o.node[other]?.g || '')}</span>` : '';
    const kids = (n.kids || []).map((k) => node(k, side, R, depth + 1)).join('');
    if (n.k === 'goal') return `<div class="cmgoal"><span class="cmk">Goal</span><p>${esc(n.g)}</p></div>${kids}`;
    return `<section class="cmph${other ? ' paired' : ''}"><h5><span class="cmk">Phase</span>${esc(n.g)}</h5>${with_}${kids}</section>`;
  }

  // The lines between matched tasks, drawn over the gap between the columns.
  C.lines = () => {
    const box = document.querySelector('#kb-cm-stage .cmtrees');
    const svg = box?.querySelector(':scope > svg.cmlines');
    if (!box || !svg) return;
    const at = box.getBoundingClientRect();
    const top = box.scrollTop;
    svg.setAttribute('height', String(box.scrollHeight));
    svg.style.height = `${box.scrollHeight}px`;
    const F = C.focused(C.R);
    const out = [];
    for (const m of C.R?.matches || []) {
      const ra = box.querySelector(`.cmtask[data-side="a"][data-id="${m.a}"]`), rb = box.querySelector(`.cmtask[data-side="b"][data-id="${m.b}"]`);
      if (!ra || !rb || !ra.offsetParent || !rb.offsetParent) continue;
      const pa = ra.getBoundingClientRect(), pb = rb.getBoundingClientRect();
      const x1 = pa.right - at.left, y1 = pa.top - at.top + top + Math.min(pa.height / 2, 14);
      const x2 = pb.left - at.left, y2 = pb.top - at.top + top + Math.min(pb.height / 2, 14);
      const mid = (x1 + x2) / 2;
      const on = F && F.m === m;
      out.push(`<path class="${m.same ? 'same' : 'alike'}${on ? ' on' : F ? ' off' : ''}" d="M${x1.toFixed(1)} ${y1.toFixed(1)} C${mid.toFixed(1)} ${y1.toFixed(1)} ${mid.toFixed(1)} ${y2.toFixed(1)} ${x2.toFixed(1)} ${y2.toFixed(1)}"/>`);
    }
    svg.innerHTML = out.join('');
  };

  function feats(d, id) {
    const fs = d.feats.filter((f) => f.tasks.includes(id));
    return fs.length ? `<p class="cmfs"><span class="cmk">Features for it</span>${fs.map((f) => esc(f.name)).join(' · ')}</p>` : '';
  }
  function side(d, n) {
    const acts = (n.kids || []).filter((k) => k.k === 'action').slice(0, 5);
    return `<div class="cmone"><b>${esc(n.g)}</b><p class="cmts">${esc(n.s)}</p>` +
      (acts.length ? `<ul>${acts.map((a) => `<li>${esc(a.t)}</li>`).join('')}</ul>` : '') + feats(d, n.id) + '</div>';
  }
  function closest(R, F) {
    const from = F.side === 'a' ? R.A : R.B, to = F.side === 'a' ? R.B : R.A;
    const v = from.vec[F.n.id];
    let best = null, s = -2;
    for (const t of to.tasks) { const x = to.vec[t.id] ? C.dot(v, to.vec[t.id]) : -2; if (x > s) { s = x; best = t; } }
    return best ? { n: best, s } : null;
  }
  function foot(R) {
    const F = C.focused(R);
    if (!F) return `<div class="cmfoot quiet"><p>Pick a step in either tree to read both sides of a match and the features that serve them. Numbers pair the matched steps; a solid line is the same move, a dashed one alike.</p></div>`;
    if (F.m) {
      const a = R.A.node[F.m.a], b = R.B.node[F.m.b];
      return `<div class="cmfoot"><div class="cmpair">${side(R.A, a)}<div class="cmsim"><span class="cmn">${F.m.k}</span>` +
        `<b>${two(F.m.s)}</b><span>${F.m.same ? 'Same move' : 'Alike'}</span></div>${side(R.B, b)}</div></div>`;
    }
    const c = closest(R, F);
    const other = F.side === 'a' ? R.B : R.A;
    return `<div class="cmfoot"><div class="cmpair lone">${F.side === 'a' ? side(R.A, F.n) : ''}<div class="cmsim"><b>${c ? two(c.s) : '–'}</b><span>No match</span></div>` +
      `${F.side === 'b' ? side(R.B, F.n) : ''}</div><p class="cmnear">${esc(C.short(other.title))} has no step this close. Its closest is ${c ? `“${esc(c.n.g)}”` : 'none'}, below the ${two(C.index.task.alike)} a match needs.</p></div>`;
  }

  C.drawTrees = (R) =>
    `<div class="cmheads">${head(R.A, 'a', R)}<span></span>${head(R.B, 'b', R)}</div>` +
    `<div class="cmtrees"><svg class="cmlines" aria-hidden="true"></svg><div class="cmcol" data-side="a">${node(R.A.tree, 'a', R, 0)}</div>` +
    `<span class="cmgap"></span><div class="cmcol" data-side="b">${node(R.B.tree, 'b', R, 0)}</div></div>${foot(R)}`;
})();
