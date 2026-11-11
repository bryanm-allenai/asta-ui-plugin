#!/usr/bin/env node
// The browser AstaUI's computer-use agent works in, as an MCP server on stdio.
// `astaui cua run` starts it for one run; it is the same browser the project's
// own collection runs use, so a check on your app sees what those runs saw.
// It does what a scientist's hands do: click (by element or by position),
// type, choose from a list, keys, drags, text selection, hover, the wheel,
// uploads from one test-data folder, downloads kept and readable, dialogs
// answered, the clipboard and the window size. It only opens pages on the
// app's own address.
//
// It needs Playwright and its Chromium, which `astaui cua setup` installs into
// ~/.astaui/cua. ASTAUI_PLAYWRIGHT names another folder whose node_modules has
// Playwright.
//
// Environment:
//   PILOT_SCREENS    screenshots are written here
//   PILOT_DOWNLOADS  downloads are kept here
//   PILOT_FILES      the only folder uploads may come from
//   PILOT_ORIGIN     navigate refuses any other origin (127.0.0.1 and
//                    localhost on that port count as the same one, because an
//                    app may set its cookies for either name)
//   PILOT_TRACE      if set, one JSON line per call is appended here
//   PILOT_SHOT       png (default) or jpeg
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import readline from 'node:readline';

import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

// Where Playwright is: ASTAUI_PLAYWRIGHT, else the folder `astaui cua setup` made.
const PW_HOME = process.env.ASTAUI_PLAYWRIGHT || path.join(os.homedir(), '.astaui', 'cua');

async function loadChromium() {
  try {
    const req = createRequire(path.join(PW_HOME, 'package.json'));
    const entry = new URL('index.mjs', pathToFileURL(req.resolve('playwright/package.json')));
    const { chromium } = await import(entry.href);
    return chromium;
  } catch (err) {
    throw new Error(`Playwright is not installed in ${PW_HOME} (${err.message}). Run \`astaui cua setup\`.`);
  }
}

// The plain browser tools the ones below do not replace.
const BROWSER_SCHEMAS = [
  {
    name: 'browser_tabs',
    description: 'List, open, close or select tabs.',
    inputSchema: {
      type: 'object',
      required: ['action'],
      properties: {
        action: { type: 'string', enum: ['list', 'new', 'close', 'select'] },
        index: { type: 'number', description: 'Tab index for close or select.' },
      },
    },
  },
  {
    name: 'browser_navigate',
    description: 'Open an http(s) URL in the current tab. Only the app\'s own address opens.',
    inputSchema: { type: 'object', required: ['url'], properties: { url: { type: 'string' } } },
  },
  {
    name: 'browser_navigate_back',
    description: 'Go back in the current tab.',
    inputSchema: { type: 'object', properties: {} },
  },
  {
    name: 'browser_take_screenshot',
    description: 'Screenshot of the current tab.',
    inputSchema: { type: 'object', properties: {} },
  },
  {
    name: 'browser_close',
    description: 'Close the browser. The next navigate relaunches it.',
    inputSchema: { type: 'object', properties: {} },
  },
];

const screens = process.env.PILOT_SCREENS;
const downloads = process.env.PILOT_DOWNLOADS;
const files = process.env.PILOT_FILES;
const origin = process.env.PILOT_ORIGIN;
// The same server under either loopback name. A session cookie set for one
// name is not sent to the other, so an app that signs people in needs both.
const origins = origin
  ? [origin, origin.replace('127.0.0.1', 'localhost'), origin.replace('localhost', '127.0.0.1')].filter((v, i, a) => a.indexOf(v) === i)
  : [];
const trace = process.env.PILOT_TRACE;
const jpeg = process.env.PILOT_SHOT === 'jpeg';
const CALL_LIMIT = Number(process.env.PILOT_CALL_LIMIT || 45000);
for (const dir of [screens, downloads]) if (dir) fs.mkdirSync(dir, { recursive: true });

const ref = { type: 'string', description: 'Element ref from browser_snapshot.' };
const point = {
  x: { type: 'number', description: 'Pixels from the left of the screenshot.' },
  y: { type: 'number', description: 'Pixels from the top of the screenshot.' },
};

