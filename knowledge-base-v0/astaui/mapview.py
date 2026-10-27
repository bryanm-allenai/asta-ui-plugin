"""The map: every build as a point, placed so that similar builds sit together.

``astaui map`` writes one self-contained HTML file. It can place the builds by
several representations (the whole card, the raw prompts and code, data shape
alone, and so on), so you can see which one puts together the builds you would
call the same job: the comparison the Workspace's Map section asks for. Pairs you
judged by eye are drawn as lines, and requests you pass with ``--query`` land
among their nearest builds.
"""

from __future__ import annotations

import html
import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, Sequence

from .cards import part_spans
from .index import Index
from .kb import KB
from .ontology import FACETS
from .vec import dot, place_by_neighbours, project_2d
from .workflows import StepSpace, families

CHANNELS = [
    ("card", "Card", "The whole card: summary, workflow and all five facets"),
    ("workflow", "Workflow", "The general workflow: its name and steps, in words any science could use"),
    ("structure", "Structure", "Task, data, stage and mechanism words only, with nothing from the field"),
    ("raw", "Prompts and code", "The prompts and code as they are, before any describing"),
    ("data", "Data shape", "The data facet alone"),
    ("task", "Task", "The task facet alone"),
    ("mechanism", "Mechanism", "Views, interactions and patterns"),
    ("prompt", "Prompts", "The prompts alone"),
]


def _first(app: Dict[str, Any], facet: str, lst: str) -> str:
    words = (app.get(facet) or {}).get(lst) or []
    return words[0] if words else "none"


