/* Agent Runs: "Show every run" lets the picked build go, the way Close does, so
   the lens goes back to every run's strip. */
(() => {
  document.addEventListener('click', (e) => {
    if (!e.target.closest('[data-runs-all]')) return;
    document.getElementById('kb-close')?.click();
  });
})();