const SCHEMAS = [
  ...BROWSER_SCHEMAS.filter((s) => !['browser_click', 'browser_type', 'browser_snapshot'].includes(s.name)),
  {
    name: 'browser_snapshot',
    description: 'Accessibility tree of the current tab, with [ref=eN] markers. Refs go stale when the page redraws that part, so snapshot again after a change. Give a ref to see only that part of the page, when the whole tree is too long.',
    inputSchema: { type: 'object', properties: { ref } },
  },
  {
    name: 'browser_type',
    description: 'Type into a field by ref. By default it replaces what the field holds. add: true types at the end of what is already there instead, key by key, as a person would (use it for long text, rich-text editors, and fields you are writing in more than once). submit presses Enter afterwards.',
    inputSchema: {
      type: 'object',
      required: ['ref', 'text'],
      properties: { ref, text: { type: 'string' }, add: { type: 'boolean' }, submit: { type: 'boolean' } },
    },
  },
  {
    name: 'browser_color_scheme',
    description: 'Show the page in the light or dark colour scheme, as if the computer were set to it.',
    inputSchema: { type: 'object', required: ['scheme'], properties: { scheme: { type: 'string', enum: ['light', 'dark'] } } },
  },
  {
    name: 'browser_click',
    description: 'Click an element by snapshot ref, or a point on the screenshot by x and y (for charts, canvases and anything the snapshot does not list). double for a double-click, button "right" for a right-click, modifiers such as ["Shift"] to hold keys while clicking.',
    inputSchema: {
      type: 'object',
      properties: {
        ref, ...point,
        double: { type: 'boolean' },
        button: { type: 'string', enum: ['left', 'right', 'middle'] },
        modifiers: { type: 'array', items: { type: 'string', enum: ['Shift', 'Control', 'Alt', 'Meta'] } },
      },
    },
  },
  {
    name: 'browser_select_option',
    description: 'Choose one or more options in a native <select> (a dropdown list) by its ref. values are option labels or values.',
    inputSchema: {
      type: 'object',
      required: ['ref', 'values'],
      properties: { ref, values: { type: 'array', items: { type: 'string' } } },
    },
  },
  {
    name: 'browser_press_key',
    description: 'Press a key or chord, such as "j", "Escape", "ArrowDown", "Control+z", "Shift+ArrowRight". With a ref, the element is focused first; without, the key goes to whatever has focus.',
    inputSchema: { type: 'object', required: ['key'], properties: { key: { type: 'string' }, ref } },
  },
  {
    name: 'browser_hover',
    description: 'Move the pointer over an element (by ref) or a point (x, y) and leave it there, to show tooltips and hover states. The reply also gives the text of any tooltip the element carries (a title), which a screenshot does not show.',
    inputSchema: { type: 'object', properties: { ref, ...point } },
  },
  {
    name: 'browser_drag',
    description: 'Press, move and release the pointer: from an element or point to another element or point. Use it to move cards and notes, drag sliders and handles, draw a box, or pan a canvas. Give from_ref or from_x/from_y, and to_ref or to_x/to_y.',
    inputSchema: {
      type: 'object',
      properties: {
        from_ref: ref, from_x: { type: 'number' }, from_y: { type: 'number' },
        to_ref: ref, to_x: { type: 'number' }, to_y: { type: 'number' },
      },
    },
  },
  {
    name: 'browser_select_text',
    description: 'Select text inside an element the way a person drags across it: the exact words in text, or the whole element without it. Use it where an interface acts on highlighted text (coding a passage, quoting, tagging a sentence).',
    inputSchema: { type: 'object', required: ['ref'], properties: { ref, text: { type: 'string' } } },
  },
  {
    name: 'browser_scroll',
    description: 'Turn the mouse wheel over an element or point (or the middle of the window). dy > 0 scrolls down, dx > 0 right. zoom: true holds Control, which many maps and canvases treat as zoom.',
    inputSchema: {
      type: 'object',
      properties: { ref, ...point, dx: { type: 'number' }, dy: { type: 'number' }, zoom: { type: 'boolean' } },
    },
  },
  {
    name: 'browser_list_files',
    description: 'List the test files you may upload.',
    inputSchema: { type: 'object', properties: {} },
  },
  {
    name: 'browser_upload',
    description: 'Give files from the test-data folder to the page. If a file picker is open (you clicked an upload button), it answers that picker; otherwise ref must be the file input itself.',
    inputSchema: {
      type: 'object',
      required: ['names'],
      properties: { names: { type: 'array', items: { type: 'string' } }, ref },
    },
  },
  {
    name: 'browser_downloads',
    description: 'List the files the page has downloaded in this run.',
    inputSchema: { type: 'object', properties: {} },
  },
  {
    name: 'browser_read_download',
    description: 'Read the start of a downloaded file as text (CSV, JSON, Markdown, GFF and so on). Binary files report only their size.',
    inputSchema: { type: 'object', required: ['name'], properties: { name: { type: 'string' } } },
  },
  {
    name: 'browser_read_clipboard',
    description: 'Read what the page last copied to the clipboard.',
    inputSchema: { type: 'object', properties: {} },
  },
  {
    name: 'browser_resize',
    description: 'Set the window size, for a wider plate or table or to see a phone layout. Starts at 1280 x 800.',
    inputSchema: {
      type: 'object',
      required: ['width', 'height'],
      properties: { width: { type: 'number' }, height: { type: 'number' } },
    },
  },
];

