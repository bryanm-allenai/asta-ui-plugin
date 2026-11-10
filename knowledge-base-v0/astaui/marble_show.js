/* The map's Show boxes: which builds it holds, by how each came. The choice is
   a look on the bar, filed like its others: data-hide names the kinds left
   off, none named means the made-up builds are off, "none" that nothing is.
   The rules in kb-map-show hide the builds and draw the boxes; this files a
   press, says each box's state to whoever cannot see it, and drops a
   neighbour line that would run to a build the map is not showing (a hidden
   dot has no place, so its line ends in the plot's corner). */
(() => {
  const byId = (id) => document.querySelector(`[data-marble-id="${id}"]`);
  const OFF = 'seed';
  const nudge = () => dispatchEvent(new Event('resize'));
  const hidden = (tools) => new Set((tools.getAttribute('data-hide') ?? OFF).split(' ').filter((k) => k && k !== 'none'));

  function say() {
    const tools = byId('kb-map-tools');
    if (!tools) return;
    const off = hidden(tools);
    for (const b of tools.querySelectorAll('button[data-from]')) {
      const on = String(!off.has(b.dataset.from));
      if (b.getAttribute('aria-pressed') !== on) b.setAttribute('aria-pressed', on);
    }
  }

  document.addEventListener('click', (e) => {
    const b = e.target.closest('button[data-from]');
    const tools = b && byId('kb-map-tools');
    if (!tools || !tools.contains(b)) return;
    const off = hidden(tools);
    if (!off.delete(b.dataset.from)) off.add(b.dataset.from);
    const list = [...off].sort().join(' ');
    const value = list === OFF ? null : list || 'none';
    if (tools.getAttribute('data-hide') === value) return;
    if (value === null) tools.removeAttribute('data-hide');
    else tools.setAttribute('data-hide', value);
    const m = window.marble;
    const id = m?.id?.(tools);
    if (id) m.op({ type: 'setAttr', id, name: 'data-hide', value }, { immediate: true, look: true });
    say();
    nudge();
  });

  const corner = (l, x, y) => l.getAttribute(x) === '0' && l.getAttribute(y) === '0';
  function trim() {
    for (const l of document.querySelectorAll('#kb-map-pts svg.lines line')) {
      if (corner(l, 'x1', 'y1') || corner(l, 'x2', 'y2')) l.remove();
    }
  }

  let watched = null;
  function watch() {
    const tools = byId('kb-map-tools');
    if (!tools || tools === watched) return;
    watched = tools;
    new MutationObserver(() => { say(); nudge(); }).observe(tools, { attributes: true, attributeFilter: ['data-hide'] });
    const plot = byId('kb-map-pts');
    if (plot) new MutationObserver(trim).observe(plot, { childList: true, subtree: true });
    say();
  }
  watch();
  const ready = (m) => m.register?.(watch);
  if (window.marble) ready(window.marble);
  else addEventListener('marble:ready', (e) => ready(e.detail), { once: true });
})();
