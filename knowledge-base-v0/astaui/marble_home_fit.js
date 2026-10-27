/* Home fits the panel. Each density in turn, roomiest first, until nothing is
   below the fold; then the view shrinks a little; and if it still spills, the
   sections go side by side as pages, and the same again for those; past even
   that, the pages run on to a fourth rather than hide anything. What it
   sets lives on <html>, which the file never keeps: it is worked out again on
   every load, resize and refresh. */
(() => {
  const root = document.documentElement;
  const byId = (id) => document.getElementById(id);
  const STEPS = 8, SMALLEST = 0.9;
  let frame = 0;
  const home = () => byId('kb-v-home');
  const paged = () => root.getAttribute('data-kb-fit')?.includes('pages');
  // As pages, too much is a fourth page; on one page, anything past either edge.
  const spills = (v) => {
    if (!paged()) return v.scrollHeight > v.clientHeight + 1 || v.scrollWidth > v.clientWidth + 1;
    const gap = parseFloat(getComputedStyle(v).columnGap) || 0;
    return v.scrollWidth > 3 * v.clientWidth + 2 * gap + 1;
  };
  const set = (n, more) => {
    const words = [...Array.from({ length: n }, (_, i) => String(i + 1)), ...more].join(' ');
    if (words) root.setAttribute('data-kb-fit', words); else root.removeAttribute('data-kb-fit');
  };
  const zoom = (z) => z < 1 ? root.style.setProperty('--kb-home-zoom', z.toFixed(3)) : root.style.removeProperty('--kb-home-zoom');
  // As pages: which one is showing, and turning to one by its name.
  const stride = (v) => v.clientWidth + (parseFloat(getComputedStyle(v).columnGap) || 0);
  function current() {
    const v = home(), nav = byId('kb-home-pages');
    if (!v || !nav) return;
    const at = paged() ? Math.round(v.scrollLeft / stride(v)) : -1;
    [...nav.children].forEach((b, i) => {
      if (i === at && !b.hasAttribute('aria-current')) b.setAttribute('aria-current', 'true');
      else if (i !== at && b.hasAttribute('aria-current')) b.removeAttribute('aria-current');
    });
  }
  // The densest it needs, then the least shrinking that fits; false if even both are not enough.
  function settle(v, more) {
    zoom(1);
    let n = 0;
    set(0, more);
    while (spills(v) && n < STEPS) set(++n, more);
    if (!spills(v)) return true;
    zoom(SMALLEST);
    if (spills(v)) return false;
    let lo = SMALLEST, hi = 1;
    for (let i = 0; i < 6; i++) {
      const mid = (lo + hi) / 2;
      zoom(mid);
      if (spills(v)) hi = mid; else lo = mid;
    }
    zoom(lo);
    return true;
  }
  function fit() {
    frame = 0;
    const v = home();
    if (!v || getComputedStyle(v).display === 'none') return;
    const page = paged() ? Math.round(v.scrollLeft / stride(v)) : 0;
    if (!settle(v, []) && !settle(v, ['pages'])) set(STEPS, ['pages']);
    if (paged()) v.scrollLeft = page * stride(v);
    current();
  }
  const schedule = () => { if (!frame) frame = requestAnimationFrame(fit); };
  function turn(e) {
    const b = e.target.closest('#kb-home-pages > button'), v = home();
    if (!b || !v) return;
    const i = [...b.parentElement.children].indexOf(b);
    v.scrollTo({ left: i * stride(v), behavior: 'smooth' });
  }
  // As pages, the wheel turns them: one page a gesture, however long it runs on.
  let quiet = 0, turned = false;
  function wheel(e) {
    const v = home();
    if (!paged() || e.ctrlKey || Math.abs(e.deltaX) >= Math.abs(e.deltaY)) return;
    e.preventDefault();
    clearTimeout(quiet);
    quiet = setTimeout(() => { turned = false; }, 220);
    if (turned || Math.abs(e.deltaY) < 4) return;
    turned = true;
    v.scrollBy({ left: Math.sign(e.deltaY) * stride(v), behavior: 'smooth' });
  }
  let watching = null;
  function watch() {
    const v = home(), lens = byId('kb-lens');
    if (!v || v === watching) return;
    watching = v;
    const sized = new ResizeObserver(schedule);
    sized.observe(v);
    sized.observe(v.parentElement);
    new MutationObserver(schedule).observe(v, { childList: true, subtree: true, characterData: true });
    if (lens) new MutationObserver(schedule).observe(lens, { attributes: true, attributeFilter: ['data-view'] });
    v.addEventListener('wheel', wheel, { passive: false });
    v.addEventListener('scroll', current, { passive: true });
    schedule();
  }
  document.addEventListener('click', turn);
  watch();
  document.fonts?.ready.then(schedule);
  // The page names say which page shows; that is the page's to know, not the file's.
  const ready = (marble) => { marble.pageOnly?.('aria-current'); marble.register(() => { watch(); schedule(); }); };
  if (window.marble) ready(window.marble);
  else addEventListener('marble:ready', (e) => ready(e.detail), { once: true });
})();