let browser = null;
let context = null;
const tabs = [];
let selected = 0;
let shot = 0;
let chooser = null;
const events = [];
const consoleErrors = [];
let step = 0;
let stuck = 0;
const saved = [];

const current = () => {
  if (!tabs.length) throw new Error('no open tab — navigate or open one first');
  return tabs[selected];
};
const info = async (page) => ({ url: page.url(), title: await page.title() });
const at = (page, r) => page.locator(`aria-ref=${r}`);

async function centre(page, r, x, y) {
  if (r) {
    const box = await at(page, r).boundingBox();
    if (!box) throw new Error(`ref ${r} is not on screen`);
    return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  }
  if (typeof x === 'number' && typeof y === 'number') return { x, y };
  throw new Error('give a ref, or x and y');
}

function watch(page) {
  page.on('console', (msg) => { if (msg.type() === 'error') consoleErrors.push(msg.text().slice(0, 300)); });
  page.on('pageerror', (err) => consoleErrors.push(`uncaught: ${String(err.message).slice(0, 300)}`));
  page.on('dialog', async (dialog) => {
    events.push(`a ${dialog.type()} dialog said "${dialog.message()}" and was accepted`);
    await dialog.accept(dialog.type() === 'prompt' ? dialog.defaultValue() : undefined).catch(() => {});
  });
  page.on('filechooser', (fc) => {
    chooser = fc;
    events.push(`a file picker opened${fc.isMultiple() ? ' (several files allowed)' : ''}; answer it with browser_upload`);
  });
  page.on('download', async (dl) => {
    const name = dl.suggestedFilename().replace(/[/\\]/g, '_');
    if (!downloads) {
      events.push(`the page downloaded ${name}, but this run keeps no downloads`);
      return;
    }
    await dl.saveAs(path.join(downloads, name)).catch(() => {});
    saved.push(name);
    events.push(`the page downloaded ${name}; read it with browser_read_download`);
  });
  page.on('popup', (popup) => {
    tabs.push(popup);
    watch(popup);
    events.push(`the page opened a new tab (${tabs.length - 1}); select it with browser_tabs`);
  });
}

