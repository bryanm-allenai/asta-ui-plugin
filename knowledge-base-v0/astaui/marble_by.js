/* The map's Cluster by: one look on the bar, data-arrange, holding the key of
   the islands shown ("field" for discipline, or a dimension's key); none set
   is the flat map. A press also points data-channel at that dimension (none,
   the whole card, for the flat map and for discipline), so the neighbour
   lines and captions follow it. The older cards are only ever flat, so a
   press clears data-cards. Each look is filed like the bar's others; the
   generated rules in kb-map-groups press the choice, and this says it to
   whoever cannot see it. */
(() => {
  // Which copy of this script the tab runs, so a newer page can tell an open
  // tab to reload into it.
  window.astauiClusterBy = 2;
  const byId = (id) => document.querySelector(`[data-marble-id="${id}"]`);

  function say() {
    const tools = byId('kb-map-tools');
    if (!tools) return;
    const keys = [...tools.querySelectorAll('button[data-by]')].map((b) => b.dataset.by);
    const arrange = tools.getAttribute('data-arrange');
    const now = tools.getAttribute('data-cards') !== 'prompts' && keys.includes(arrange) ? arrange : 'none';
    for (const b of tools.querySelectorAll('button[data-by]')) {
      const on = String(b.dataset.by === now);
      if (b.getAttribute('aria-pressed') !== on) b.setAttribute('aria-pressed', on);
    }
  }

  function set(tools, name, value) {
    if (tools.getAttribute(name) === value) return;
    if (value === null) tools.removeAttribute(name);
    else tools.setAttribute(name, value);
    const id = window.marble?.id?.(tools);
    if (id) window.marble.op({ type: 'setAttr', id, name, value }, { immediate: true, look: true });
  }

  document.addEventListener('click', (e) => {
    const b = e.target.closest('button[data-by]');
    const tools = b && byId('kb-map-tools');
    if (!tools || !tools.contains(b)) return;
    const by = b.dataset.by;
    set(tools, 'data-cards', null);
    set(tools, 'data-arrange', by === 'none' ? null : by);
    set(tools, 'data-channel', by === 'none' || by === 'field' ? null : by);
    say();
  });

  let watched = null;
  function watch() {
    const tools = byId('kb-map-tools');
    if (!tools || tools === watched) return;
    watched = tools;
    new MutationObserver(say).observe(tools, { attributes: true, attributeFilter: ['data-arrange', 'data-channel', 'data-cards'] });
    say();
  }
  watch();
  const ready = (m) => m.register?.(watch);
  if (window.marble) ready(window.marble);
  else addEventListener('marble:ready', (e) => ready(e.detail), { once: true });
})();
