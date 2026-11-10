/* The map's neighbour lines and its pressed choices are drawn again when the
   page's looks change or the window resizes. Switching between Grouped and
   Spread, or pressing a cluster's name, changes a look the page does not
   watch, so it asks for a redraw the way a resize does: at once, and again
   once the dots have arrived. */
(() => {
  const nudge = () => dispatchEvent(new Event('resize'));
  let watched = null;
  function watch() {
    const tools = document.getElementById('kb-map-tools');
    if (!tools || tools === watched) return;
    watched = tools;
    new MutationObserver(() => { nudge(); setTimeout(nudge, 500); })
      .observe(tools, { attributes: true, attributeFilter: ['data-arrange', 'data-cluster'] });
  }
  watch();
  const ready = (marble) => marble.register?.(watch);
  if (window.marble) ready(window.marble);
  else addEventListener('marble:ready', (e) => ready(e.detail), { once: true });
})();