async function ensureContext() {
  if (context) return;
  const chromium = await loadChromium();
  const proxy = process.env.PILOT_PROXY ? { server: process.env.PILOT_PROXY, bypass: '127.0.0.1,localhost' } : undefined;
  // Fewer renderer and helper processes: one interface per browser, and the
  // PC runs several of these beside the drive.
  const args = ['--renderer-process-limit=2', '--disable-extensions', '--disable-background-networking',
    '--disable-component-update', '--disable-features=Translate,MediaRouter,OptimizationHints'];
  browser = await chromium.launch({ headless: true, proxy, args });
  context = await browser.newContext({ viewport: { width: 1280, height: 800 }, acceptDownloads: true });
  context.setDefaultTimeout(5000);
  // Interfaces that ask for a file through the File System Access picker
  // (showOpenFilePicker) cannot be answered by a browser driver at all, so
  // uploads there are impossible. Standing in a plain file input makes the
  // page's own code take the ordinary path, which browser_upload can answer.
  await context.addInitScript(() => {
    const pick = (multiple) => new Promise((resolve, reject) => {
      const input = document.createElement('input');
      input.type = 'file';
      input.multiple = Boolean(multiple);
      Object.assign(input.style, { position: 'fixed', left: '-9999px', width: '1px', height: '1px' });
      (document.body || document.documentElement).appendChild(input);
      input.addEventListener('change', () => {
        const files = Array.from(input.files || []);
        input.remove();
        if (!files.length) {
          reject(new DOMException('the picker was closed', 'AbortError'));
          return;
        }
        resolve(files.map((file) => ({
          kind: 'file',
          name: file.name,
          getFile: async () => file,
          isSameEntry: async (other) => other?.name === file.name,
          queryPermission: async () => 'granted',
          requestPermission: async () => 'granted',
          createWritable: async () => {
            throw new DOMException('writing files back is not allowed here', 'NotAllowedError');
          },
        })));
      });
      input.click();
    });
    window.showOpenFilePicker = (options = {}) => pick(options.multiple);
    window.showDirectoryPicker = () => Promise.reject(new DOMException('choosing a folder is not available here', 'AbortError'));
  });
  for (const o of origins) await context.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: o }).catch(() => {});
}

async function openTab() {
  await ensureContext();
  const page = await context.newPage();
  watch(page);
  tabs.push(page);
  selected = tabs.length - 1;
  return page;
}

async function reset() {
  const closing = browser;
  browser = null;
  context = null;
  tabs.length = 0;
  selected = 0;
  chooser = null;
  if (closing) await closing.close().catch(() => {});
}

function inFiles(name) {
  if (!files) throw new Error('this run has no test files');
  const full = path.resolve(files, String(name));
  if (!full.startsWith(path.resolve(files) + path.sep)) throw new Error(`${name} is not in the test files`);
  if (!fs.existsSync(full)) throw new Error(`no test file ${name}`);
  return full;
}

