// Check a walkthrough against the interface it walks through.
//
//   node check.mjs <app/index.html> <walkthrough.json> [--shots <folder>]
//
// Opens the page in a headless Chromium (Playwright), then goes through the
// steps in order the way the player does: clicks each step's `prep` controls,
// finds its `target`, and checks that it is on the page, shown, and the only
// visible match. With --shots it saves one picture per step with the target
// boxed, to look at. Prints one line per step and a JSON summary last; exits 1
// when any step has a problem.
//
// Playwright comes from, in order: PLAYWRIGHT_CORE (a path to playwright-core),
// node_modules/playwright-core next to this file or in the working folder,
// and the Marble Drive app's own copy.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';

const args = process.argv.slice(2);
const shotsAt = args.indexOf('--shots');
const shots = shotsAt >= 0 ? args.splice(shotsAt, 2)[1] : null;
const [page, file] = args;
if (!page || !file) { console.error('usage: node check.mjs <app/index.html> <walkthrough.json> [--shots <folder>]'); process.exit(2); }

const here = path.dirname(fileURLToPath(import.meta.url));
const tries = [
  process.env.PLAYWRIGHT_CORE,
  path.join(here, 'node_modules/playwright-core'),
  path.join(process.cwd(), 'node_modules/playwright-core'),
  path.join(process.env.MARBLE_APP || path.join(os.homedir(), '.local/share/marble-drive/app/current/marble-drive'), 'node_modules/playwright-core'),
].filter(Boolean);
let chromium = null;
for (const t of tries) {
  const entry = path.join(t, 'index.mjs');
  if (!fs.existsSync(entry)) continue;
  ({ chromium } = await import(pathToFileURL(entry).href));
  break;
}
if (!chromium) { console.error(`No playwright-core found (looked in ${tries.join(', ')}).`); process.exit(2); }

const w = JSON.parse(fs.readFileSync(file, 'utf8'));
const words = (s) => String(s || '').split(/\s+/).filter(Boolean).length;
const LIMITS = { title: 6, say: 30, do: 16 };
const problems = [];
const report = [];
if (!w.goal) problems.push('no goal');
if (!w.end) problems.push('no end');
const phases = (w.phases || []).filter((p) => (p.steps || []).length);
if (phases.length < 2 && (phases[0]?.steps || []).length < 3) problems.push('fewer than three steps');

if (shots) fs.mkdirSync(shots, { recursive: true });
const browser = await chromium.launch({ headless: true });
try {
  const tab = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  const errors = [];
  tab.on('pageerror', (e) => errors.push(String(e.message || e)));
  await tab.goto(pathToFileURL(path.resolve(page)).href, { waitUntil: 'load', timeout: 20000 });
  await tab.waitForTimeout(700);
  let n = 0;
  for (const [pi, p] of phases.entries()) {
    for (const s of p.steps) {
      n++;
      const id = `${n} (${p.name}: ${s.title || s.target})`;
      const issues = [];
      for (const k of Object.keys(LIMITS)) if (words(s[k]) > LIMITS[k]) issues.push(`${k} has ${words(s[k])} words, keep it under ${LIMITS[k] + 1}`);
      for (const sel of s.prep || []) {
        const found = await tab.evaluate((q) => { try { const e = [...document.querySelectorAll(q)].find((x) => x.getBoundingClientRect().width > 0); if (e) { e.click(); return true; } } catch (e) { return 'bad'; } return false; }, sel);
        if (found !== true) issues.push(`prep ${sel} ${found === 'bad' ? 'is not a valid selector' : 'finds nothing visible to click'}`);
        await tab.waitForTimeout(250);
      }
      const r = await tab.evaluate((q) => {
        let all;
        try { all = [...document.querySelectorAll(q)]; } catch (e) { return { bad: true }; }
        const shown = all.filter((e) => { const b = e.getBoundingClientRect(); return b.width > 0 && b.height > 0 && getComputedStyle(e).visibility !== 'hidden'; });
        const e = shown[0];
        if (e) e.scrollIntoView({ block: 'nearest' });
        const b = e?.getBoundingClientRect();
        return { total: all.length, shown: shown.length, box: b && { x: b.x, y: b.y, w: b.width, h: b.height }, tag: e?.tagName.toLowerCase(), text: (e?.innerText || e?.value || e?.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim().slice(0, 60) };
      }, s.target || '');
      if (!s.target) issues.push('no target');
      else if (r.bad) issues.push(`target ${s.target} is not a valid selector`);
      else if (!r.total) issues.push(`target ${s.target} matches nothing`);
      else if (!r.shown) issues.push(`target ${s.target} is on the page but not shown at this point`);
      else if (r.shown > 1) issues.push(`target ${s.target} matches ${r.shown} visible elements; the player rings the first`);
      if (r.box && (r.box.w > 1200 && r.box.h > 700)) issues.push('target is nearly the whole page; pick the control itself');
      if (shots && r.box) {
        await tab.evaluate((b) => { const d = document.createElement('div'); d.id = '__wt_box'; Object.assign(d.style, { position: 'fixed', left: `${b.x - 4}px`, top: `${b.y - 4}px`, width: `${b.w + 8}px`, height: `${b.h + 8}px`, outline: '3px solid #e5484d', zIndex: 2147483647, pointerEvents: 'none' }); document.body.append(d); }, r.box);
        await tab.screenshot({ path: path.join(shots, `step-${String(n).padStart(2, '0')}.png`) });
        await tab.evaluate(() => document.getElementById('__wt_box')?.remove());
      }
      const ok = !issues.filter((x) => !/visible elements/.test(x)).length;
      report.push({ step: n, phase: pi + 1, target: s.target, found: r.tag ? `<${r.tag}> ${r.text}` : null, ok, issues });
      console.log(`${ok ? 'ok  ' : 'FIX '} step ${id}${r.tag ? ` -> <${r.tag}> ${r.text}` : ''}${issues.length ? `\n     ${issues.join('\n     ')}` : ''}`);
    }
  }
  if (errors.length) problems.push(`the page threw: ${errors.slice(0, 3).join(' | ')}`);
} finally {
  await browser.close();
}
const bad = report.filter((x) => !x.ok).length + problems.length;
for (const p of problems) console.log(`FIX  ${p}`);
console.log(JSON.stringify({ steps: report.length, phases: phases.length, ok: report.length - report.filter((x) => !x.ok).length, problems, report }));
process.exit(bad ? 1 : 0);
