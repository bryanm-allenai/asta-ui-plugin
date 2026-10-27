// Affordances: history, editable — composed from Marble's lib/affordances.js. One closure: replace it whole.
(() => {
  const begin = (marble) => {
    const TRANSIENT = 'data-marble-transient';
    const ID = 'data-marble-id';

    const isTransient = (el) => el.hasAttribute(TRANSIENT);
    const persistentChildren = (el) => [...el.children].filter((c) => !isTransient(c));

    function nextPersistentSibling(el) {
      let sibling = el.nextElementSibling;
      while (sibling && isTransient(sibling)) sibling = sibling.nextElementSibling;
      return sibling;
    }

    // An element can hold several roles at once — a beat is both editable and a
    // sortable item — so wiring is tracked per role, not per element.
    const roles = new WeakMap();
    function claim(el, role) {
      const held = roles.get(el) ?? new Set();
      if (held.has(role)) return false;
      held.add(role);
      roles.set(el, held);
      return true;
    }

    const within = (root, selector) => [
      ...(root.matches?.(selector) ? [root] : []),
      ...root.querySelectorAll(selector),
    ];

    // Reading a style attribute back off an element hands the file the
    // browser's own serialization — respaced, reordered, semicolon appended —
    // which is the renormalization the patcher exists to avoid. Every gesture
    // that writes an inline style composes it here instead, so the bytes in the
    // page and the bytes in the file are the same bytes. A null drops a
    // declaration; everything else the element carries is kept, in its order,
    // because a position owns where a piece is and nothing else about it.
    //
    // A host that serves the vocabulary module has already made this decision
    // once, for every writer; that is the same function, preferred when it is
    // there, and this is what a document falls back to under a host that serves
    // only the carrier.
    function composeStyle(el, declarations) {
      const shared = globalThis.marbleVocabulary?.styleWith;
      if (shared) return shared(el, declarations);
      const dropped = new Set(Object.keys(declarations));
      const rest = (el.getAttribute('style') ?? '')
        .split(';')
        .map((declaration) => declaration.trim())
        .filter((declaration) => declaration && !dropped.has(declaration.slice(0, declaration.indexOf(':')).trim().toLowerCase()));
      const next = Object.entries(declarations)
        .filter(([, value]) => value !== null && value !== undefined && value !== '')
        .map(([name, value]) => `${name}:${value}`);
      return [...next, ...rest].join(';');
    }

    // Each part contributes its own styling, its own wiring pass, and the
    // selector for what it makes touchable — so removing a part removes all
    // three and nothing dangles.
    const css = [];
    const wirers = [];
    const addressable = [];
    // False during the first register pass (the document as it loaded), true
    // afterwards. A row that is wired later is a row that just arrived, and
    // its chrome should say so rather than waiting for a hover.
    let live = false;

    // A subtree that isn't in the document yet can't be addressed by path, so
    // it carries its ids with it — they are serialized into the insert op.
    function assignIdsIn(root) {
      for (const el of [root, ...root.querySelectorAll('*')]) {
        if (isTransient(el) || marble.id(el)) continue;
        if (el === root || el.matches(ADDRESSABLE)) el.setAttribute(ID, marble.newId());
      }
    }

    // These live in the page and never in the file, which the carrier has no
    // way to know until it is told.
    marble.pageOnly('contenteditable', 'spellcheck');
    addressable.push('[data-marble-editable]');
    wirers.push(wireEditable);

    function wireEditable(root) {
      for (const el of within(root, '[data-marble-editable]')) {
        if (!claim(el, 'editable')) continue;

        // plaintext-only keeps the browser from injecting <div> and <br> soup
        // on Enter, so textContent stays the whole truth and setText is safe.
        el.setAttribute('contenteditable', 'plaintext-only');
        if (el.contentEditable !== 'plaintext-only') el.setAttribute('contenteditable', 'true');
        el.spellcheck = false;

        // One undo step per edit session: prior text is captured on focus, and
        // keystrokes coalesce against that same entry until blur.
        let prior = null;
        el.addEventListener('focus', () => {
          prior = marble.text(el);
        });
        el.addEventListener('input', (event) => {
          const id = marble.id(el);
          const text = marble.text(el);
          const op = { type: 'setText', id, text };
          // The browser's own undo inside the field arrives here as an input
          // like any other, and it is not a new edit. Recording it put the state
          // just undone back on the ring — and cleared the redo with it — so the
          // next Mod+Z moved the document forward instead of back. File where
          // the text ended up, and let the session start again from there.
          if (event.inputType === 'historyUndo' || event.inputType === 'historyRedo') {
            prior = text;
            marble.op(op);
            return;
          }
          if (prior !== null && text !== prior) {
            marble.record(
              { redo: [op], undo: [{ type: 'setText', id, text: prior }] },
              { coalesce: true },
            );
          }
          marble.op(op);
        });
        el.addEventListener('blur', () => {
          prior = null;
          marble.flush();
        });

        // Most editable nodes here are a heading or a single line, where Enter
        // means "done" and a newline buried in the text is a mistake you can't
        // see. Shift-Enter still breaks the line where a break is wanted.
        el.addEventListener('keydown', (event) => {
          if (event.key === 'Escape' || (event.key === 'Enter' && !event.shiftKey)) {
            event.preventDefault();
            el.blur();
          }
        });
      }
    }

    // Undo/redo is a carrier capability; binding the keys is the app's call,
    // same as drawing a save indicator. Native inputs keep the browser's own
    // undo — marble editables preventDefault so the stacks do not fight.
    addEventListener('keydown', (event) => {
      const mod = event.metaKey || event.ctrlKey;
      if (!mod || event.altKey) return;
      const key = event.key.toLowerCase();
      const isUndo = key === 'z' && !event.shiftKey;
      const isRedo = (key === 'z' && event.shiftKey) || key === 'y';
      if (!isUndo && !isRedo) return;

      const target = event.target;
      if (
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        (target instanceof HTMLElement &&
          target.isContentEditable &&
          !target.hasAttribute('data-marble-editable') &&
          !target.closest('[data-marble-editable]'))
      ) {
        return;
      }

      // A staged proposal is not history yet — Mod+Z discards it instead.
      if (isUndo && typeof marble.discardStaged === 'function' && marble.discardStaged()) {
        event.preventDefault();
        return;
      }

      // Anything still here with a caret in it is a marble editable — the guard
      // above sent the native inputs home. Inside one, the carrier owns the
      // history whether or not there is a step left in it: letting the key
      // through at the bottom of the ring handed the document to the browser's
      // own undo, which rewrites the field without the file hearing about it.
      const editing = target instanceof HTMLElement && target.isContentEditable;

      if (isUndo && marble.canUndo) {
        event.preventDefault();
        marble.undo();
      } else if (isRedo && marble.canRedo) {
        event.preventDefault();
        marble.redo();
      } else if (editing) {
        event.preventDefault();
      }
    });

    const style = document.createElement('style');
    style.setAttribute(TRANSIENT, '');
    style.textContent = css.join('\n');
    document.head.append(style);

    // Anything a hand can act on has to be addressable in the file first.
    const ADDRESSABLE = addressable.join(', ');
    marble.address(document.querySelectorAll(ADDRESSABLE));

    // Runs now over the document as it stands, and again over anything that
    // arrives later — an insert, an accepted proposal, an edit made to the file
    // in another window.
    marble.register((root) => {
      for (const wirer of wirers) wirer(root);
      live = true;
    });
  };

  // The carrier is injected after the document has been parsed, so this waits
  // rather than the other way round. No carrier, no affordances: the document
  // is still a page you can read, it just isn't one you can change.
  if (window.marble) begin(window.marble);
  else addEventListener('marble:ready', (event) => begin(event.detail), { once: true });
})();