const handlers = {
  async browser_tabs(input) {
    const action = String(input.action ?? 'list');
    if (action === 'new') await openTab();
    else if (action === 'select' || action === 'close') {
      const index = input.index == null ? selected : Number(input.index);
      if (!Number.isInteger(index) || index < 0 || index >= tabs.length) throw new Error(`no tab ${input.index}`);
      if (action === 'select') selected = index;
      else {
        const [page] = tabs.splice(index, 1);
        await page.close();
        if (index < selected) selected -= 1;
        if (selected >= tabs.length) selected = Math.max(0, tabs.length - 1);
      }
    } else if (action !== 'list') throw new Error(`unknown tabs action "${action}"`);
    return {
      tabs: await Promise.all(tabs.map(async (page, index) => ({ index, ...(await info(page)) }))),
      selected: tabs.length ? selected : null,
    };
  },

  async browser_navigate(input) {
    let url;
    try {
      url = new URL(String(input.url ?? ''));
    } catch {
      throw new Error('not a URL');
    }
    if (url.protocol !== 'http:' && url.protocol !== 'https:') throw new Error('only http(s) URLs are allowed');
    if (origins.length && !origins.includes(url.origin)) throw new Error(`only pages on ${origins.join(' or ')} may be opened`);
    const page = tabs.length ? current() : await openTab();
    await page.goto(url.href);
    return info(page);
  },

  async browser_navigate_back() {
    await current().goBack();
    return info(current());
  },

  async browser_snapshot(input) {
    const page = current();
    let snapshot = await page.ariaSnapshot({ mode: 'ai' });
    if (input.ref) {
      const lines = snapshot.split('\n');
      const start = lines.findIndex((l) => l.includes(`[ref=${input.ref}]`));
      if (start < 0) throw new Error(`no ref ${input.ref}; snapshot the whole page again`);
      const indent = lines[start].search(/\S/);
      let end = start + 1;
      while (end < lines.length && lines[end].search(/\S/) > indent) end += 1;
      snapshot = lines.slice(start, end).join('\n');
    }
    const LIMIT = 40000;
    if (snapshot.length > LIMIT) {
      return {
        snapshot: snapshot.slice(0, LIMIT),
        truncated: `the tree is ${snapshot.length} characters; this is the first ${LIMIT}. Snapshot a ref inside it to see the rest, or work by screenshot position.`,
      };
    }
    return { snapshot };
  },

  async browser_click(input) {
    const page = current();
    const opts = {
      button: input.button ?? 'left',
      clickCount: input.double ? 2 : 1,
      modifiers: input.modifiers ?? [],
    };
    if (input.ref) {
      const loc = at(page, input.ref);
      if (input.double) await loc.dblclick({ button: opts.button, modifiers: opts.modifiers });
      else await loc.click(opts);
    } else {
      const p = await centre(page, null, input.x, input.y);
      for (const m of opts.modifiers) await page.keyboard.down(m);
      await page.mouse.click(p.x, p.y, { button: opts.button, clickCount: opts.clickCount });
      for (const m of opts.modifiers) await page.keyboard.up(m);
    }
    return { ok: true };
  },

  async browser_type(input) {
    const page = current();
    const loc = at(page, input.ref);
    if (input.add) {
      await loc.click();
      await page.keyboard.press('Control+End');
      await page.keyboard.type(String(input.text ?? ''), { delay: 5 });
    } else {
      await loc.fill(String(input.text ?? ''));
    }
    if (input.submit) await page.keyboard.press('Enter');
    return { ok: true };
  },

  async browser_color_scheme(input) {
    const colorScheme = input.scheme === 'dark' ? 'dark' : 'light';
    await current().emulateMedia({ colorScheme });
    return { scheme: colorScheme };
  },

  async browser_select_option(input) {
    const chosen = await at(current(), input.ref).selectOption((input.values ?? []).map(String));
    return { chosen };
  },

  async browser_press_key(input) {
    const page = current();
    if (input.ref) await at(page, input.ref).press(String(input.key));
    else await page.keyboard.press(String(input.key));
    return { ok: true };
  },

  async browser_hover(input) {
    const page = current();
    const p = await centre(page, input.ref, input.x, input.y);
    if (input.ref) await at(page, input.ref).hover();
    else await page.mouse.move(p.x, p.y);
    const tooltip = await page.evaluate(({ x, y }) => {
      for (let el = document.elementFromPoint(x, y); el; el = el.parentElement) {
        const t = el.getAttribute?.('title') || [...el.children].find((c) => c.tagName.toLowerCase() === 'title')?.textContent;
        if (t) return t.trim();
      }
      return null;
    }, p);
    return tooltip ? { ok: true, tooltip } : { ok: true };
  },

  async browser_drag(input) {
    const page = current();
    const from = await centre(page, input.from_ref, input.from_x, input.from_y);
    const to = await centre(page, input.to_ref, input.to_x, input.to_y);
    await page.mouse.move(from.x, from.y);
    await page.mouse.down();
    await page.mouse.move(from.x + 4, from.y + 4, { steps: 2 });
    await page.mouse.move(to.x, to.y, { steps: 16 });
    await page.mouse.up();
    return { ok: true, from, to };
  },

  async browser_select_text(input) {
    const page = current();
    const handle = await at(page, input.ref).elementHandle();
    if (!handle) throw new Error(`no element ${input.ref}`);
    const rects = await handle.evaluate((el, want) => {
      const inView = (r) => r.top >= 0 && r.bottom <= innerHeight && r.left >= 0 && r.right <= innerWidth;
      const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
      const nodes = [];
      let all = '';
      for (let n = walker.nextNode(); n; n = walker.nextNode()) {
        nodes.push({ n, start: all.length });
        all += n.data;
      }
      if (!nodes.length) return null;
      let from = 0;
      let to = all.length;
      if (want) {
        from = all.indexOf(want);
        if (from < 0) return { missing: true };
        to = from + want.length;
      }
      const locate = (offset) => {
        for (let i = nodes.length - 1; i >= 0; i -= 1) {
          if (offset >= nodes[i].start) return [nodes[i].n, Math.min(offset - nodes[i].start, nodes[i].n.data.length)];
        }
        return [nodes[0].n, 0];
      };
      const range = document.createRange();
      range.setStart(...locate(from));
      range.setEnd(...locate(to));
      // A drag can only cover what is on screen: bring the words into view first.
      let boxes = [...range.getClientRects()].filter((r) => r.width > 0);
      if (boxes.length && !boxes.every(inView)) {
        (range.startContainer.parentElement ?? el).scrollIntoView({ block: 'center' });
        boxes = [...range.getClientRects()].filter((r) => r.width > 0);
      }
      if (!boxes.length) return null;
      const a = boxes[0];
      const b = boxes[boxes.length - 1];
      return { x1: a.left + 1, y1: a.top + a.height / 2, x2: b.right - 1, y2: b.top + b.height / 2 };
    }, input.text ?? '');
    if (rects?.missing) throw new Error(`"${input.text}" is not in that element`);
    if (!rects) throw new Error('that element has no visible text');
    await page.mouse.move(rects.x1, rects.y1);
    await page.mouse.down();
    await page.mouse.move(rects.x2, rects.y2, { steps: 12 });
    await page.mouse.up();
    const got = await page.evaluate(() => String(window.getSelection()));
    return { selected: got.slice(0, 300) };
  },

  async browser_scroll(input) {
    const page = current();
    const vp = page.viewportSize() ?? { width: 1280, height: 800 };
    const p = input.ref || typeof input.x === 'number'
      ? await centre(page, input.ref, input.x, input.y)
      : { x: vp.width / 2, y: vp.height / 2 };
    await page.mouse.move(p.x, p.y);
    if (input.zoom) await page.keyboard.down('Control');
    await page.mouse.wheel(Number(input.dx ?? 0), Number(input.dy ?? 0));
    if (input.zoom) await page.keyboard.up('Control');
    return { ok: true };
  },

  async browser_list_files() {
    if (!files || !fs.existsSync(files)) return { files: [] };
    return {
      files: fs.readdirSync(files).filter((n) => !n.startsWith('.')).map((name) => ({
        name,
        bytes: fs.statSync(path.join(files, name)).size,
      })),
    };
  },

  async browser_upload(input) {
    const paths = (input.names ?? []).map(inFiles);
    if (chooser) {
      await chooser.setFiles(paths);
      chooser = null;
    } else if (input.ref) {
      await at(current(), input.ref).setInputFiles(paths);
    } else {
      throw new Error('no file picker is open; click the upload control first, or give the file input ref');
    }
    return { uploaded: input.names };
  },

  async browser_downloads() {
    return { downloads: saved };
  },

  async browser_read_download(input) {
    if (!downloads) throw new Error('this run keeps no downloads');
    const name = String(input.name).replace(/[/\\]/g, '_');
    const full = path.join(downloads, name);
    if (!fs.existsSync(full)) throw new Error(`no download ${name}`);
    const buf = fs.readFileSync(full);
    const text = buf.subarray(0, 8000).toString('utf8');
    if (/\u0000/.test(text)) return { name, bytes: buf.length, binary: true };
    return { name, bytes: buf.length, text, truncated: buf.length > 8000 };
  },

  async browser_read_clipboard() {
    return { text: await current().evaluate(() => navigator.clipboard.readText()) };
  },

  async browser_resize(input) {
    const width = Math.max(320, Math.min(2560, Number(input.width)));
    const height = Math.max(400, Math.min(1600, Number(input.height)));
    await current().setViewportSize({ width, height });
    return { width, height };
  },

  async browser_take_screenshot() {
    const page = current();
    const image = await page.screenshot(jpeg ? { type: 'jpeg', quality: 70 } : {});
    const out = { ...(await info(page)), image };
    if (screens) {
      shot += 1;
      const file = `${String(shot).padStart(3, '0')}.${jpeg ? 'jpg' : 'png'}`;
      fs.writeFileSync(path.join(screens, file), image);
      out.saved = `screens/${file}`;
    }
    return out;
  },

  async browser_close() {
    await reset();
    return { ok: true };
  },
};