def map_data(kb: KB, index: Index, method: str = "pca", queries: Sequence[str] = ()) -> Dict[str, Any]:
    index.ensure()
    cards = {c["id"]: c for c in kb.cards()}
    builds = {b.id: b for b in kb.builds()}
    items = []
    for bid, b in builds.items():
        card = cards.get(bid)
        app = card["app"] if card else {}
        items.append({
            "id": bid,
            "title": app.get("title") or b.title,
            "summary": app.get("summary", ""),
            "kind": b.kind or "unknown",
            "author": (b.meta.get("author") or {}).get("name", ""),
            "field": (app.get("field") or {}).get("text", "") or (b.meta.get("author") or {}).get("field", ""),
            "fieldTerm": _first(app, "field", "disciplines"),
            "verb": _first(app, "task", "verbs"),
            "shape": _first(app, "data", "shapes"),
            "stage": _first(app, "stage", "terms"),
            "pattern": _first(app, "mechanism", "patterns"),
            "facets": {f: app.get(f) for f in FACETS} if card else {},
            "prompts": [t.get("text", "") for t in b.prompts],
            "parts": [{"title": p.get("title"), "level": p.get("level"), "summary": p.get("summary", ""),
                       "spans": [{k: sp.get(k) for k in ("file", "start", "end", "role", "symbol")} for sp in part_spans(p)]}
                      for p in (card or {}).get("parts", [])],
            "entry": str(b.path / b.meta["entry"]) if b.meta.get("entry") else None,
            "carded": card is not None,
        })
    # Each build's workflow family, named by its most central member's workflow.
    family = {}
    for fam in (families(StepSpace(index, cards))["families"] if cards else []):
        label = fam["name"] if len(fam["members"]) > 1 else "none"
        for m in fam["members"]:
            family[m["id"]] = label
    for it in items:
        it["family"] = family.get(it["id"], "none")
        wf = (cards.get(it["id"]) or {}).get("app", {}).get("workflow") or {}
        it["workflow"] = wf
    qvecs = index.embed_queries(queries) if queries else []
    channels = {}
    used_method = method
    for key, label, says in CHANNELS:
        vecs = index.channel(key)
        ids = [it["id"] for it in items if it["id"] in vecs]
        if len(ids) < 2:
            continue
        pts, used_method = project_2d([vecs[i] for i in ids], method=method)
        neigh = {}
        for i in ids:
            sims = sorted(((dot(vecs[i], vecs[j]), j) for j in ids if j != i), reverse=True)[:5]
            neigh[i] = [[j, round(s, 3)] for s, j in sims]
        placed = []
        # A request is plain words, so it is only placed where builds are words too.
        for q, qv in (zip(queries, qvecs) if key in ("card", "raw", "prompt") else ()):
            sims = [dot(qv, vecs[i]) for i in ids]
            at = place_by_neighbours(sims, pts)
            if at:
                top = sorted(zip(sims, ids), reverse=True)[:3]
                placed.append({"text": q, "x": at[0], "y": at[1], "near": [[j, round(s, 3)] for s, j in top]})
        channels[key] = {"label": label, "says": says, "points": {i: [round(p[0], 4), round(p[1], 4)] for i, p in zip(ids, pts)},
                         "neighbours": neigh, "queries": placed}
    return {
        "name": kb.config.get("name", "Knowledge base"),
        "embedder": index.embedder.id,
        "method": used_method,
        "made": date.today().isoformat(),
        "items": items,
        "pairs": kb.pairs(),
        "channels": channels,
    }


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  /* In Asta: asta.css (tokens, both fonts, the parts) is put in front of this
     sheet when the page is served (__ASTA__ below). This only says how the page
     wears it: light or dark by the system's setting, depth from tone and
     strokes, never a shadow. */
  __ASTA__
  :root {
    --page: var(--color-background);
    --pane: var(--surface-pane);
    --raised: var(--surface-raised);
    --field: var(--surface-field);
    --tint: var(--surface);
    --hover: var(--surface-strong);
    --text: var(--color-text);
    --link: var(--color-link);
    --green: var(--color-interactive-primary);
    --picked: var(--color-interactive-default);
    --picked-soft: color-mix(in srgb, var(--color-green) 14%, transparent);
    --good: var(--success);
    --c1: var(--data-1); --c2: var(--data-2); --c3: var(--data-3); --other: var(--data-other);
    --r: var(--radius-xs); --r-sm: var(--radius-3xs); --r-text: var(--radius-3xs); --pill: 999px;
    --ease: cubic-bezier(.22, .61, .36, 1); --t: 160ms;
    --ui: var(--font-body-sm);
    --mono: var(--font-mono);
  }
  * { box-sizing: border-box; }
  html, body { height: 100%; margin: 0; }
  body { display: grid; grid-template-columns: minmax(0, 1fr); grid-template-rows: auto minmax(0, 1fr); background: var(--page); color: var(--text); font: 14px/1.5 var(--ui); }
  button, select, input { font: inherit; color: inherit; }
  :focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
  header { display: flex; flex-wrap: wrap; align-items: center; gap: .6rem 1rem; padding: .7rem 1rem; border-bottom: 1px solid var(--stroke); }
  h1 { margin: 0; font: 700 1.05rem/1 var(--font-heading-sm); }
  .meta { color: var(--text-muted); font-size: .85rem; }
  .controls { display: flex; flex-wrap: wrap; align-items: center; gap: .5rem .9rem; margin-left: auto; }
  /* The segmented choice as Ai2's spec sheet draws it: a pill trough, the pressed one green. */
  .seg { display: inline-flex; flex-wrap: wrap; gap: 2px; max-width: 100%; padding: 3px; border: 1px solid var(--stroke); border-radius: var(--pill); background: var(--tint); }
  .seg button { flex: none; white-space: nowrap; border: 0; background: none; padding: .22rem .7rem; border-radius: var(--pill); cursor: pointer; color: var(--text); font-size: 13px; font-weight: 600; }
  .seg button:hover { background: var(--hover); }
  .seg button[aria-pressed="true"] { background: var(--green); color: var(--color-extra-dark-teal); }
  label.inline { display: inline-flex; align-items: center; gap: .35rem; color: var(--text-muted); font-size: .9rem; }
  input[type=checkbox] { accent-color: var(--color-interactive-default); }
  select, input[type=search] { padding: .25rem .5rem; border: 1px solid var(--stroke); border-radius: var(--r-sm); background: var(--field); color: var(--text); }
  input[type=search] { width: 11rem; min-width: 0; }
  main { display: grid; grid-template-columns: minmax(0, 1fr) 24rem; min-height: 0; }
  .plotwrap { position: relative; min-height: 0; padding: .8rem; display: grid; grid-template-rows: auto minmax(0, 1fr); gap: .5rem; }
  .says { color: var(--text-muted); font-size: .85rem; }
  .legend { display: flex; flex-wrap: wrap; gap: .3rem 1rem; font-size: .85rem; color: var(--text-muted); }
  .legend i { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: .35rem; vertical-align: -1px; }
  svg.plot { width: 100%; height: 100%; background: var(--raised); border: 1px solid var(--stroke); border-radius: var(--r); }
  .dot { stroke: var(--raised); stroke-width: 2; cursor: pointer; transition: r var(--t) var(--ease); }
  .dot.dim { opacity: .25; }
  .dot.sel { stroke: var(--text); }
  .hit { fill: transparent; cursor: pointer; }
  /* A halo in the plot's own colour keeps a label legible where it crosses a line or a dot. */
  .lbl { font-size: 11.5px; fill: var(--text-muted); pointer-events: none; paint-order: stroke; stroke: var(--raised); stroke-width: 3px; stroke-linejoin: round; }
  .lbl.sel { fill: var(--text); font-weight: 600; }
  .pair { stroke: var(--text-faint); stroke-width: 1.5; fill: none; }
  .pair.related { stroke-dasharray: 4 4; }
  .pair.different { display: none; }
  .q { fill: var(--raised); stroke: var(--text); stroke-width: 2; }
  .qline { stroke: var(--text); stroke-width: 1; opacity: .35; }
  .qlbl { font-size: 11.5px; fill: var(--text); font-weight: 600; pointer-events: none; paint-order: stroke; stroke: var(--raised); stroke-width: 3px; stroke-linejoin: round; }
  .tip { position: absolute; pointer-events: none; max-width: 20rem; padding: .45rem .6rem; background: var(--raised); border: 1px solid var(--stroke);
         border-radius: var(--r-sm); font-size: .85rem; opacity: 0; transition: opacity 110ms; }
  .tip b { display: block; font-weight: 600; }
  .tip span { color: var(--text-muted); }
  aside { border-left: 1px solid var(--stroke); overflow: auto; padding: 1rem; background: var(--pane); }
  aside h2 { margin: 0 0 .2rem; font-size: 1.05rem; font-weight: 600; }
  aside h3 { margin: 1.1rem 0 .35rem; font-size: .85rem; font-weight: 600; color: var(--text-muted); }
  aside p { margin: .3rem 0; }
  .chips { display: flex; flex-wrap: wrap; gap: .25rem; }
  .chip { padding: .05rem .5rem; border: 0; border-radius: var(--r-sm); background: var(--color-extra-subtle); color: var(--color-on-extra-subtle); font-size: .8rem; }
  .facet { display: grid; grid-template-columns: 5.5rem 1fr; gap: .4rem; padding: .3rem 0; border-bottom: 1px solid var(--stroke); font-size: .9rem; }
  .facet:last-child { border-bottom: 0; }
  .facet > b { font-weight: 500; color: var(--text-muted); }
  ol.prompts { margin: 0; padding-left: 1.2rem; font-size: .88rem; }
  ol.prompts li { margin: .3rem 0; }
  .part { padding: .35rem 0; border-bottom: 1px solid var(--stroke); font-size: .88rem; }
  .part code, .where { font: 12px var(--mono); color: var(--text-muted); }
  .neigh button { display: flex; justify-content: space-between; width: 100%; padding: .3rem .45rem; border: 0; border-radius: var(--r-sm);
                  background: none; cursor: pointer; text-align: left; }
  .neigh button:hover { background: var(--hover); }
  .neigh span { color: var(--text-muted); font-variant-numeric: tabular-nums; }
  a { color: var(--link); }
  .list button { display: block; width: 100%; padding: .3rem .45rem; border: 0; border-radius: var(--r-sm); background: none; cursor: pointer; text-align: left; }
  .list button:hover { background: var(--hover); }
  .list small { color: var(--text-muted); }
  /* A narrow window stacks the plot over the details; the controls take the full width
     and the view buttons scroll sideways rather than wrapping into tall pills. */
  @media (max-width: 860px) {
    main { grid-template-columns: minmax(0, 1fr); grid-template-rows: minmax(22rem, 60vh) auto; }
    aside { border-left: 0; border-top: 1px solid var(--stroke); }
    .controls { margin-left: 0; width: 100%; }
    /* 16px keeps a phone from zooming in when a field takes focus. */
    select, input[type=search] { font-size: 16px; }
  }
