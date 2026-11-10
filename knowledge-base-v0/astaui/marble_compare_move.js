/* Compare Two, part 3 of 4: what could move between the two builds. A
   feature is a widget and the small workflow around it, and each serves some
   of its build's tasks. Where a task of one build matches a task of the
   other, the features that serve it are what an agent building the first
   kind of tool could take from the second: workflow-to-ui reads them from
   the build's tree.json, with their screens. Features alike in both are a
   pattern that has already travelled. */
(() => {
  const C = (window.kbCompare = window.kbCompare || {});
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

  // How close the two are, in a sentence, for the bar.
  C.summary = (R) => {
    const sa = C.short(R.A.title), sb = C.short(R.B.title);
    const ma = R.matches.length, same = R.matches.filter((m) => m.same).length;
    const at = R.at == null ? null : Math.min(99, Math.max(1, R.at));
    const where = at == null ? '' : at >= 50 ? `closer than ${at}% of pairs of builds` : `less close than ${100 - at}% of pairs of builds`;
    return `<p class="cmsum"><b>${C.two(R.close)}</b> workflow closeness${where ? `, ${where}` : ''}. ` +
      `${ma ? `${C.plural(ma, 'step')} match${ma === 1 ? 'es' : ''} (${same} the same move): ${ma} of ${sa}’s ${R.A.tasks.length}, ${ma} of ${sb}’s ${R.B.tasks.length}.` : 'No step matches.'}</p>`;
  };

  const ref = (d, f) => `kb/builds/${d.id}/tree.json › features › ${f.fid || f.id}`;
  function feature(d, f, extra) {
    const sc = (f.sc || []).slice(0, 3);
    return `<article class="cmfeat"><div class="cmfh"><h5>${esc(f.name)}</h5>${f.check && f.check !== 'replayed' ? `<span class="cmchk">${esc(f.check.replace(/_/g, ' '))}</span>` : ''}</div>` +
      `<p>${esc(f.g)}</p>${extra || ''}` +
      (sc.length ? `<div class="cmthumbs">${sc.map((p) => `<a href="${C.file(p)}" target="_blank" rel="noopener">${C.img(p, f.name)}</a>`).join('')}</div>` : '') +
      (f.steps?.length ? `<details><summary>How a person uses it</summary><ol>${f.steps.map((s) => `<li>${esc(s)}</li>`).join('')}</ol></details>` : '') +
      `<code class="cmref">${esc(ref(d, f))}</code></article>`;
  }
  function serves(R, x, toA) {
    const to = C.short(toA ? R.A.title : R.B.title);
    const steps = x.ms.map((m) => `<li><span class="cmn">${m.k}</span>${esc((toA ? R.A.node[m.a] : R.B.node[m.b])?.g || '')}</li>`).join('');
    const how = x.gap ? `${esc(to)} has no feature for this step.` : `${esc(to)} already does this step with ${x.theirs.map((g) => esc(g.name)).join(' and ')}.`;
    return `<div class="cmfor2"><span class="cmk">${x.gap ? 'Fills a gap' : 'Another way'} · serves ${esc(to)}’s step</span><ul>${steps}</ul><p class="cmhow">${how}</p></div>`;
  }
  function lendList(R, L, from, toA) {
    const to = toA ? R.A : R.B;
    if (!L.out.length) return `<p class="cmquiet">Nothing: ${esc(C.short(from.title))} has no feature for a shared step that ${esc(C.short(to.title))} lacks.</p>`;
    return `<div class="cmfeats">${L.out.map((x) => feature(from, x.f, serves(R, x, toA))).join('')}</div>`;
  }

  C.drawMove = (R) => {
    const sa = esc(C.short(R.A.title)), sb = esc(C.short(R.B.title));
    const offer = (L, from, to) => (L.out.length
      ? `${from} offers ${C.plural(L.out.length, 'feature')} for steps the two share: ${L.gaps} for a step ${to} has no feature for, ${L.out.length - L.gaps} another way to do one it has.`
      : `${from} offers no feature for a shared step that ${to} lacks.`);
    const lead = R.matches.length
      ? `Retrieved for a tool like ${sa}, ${offer(R.bToA, sb, sa)} The other way, ${offer(R.aToB, sa, sb)} ` +
        `${R.both.length ? `${C.plural(R.both.length, 'feature')} ${R.both.length === 1 ? 'is' : 'are'} alike in both: patterns already found in both builds.` : 'No feature is alike in both.'}`
      : `The two workflows share no step, so neither build’s features serve the other’s work. Anything taken across would be a guess.`;
    const both = R.both.length
      ? `<div class="cmboth">${R.both.map((x) => `<div class="cmbrow"><div><h5>${esc(x.a.name)}</h5><p>${esc(x.a.g)}</p></div>` +
          `<div class="cmsim"><b>${C.two(x.s)}</b><span>${x.same ? 'Same' : 'Alike'}</span></div><div><h5>${esc(x.b.name)}</h5><p>${esc(x.b.g)}</p></div></div>`).join('')}</div>`
      : '<p class="cmquiet">None.</p>';
    const beyond = (d, L) => (L.beyond.length
      ? `<li><b>${esc(C.short(d.title))}</b>: ${L.beyond.map((x) => esc(x.f.name)).join(' · ')}</li>` : '');
    const rest = beyond(R.A, R.aToB) + beyond(R.B, R.bToA);
    return `<div class="cmmove"><p class="cmlead">${lead}</p>` +
      `<section class="cmsec"><h4>What ${sb} could lend ${sa}</h4>${lendList(R, R.bToA, R.B, true)}</section>` +
      `<section class="cmsec"><h4>What ${sa} could lend ${sb}</h4>${lendList(R, R.aToB, R.A, false)}</section>` +
      `<section class="cmsec"><h4>Alike in both</h4>${both}</section>` +
      (rest ? `<section class="cmsec"><h4>Features for steps only one has</h4><p class="cmquiet">These serve work the other build does not do, so they would not transfer unless that work is wanted.</p><ul class="cmrest">${rest}</ul></section>` : '') +
      '</div>';
  };
})();