async function call(name, input = {}) {
  const handler = Object.hasOwn(handlers, name) ? handlers[name] : null;
  if (!handler) return { error: `no tool "${name}"` };
  let out;
  try {
    // A call that never settles (a native drag can leave Chromium waiting
    // forever) would hold up every call queued behind it, so give up on it.
    let timer;
    const limit = new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('STUCK')), CALL_LIMIT); });
    try {
      out = await Promise.race([handler(input), limit]);
    } finally {
      clearTimeout(timer);
    }
    stuck = 0;
    if (tabs.length && name !== 'browser_close') await current().waitForTimeout(150);
  } catch (err) {
    if (err.message === 'STUCK') {
      const page = tabs.length ? current() : null;
      const quick = (p) => Promise.race([p, new Promise((r) => setTimeout(r, 2000))]).catch(() => {});
      stuck += 1;
      if (stuck >= 2) {
        // Twice in a row: the page is wedged. Start a fresh browser.
        await Promise.race([reset(), new Promise((r) => setTimeout(r, 5000))]).catch(() => {});
        browser = null; context = null; tabs.length = 0; selected = 0;
        stuck = 0;
        out = { error: `${name} did not finish within ${CALL_LIMIT / 1000} s, the second call in a row to hang, so the browser was restarted. Open the interface again with browser_navigate; what the page held in memory is gone.` };
      } else {
        if (page) { await quick(page.mouse.up()); await quick(page.keyboard.press('Escape')); }
        out = { error: `${name} did not finish within ${CALL_LIMIT / 1000} s and was abandoned; the mouse was released and Escape pressed. Take a screenshot to see the state; if the page is stuck, load it again with browser_navigate.` };
      }
      if (events.length) out = { ...out, events: events.splice(0) };
      return traced(name, input, out);
    }
    const first = err.message.split('\n')[0];
    out = { error: /Timeout|aria-ref/.test(first) && input.ref ? `${first} (the element may have been redrawn: snapshot again for a fresh ref, or use x and y)` : first };
  }
  if (events.length) out = { ...out, events: events.splice(0) };
  return traced(name, input, out);
}