</style>
</head>
<body>
<header>
  <h1>__TITLE__</h1>
  <span class="meta" id="meta"></span>
  <div class="controls">
    <div class="seg" id="channels" role="group" aria-label="Place builds by"></div>
    <label class="inline">Colour by
      <select id="colour">
        <option value="family">Workflow family</option>
        <option value="fieldTerm">Field</option>
        <option value="verb">Task</option>
        <option value="shape">Data shape</option>
        <option value="stage">Stage</option>
        <option value="pattern">Pattern</option>
        <option value="kind">Where it came from</option>
      </select>
    </label>
    <label class="inline">Find <input type="search" id="find" placeholder="a title or a word"></label>
    <label class="inline"><input type="checkbox" id="pairs" checked> Judged pairs</label>
  </div>
</header>
<main>
  <div class="plotwrap">
    <div>
      <div class="says" id="says"></div>
      <div class="legend" id="legend"></div>
    </div>
    <svg class="plot" id="plot" role="img" aria-label="Map of the builds"></svg>
    <div class="tip" id="tip"></div>
  </div>
  <aside id="side"></aside>
</main>
<script>
const DATA = __DATA__;
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const byId = Object.fromEntries(DATA.items.map((it) => [it.id, it]));
const keys = Object.keys(DATA.channels);
let channel = keys.includes("card") ? "card" : keys[0];
let colourBy = "family";
let selected = null;

