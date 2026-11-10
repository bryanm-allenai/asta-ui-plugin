/* Check Runs, part 3 of 4: what the agent did, call by call (the words it
   wrote before each, what it clicked or typed, where on the screen, what came
   back, and the screens it kept, a click marked on the screen it was aimed
   at), the tree it wrote with the screens each node cites, the replay, and a
   viewer for a screen at full size. All of it transient. */
(() => {
  const K = (window.kbCheck = window.kbCheck || {});
  const { byId, esc } = K;
  const VERB = { navigate: 'Opened', click: 'Clicked', double_click: 'Double-clicked', right_click: 'Right-clicked', type: 'Typed', press_key: 'Pressed',
    scroll: 'Scrolled', drag: 'Dragged', select_option: 'Chose', select_text: 'Selected text', hover: 'Pointed at', upload: 'Uploaded', resize: 'Resized the window',
    zoom: 'Zoomed', take_screenshot: 'Took a screenshot', snapshot: 'Read the page', downloads: 'Listed downloads', read_download: 'Read a download',
    list_files: 'Listed the files it may upload', navigate_back: 'Went back', evaluate: 'Ran script', clipboard: 'Used the clipboard', wait_for: 'Waited' };
  const LOOKS = new Set(['take_screenshot', 'snapshot']);
  const AIMED = new Set(['click', 'double_click', 'right_click', 'hover', 'drag', 'select_text']);
  const clock = (s) => (s == null ? '' : `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`);
  const src = (d, rel) => K.file(`${d.base}/${rel}`);

  // A screen, small; with a dot where a click was aimed.
  function shot(d, rel, at, label) {
    if (!rel) return '';
    const dot = at ? `<i class="ckdot" style="left:${(100 * at[0] / at[2]).toFixed(2)}%;top:${(100 * at[1] / at[3]).toFixed(2)}%"></i>` : '';
    return `<button type="button" class="ckshot" data-src="${esc(src(d, rel))}"${at ? ` data-at="${at.join(',')}"` : ''} aria-label="${esc(label || rel)}, larger">` +
      `<span class="ckim"><img loading="lazy" alt="" src="${esc(src(d, rel))}">${dot}</span><span class="ckcap">${esc(label || '')}</span></button>`;
  }

  K.drawSteps = (d, run, which) => {
    const steps = run?.steps || [];
    if (!steps.length) {
      return `<p class="ckp m">${which === 'replay' ? 'No replay was run.' : d.row?.status === 'code'
        ? 'No browser calls: the app would not install or start, so the agent wrote its tree from the code alone.'
        : 'No browser calls were recorded for this run.'}</p>`;
    }
    const byN = new Map(steps.map((s) => [s.n, s]));
    const all = K.st.all;
    const shown = all ? steps : steps.filter((s) => !LOOKS.has(s.tool) || s.said || s.err);
    const rows = shown.map((s) => {
      const before = s.on != null && byN.get(s.on)?.kept;
      const after = s.then != null && byN.get(s.then)?.kept;
      const own = s.kept && (all || s.said) ? shot(d, s.kept, null, `screen ${s.shot}`) : '';
      const shots = (before ? shot(d, before, s.at, `${AIMED.has(s.tool) ? 'aimed at' : 'before'}, screen ${byN.get(s.on).shot}`) : '') + (after ? shot(d, after, null, `after, screen ${byN.get(s.then).shot}`) : '') + own;
      const at = s.at && !s.a ? `at ${s.at[0]}, ${s.at[1]}` : s.at && ['click', 'double_click', 'right_click', 'hover'].includes(s.tool) ? `at ${s.at[0]}, ${s.at[1]}` : '';
      return `<li class="ckstep${s.err ? ' bad' : ''}${LOOKS.has(s.tool) ? ' look' : ''}">` +
        (s.said ? `<p class="cksaid">${esc(s.said)}</p>` : '') +
        `<div class="ckdo"><span class="ckn">${s.n}</span><span class="ckt">${clock(s.s)}</span>` +
        `<span class="ckwhat"><b>${esc(VERB[s.tool] || s.tool)}</b>${s.a ? ` ${esc(s.a)}` : ''}${at ? ` <span class="faint">${at}</span>` : ''}` +
        (s.url && s.tool !== 'navigate' ? ` <span class="ckurl">${esc(s.url)}</span>` : '') + `</span></div>` +
        (s.refused ? s.refused.map((x) => `<p class="ckerr">Refused before it ran: ${esc(x)}</p>`).join('') : '') +
        (s.err ? `<p class="ckerr">${esc(s.err)}</p>` : '') + (s.ev ? `<p class="ckres">Events: ${esc(s.ev)}</p>` : '') +
        (s.res ? `<p class="ckres">${esc(s.res)}</p>` : '') +
        (shots ? `<div class="ckshots">${shots}</div>` : '') + `</li>`;
    }).join('');
    const kept = steps.filter((s) => s.kept).length;
    const taken = steps.filter((s) => s.shot).length;
    return `<div class="ckbar"><p class="ckp m">${steps.length} browser calls over ${clock(steps[steps.length - 1].s)}. It took ${taken} screenshots; the run kept the ${kept} its tree, replay or review cite, so most calls show no screen.</p>` +
      `<label class="ckall"><input type="checkbox" class="ckalls"${all ? ' checked' : ''}> Show screenshots and page reads too</label></div>` +
      `<ol class="cksteps">${rows}</ol>` + (run.closing ? `<section class="cksec"><h4>What it said at the end</h4><p class="cksaid">${esc(run.closing)}</p></section>` : '');
  };

  // ---- the tree it wrote
  const chips = (d, screens) => (screens || []).map((r) => `<button type="button" class="ckchip" data-src="${esc(src(d, r))}">${esc(r.replace(/^.*\/(\d+)\.\w+$/, '$1'))}</button>`).join('');
  const label = (n) => esc(n.label || n.specific || n.general || n.name || '');
  function node(d, n, checks) {
    const kids = (n.children || []).map((c) => node(d, c, checks)).join('');
    if (n.kind === 'action') return `<li class="ckact">${label(n)} ${chips(d, n.screens)}</li>`;
    const c = n.id ? checks[n.id] : null;
    const status = n.check || c?.status;
    const tag = status ? `<span class="ckchk ${status === 'replayed' ? 'hi' : 'mid'}">${esc(status)}</span>` : '';
    return `<li class="cknode k-${esc(n.kind || '')}"><div class="cknh"><span class="ckkind">${esc(n.kind || '')}${n.branch ? ` · ${esc(n.branch)}` : ''}</span>${tag}</div>` +
      `<p class="ckgen">${esc(n.general || n.name || '')}</p>${n.specific && n.specific !== n.general ? `<p class="ckspec">${esc(n.specific)}</p>` : ''}` +
      (n.screens?.length ? `<p class="ckspec">Screens ${chips(d, n.screens)}</p>` : '') +
      (c?.note ? `<p class="ckres">Replay: ${esc(c.note)}</p>` : '') +
      (kids ? `<ol class="ckkids">${kids}</ol>` : '') + `</li>`;
  }
  K.drawTree = (d) => {
    const t = d.tree || {};
    if (!t.tree) return '<p class="ckp m">The agent wrote no tree for this run.</p>';
    const checks = {};
    for (const x of [...(d.check?.tasks || []), ...(d.check?.features || [])]) checks[x.id] = x;
    const feats = (t.features || []).map((f) => `<li class="cknode"><div class="cknh"><span class="ckkind">feature</span>${f.id && checks[f.id] ? `<span class="ckchk ${checks[f.id].status === 'replayed' ? 'hi' : 'mid'}">${esc(checks[f.id].status)}</span>` : ''}</div>` +
      `<p class="ckgen">${esc(f.name || f.general || '')}</p><p class="ckspec">${esc(f.specific || f.general || '')}</p>` +
      (f.steps?.length ? `<ol class="ckul">${f.steps.map((s) => `<li>${esc(s)}</li>`).join('')}</ol>` : '') +
      (f.screens?.length ? `<p class="ckspec">Screens ${chips(d, f.screens)}</p>` : '') + `</li>`).join('');
    const data = t.data ? `<p class="ckp m"><b>Data it used:</b> ${esc(t.data.source || '')}${t.data.note ? `. ${esc(t.data.note)}` : ''}</p>` : '';
    return data + `<ol class="cktree">${node(d, t.tree, checks)}</ol>` +
      (feats ? `<section class="cksec"><h4>Features it named</h4><ol class="cktree">${feats}</ol></section>` : '') +
      (t.not_done?.length ? `<section class="cksec"><h4>What it could not do</h4><ul class="ckul">${t.not_done.map((x) => `<li>${esc(typeof x === 'string' ? x : JSON.stringify(x))}</li>`).join('')}</ul></section>` : '') +
      (t.screens_never_reached?.length ? `<section class="cksec"><h4>Screens it never reached</h4><ul class="ckul">${t.screens_never_reached.map((x) => `<li>${esc(typeof x === 'string' ? x : JSON.stringify(x))}</li>`).join('')}</ul></section>` : '');
  };

  K.drawReplay = (d) => {
    const c = d.check || {};
    const items = [...(c.tasks || []), ...(c.features || [])];
    const head = items.length ? `<section class="cksec"><h4>A second agent redid each task and feature from the tree alone</h4><ul class="ckul">${items.map((x) =>
      `<li><b class="${x.status === 'replayed' ? 'hi' : 'mid'}">${esc(x.id)} ${esc(x.status || '')}</b> ${esc(x.note || '')} ${chips(d, x.screens)}</li>`).join('')}</ul></section>` : '';
    return head + `<section class="cksec"><h4>Its browser calls</h4>${K.drawSteps(d, d.replay, 'replay')}</section>`;
  };

  // ---- a screen at full size
  function viewer() {
    let v = document.querySelector('dialog.ckview');
    if (!v) {
      v = document.createElement('dialog');
      v.className = 'ckview';
      v.setAttribute('data-marble-transient', '');
      v.innerHTML = '<div class="ckvbar"><span class="ckvt"></span><button type="button" class="link ckvx">Close</button></div><div class="ckvim"><img alt=""><i class="ckdot"></i></div>';
      (byId('kb-v-check') || document.body).append(v);
      v.addEventListener('click', (e) => { if (e.target === v || e.target.closest('.ckvx')) v.close(); });
    }
    return v;
  }
  document.addEventListener('click', (e) => {
    const b = e.target.closest('#kb-v-check :is(.ckshot, .ckchip)');
    if (!b) return;
    const v = viewer();
    v.querySelector('img').src = b.dataset.src;
    const dot = v.querySelector('.ckdot');
    const at = b.dataset.at?.split(',').map(Number);
    dot.style.display = at ? 'block' : 'none';
    if (at) { dot.style.left = `${100 * at[0] / at[2]}%`; dot.style.top = `${100 * at[1] / at[3]}%`; }
    v.querySelector('.ckvt').textContent = b.getAttribute('aria-label') || b.textContent;
    if (!v.open) v.showModal();
  });
  document.addEventListener('change', (e) => {
    if (!e.target.matches?.('#kb-v-check .ckalls')) return;
    K.st.all = e.target.checked;
    K.keep();
    K.redrawPart?.();
  });
  K.ready?.();
})();