function traced(name, input, out) {
  if (trace) {
    step += 1;
    let url = null;
    try { url = tabs.length ? current().url() : null; } catch {}
    const { text, ...rest } = input;
    const line = { step, t: new Date().toISOString(), tool: name, input: text === undefined ? rest : { ...rest, text: String(text).slice(0, 200) }, url };
    if (out?.saved) line.screen = out.saved;
    if (out?.error) line.error = out.error;
    if (out?.events) line.events = out.events;
    if (consoleErrors.length) line.console = consoleErrors.splice(0);
    fs.appendFileSync(trace, `${JSON.stringify(line)}\n`);
  }
  return out;
}

function result(payload) {
  const isError = Boolean(payload?.error);
  const { image, ...rest } = payload ?? {};
  const content = [{ type: 'text', text: JSON.stringify(rest, null, 2) }];
  if (image) content.push({ type: 'image', data: Buffer.from(image).toString('base64'), mimeType: jpeg ? 'image/jpeg' : 'image/png' });
  return { content, isError };
}

const send = (message) => process.stdout.write(`${JSON.stringify(message)}\n`);
const reply = (id, res) => send({ jsonrpc: '2.0', id, result: res });
const fail = (id, code, message) => send({ jsonrpc: '2.0', id, error: { code, message } });

// One call at a time, in the order they came, so a screenshot never overtakes
// the click before it.
let queue = Promise.resolve();

async function handle({ id, method, params }) {
  if (id === undefined || id === null) return;
  switch (method) {
    case 'initialize':
      return reply(id, {
        protocolVersion: params?.protocolVersion ?? '2025-06-18',
        capabilities: { tools: {} },
        serverInfo: { name: 'browser', version: '0.2.0' },
      });
    case 'ping':
      return reply(id, {});
    case 'tools/list':
      return reply(id, { tools: SCHEMAS });
    case 'tools/call':
      return reply(id, result(await call(params?.name, params?.arguments ?? {})));
    default:
      return fail(id, -32601, `no method "${method}"`);
  }
}

const rl = readline.createInterface({ input: process.stdin });
rl.on('line', (line) => {
  let message;
  try {
    message = JSON.parse(line);
  } catch {
    return;
  }
  queue = queue.then(() => handle(message)).catch((err) => fail(message.id, -32603, err.message));
});
rl.on('close', () => {
  queue.finally(() => reset().finally(() => process.exit(0)));
});
