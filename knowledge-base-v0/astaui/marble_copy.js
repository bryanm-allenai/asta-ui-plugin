/* Copy: a button with data-copy puts the code beside it on the clipboard and says
   so for a moment. Where the clipboard is refused, it selects the code instead, to
   copy with the keys. What the button says is the tab's own, never filed. */
(() => {
  document.addEventListener('click', (e) => {
    const b = e.target.closest('button[data-copy]');
    const code = b?.parentElement?.querySelector('code');
    if (!code) return;
    const said = (how) => {
      b.setAttribute('data-copied', how);
      clearTimeout(b.kbCopied);
      b.kbCopied = setTimeout(() => b.removeAttribute('data-copied'), 2000);
    };
    const select = () => {
      const range = document.createRange();
      range.selectNodeContents(code);
      const sel = getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      said('no');
    };
    const text = code.textContent.trim();
    if (navigator.clipboard?.writeText) navigator.clipboard.writeText(text).then(() => said('yes'), select);
    else select();
  });
  const ready = (marble) => marble.pageOnly?.('data-copied');
  if (window.marble) ready(window.marble);
  else addEventListener('marble:ready', (e) => ready(e.detail), { once: true });
})();