$("#meta").textContent = `${DATA.items.length} builds · ${DATA.items.filter((i) => i.carded).length} with cards · ${DATA.embedder} · ${DATA.method} · ${DATA.made}`;
for (const k of keys) {
  const b = document.createElement("button");
  b.textContent = DATA.channels[k].label;
  b.dataset.k = k;
  b.title = DATA.channels[k].says;
  b.onclick = () => { channel = k; draw(); };
  $("#channels").append(b);
}
$("#colour").onchange = (e) => { colourBy = e.target.value; draw(); };
$("#find").oninput = () => draw();
$("#pairs").onchange = () => draw();

function palette() {
  // The three most common values get the three hues, in a fixed order; the rest are Other.
  const counts = {};
  for (const it of DATA.items) if (DATA.channels[channel].points[it.id]) counts[it[colourBy]] = (counts[it[colourBy]] || 0) + 1;
  const top = Object.entries(counts).filter(([v]) => v !== "none").sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, 3).map(([v]) => v);
  const slot = (v) => { const i = top.indexOf(v); return i >= 0 ? `var(--c${i + 1})` : "var(--other)"; };
  return { top, slot, other: Object.keys(counts).length > top.length };
}

function draw() {
  const ch = DATA.channels[channel];
  document.querySelectorAll("#channels button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.k === channel)));
  $("#says").textContent = `Placed by: ${ch.says.toLowerCase()}. Closer means more alike.`;
  const pal = palette();
  $("#legend").innerHTML = pal.top.map((v, i) => `<span><i style="background:var(--c${i + 1})"></i>${esc(v)}</span>`).join("")
    + (pal.other ? `<span><i style="background:var(--other)"></i>Other</span>` : "");
  const svg = $("#plot");
  const W = svg.clientWidth || 800, H = svg.clientHeight || 600, pad = 48;
  const sx = (x) => pad + x * (W - 2 * pad), sy = (y) => pad + y * (H - 2 * pad);
  const find = $("#find").value.trim().toLowerCase();
  const match = (it) => !find || [it.title, it.summary, it.field, it.verb, it.shape].join(" ").toLowerCase().includes(find);
  const ids = Object.keys(ch.points);
  let s = "";
  if ($("#pairs").checked) {
    for (const p of DATA.pairs) {
      const a = ch.points[p.a], b = ch.points[p.b];
      if (!a || !b) continue;
      s += `<line class="pair ${esc(p.judgment)}" x1="${sx(a[0])}" y1="${sy(a[1])}" x2="${sx(b[0])}" y2="${sy(b[1])}"><title>${esc(p.judgment)}: ${esc(p.note || "")}</title></line>`;
    }
  }
  for (const q of ch.queries || []) {
    for (const [j] of q.near) { const b = ch.points[j]; s += `<line class="qline" x1="${sx(q.x)}" y1="${sy(q.y)}" x2="${sx(b[0])}" y2="${sy(b[1])}"/>`; }
  }
  // Every title fits beside its dot on a wide plot; on a narrow one only the selected build is named.
  const showLabels = ids.length <= 40 && W >= 560;
  const labels = [];
  for (const id of ids) {
    const it = byId[id], [x, y] = ch.points[id];
    const cls = ["dot", match(it) ? "" : "dim", id === selected ? "sel" : ""].join(" ");
    s += `<circle class="${cls}" cx="${sx(x)}" cy="${sy(y)}" r="${id === selected ? 7 : 5.5}" fill="${pal.slot(it[colourBy])}"/>`;
    s += `<circle class="hit" data-id="${esc(id)}" cx="${sx(x)}" cy="${sy(y)}" r="14"/>`;
    if (showLabels || id === selected) labels.push({ x: sx(x), y: sy(y), text: it.title, cls: "lbl" + (id === selected ? " sel" : ""), first: id === selected });
  }
  for (const q of ch.queries || []) {
    s += `<circle class="q" cx="${sx(q.x)}" cy="${sy(q.y)}" r="6"><title>${esc(q.text)}</title></circle>`;
    labels.push({ x: sx(q.x), y: sy(q.y), text: q.text.length > 48 ? q.text.slice(0, 46) + "…" : q.text, cls: "qlbl", first: true });
  }
  s += placeLabels(labels, ids.map((id) => [sx(ch.points[id][0]), sy(ch.points[id][1])]), W, H);
  svg.innerHTML = s;
  svg.querySelectorAll(".hit").forEach((el) => {
    el.onmouseenter = (e) => tip(e, byId[el.dataset.id]);
    el.onmousemove = (e) => tip(e, byId[el.dataset.id]);
    el.onmouseleave = () => { $("#tip").style.opacity = 0; };
    el.onclick = () => { selected = el.dataset.id; draw(); side(); };
  });
  if (!selected) side();
}

// Put each label where it overlaps least: right, left, above or below its point,
// queries and the selection first. Text is measured roughly at 6.3px a character.
function placeLabels(labels, dots, W, H) {
  const boxes = dots.map(([x, y]) => [x - 7, y - 7, x + 7, y + 7]);
  const overlap = (a, b) => Math.max(0, Math.min(a[2], b[2]) - Math.max(a[0], b[0])) * Math.max(0, Math.min(a[3], b[3]) - Math.max(a[1], b[1]));
  labels.sort((a, b) => (b.first ? 1 : 0) - (a.first ? 1 : 0));
  let out = "";
  for (const l of labels) {
    const w = l.text.length * 6.3, h = 14;
    // Above and below, the label slides sideways to stay inside the plot.
    const centred = Math.min(Math.max(l.x - w / 2, 4), W - 4 - w);
    const spots = [
      [l.x + 9, l.y + 4, "start"], [l.x - 9, l.y + 4, "end"],
      [centred, l.y - 10, "start"], [centred, l.y + 18, "start"],
    ];
    let best = null;
    for (const [x, y, anchor] of spots) {
      const x0 = anchor === "start" ? x : x - w;
      const box = [x0, y - h + 3, x0 + w, y + 3];
      let cost = boxes.reduce((sum, b) => sum + overlap(box, b), 0);
      if (box[0] < 2 || box[2] > W - 2 || box[1] < 2 || box[3] > H - 2) cost += 1e6;
      if (!best || cost < best.cost) best = { x, y, anchor, box, cost };
    }
    boxes.push(best.box);
    out += `<text class="${l.cls}" x="${best.x}" y="${best.y}" text-anchor="${best.anchor}">${esc(l.text)}</text>`;
  }
  return out;
}

function tip(e, it) {
  const t = $("#tip"), box = $(".plotwrap").getBoundingClientRect();
  t.innerHTML = `<b>${esc(it.title)}</b><span>${esc(it.field || it.kind)}</span>`;
  t.style.left = Math.min(e.clientX - box.left + 14, box.width - 300) + "px";
  t.style.top = (e.clientY - box.top + 14) + "px";
  t.style.opacity = 1;
}

function facetRow(name, f) {
  if (!f) return "";
  const words = Object.entries(f).filter(([k, v]) => Array.isArray(v)).flatMap(([, v]) => v);
  return `<div class="facet"><b>${name}</b><div>${esc(f.text || "")}${f.item ? `<br><span class="meta">One item: ${esc(f.item)}</span>` : ""}
    ${words.length ? `<div class="chips">${words.map((w) => `<span class="chip">${esc(w)}</span>`).join("")}</div>` : ""}</div></div>`;
}

function side() {
  const el = $("#side");
  if (!selected) {
    el.innerHTML = `<h2>The builds</h2><p class="meta">Pick one on the map or here to see its card, its prompts and its nearest neighbours.</p>
      <div class="list">${DATA.items.map((it) => `<button data-id="${esc(it.id)}">${esc(it.title)}<br><small>${esc(it.field || it.kind)}</small></button>`).join("")}</div>`;
    el.querySelectorAll("button").forEach((b) => b.onclick = () => { selected = b.dataset.id; draw(); side(); });
    return;
  }
  const it = byId[selected], ch = DATA.channels[channel];
  const n = (ch.neighbours[selected] || []).map(([j, s]) => `<button data-id="${esc(j)}">${esc(byId[j].title)}<span>${s.toFixed(2)}</span></button>`).join("");
  el.innerHTML = `
    <p><button class="chip" id="back">All builds</button></p>
    <h2>${esc(it.title)}</h2>
    <p class="meta">${esc([it.field, it.author && "by " + it.author, it.kind + " build"].filter(Boolean).join(" · "))}</p>
    ${it.summary ? `<p>${esc(it.summary)}</p>` : `<p class="meta">No card yet: run <code>astaui extract ${esc(it.id)}</code>.</p>`}
    ${it.entry ? `<p><a href="${esc(it.entry)}" target="_blank" rel="noopener">Open the interface</a></p>` : ""}
    <h3>Nearest, placed by ${esc(ch.label.toLowerCase())}</h3><div class="neigh">${n || '<p class="meta">None</p>'}</div>
    ${it.workflow && it.workflow.name ? `<h3>Workflow</h3><p><b>${esc(it.workflow.name)}</b></p><ol class="prompts">${(it.workflow.steps || []).map((st) => `<li>${esc(st.step)}${st.here ? `<br><span class="meta">${esc(st.here)}</span>` : ""}</li>`).join("")}</ol>${(it.workflow.distinctive || []).length ? `<p class="meta">Particular to it: ${esc(it.workflow.distinctive.join("; "))}</p>` : ""}` : ""}
    ${it.carded ? `<h3>Card</h3>${facetRow("Task", it.facets.task)}${facetRow("Data", it.facets.data)}${facetRow("Stage", it.facets.stage)}${facetRow("Mechanism", it.facets.mechanism)}${facetRow("Field", it.facets.field)}` : ""}
    ${it.parts.length ? `<h3>Parts</h3>${it.parts.map((p) => `<div class="part"><b>${esc(p.title)}</b> <span class="meta">${esc(p.level)}</span><br>${esc(p.summary)}${(p.spans || []).map((sp) => `<br><code>${esc(sp.file)}:${sp.start}-${sp.end} ${esc(sp.role || "")}${sp.symbol ? " " + esc(sp.symbol) : ""}</code>`).join("")}</div>`).join("")}` : ""}
    <h3>Prompts</h3><ol class="prompts">${it.prompts.map((t) => `<li>${esc(t)}</li>`).join("")}</ol>`;
  el.querySelector("#back").onclick = () => { selected = null; draw(); side(); };
  el.querySelectorAll(".neigh button").forEach((b) => b.onclick = () => { selected = b.dataset.id; draw(); side(); });
}

addEventListener("resize", draw);
draw();
</script>
</body>
</html>
"""


def render(data: Dict[str, Any]) -> str:
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    asta = (Path(__file__).parent / "asta.css").read_text(encoding="utf-8")
    return PAGE.replace("__ASTA__", asta).replace("__TITLE__", html.escape(f"{data['name']}: map")).replace("__DATA__", blob)
