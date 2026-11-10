/* AstaUI walkthrough player.
 *
 * Shows a step-by-step walkthrough of an interface on top of it, from a
 * walkthrough written for that interface (see ../walkthrough.md):
 *
 *   <script type="application/json" id="astaui-walkthrough">{...}</script>
 *   <script src="astaui-walkthrough.js"></script>
 *
 * The walkthrough is the work in order: its goal, the phases it moves through,
 * and in each phase the steps a person takes, each pinned to one control of
 * the interface. The player rings that control, dims the rest a little, and
 * puts a short card beside it. It draws in a layer of its own (a shadow root),
 * so it never changes the interface's layout or styles, and the person can
 * keep using the interface while it is open.
 *
 * The same file serves every interface, so walkthroughs look and work alike
 * whichever way the interface was built.
 */
(() => {
  if (window.__astauiWalkthrough) return;
  window.__astauiWalkthrough = true;

  const read = () => {
    if (window.ASTAUI_WALKTHROUGH) return window.ASTAUI_WALKTHROUGH;
    const el = document.getElementById('astaui-walkthrough');
    if (!el) return null;
    try { return JSON.parse(el.textContent); } catch (e) { console.warn('astaui walkthrough: not JSON', e); return null; }
  };

  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* storage refused: fine */ } },
  };

  const CSS = `
:host { all: initial; }
* { box-sizing: border-box; }
.layer { position: fixed; inset: 0; pointer-events: none; z-index: 2147483000;
  font: 14px/1.45 Manrope, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; color: var(--ink);
  /* Asta's palette: dark teal on white in light, cream on dark teal in dark. */
  --ink: #0a3235; --soft: #3f7274; --line: #0326294d; --paper: #ffffff; --wash: #0326291a;
  --act: #0fcb8c; --act-ink: #0a3235; --ring: #105257; --halo: #ffffff; --dim: #03262966; }
@media (prefers-color-scheme: dark) {
  .layer { --ink: #faf2e9; --soft: #faf2e999; --line: #faf2e933; --paper: #0a3235; --wash: #faf2e91a;
    --act: #0fcb8c; --act-ink: #0a3235; --ring: #faf2e9; --halo: #032629; --dim: #03262999; }
}
button { font: inherit; color: inherit; cursor: pointer; }
.launch { position: fixed; left: 14px; bottom: 14px; pointer-events: auto; display: inline-flex; align-items: center;
  gap: 6px; height: 32px; padding: 0 12px 0 10px; border-radius: 4px; border: 1px solid var(--line);
  background: var(--paper); font-size: 13px; font-weight: 600; }
.launch:hover { background: color-mix(in srgb, var(--paper), var(--ink) 7%); }
.launch svg { width: 14px; height: 14px; fill: none; stroke: currentColor; stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round; }
.launch[hidden] { display: none; }
.ring { position: fixed; border-radius: 10px; pointer-events: none; outline: 2px solid var(--ring);
  box-shadow: 0 0 0 4px var(--halo), 0 0 0 100vmax var(--dim); transition: all .22s cubic-bezier(.2,.8,.2,1); }
.ring[hidden] { display: none; }
.card { position: fixed; width: min(340px, calc(100vw - 24px)); pointer-events: auto; background: var(--paper);
  border: 1px solid var(--line); border-radius: 12px; padding: 14px 16px 12px;
  transition: left .22s cubic-bezier(.2,.8,.2,1), top .22s cubic-bezier(.2,.8,.2,1); }
.card[hidden] { display: none; }
.card:focus { outline: none; }
.phases { display: flex; gap: 4px; margin: 0 26px 10px 0; }
.phases span { flex: 1; height: 4px; border-radius: 2px; background: var(--line); }
.phases span[data-on] { background: var(--ink); }
.phases span[data-done] { background: var(--soft); opacity: .55; }
.eyebrow { font-size: 12px; color: var(--soft); margin: 0 0 2px; }
h2 { font-size: 16px; line-height: 1.3; margin: 0 0 6px; font-weight: 650; }
p { margin: 0 0 8px; }
.do { display: flex; gap: 8px; align-items: baseline; background: var(--wash); border-radius: 4px; padding: 7px 10px; margin: 0 0 10px; }
.do b { font-size: 12px; font-weight: 650; white-space: nowrap; }
.note { font-size: 12.5px; color: var(--soft); }
ol.map { margin: 4px 0 10px; padding: 0; list-style: none; counter-reset: ph; }
ol.map li { counter-increment: ph; display: grid; grid-template-columns: 22px 1fr; gap: 0 6px; padding: 5px 0; border-top: 1px solid var(--line); }
ol.map li:first-child { border-top: 0; }
ol.map li::before { content: counter(ph); font-size: 12px; font-weight: 650; color: var(--soft); padding-top: 1px; }
ol.map li span { display: block; font-size: 12.5px; color: var(--soft); grid-column: 2; }
.foot { display: flex; align-items: center; gap: 8px; margin-top: 4px; }
.count { font-size: 12px; color: var(--soft); margin-right: auto; }
.btn { height: 32px; padding: 0 12px; border-radius: 4px; border: 1px solid var(--line); background: var(--paper); font-size: 13px; font-weight: 600; }
.btn:hover { background: color-mix(in srgb, var(--paper), var(--ink) 7%); }
.btn.go { background: var(--act); color: var(--act-ink); border-color: var(--act); font-weight: 600; }
.btn:focus-visible, .launch:focus-visible, .x:focus-visible { outline: 2px solid var(--ring); outline-offset: 2px; }
.x { position: absolute; top: 8px; right: 8px; width: 26px; height: 26px; border: 0; background: none;
  display: grid; place-items: center; color: var(--soft); border-radius: 4px; }
.x:hover { background: var(--wash); color: var(--ink); }
.x svg { width: 12px; height: 12px; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; }
@media (prefers-reduced-motion: reduce) { .ring, .card { transition: none; } }
`;

  function start(w) {
    const phases = (w.phases || []).filter((p) => p && (p.steps || []).length);
    if (!phases.length) return;
    const steps = [];
    phases.forEach((p, pi) => p.steps.forEach((s, si) => steps.push({ ...s, pi, si, phase: p })));
    const key = `astaui-walkthrough:${location.pathname}:${w.title || document.title}`;

    const host = document.createElement('astaui-walkthrough');
    host.setAttribute('data-astaui-layer', '');
    const root = host.attachShadow({ mode: 'open' });
    root.innerHTML = `<style>${CSS}</style><div class="layer"><div class="ring" hidden></div>
      <section class="card" role="dialog" aria-modal="false" aria-live="polite" tabindex="-1" hidden></section>
      <button class="launch" type="button" aria-label="Walkthrough: how to use this interface">
      <svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="3.5" cy="12.5" r="1.8"/><circle cx="12.5" cy="3.5" r="1.8"/><path d="M5.3 12.5h4.2a2.5 2.5 0 0 0 0-5h-3a2.5 2.5 0 0 1 0-5h4.2"/></svg>Walkthrough</button></div>`;
    (document.body || document.documentElement).append(host);
    const ring = root.querySelector('.ring');
    const card = root.querySelector('.card');
    const launch = root.querySelector('.launch');

    let at = -1; // -1 overview, steps.length the end
    let target = null;
    let off = null;
    const h = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
    const btn = (label, cls, fn) => { const b = h('button', `btn ${cls || ''}`, label); b.type = 'button'; b.addEventListener('click', fn); return b; };
    const X = () => {
      const b = h('button', 'x'); b.type = 'button'; b.setAttribute('aria-label', 'Close the walkthrough');
      b.innerHTML = '<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M2 2l8 8M10 2l-8 8"/></svg>';
      b.addEventListener('click', close); return b;
    };
    const bar = (pi) => {
      const d = h('div', 'phases');
      d.setAttribute('aria-hidden', 'true');
      phases.forEach((_, i) => { const s = h('span'); if (i === pi) s.dataset.on = ''; else if (i < pi) s.dataset.done = ''; d.append(s); });
      return d;
    };

    function find(sel) {
      if (!sel) return null;
      try {
        for (const e of document.querySelectorAll(sel)) {
          const r = e.getBoundingClientRect();
          if (r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== 'hidden') return e;
        }
      } catch (e) { /* a selector the page does not understand */ }
      return null;
    }
    function prep(s) {
      for (const sel of s.prep || []) {
        const e = find(sel);
        if (e) e.click();
      }
    }

    function place() {
      if (card.hidden) return;
      const vw = innerWidth, vh = innerHeight, cw = card.offsetWidth, ch = card.offsetHeight, gap = 14;
      if (!target || !target.isConnected) {
        ring.hidden = true;
        card.style.left = `${Math.max(12, (vw - cw) / 2)}px`;
        card.style.top = `${Math.max(12, (vh - ch) / 2)}px`;
        return;
      }
      const r = target.getBoundingClientRect();
      const pad = 6;
      ring.hidden = false;
      Object.assign(ring.style, { left: `${r.left - pad}px`, top: `${r.top - pad}px`, width: `${r.width + pad * 2}px`, height: `${r.height + pad * 2}px` });
      const fits = {
        right: vw - r.right - gap - pad >= cw + 12, left: r.left - gap - pad >= cw + 12,
        below: vh - r.bottom - gap - pad >= ch + 12, above: r.top - gap - pad >= ch + 12,
      };
      const clampX = (x) => Math.min(Math.max(12, x), vw - cw - 12);
      const clampY = (y) => Math.min(Math.max(12, y), vh - ch - 12);
      let x, y;
      if (fits.right) { x = r.right + pad + gap; y = clampY(r.top); }
      else if (fits.left) { x = r.left - pad - gap - cw; y = clampY(r.top); }
      else if (fits.below) { x = clampX(r.left); y = r.bottom + pad + gap; }
      else if (fits.above) { x = clampX(r.left); y = r.top - pad - gap - ch; }
      else { x = clampX(vw - cw - 12); y = clampY(vh - ch - 12); }
      card.style.left = `${x}px`;
      card.style.top = `${y}px`;
    }
    let raf = 0;
    const follow = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(place); };

    function show(i) {
      if (off) { off(); off = null; }
      at = Math.max(-1, Math.min(i, steps.length));
      store.set(`${key}:at`, String(at));
      card.replaceChildren();
      card.hidden = false;
      launch.hidden = true;
      target = null;
      if (at === -1) overview();
      else if (at === steps.length) end();
      else step(steps[at]);
      card.prepend(X());
      follow();
      card.focus({ preventScroll: true });
    }
    function overview() {
      card.setAttribute('aria-label', 'Walkthrough: overview');
      card.append(h('p', 'eyebrow', `${steps.length} steps in ${phases.length} ${phases.length === 1 ? 'part' : 'parts'}`),
        h('h2', '', w.title || 'How this works'));
      if (w.goal) card.append(h('p', '', w.goal));
      const ol = h('ol', 'map');
      for (const p of phases) { const li = h('li', '', p.name); if (p.say) li.append(h('span', '', p.say)); ol.append(li); }
      card.append(ol);
      const f = h('div', 'foot');
      f.append(h('span', 'count', ''), btn('Not now', '', close), btn('Start', 'go', () => show(0)));
      card.append(f);
    }
    function end() {
      card.setAttribute('aria-label', 'Walkthrough: done');
      card.append(bar(phases.length), h('p', 'eyebrow', 'Done'), h('h2', '', 'That is the whole workflow'));
      if (w.end) card.append(h('p', '', w.end));
      const f = h('div', 'foot');
      f.append(h('span', 'count', ''), btn('Start again', '', () => show(-1)), btn('Close', 'go', close));
      card.append(f);
    }
    function step(s) {
      prep(s);
      target = find(s.target);
      if (target) target.scrollIntoView({ block: 'nearest', inline: 'nearest' });
      card.setAttribute('aria-label', `Step ${at + 1} of ${steps.length}: ${s.title || ''}`);
      card.append(bar(s.pi), h('p', 'eyebrow', `${s.pi + 1} · ${s.phase.name}`), h('h2', '', s.title || ''));
      if (s.say) card.append(h('p', '', s.say));
      if (s.do) { const d = h('div', 'do'); d.append(h('b', '', 'Try it'), h('span', '', s.do)); card.append(d); }
      if (!target) card.append(h('p', 'note', 'This part is not on screen right now. It appears once the step before it is done.'));
      const f = h('div', 'foot');
      f.append(h('span', 'count', `Step ${at + 1} of ${steps.length}`));
      f.append(btn('Back', '', () => show(at - 1)));
      f.append(btn(at === steps.length - 1 ? 'Finish' : 'Next', 'go', () => show(at + 1)));
      card.append(f);
      if (target && s.next_on) {
        const here = at;
        const go = () => setTimeout(() => { if (at === here) show(here + 1); }, 450);
        target.addEventListener(s.next_on, go, { once: true });
        off = () => target && target.removeEventListener(s.next_on, go);
      }
    }
    function close() {
      if (off) { off(); off = null; }
      card.hidden = true;
      ring.hidden = true;
      target = null;
      launch.hidden = false;
      store.set(`${key}:seen`, '1');
      launch.focus({ preventScroll: true });
    }

    launch.addEventListener('click', () => {
      const last = +store.get(`${key}:at`);
      show(last >= 0 && last < steps.length ? last : -1);
    });
    addEventListener('scroll', follow, true);
    addEventListener('resize', follow);
    new ResizeObserver(follow).observe(document.documentElement);
    addEventListener('keydown', (e) => {
      if (card.hidden) return;
      const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName) || e.target.isContentEditable;
      if (e.key === 'Escape') { close(); return; }
      if (typing) return;
      if (e.key === 'ArrowRight' && at < steps.length) { e.preventDefault(); show(at + 1); }
      if (e.key === 'ArrowLeft' && at > -1) { e.preventDefault(); show(at - 1); }
    });
    // The first time the interface opens, offer the overview; after that the
    // Walkthrough button opens it where the person left off.
    if (!store.get(`${key}:seen`)) setTimeout(() => show(-1), 600);
    window.astauiWalkthrough = { open: (i = -1) => show(i), close, steps };
  }

  const go = () => { const w = read(); if (w) start(w); };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', go, { once: true });
  else go();
})();
