"""What each part of the console page holds, as blocks.

The page (marble.py) is a fixed skeleton: a catalog of the knowledge base's
objects on the left, a lens in the middle, an inspector on the right. Each has
slots, elements whose children are blocks. This module says what every slot
should hold, as a list of (id, markup).

Every object a person can pick (a build, a word, a test request, a pair) is
named the same way everywhere it appears, in a `data-pick` attribute: `b:<build>`,
`t:<list>:<word>`, `q:<request>`, `p:<build>|<build>`. Picking one anywhere picks
it everywhere: the catalog row, the point on the map, the cell in the grid and the
inspector all follow the one selection the page keeps.

Every block carries one id, made from what it shows, so the same thing keeps the
same id from one refresh to the next and a refresh only touches what changed.
Nothing inside a block carries an id; Marble mints those when a block lands. Every
block stays under one edit's size, because an agent can only change what it has
read whole.
"""

from __future__ import annotations

import html as _html
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote

from .atlas import CHANNELS, COLOURS, TERM_LISTS, Atlas
from .cards import part_spans, slug
from .kb import user_config

Block = Tuple[str, str]
BLOCK_LIMIT = 11000
CODE_LINES = 28
ROLE_ORDER = ("logic", "markup", "style", "data", "other")
ROLE_WORD = {"logic": "Script", "markup": "Markup", "style": "Style", "data": "Data", "other": "Other"}
FACTS = [("f", "Workflow family"), ("d", "Discipline"), ("s", "Data shape"), ("t", "Task"), ("g", "Stage"),
         ("p", "Pattern"), ("k", "Source"), ("c", "Consent")]
FACT_WORD = {"f": "workflow family", "d": "discipline", "k": "source", "c": "consent", "s": "data shape",
             "t": "task", "g": "stage", "p": "pattern"}
WORD_OF = {"data-shapes": "data shape", "task-verbs": "task", "stage-terms": "stage", "mechanism-views": "view",
           "mechanism-interactions": "interaction", "mechanism-patterns": "pattern", "field-disciplines": "discipline"}
CLI = "python3 Ai2/AstaUI/knowledge-base-v0/astaui_cli.py"
DOC_HINT = "Ai2/AstaUI/AstaUI Console.mrbl"
# What every brief that lands edits on the page says about landing them.
APPLY = ("It writes the edits that bring this page up to date as numbered batch files and prints where they are. "
         "For each batch file in order: print it whole with cat; if its \"reads\" list is not empty, read those elements first "
         "with read_document, passing the ids; then call apply_ops on this document with the batch's note and ops exactly as "
         "written. Change nothing else. If apply_ops refuses because an element changed since you read it, read that element "
         "again and apply the same batch again. If it prints that there is nothing to apply, apply nothing.")
DOC = f"--doc \"<this document's path in the drive; it was {DOC_HINT}>\""
# Where this drive answers from outside: a share link made on this computer
# names 127.0.0.1, which no scientist can reach. The owner's own setting, so it
# is not written into code anyone can read.
DRIVE_URL = os.environ.get("ASTAUI_DRIVE_URL") or user_config().get("drive-url") or "<the address this drive answers at from outside>"
MODE_WORD = {"card": "Card", "workflow": "Workflow", "structure": "Structure", "data": "Data", "summary": "Summary",
             "prompt": "Prompts", "raw": "Prompts and code"}


# Where a build came from, as the Sharing lens says it: how it came (its kind),
# who may see it (its consent) and what it was filed from (its sources).
KIND_WORD = {"study": "From the study's participants", "contributed": "Filed by the people who built them",
             "seed": "Written for the prototype"}
KIND_ORDER = ("study", "contributed", "seed")
CONSENT_WORD = {"synthetic": "Anyone (invented)", "team": "Project team", "public": "Anyone"}
SOURCE_WORD = {"prompt log": "Prompt log", "repo": "Repository", "skill file": "Skill file"}
CHECK_BRIEF = ("A scientist sent the build {id} (\"{title}\") {where}. Check it before it "
               "joins the knowledge base, as the asta-ui:review-publish skill says (Ai2/AstaUI/knowledge-base-v0/skills/"
               "review-publish/SKILL.md; read it first). From the drive's folder run `{cli} incoming --review {id}`: it copies the "
               "knowledge base with this build in it into a folder of its own and prints where. Run the skill's checks there, with "
               "`--kb <that folder>` before each command, and read the build's prompts, code, build.json and card yourself for what "
               "a program cannot catch. If anything must change, change nothing and answer with exactly what and where. If it "
               "holds, run `{cli} incoming --take {id}`, then `{cli} index`, then refresh this console: run `{cli} marble-ops "
               "refresh {doc}`. {apply} Do not commit or push. Then answer in one sentence.")
LINK_BRIEF = ("Have the AstaUI line send scientists' builds to this drive. Read kb-so-link with read_document: it should hold an "
              "Add only share link to {page} (an address ending in /s/ and 38 letters and digits). If it is empty or holds something "
              "else, change nothing and say what it holds. From the drive's folder run `{cli} config inbox-link \"<the link>\" "
              "--public {public}`: it checks that the link opens {page} from outside this computer, and saves it. If that fails, "
              "change nothing and answer with what it said. Then refresh this console: run `{cli} marble-ops refresh {doc}`. "
              "{apply} Then answer in one sentence.")

# -- markup ---------------------------------------------------------------------------------

def esc(s: Any) -> str:
    return _html.escape("" if s is None else str(s), quote=True)


def el(tag: str, inner: str = "", cls: str = "", **attrs: Any) -> str:
    a = f' class="{esc(cls)}"' if cls else ""
    for k, v in attrs.items():
        if v is None or v is False:
            continue
        name = k.rstrip("_").replace("_", "-")
        a += f" {name}" if v is True else f' {name}="{esc(v)}"'
    return f"<{tag}{a}>{inner}</{tag}>"


def tx(tag: str, s: Any, cls: str = "", **attrs: Any) -> str:
    return el(tag, esc(s), cls, **attrs)


def blk(bid: str, tag: str, inner: str = "", cls: str = "", **attrs: Any) -> Block:
    return bid, el(tag, inner, cls, **{"data-marble-id": bid}, **attrs)


def btn(inner: str, cls: str = "", **attrs: Any) -> str:
    return el("button", inner, cls, type="button", **attrs)


def pct(x: Optional[float]) -> str:
    return "–" if x is None else f"{round(x * 100)}%"


def num(x: Optional[float], d: int = 2) -> str:
    return "–" if x is None else f"{x:.{d}f}"


def plural(n: int, one: str, many: Optional[str] = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def ordinal(n: int) -> str:
    return {1: "first", 2: "second", 3: "third"}.get(n, f"{n}th")


def joined(items: Iterable[str]) -> str:
    return "; ".join(str(x).strip().rstrip(".") for x in items if str(x).strip())


def key_of(text: str) -> str:
    """A short, stable piece of an id for a word or a name."""
    return slug(text, "x")[:40]


def short_title(title: str, limit: int = 32) -> str:
    """A build's title, short enough to label a point: the name before what it is for."""
    t = (title or "").strip()
    for cut in (" for ", " before ", " with ", ": ", " — "):
        if cut in t and t.index(cut) >= 8:
            t = t[: t.index(cut)]
    if len(t) > limit:
        t = t[:limit].rsplit(" ", 1)[0] + "…"
    return t


def pair_key(a: str, b: str) -> str:
    x, y = sorted((a, b))
    return f"p:{x}|{y}"


def drive_href(path: Optional[Path]) -> Optional[str]:
    """Where the drive serves a file that is not a document: /drive/file with the
    file's path from the drive's folder, the nearest folder above it that holds the
    drive's own .marble. None when the file is in no drive."""
    if path is None:
        return None
    p = Path(path).resolve()
    for d in p.parents:
        if (d / ".marble").is_dir():
            return "/drive/file?path=" + quote(p.relative_to(d).as_posix(), safe="")
    return None


def style_blocks(prefix: str, rules: List[str]) -> List[Block]:
    """Numbers that move together (where every point sits, how alike every pair is)
    kept as CSS rules in a few <style> blocks, so that when they move it is one edit
    each and not one per point."""
    return [blk(f"{prefix}-{n}", "style", "\n".join(part)) for n, part in enumerate(chunk_rows(rules, BLOCK_LIMIT - 500), 1) if part]


def chunk_rows(rows: List[str], limit: int = BLOCK_LIMIT - 1500) -> List[List[str]]:
    out, cur, size = [], [], 0
    for r in rows:
        if cur and size + len(r) > limit:
            out.append(cur)
            cur, size = [], 0
        cur.append(r)
        size += len(r)
    if cur or not out:
        out.append(cur)
    return out


def row(pick: str, title: str, meta: str = "", n: Any = "", dot: str = "", **attrs: Any) -> str:
    """A list row: a dot when something needs saying, the name, one line of context,
    and a number on the right."""
    return btn(el("i", "", "dot", data_s=dot or None) + tx("span", title, "t") + (tx("span", meta, "m") if meta else "")
               + (tx("span", n, "n") if n != "" else ""), "row", data_pick=pick, **attrs)



def run_btn(label: str, brief: str, scope: str, cls: str = "run") -> str:
    """A button that starts an agent on a brief when pressed (the Drive runs it)."""
    return btn(esc(label), cls, data_marble_on="press", data_marble_scope=scope, data_marble_run=brief)


def day(s: Optional[str]) -> str:
    """A date as the page says it: Oct 25, 2026."""
    try:
        return datetime.strptime((s or "")[:10], "%Y-%m-%d").strftime("%b %-d, %Y")
    except ValueError:
        return s or "–"


def moment(s: Optional[str]) -> str:
    """A time as the page says it, in this computer's zone: Oct 27, 15:00."""
    try:
        t = datetime.fromisoformat(s or "")
    except ValueError:
        return s or "–"
    return (t.astimezone() if t.tzinfo else t).strftime("%b %-d, %H:%M")


def maker(author: Dict[str, Any]) -> Tuple[str, str]:
    """Who made a build: their name (a pseudonym unless they asked to be named), and their role and field."""
    return author.get("name") or "Not named", ", ".join(x for x in (author.get("role"), author.get("field")) if x)

# -- the views --------------------------------------------------------------------------------

class Views:
    """Everything the page shows, computed once and handed out slot by slot."""

    def __init__(self, console, embedder: Optional[str] = None):
        self.console = console
        self.embedder = embedder
        self.kb = console.kb()
        self._ready = False

    def prep(self) -> None:
        """The atlas and what follows from it, computed the first time a part of the
        page needs it (a search or an evaluation does not)."""
        if self._ready:
            return
        self._ready = True
        kb, console, embedder = self.kb, self.console, self.embedder
        searcher = console.searcher(embedder)
        self.atlas = Atlas(kb, searcher.index, space=console.space(embedder) if kb.card_ids() else None)
        a = self.atlas
        self.titles = {i: (a.cards[i]["app"].get("title") if i in a.cards else a.builds[i].title) for i in a.ids}
        self.short = {i: short_title(t) for i, t in self.titles.items()}
        self.layouts = a.layouts() if a.cards else {}
        self.neigh = a.neighbours(5) if a.cards else {}
        self.matrix = a.matrix() if a.cards else {"order": a.ids, "raw": {}, "scaled": {}}
        self.order = self.matrix["order"]
        self.facts = a.facts()
        self.colours = a.colour_slots()
        self.faith = a.faithfulness(self.layouts) if self.layouts else {}
        self.pairs = {pair_key(p["a"], p["b"]): p for p in kb.pairs() if p.get("a") and p.get("b")}
        self.terms = a.terms()
        self.rows = {r["id"]: r for r in console.builds(embedder)}
        self.ev = console.evaluation(embedder, run=False)
        self.requests = a.requests(self.layouts) if self.layouts else []
        self.family = a.family_of()

    def tags(self, i: str) -> str:
        return "|" + "|".join(f"{k}:{v.replace('|', ' ')}" for k, vs in self.facts[i].items() for v in vs) + "|"

    def ranks(self) -> Dict[str, Dict[str, Any]]:
        """The last evaluation's result for each test request, by id."""
        return {r["id"]: r for r in ((self.ev.get("queries") or {}).get("queries") or [])}

    # -- the catalog --------------------------------------------------------------------------
    def catalog(self) -> Dict[str, List[Block]]:
        self.prep()
        a = self.atlas
        out: Dict[str, List[Block]] = {}
        builds = []
        for i in sorted(a.ids, key=lambda i: self.titles[i].lower()):
            r = self.rows.get(i, {})
            dot = "danger" if r.get("problems") else "caution" if not r.get("card") else ""
            fam = self.family.get(i) or "no close relative"
            disc = (self.facts[i].get("d") or ["none"])[0]
            builds.append(blk(f"kb-cb-{i}", "div", row(f"b:{i}", self.titles[i], f"{disc} · {fam}", dot=dot), "item",
                              data_tags=self.tags(i)))
        out["kb-cat-builds"] = builds

        for l in self.terms:
            key = f"{l['facet']}-{l['list']}"
            rows = sorted(l["rows"], key=lambda r: (r["status"] != "proposed", not r["builds"], -len(r["builds"]), r["term"]))
            blocks, seen = [], set()
            for r in rows:
                bid = f"kb-cw-{key}-{key_of(r['term'])}"
                while bid in seen:
                    bid += "-2"
                seen.add(bid)
                if r["status"] == "proposed":
                    meta, dot = f"Proposed by {plural(len(r['builds']), 'card')}; the list lacks it", "caution"
                elif not r["builds"]:
                    meta, dot = "No build uses it yet", "ring"
                else:
                    meta, dot = r["means"], ""
                blocks.append(blk(bid, "div", row(f"t:{key}:{r['term']}", r["term"], meta, len(r["builds"]), dot), "item"))
            out[f"kb-cw-{key}"] = blocks

        ranks = self.ranks()
        reqs = []
        for q in self.kb.queries():
            r = ranks.get(q.get("id"), {})
            rank = (r.get("ranks") or {}).get("card")
            dot = "" if rank == 1 else "danger" if rank is None and r else "caution" if rank else ""
            meta = "Should find " + ", ".join(self.short.get(w, w) for w in q.get("wanted", [])) if q.get("wanted") else "Lists no build"
            if r:
                meta += " · " + ("found first" if rank == 1 else f"found {ordinal(rank)}" if rank else "missed")
            reqs.append(blk(f"kb-cq-{q['id']}", "div", row(f"q:{q['id']}", f"{q['id']} · {q.get('request', '')}", meta, dot=dot), "item"))
        out["kb-cat-reqs"] = reqs

        pairs: List[Block] = []
        judged, unjudged = self.pair_rows()
        if judged:
            pairs.append(blk("kb-cp-h", "h3", "Judged by eye", "lgroup"))
        w = self.matrix["raw"].get("w") or {}
        for key, p in judged:
            x, y = key[2:].split("|")
            sim = w.get((x, y), w.get((y, x)))
            j = p.get("judgment", "")
            pairs.append(blk(f"kb-cp-{x}--{y}", "div", row(key, f"{self.short[x]} and {self.short[y]}",
                                                          f"{'The same' if j == 'same' else j.capitalize()}" + (f": {p['note']}" if p.get("note") else ""),
                                                          num(sim), dot=f"j-{j}"), "item"))
        if unjudged:
            pairs.append(blk("kb-cs-h", "h3", "Alike by workflow, not judged yet", "lgroup"))
        for s, x, y in unjudged:
            x, y = sorted((x, y))
            pairs.append(blk(f"kb-cs-{x}--{y}", "div", row(pair_key(x, y), f"{self.short[x]} and {self.short[y]}",
                                                          "Judge them by eye for the evaluation", num(s), dot="ring"), "item"))
        out["kb-cat-pairs"] = pairs
        return out

    def pair_rows(self) -> Tuple[List[Tuple[str, Dict[str, Any]]], List[Tuple[float, str, str]]]:
        """The Pairs list: the pairs judged by eye whose builds are both here, the same
        first, then the eight most alike by workflow that nobody has judged yet."""
        order = ("same", "related", "different")
        judged = sorted(((k, p) for k, p in self.pairs.items() if all(b in self.short for b in k[2:].split("|"))),
                        key=lambda kv: (order.index(kv[1]["judgment"]) if kv[1].get("judgment") in order else 3, kv[0]))
        w = self.matrix["raw"].get("w") or {}
        unjudged = sorted(((s, x, y) for (x, y), s in w.items() if pair_key(x, y) not in self.pairs), reverse=True)[:8]
        return judged, unjudged

    # -- home: what needs a decision, and what the knowledge base is ----------------------------
    def home(self) -> Dict[str, List[Block]]:
        self.prep()
        a = self.atlas
        o = self.console.overview(self.embedder)
        items: List[Tuple[int, str, str, str, str, str, Dict[str, Any]]] = []   # (order, key, level, title, why, action, attrs)
        for r in self.rows.values():
            if not r.get("card"):
                items.append((1, f"nocard-{r['id']}", "caution", f"{r['title']} has no card",
                              f"Without one it cannot be found. Write it with {CLI} extract {r['id']}.", "Open the build", {"data_pick": f"b:{r['id']}"}))
            elif r.get("problems"):
                items.append((0, f"card-{r['id']}", "danger", f"{r['title']}'s card has {plural(r['problems'], 'problem')}",
                              f"{CLI} card check {r['id']} says what to fix.", "Open the build", {"data_pick": f"b:{r['id']}"}))
        from .privacy import scan_build
        for b in a.builds.values():
            found = scan_build(b)
            must = [f for f in found if f.level == "block"]
            look = [f for f in found if f.level != "block"]
            if must:
                items.append((0, f"private-{b.id}", "danger", f"{self.titles[b.id]} holds something private",
                              f"{must[0].what} in {must[0].file}:{must[0].line}. It must go before the build is shared.", "Open the build", {"data_pick": f"b:{b.id}"}))
            elif look:
                items.append((2, f"look-{b.id}", "caution", f"{self.titles[b.id]} has {plural(len(look), 'thing')} to look at before sharing",
                              f"{look[0].what} in {look[0].file}:{look[0].line}.", "Open the build", {"data_pick": f"b:{b.id}"}))
        if not o["index"].get("fresh"):
            items.append((1, "index", "caution", "The vectors are out of date", "The map, the grid and search use the old ones until Refresh rebuilds them.",
                          "", {}))
        for l in self.terms:
            key = f"{l['facet']}-{l['list']}"
            for r in l["rows"]:
                if r["status"] == "proposed":
                    items.append((2, f"prop-{key}-{key_of(r['term'])}", "caution", f"“{r['term']}” was proposed as a {WORD_OF.get(key, 'word')}",
                                  f"{plural(len(r['builds']), 'card')} {'uses' if len(r['builds']) == 1 else 'use'} it and the list lacks it. Add it, or merge it into a word the list has.",
                                  "Decide", {"data_pick": f"t:{key}:{r['term']}"}))
        ranks = self.ranks()
        if self.ev.get("never"):
            items.append((3, "eval", "", "The evaluation has not run with this embedder", "It measures how often search finds what each test request wants.",
                          "Open Evaluation", {"data_go": "eval"}))
        for qid, r in ranks.items():
            rank = (r.get("ranks") or {}).get("card")
            if rank != 1:
                want = ", ".join(self.short.get(w, w) for w in r.get("wanted", []))
                items.append((3, f"miss-{qid}", "caution" if rank else "danger",
                              f"Test request {qid} " + (f"finds {want} {ordinal(rank)}, not first" if rank else f"misses {want}"),
                              r.get("request", "")[:140] + ("…" if len(r.get("request", "")) > 140 else ""), "See the request", {"data_pick": f"q:{qid}"}))
        w = self.matrix["raw"].get("w") or {}
        close = sorted(((s, x, y) for (x, y), s in w.items() if pair_key(x, y) not in self.pairs), reverse=True)[:3]
        for s, x, y in close:
            items.append((4, f"judge-{min(x, y)}--{max(x, y)}", "", f"{self.short[x]} and {self.short[y]} read alike and are not judged",
                          f"{num(s)} alike by workflow. Judging them by eye gives the evaluation one more pair.", "Judge the pair", {"data_pick": pair_key(x, y)}))
        unused = sum(1 for l in self.terms for r in l["rows"] if r["status"] == "vocab" and not r["builds"])
        if unused:
            items.append((5, "unused", "", f"{plural(unused, 'word')} in the ontology no build uses",
                          "They are kept for builds to come; retire the ones that will never fit.", "Open Coverage", {"data_go": "coverage"}))
        items.sort(key=lambda t: (t[0], t[1]))
        attn: List[Block] = []
        for _, key, level, title, why, action, attrs in items[:14]:
            act = btn(esc(action), "link", **attrs) if action else ""
            attn.append(blk(f"kb-at-{key_of(key)}", "div", el("i", "", "dot", data_s=level or None)
                            + el("div", tx("b", title) + tx("p", why), "atext") + act, "att"))
        if len(items) > 14:
            attn.append(blk("kb-at-more", "p", esc(f"And {len(items) - 14} more of the same kinds."), "muted small"))
        if not attn:
            attn.append(blk("kb-at-none", "p", "Nothing needs a decision.", "muted"))

        c = o["counts"]
        fams = [f for f in a.families()["families"] if len(f["members"]) > 1] if a.cards else []
        words = sum(1 for l in self.terms for r in l["rows"] if r["status"] == "vocab")
        tiles = [("builds", "Builds", c["builds"], {"data_cat_to": "builds"}),
                 ("families", "Workflow families", len(fams), {"data_go": "workflows"}),
                 ("words", "Words in the ontology", words, {"data_cat_to": "words"}),
                 ("parts", "Parts with their code", c["parts"], {"data_go": "home", "data_go_to": "kb-home-code"}),
                 ("queries", "Test requests", c["queries"], {"data_cat_to": "reqs"}),
                 ("pairs", "Pairs judged by eye", c["pairs"], {"data_cat_to": "pairs"})]
        glance = [blk(f"kb-gl-{k}", "button", tx("b", v) + tx("span", label), "tile", type="button", **attrs) for k, label, v, attrs in tiles]

        comp = a.composition()
        charts = []
        for key, title in (("d", "Disciplines"), ("f", "Workflow families"), ("s", "Data shapes"), ("t", "Tasks"),
                           ("g", "Stages"), ("p", "Patterns"), ("k", "Where they came from"), ("c", "Consent")):
            buckets = comp[key]
            if not buckets:
                continue
            top = max(len(ids) for _, ids in buckets) or 1
            # Every bar, biggest first: the page shows as many as fit the panel
            # and counts the rest under the chart ("4 more in Filter").
            bars = "".join(btn(tx("span", v, "bl") + el("span", el("i", "", "", style=f"--v:{round(len(ids) / top, 3)}"), "bt") + tx("span", len(ids), "bn num"),
                               "bar", data_filter=f"{key}:{v}") for v, ids in buckets)
            charts.append(blk(f"kb-mk-c-{key}", "div", tx("h3", title) + el("div", bars, "bars"), "chart"))

        code = comp["code"]
        topl = max((x["lines"] for x in code), default=1) or 1
        legend = "".join(el("span", el("i", "", f"sw r-{r}") + tx("span", ROLE_WORD[r]), "lgi") for r in ROLE_ORDER[:3]) + \
            el("span", el("i", "", "sw r-rest") + tx("span", "Data and other"), "lgi") + \
            el("span", el("i", "", "sw track") + tx("span", "Lines no part points at"), "lgi") + \
            el("span", el("i", "", "sw tick") + tx("span", "One part's slice"), "lgi")
        code_blocks = [blk("kb-mk-code-head", "div", tx("p", "Each bar is a build's main file. The coloured part is the code its parts point at, by role; "
                                                          "the mark is the median size of the slice a search hands back for one part, helpers included.", "muted small")
                           + el("div", legend, "lg on"), "chart-head")]
        for x in sorted(code, key=lambda x: -x["lines"]):
            segs = ""
            for r in ROLE_ORDER:
                n = x["roles"].get(r, 0)
                if n:
                    segs += el("i", "", f"r-{r}" if r in ROLE_ORDER[:3] else "r-rest", style=f"--v:{round(n / topl, 4)}")
            tick = el("b", "", "tick", style=f"--v:{round(min(x['slice_median'], x['lines'] or 1) / topl, 4)}") if x["slice_median"] else ""
            say = (f"{x['lines']} lines; parts point at {sum(x['roles'].values())}; a part's slice is about {x['slice_median']}"
                   if x["lines"] else "No main file")
            bar = el("span", el("span", "", "track", style=f"--v:{round(x['lines'] / topl, 4)}") + el("span", segs, "segs") + tick, "cbar")
            code_blocks.append(blk(f"kb-mk-r-{x['id']}", "div", btn(esc(self.short[x["id"]]), "nb", data_pick=f"b:{x['id']}") + bar + tx("span", say, "small muted"), "crow"))

        return {"kb-home-attn": attn, "kb-home-glance": glance, "kb-home-make": charts, "kb-home-code": code_blocks,
                "kb-home-keeps": self.inventory(o)}

    def inventory(self, o: Dict[str, Any]) -> List[Block]:
        """The kinds of record the knowledge base keeps, how many, and where each lives."""
        c = o["counts"]
        prompts = sum(len(b.prompts) for b in self.atlas.builds.values())
        files = sum(len(b.code_files()) for b in self.atlas.builds.values())
        words = sum(1 for l in self.terms for r in l["rows"] if r["status"] == "vocab")
        rows = [
            ("builds", "Builds", c["builds"], "An interface a scientist made with a coding agent: what they asked for, and the code that came back.", "kb/builds/<id>/build.json"),
            ("prompts", "Prompts", prompts, "Each turn of what the scientist asked the agent, in order.", "kb/builds/<id>/prompts.jsonl"),
            ("code", "Code files", files, "The interface itself, as the agent left it.", "kb/builds/<id>/code/"),
            ("cards", "Cards", c["cards"], "What a build is: a summary, five facets in the ontology's words, a workflow, and its parts.", "kb/cards/<id>.json"),
            ("parts", "Parts and spans", f"{c['parts']} / {c['spans']}", "The views and components inside a build, each pointing at the lines that make it.", "inside each card"),
            ("steps", "Workflow steps", c["steps"], "Each step said twice: as a general move, and as this build does it.", "inside each card"),
            ("words", "Ontology words", f"{words} in {len(self.terms)} lists", "The words cards describe builds with, each with its meaning and other words that count as it.", "kb/ontology.json"),
            ("queries", "Test requests", c["queries"], "Requests a scientist might make, each with the builds it should find.", "kb/eval/queries.jsonl"),
            ("pairs", "Judged pairs", c["pairs"], "Two builds judged by eye as the same, related or different.", "kb/eval/pairs.jsonl"),
            ("vectors", "Vectors", o["index"].get("vectors", 0), "Embeddings of every card, step and prompt, one set per embedder. A cache, never committed.", "kb/.index/"),
            ("log", "Search log", o["activity"]["searches"], "Searches run through the plugin, and whether what came back helped. Stays on this machine.", "kb/.usage/"),
        ]
        return [blk(f"kb-ov-k-{key}", "div", el("div", tx("b", name) + tx("span", n, "num"), "kname") + tx("p", what, "kwhat")
                    + el("div", tx("code", where), "kwhere"), "krow") for key, name, n, what, where in rows]

    # -- the map ------------------------------------------------------------------------------
    def map(self) -> Dict[str, List[Block]]:
        self.prep()
        a = self.atlas
        if not self.layouts:
            return {"kb-map-pts": [], "kb-map-legend": [], "kb-map-chan": [], "kb-map-pos": []}
        sides = {key: self.label_sides(lay) for key, lay in self.layouts.items()}
        pts: List[Block] = []
        rules: List[str] = []
        for i in a.ids:
            rules.append(f'.pt[data-pick="b:{i}"]{{' + ";".join(f"--{k}x:{v[i][0]};--{k}y:{v[i][1]}" for k, v in self.layouts.items() if i in v) + "}")
            attrs: Dict[str, Any] = {"data_pick": f"b:{i}", "data_title": self.short[i]}
            for opt, _ in COLOURS:
                attrs[f"data_s{opt}"] = self.colours[opt]["slot"].get(i, 0)
            for k in self.layouts:
                if sides[k].get(i, "r") != "r":
                    attrs[f"data_l{k}"] = sides[k][i]
                nb = (self.neigh.get(i) or {}).get(k)
                if nb:
                    attrs[f"data_n{k}"] = " ".join(j for j, _ in nb[:3])
            attrs["data_tags"] = self.tags(i)
            pts.append(blk(f"kb-pt-{i}", "button", el("span", "", "dot") + tx("span", self.short[i], "lab"), "pt", type="button", **attrs))
        for q in self.requests:
            if not q["pos"]:
                continue
            rules.append(f'.rq[data-pick="q:{q["id"]}"]{{' + ";".join(f"--{k}x:{x};--{k}y:{y}" for k, (x, y) in q["pos"].items()) + "}")
            attrs = {"data_pick": f"q:{q['id']}", "data_in": "".join(q["pos"]), "data_want": " ".join(q["wanted"])}
            for k, j in q["nearest"].items():
                attrs[f"data_n{k}"] = j
            pts.append(blk(f"kb-rq-{q['id']}", "button", el("span", "", "dot") + tx("span", q["id"], "lab"), "rq", type="button", **attrs))

        # Place, the default colour, first: a wheel of the colours a dot takes by where it sits.
        legends = [blk("kb-lg-n", "div", el("span", el("i", "", "sw wheel") + tx("span", "Builds near each other share a colour"), "lgi"), "lg", data_o="n")]
        for opt, label in COLOURS:
            c = self.colours[opt]
            items = [btn(el("i", "", f"sw s{n}") + tx("span", v) + tx("span", c["count"][v], "faint"), "lgi", data_filter=f"{opt}:{v}")
                     for n, v in enumerate(c["top"], 1)]
            if c["other"]:
                word = "no close relative, or a smaller family" if opt == "f" else "everything else"
                items.append(el("span", el("i", "", "sw s0") + tx("span", "Other: " + word) + tx("span", c["other"], "faint"), "lgi"))
            legends.append(blk(f"kb-lg-{opt}", "div", "".join(items), "lg", data_o=opt))
        legends.append(blk("kb-lg-req", "div", el("span", el("i", "", "sw ring") + tx("span", "A test request, placed among the builds it is most like"), "lgi"), "lg lg-req"))

        chan = []
        for key, name, label, says in CHANNELS:
            if key not in self.layouts:
                continue
            f = self.faith.get(key)
            keep = (f" This flat picture keeps {pct(f)} of each build's three nearest neighbours; "
                    "the inspector lists the true ones.") if f is not None else ""
            chan.append(blk(f"kb-mc-{key}", "p", esc(f"{label}: {says[0].lower() + says[1:]}.{keep}"), "cap", data_k=key))
        return {"kb-map-pts": pts, "kb-map-legend": legends, "kb-map-chan": chan, "kb-map-pos": style_blocks("kb-pos", rules)}

    def label_sides(self, layout: Dict[str, Tuple[float, float]], size: float = 560.0) -> Dict[str, str]:
        """Which side of its point each label sits on, so labels overlap as little as
        they can on a plot about `size` pixels across."""
        placed: List[Tuple[float, float, float, float]] = []
        dots = [(x * size, y * size) for x, y in layout.values()]
        out = {}
        for i in sorted(layout, key=lambda i: (layout[i][1], layout[i][0])):
            x, y = layout[i][0] * size, layout[i][1] * size
            w, h = len(self.short.get(i, i)) * 6.6 + 8, 16
            best = None
            for side in ("r", "l", "a", "b"):
                if side == "r":
                    box = (x + 9, y - h / 2, x + 9 + w, y + h / 2)
                elif side == "l":
                    box = (x - 9 - w, y - h / 2, x - 9, y + h / 2)
                elif side == "a":
                    box = (x - w / 2, y - 9 - h, x + w / 2, y - 9)
                else:
                    box = (x - w / 2, y + 9, x + w / 2, y + 9 + h)
                cost = 0.0
                for p in placed:
                    ox = max(0.0, min(box[2], p[2]) - max(box[0], p[0]))
                    oy = max(0.0, min(box[3], p[3]) - max(box[1], p[1]))
                    cost += ox * oy
                for dx, dy in dots:
                    if box[0] - 5 < dx < box[2] + 5 and box[1] - 5 < dy < box[3] + 5 and (dx, dy) != (x, y):
                        cost += 120
                cost += 4 * (max(0.0, -box[0]) + max(0.0, box[2] - size) + max(0.0, -box[1]) + max(0.0, box[3] - size)) * h
                cost += {"r": 0, "l": 1, "a": 2, "b": 3}[side]
                if best is None or cost < best[0]:
                    best = (cost, side, box)
            out[i] = best[1]
            placed.append(best[2])
        return out

    # -- similarity ---------------------------------------------------------------------------
    def similarity(self) -> Dict[str, List[Block]]:
        self.prep()
        m = self.matrix
        order = self.order[:40]
        n = len(order)
        if n < 2 or not m["scaled"]:
            return {"kb-mx-grid": [], "kb-mx-legend": [], "kb-mx-vals": []}
        style = f"--n:{n}"
        head = el("span", "", "corner") + "".join(
            el("span", btn(tx("span", self.short[j]), "chb", data_pick=f"b:{j}"), "ch", id=f"mx-c-{j}") for j in order)
        blocks = [blk("kb-mx-head", "div", head, "mrow mhead", style=style, data_bs=" ".join(order))]
        for i in order:
            cells = []
            for j in order:
                if i == j:
                    cells.append(el("span", "", "cell self"))
                    continue
                p = pair_key(i, j)
                judged = self.pairs.get(p)
                cells.append(btn("", "cell", data_pick=p, data_c=j, aria_labelledby=f"mx-r-{i} mx-c-{j}",
                                 data_j=judged.get("judgment") if judged else None,
                                 data_jn=(judged.get("note") or None) if judged else None))
            rowh = btn(tx("span", self.short[i]), "rh", id=f"mx-r-{i}", data_pick=f"b:{i}")
            blocks.append(blk(f"kb-mx-r-{i}", "div", rowh + "".join(cells), "mrow", style=style, data_b=i))
        cell_rules = []
        for x in range(n):
            for y in range(x + 1, n):
                pr = tuple(sorted((order[x], order[y])))
                cell_rules.append(f'.cell[data-pick="{pair_key(*pr)}"]{{' + ";".join(f"--v{k}:{round(m['scaled'][k][pr], 3)}" for k in m["scaled"] if pr in m["scaled"][k]) + "}")
        legends = []
        for key, name, label, says in CHANNELS:
            vals = m["raw"].get(key)
            if not vals:
                continue
            lo, hi = min(vals.values()), max(vals.values())
            steps = "".join(el("i", "", "", style=f"--v:{v}") for v in (0, .25, .5, .75, 1))
            legends.append(blk(f"kb-ml-{key}", "div", tx("span", f"{label}: least alike", "faint") + tx("span", num(lo), "num")
                               + el("span", steps, "ramp") + tx("span", num(hi), "num") + tx("span", "most alike", "faint"),
                               "mlg", data_k=key, data_lo=round(lo, 4), data_hi=round(hi, 4)))
        return {"kb-mx-grid": blocks, "kb-mx-legend": legends, "kb-mx-vals": style_blocks("kb-mxv", cell_rules)}

    def pair_block(self, a: str, b: str) -> Block:
        ps = self.atlas.pair_steps(a, b)
        bits = [tx("h3", "Their workflows, step by step")]
        defining = [s for s in ps["shared"] if not s["common"]]
        common = [s for s in ps["shared"] if s["common"]]
        if not ps["shared"]:
            bits.append(tx("p", "No step in common.", "muted small"))
        for s in defining + common:
            same = s["a"] == s["b"]
            step = tx("div", s["a"] if same else f"{s['a']} / {s['b']}", "stp") + (tx("span", "most builds do this", "faint small") if s["common"] else "")
            bits.append(el("div", step + el("div", tx("span", self.short[a], "who") + tx("span", s["a_here"]), "how")
                           + el("div", tx("span", self.short[b], "who") + tx("span", s["b_here"]), "how"), "shared"))
        own = []
        if ps["only_a"]:
            own.append(f"{self.short[a]} has {plural(ps['only_a'], 'step')} of its own")
        if ps["only_b"]:
            own.append(f"{self.short[b]} has {plural(ps['only_b'], 'step')} of its own")
        if own:
            bits.append(tx("p", "; ".join(own) + ".", "muted small"))
        html = "".join(bits)
        if len(html) > BLOCK_LIMIT - 300:
            html = "".join(bits[:4]) + tx("p", "The rest is in the Workflows view.", "muted small")
        return blk(f"kb-mp-{a}--{b}", "div", html, "pair", data_for=pair_key(a, b))

    # -- coverage: which builds use which words ------------------------------------------------------
    def coverage(self) -> Dict[str, List[Block]]:
        self.prep()
        a = self.atlas
        order = self.order
        out: Dict[str, List[Block]] = {}
        for l in self.terms:
            key = f"{l['facet']}-{l['list']}"
            rows = sorted(l["rows"], key=lambda r: (r["status"] != "proposed", not r["builds"], -len(r["builds"]), r["term"]))
            used = sum(1 for r in rows if r["status"] == "vocab" and r["builds"])
            unused = sum(1 for r in rows if r["status"] == "vocab" and not r["builds"])
            proposed = sum(1 for r in rows if r["status"] == "proposed")
            stats = f"{plural(used + unused, 'word')} in the list: {used} used, {unused} not yet" + (f"; {proposed} proposed by cards" if proposed else "") + "."
            rule = ("An open list: a card may use a word it lacks." if l["open"]
                    else "A closed list: a word a card needs and the list lacks is kept on the card and proposed here.")
            out[f"kb-cov-{key}-head"] = [blk(f"kb-th-{key}", "div", tx("h3", l["label"]) + tx("p", l["says"] + ". " + stats, "muted")
                                             + tx("p", rule, "faint small"), "thead")]
            style = f"--n:{len(order)}"
            cols = el("span", "", "corner") + "".join(el("span", btn(tx("span", self.short[i]), "chb", data_pick=f"b:{i}"), "ch") for i in order) \
                + el("span", tx("span", "Builds"), "ch cnt")
            blocks = [blk(f"kb-tc-{key}", "div", cols, "trow tcols", style=style, data_bs=" ".join(order))]
            seen = set()
            for r in rows:
                tid = f"kb-tr-{key}-{key_of(r['term'])}"
                while tid in seen:
                    tid += "-2"
                seen.add(tid)
                status = r["status"] if r["status"] == "proposed" else ("vocab" if r["builds"] else "unused")
                cells = "".join(el("i", "", "y" if i in r["builds"] else "") for i in order)
                name = tx("b", r["term"]) + (tx("small", r["means"]) if r["means"] else tx("small", "Proposed by a card; not in the list yet", "prop") if status == "proposed" else "")
                blocks.append(blk(tid, "div", btn(name, "tn", data_pick=f"t:{key}:{r['term']}") + el("span", cells, "cells") + tx("span", len(r["builds"]), "ct num"),
                                  "trow", style=style, data_t=r["term"], data_st=status, data_also="|".join(r["also"]) or None))
            out[f"kb-cov-{key}-rows"] = blocks

        ont = a.ont
        weights = ont.weights()
        top = max(weights.values()) or 1
        says = {f: (ont.facets[f].get("says") or "") for f in ont.facets}
        says["summary"] = "The card's summary, in a few plain sentences."
        says["workflow"] = "The general workflow: its name and steps."
        wblocks = []
        for f in ("task", "data", "stage", "mechanism", "field", "workflow", "summary"):
            w = weights.get(f, 0)
            wblocks.append(blk(f"kb-tw-{f}", "div", el("div", tx("b", f.capitalize()) + tx("span", num(w), "num"), "wname")
                               + el("span", el("i", "", "", style=f"--v:{round(w / top, 3)}"), "wbar") + tx("p", says.get(f, ""), "muted small")
                               + btn("Change the weight", "link", data_queue="set-weight", data_facet=f, data_pre_weight=num(w)), "weight"))
        out["kb-cov-weights"] = wblocks
        log = []
        for c in reversed(ont.data.get("changes", [])):
            v = str(c.get("version", ""))
            log.append(blk(f"kb-ol-{key_of(v)}", "li", tx("b", f"Version {v}") + tx("span", " · " + str(c.get("date", "")) + (f" · {c['by']}" if c.get("by") else ""), "faint small")
                           + tx("div", c.get("change", "")) + tx("div", "Because: " + str(c.get("because", "")), "muted small")))
        out["kb-cov-log"] = log
        return out

    # -- workflows ------------------------------------------------------------------------------
    def workflows(self) -> Dict[str, List[Block]]:
        self.prep()
        a = self.atlas
        if not a.cards:
            return {"kb-wf-body": [], "kb-wf-fams": []}
        fams = a.families()
        out = [blk("kb-wf-intro", "p", esc(
            f"Two steps count as the same move when their similarity stands out against every step comparison in the knowledge base "
            f"(above {num(fams.get('step_threshold'))} here). A family is builds whose workflows share enough moves that are not common to all."),
            "muted small")]
        # The Workflows lens shows one family at a time, chosen by number in its bar
        # (data-fam on kb-wf-tools; none means the first).
        picks: List[Block] = []
        for fi, fam in enumerate(a.alignments(), 1):
            members = fam["members"]
            head = el("tr", tx("th", "Step") + "".join(
                el("th", btn(esc(self.short[m]), "nb", data_pick=f"b:{m}"), "central" if m == fam["central"] else "", data_b=m)
                for m in members))
            rows = ""
            for r in fam["rows"]:
                n = len(r["cells"])
                kind = {"common": "most builds do this", "shared": f"all {n}", "some": f"{n} of {len(members)}", "own": "only one"}[r["kind"]]
                cells = "".join((el("td", tx("span", self.short[m], "who") + esc(r["cells"][m]), data_b=m) if m in r["cells"]
                                 else el("td", tx("span", self.short[m], "who") + tx("span", "does not", "faint small"), "none", data_b=m))
                                for m in members)
                rows += el("tr", el("th", tx("span", r["step"]) + tx("small", kind, "kind"), "", scope="row") + cells, data_kind=r["kind"])
            dist = "".join(el("td", tx("span", self.short[m], "who") + (el("ul", "".join(tx("li", d) for d in fam["distinctive"].get(m, [])), "plain small")
                                                                         if fam["distinctive"].get(m) else tx("span", "Nothing written", "faint small")), data_b=m)
                           for m in members)
            rows += el("tr", el("th", tx("span", "Particular to it"), "", scope="row") + dist, data_kind="own-case")
            table = el("table", el("thead", head) + el("tbody", rows), "align", style=f"--n:{len(members)}")
            title = el("h3", esc(fam["name"]) + tx("span", f" · {plural(len(members), 'build')}", "faint small"))
            html = title + table
            if len(html) > BLOCK_LIMIT:
                html = title + tx("p", "This family is too large to line up here; see `astaui workflows`.", "muted")
            out.append(blk(f"kb-wf-f-{key_of(fam['name'])}-{key_of(fam['central'])}", "div", html, "family", data_members=" ".join(members), data_fi=fi))
            picks.append(blk(f"kb-wf-fb-{fi}", "button", tx("span", fam["name"]) + tx("small", plural(len(members), "build"), "faint"), "",
                             type="button", title=fam["name"], data_set="fam", data_to=str(fi), data_default=fi == 1))
        alone = [f["members"][0] for f in fams["families"] if len(f["members"]) == 1]
        if alone:
            items = "".join(el("li", btn(esc(m["title"]), "nb", data_pick=f"b:{m['id']}") + tx("span", " · " + m["name"], "muted small"))
                            for m in alone)
            fi = len(picks) + 1
            out.append(blk("kb-wf-alone", "div", tx("h3", "No close relative yet") + el("ul", items, "plain"), "family", data_fi=fi))
            picks.append(blk(f"kb-wf-fb-{fi}", "button", tx("span", "No close relative yet") + tx("small", plural(len(alone), "build"), "faint"), "",
                             type="button", data_set="fam", data_to=str(fi), data_default=fi == 1))
        if fams.get("common_moves"):
            out.append(blk("kb-wf-common", "p", esc("Moves most builds have, so they do not make a family: " + "; ".join(fams["common_moves"])), "muted small"))
        return {"kb-wf-body": out, "kb-wf-fams": picks}

    # -- the inspector -------------------------------------------------------------------------------
    def inspector(self) -> Dict[str, List[Block]]:
        self.prep()
        a = self.atlas
        blocks: List[Block] = []
        ranks = self.ranks()
        wanted_by: Dict[str, List[str]] = {}
        for q in self.kb.queries():
            for w in q.get("wanted", []):
                wanted_by.setdefault(w, []).append(q["id"])
        for i in a.ids:
            blocks.extend(self.build_blocks(i, wanted_by.get(i, [])))
        reqs = {q["id"]: q for q in self.requests}
        qblocks = [self.request_block(q, reqs.get(q["id"]), ranks.get(q["id"])) for q in self.kb.queries()]
        pblocks = []
        ids = [i for i in self.order if i in a.space.vecs]
        close = set()
        for i in ids:
            close |= {pair_key(i, j) for j, _ in (self.neigh.get(i) or {}).get("w", [])[:4]}
        for x in range(len(ids)):
            for y in range(x + 1, len(ids)):
                p, q = sorted((ids[x], ids[y]))
                if len(ids) > 20 and pair_key(p, q) not in close and pair_key(p, q) not in self.pairs and not (self.family.get(p) and self.family.get(p) == self.family.get(q)):
                    continue
                pblocks.append(self.pair_block(p, q))
        return {"kb-insp-b": blocks, "kb-insp-q": qblocks, "kb-insp-p": pblocks}

    def build_blocks(self, i: str, wanted_by: List[str]) -> List[Block]:
        a = self.atlas
        card = a.cards.get(i)
        app = card["app"] if card else {}
        f = self.facts[i]
        r = self.rows.get(i, {})
        status = ("No card yet." if not card else f"Its card has {plural(r['problems'], 'problem')}." if r.get("problems") else "")
        head = el("header", tx("h2", self.titles[i]) + tx("p", f"{i} · {(app.get('field') or {}).get('text', '')}", "meta")
                  + (tx("p", status, "warn small") if status else ""), "ih")
        facts = ""
        for key, label in FACTS:
            vals = [v for v in (f.get(key) or []) if v]
            if vals:
                facts += el("div", tx("dt", label) + el("dd", "".join(btn(esc(v), "fact", data_filter=f"{key}:{v}") for v in vals)))
        acts = el("div", btn("On the map", "link", data_go="map") + btn("In the grid", "link", data_go="similar")
                  + btn("Its words", "link", data_go="coverage") + btn("Its family", "link", data_go="workflows"), "acts")
        rows = ""
        for key, name, label, _ in CHANNELS:
            nb = (self.neigh.get(i) or {}).get(key)
            if nb:
                rows += el("tr", tx("th", label) + el("td", "".join(btn(esc(self.short[j]) + tx("span", num(s), "num"), "nb", data_pick=f"b:{j}") for j, s in nb[:3])), data_k=key)
        near = (tx("h3", "Nearest, by each representation") + el("table", rows, "near")) if rows else ""
        # Its screenshot, last in the markup and first on the page (marble_shots.css), so
        # a page that predates it takes it as one insert.
        href = drive_href(a.builds[i].screenshot()) if i in a.builds else None
        shot = (el("a", f'<img src="{esc(href)}" alt="{esc(f"Screenshot of {self.titles[i]}, as it first opens")}" loading="lazy" decoding="async">',
                   "shot", href=href, target="_blank", rel="noopener", title="Open the screenshot full size") if href else "")
        first = blk(f"kb-ib-{i}", "div", head + el("dl", facts, "facts") + acts + near + shot, "ib", data_for=f"b:{i}")
        if not card:
            return [first]
        wf = app.get("workflow") or {}
        inner = [tx("h3", "What it is"), tx("p", app.get("summary", ""))]
        if wf.get("steps"):
            inner.append(tx("h3", "Workflow: " + wf.get("name", "")))
            inner.append(el("ol", "".join(el("li", tx("span", s["step"]) + tx("div", s.get("here", ""), "here")) for s in wf["steps"]), "steps"))
        if wf.get("distinctive"):
            inner.append(tx("h3", "Particular to this case"))
            inner.append(el("ul", "".join(tx("li", x) for x in wf["distinctive"]), "plain small"))
        parts = []
        for p in card.get("parts", []):
            spans = part_spans(p)
            parts.append(el("li", tx("b", p.get("title", "")) + tx("span", f" · {p.get('level')} · {plural(len(spans), 'span')}", "faint small")
                            + tx("div", p.get("summary", ""), "here")))
        inner.append(tx("h3", "Parts, each with the code that makes it"))
        inner.append(el("ul", "".join(parts), "plain"))
        inner.append(tx("p", f"One part's code: {CLI} slice {i} <part>", "faint small mono"))
        mine = [(k, p) for k, p in self.pairs.items() if i in k[2:].split("|")]
        if mine:
            items = ""
            for k, p in mine:
                other = [x for x in k[2:].split("|") if x != i][0]
                j = p.get("judgment", "")
                items += el("li", btn(esc(self.short.get(other, other)), "nb", data_pick=k) + tx("span", f" · {'the same' if j == 'same' else j}", "muted small"))
            inner.append(tx("h3", "Judged by eye against"))
            inner.append(el("ul", items, "plain"))
        if wanted_by:
            inner.append(tx("h3", "Test requests that should find it"))
            inner.append(el("ul", "".join(el("li", btn(esc(q), "nb", data_pick=f"q:{q}")) for q in wanted_by), "plain inline"))
        html = "".join(inner)
        while len(html) > BLOCK_LIMIT and len(inner) > 3:
            inner.pop(-1)
            html = "".join(inner)
        return [first, blk(f"kb-ic-{i}", "div", html, "ic", data_for=f"b:{i}")]

    def request_block(self, q: Dict[str, Any], placed: Optional[Dict[str, Any]], r: Optional[Dict[str, Any]]) -> Block:
        wanted = q.get("wanted", [])
        head = el("header", tx("h2", f"Test request {q['id']}") + tx("p", q.get("request", ""), "req"), "ih")
        want = (el("p", tx("span", "Should find ", "muted") + "".join(btn(esc(self.short.get(w, w)), "fact", data_pick=f"b:{w}") for w in wanted))
                if wanted else tx("p", "Lists no build it should find.", "muted small"))
        if q.get("far"):
            want += el("p", tx("span", "From another field ", "muted") + "".join(btn(esc(self.short.get(w, w)), "fact", data_pick=f"b:{w}") for w in q["far"]))
        body = head + want + el("div", btn("On the map", "link", data_go="map"), "acts")
        if r and r.get("ranks"):
            rows = ""
            for mode, rank in r["ranks"].items():
                said = "found first" if rank == 1 else f"found {ordinal(rank)}" if rank else "missed"
                rows += el("tr", tx("th", MODE_WORD.get(mode, mode)) + tx("td", said, "good" if rank == 1 else "err" if not rank or rank > 3 else ""))
            body += tx("h3", "Where the search puts what it should find") + el("table", rows, "near")
        if placed and placed.get("nearest"):
            rows = ""
            for key, name, label, _ in CHANNELS:
                j = placed["nearest"].get(key)
                if j:
                    hit = j in wanted
                    rows += el("tr", tx("th", label) + el("td", btn(esc(self.short.get(j, j)), "nb", data_pick=f"b:{j}")
                                                           + tx("span", "wanted" if hit else "", "good small")), data_k=key)
            body += tx("h3", "Closest build on the map, by representation") + el("table", rows, "near")
        return blk(f"kb-iq-{q['id']}", "div", body, "iq", data_for=f"q:{q['id']}")

    # -- the filter menu ----------------------------------------------------------------------------
    def filter_menu(self) -> Dict[str, List[Block]]:
        self.prep()
        comp = self.atlas.composition()
        out = []
        for key, label in FACTS:
            buckets = comp.get(key) or []
            if not buckets:
                continue
            opts = "".join(btn(tx("span", v) + tx("span", len(ids), "n"), "opt", data_filter=f"{key}:{v}") for v, ids in buckets[:12])
            out.append(blk(f"kb-fm-{key}", "div", tx("h4", label) + el("div", opts, "opts"), "fgroup"))
        return {"kb-filter-menu": out}

    # -- evaluation, activity, search ------------------------------------------------------------------
    def evaluation(self, run: bool = False) -> Dict[str, List[Block]]:
        ev = self.console.evaluation(self.embedder, run=run)
        # Each block says which part of the lens it belongs to (data-part): the run, and
        # the three tables the Evaluation bar switches between.
        out: List[Tuple[str, str]] = []
        if ev.get("never"):
            return {"kb-eval-body": [blk("kb-ev-1", "p", "Not run yet with this embedder. Run the evaluation to measure the search.", "muted", data_part="run")]}
        q, p = ev.get("queries") or {}, ev.get("pairs") or {}
        modes = list((q.get("modes") or {}).keys())
        at = ev.get("at", "")
        out.append((tx("p", f"Run {at[:16].replace('T', ' ')} UTC with {ev.get('embedder')}. Each test request lists the builds it should find.", "muted"), "run"))
        rows = el("tr", tx("th", "Representation") + tx("th", "First", "num") + tx("th", "Top 3", "num") + tx("th", "Mean reciprocal rank", "num"))
        for m in modes:
            r = q["modes"][m]
            rows += el("tr", el("td", tx("b", MODE_WORD.get(m, m)) + tx("div", ev.get("modes", {}).get(m, ""), "faint small"))
                       + tx("td", pct(r["top1"]), "num") + tx("td", pct(r["top3"]), "num") + tx("td", num(r["mrr"]), "num"))
        out.append((el("div", el("table", rows, "stack"), "tablewrap"), "reps"))
        line = []
        if q.get("far"):
            line.append(f"The far match was a listed one for {pct(q['far']['hit'])} of the {q['far']['queries']} requests that list one.")
        if q.get("steps"):
            line.append(f"{pct(q['steps']['with_code'])} of the {q['steps']['steps']} steps got code, and {pct(q['steps']['from_wanted'])} of it came from a build the request wanted.")
        if line:
            out.append((tx("p", " ".join(line)), "reps"))
        if p.get("channels"):
            rows = el("tr", "".join(tx("th", h, "num" if i else "") for i, h in enumerate(["Representation", "Spearman", "Separation", "Same", "Related", "Different"])))
            for c, mm in p["channels"].items():
                mean = mm["mean"]
                rows += el("tr", tx("td", c) + tx("td", num(mm["spearman"]), "num") + tx("td", pct(mm["auc"]), "num")
                           + tx("td", num(mean["same"]), "num") + tx("td", num(mean["related"]), "num") + tx("td", num(mean["different"]), "num"))
            out.append((tx("h3", "Pairs judged by eye"), "pairs"))
            out.append((el("div", el("table", rows, "stack"), "tablewrap"), "pairs"))
        if q.get("queries"):
            def head() -> str:
                return el("tr", tx("th", "Request") + "".join(tx("th", MODE_WORD.get(m, m), "num") for m in modes))
            trs = []
            for r in q["queries"]:
                cells = ""
                for m in modes:
                    v = r["ranks"].get(m)
                    cells += el("td", tx("span", MODE_WORD.get(m, m), "h") + esc("–" if v is None else v), "num " + ("good" if v == 1 else "faint" if v is None else "err" if v > 3 else ""))
                trs.append(el("tr", el("td", btn(esc(r["id"]), "nb", data_pick=f"q:{r['id']}") + " " + tx("span", r["request"][:90] + "…", "small")) + cells))
            out.append((tx("h3", "Request by request: where each representation puts the build it should find"), "requests"))
            for part in chunk_rows(trs):
                out.append((el("div", el("table", head() + "".join(part), "stack ranks"), "tablewrap"), "requests"))
        return {"kb-eval-body": [(f"kb-ev-{n}", _with_id(h, f"kb-ev-{n}", part=part)) for n, (h, part) in enumerate(out, 1)]}

    def activity(self) -> Dict[str, List[Block]]:
        rows = self.console.activity()
        if not rows:
            return {"kb-activity-body": [blk("kb-ac-1", "p", esc("No searches logged yet. Searches run through the plugin or `astaui search` appear here; the console's own do not."), "muted")]}
        trs = []
        for r in rows[:60]:
            if r.get("event") != "search":
                continue
            fb = "; ".join(f"{f['build']}: " + ("helped" if f.get("helped") is True else "did not help" if f.get("helped") is False else "no answer")
                           for f in r.get("feedback", [])) or "none yet"
            trs.append(el("tr", tx("td", r.get("at", "")[:16].replace("T", " "), "small")
                          + el("td", esc(r.get("request") or "(query card only)") + tx("div", "described: " + (", ".join(r.get("described") or []) or "nothing"), "faint small"))
                          + tx("td", ", ".join(f"{i} {num(s)}" for i, s in r.get("results", [])), "small")
                          + tx("td", fb, "small")))
        head = el("tr", tx("th", "When") + tx("th", "Request") + tx("th", "Came back") + tx("th", "Feedback"))
        return {"kb-activity-body": [blk(f"kb-ac-{n}", "div", el("table", head + "".join(part), "stack"), "tablewrap")
                                     for n, part in enumerate(chunk_rows(trs), 1)]}

    def search(self, request: str, card: Optional[Dict[str, Any]]) -> Dict[str, List[Block]]:
        res = self.console.search({"request": request, "card": card, "k": 3, "embedder": self.embedder})
        return {"kb-search-results": search_blocks(res)}

    # -- sources: how a build comes in, and where each one came from ------------------------------
    def sources(self) -> Dict[str, List[Block]]:
        """The line that has a scientist file an app they built (sources.share_line),
        the builds scientists sent that wait to be checked and added, and where every
        build came from: grouped by how it came, a row a build, newest first."""
        from .sources import BRANCH_PREFIX, arrivals, inbox_page, incoming, share_line
        self.prep()
        a = self.atlas
        share = share_line(self.kb)
        page = inbox_page(self.kb)
        inbox = el("a", "Builds sent in", href="/a/" + quote(page, safe="/")) if page else esc("Builds sent in")
        hub = el("a", "Add them on GitHub", href=share["access"], target="_blank", rel="noopener") if share["access"] else ""
        line: List[Block] = []
        if share["line"]:
            copy = btn(tx("span", "Copy", "c0") + tx("span", "Copied", "c1") + tx("span", "Selected", "c2"), "run primary",
                       data_copy=True, aria_live="polite")
            where = ("They paste it once into the coding agent they use (Claude Code, Codex, Cursor, Gemini CLI or another), "
                     "in the folder of an app they built." if share.get("any_agent") else
                     "They paste it once into a terminal, in the folder of an app they built with Claude Code.")
            line += [blk("kb-so-where", "p", esc(where), "small muted"),
                     blk("kb-so-cmd", "div", el("code", esc(share["line"])) + copy, "socmd")]
            if share["link"]:
                agent = "their agent" if share.get("any_agent") else "Claude Code"
                steps = ("Installs the AstaUI skills for " + ("the agents on their computer" if share.get("any_agent") else "Claude Code")
                         + ", files their app under the name git has for them, for the project team, takes out keys, emails and "
                         "home paths, and sends it here. It asks them nothing.",
                         f"From then on, what they ask {agent} to build for their research comes here too, and an app "
                         "filed again replaces its earlier copy.")
                line.append(blk("kb-so-steps", "ol", "".join(tx("li", s) for s in steps), "sosteps"))
                if share["access"]:
                    line.append(blk("kb-so-access", "p", esc("They need read access to the repository to install it. ") + hub, "small muted"))
            else:
                steps = ["Files their app under the name git has for them, for the project team, and takes out keys, emails "
                         "and home paths."]
                if share["access"]:
                    steps.append(f"Pushes it to {share['repo']} as the branch {BRANCH_PREFIX}<its id>, which shows here to check and add.")
                line.append(blk("kb-so-steps", "ol", "".join(tx("li", s) for s in steps), "sosteps"))
                if share["access"]:
                    line.append(blk("kb-so-access", "p", esc("Until the line has a link to this drive, they need write access to the repository. ")
                                    + hub, "small muted"))
                if page:
                    brief = LINK_BRIEF.format(page=page, cli=CLI, public=DRIVE_URL, doc=DOC, apply=APPLY)
                    line += [blk("kb-so-drive", "p", esc("To have builds come straight to this drive instead, open ") + inbox
                                 + esc(", press Share, choose Add only, copy the link and paste it here."), "small sodrive"),
                             blk("kb-so-link", "p", "", "ask", data_marble_editable="write",
                                 data_ph="The Add only link to Builds sent in"),
                             blk("kb-so-use", "div", run_btn("Use this link", brief, "kb-v-sources", "run outline"), "actions")]
        else:
            line.append(blk("kb-so-where", "p", esc("This knowledge base has no GitHub repository to install from, so there is no line to send."), "small muted"))

        inc = incoming(self.kb)
        wait: List[Block] = []
        if inc["repo"] is None and inc["inbox"] is None:
            wait.append(blk("kb-so-none", "p", esc("This knowledge base is in no git repository and no page in the drive takes builds, so nothing can be sent to it."), "small muted"))
            return {"kb-so-line": line, "kb-so-wait": wait, "kb-so-rows": self._source_rows()}
        when = inc["looked"]
        status = (tx("span", "Every hour, by itself", "on") + tx("span", "Paused", "off")
                  + (esc(f" · last looked {when.strftime('%b %-d, %H:%M')}") if when else "")
                  + ((" · " + inbox) if page else ""))
        wait.append(blk("kb-so-looked", "p", status, "small faint solooked"))

        def who(author: Dict[str, Any], prov: Dict[str, Any]) -> str:
            name, what = maker(author)
            return " · ".join(x for x in (name + (f", {what}" if what else ""), CONSENT_WORD.get(prov.get("consent"), "")) if x)

        for w in inc["waiting"]:
            if w.get("held"):
                state, cls = "Held: " + " ".join(w["held"]), "warn"
            elif w.get("via") == "drive":
                state, cls = f"Sent {moment(w.get('sent_at'))} · joins at the next run", "sowhen"
            elif w["card"]:
                state, cls = f"On the branch {w['branch']}", "sowhen"
            else:
                state, cls = f"On the branch {w['branch']}. No card yet, so the check will not pass.", "warn"
            where = (f"to this drive, where it waits on the page {w['page']}" if w.get("via") == "drive" else
                     f"to the AstaUI repository on the branch {w['branch']}")
            act = ""
            if w.get("held") or w.get("via") != "drive":
                act = run_btn("Check and add", CHECK_BRIEF.format(id=w["id"], title=w["title"], where=where, cli=CLI, doc=DOC, apply=APPLY),
                              "kb-console", "run outline")
            wait.append(blk(f"kb-so-w-{w['id']}", "div", tx("b", w["title"], "sot") + tx("span", who(w["author"], w["provenance"]), "sowho")
                            + tx("span", state, cls) + act, "soc" + (" held" if w.get("held") else "")))
        for a in arrivals(self.kb):
            joined = f"Joined {moment(a['at'])}" if a["copies"] == 1 else f"Copy {a['copies']} joined {moment(a['at'])}"
            wait.append(blk(f"kb-so-c-{a['id']}", "div", btn(esc(a["title"]), "nb sot", data_pick=f"b:{a['id']}", title=a["title"])
                            + tx("span", who(a["author"], a["provenance"]), "sowho") + tx("span", joined, "sowhen"), "soc"))
        if len(wait) == 1:
            wait.append(blk("kb-so-none", "p", esc("Nothing has come in yet."), "small muted"))
        return {"kb-so-line": line, "kb-so-wait": wait, "kb-so-rows": self._source_rows()}

    def _source_rows(self) -> List[Block]:
        """Every build, grouped by how it came, a row a build, newest first."""
        a = self.atlas
        rows: List[Block] = [blk("kb-so-head", "div", "".join(tx("span", h, role="columnheader") for h in
                                                              ("Build", "Made by", "From", "Who may see it", "Filed")), "srow shead", role="row")]
        groups: Dict[str, List[str]] = {}
        for i in a.ids:
            kind = a.builds[i].kind if i in a.builds else ""
            groups.setdefault(kind if kind in KIND_WORD else "", []).append(i)
        for kind in [k for k in KIND_ORDER if k in groups] + ([""] if "" in groups else []):
            ids = sorted(groups[kind], key=lambda i: self.titles[i].lower())
            ids.sort(key=lambda i: a.builds[i].meta.get("created") or "", reverse=True)
            rows.append(blk(f"kb-so-g-{kind or 'other'}", "div", el("span", tx("b", KIND_WORD.get(kind, "Not said")) + tx("span", len(ids), "faint"), role="cell"),
                            "sgroup", role="row"))
            for i in ids:
                meta = a.builds[i].meta
                prov = meta.get("provenance") or {}
                name, what = maker(meta.get("author") or {})
                origin = prov.get("origin") if kind != "seed" else ""
                src = ", ".join(SOURCE_WORD.get(x, x[:1].upper() + x[1:]) for x in (meta.get("sources") or [])) or "Not said"
                if prov.get("forked_from"):
                    src += f", adapted from {self.short.get(prov['forked_from'], prov['forked_from'])}"
                consent = prov.get("consent") or ""
                cells = (el("span", btn(esc(self.titles[i]), "nb", data_pick=f"b:{i}", title=self.titles[i]) + (tx("span", origin, "sorig", title=origin) if origin else ""), role="cell")
                         + el("span", tx("b", name) + (" " + tx("span", what, "faint") if what else ""), role="cell", title=f"{name}, {what}" if what else None)
                         + tx("span", src, role="cell")
                         + tx("span", CONSENT_WORD.get(consent, consent or "Not said"), role="cell")
                         + tx("span", day(meta.get("created")), "num", role="cell"))
                rows.append(blk(f"kb-so-r-{i}", "div", cells, "srow", role="row"))
        if len(rows) == 1:
            rows.append(blk("kb-so-empty", "p", esc("No builds yet."), "muted"))
        return rows

    # -- pictures of the interfaces ---------------------------------------------------------------
    def shots(self) -> Dict[str, List[Block]]:
        """Each build's screenshot beside its row in the Builds list, a pair's two beside
        its row in the Pairs list, and at the top of the inspector. They are rules, not
        markup: the drive serves each file by its path, every build's picture is a custom
        property, and whatever names a build (data-pick, data-for) takes its own, so a new
        screenshot is one changed rule and no row is written again. How they sit is
        marble_shots.css, the slot's first block."""
        self.prep()
        a = self.atlas
        urls = {i: drive_href(a.builds[i].screenshot()) for i in a.ids if i in a.builds}
        rules = []
        for i in sorted(u for u in urls if urls[u]):
            rules.append(f':root{{--shot-{i}:url("{urls[i]}")}}')
            rules.append(f'[data-pick="b:{i}"],[data-for="b:{i}"]{{--shot:var(--shot-{i})}}')
        judged, unjudged = self.pair_rows()
        for key in [k for k, _ in judged] + [pair_key(x, y) for _, x, y in unjudged]:
            x, y = key[2:].split("|")
            if urls.get(x) or urls.get(y):
                rules.append(f'[data-pick="{key}"]{{--sa:var(--shot-{x});--sb:var(--shot-{y})}}')
        css = Path(__file__).with_name("marble_shots.css").read_text(encoding="utf-8")
        return {"kb-shots": [blk("kb-shots-css", "style", "\n" + css)] + style_blocks("kb-shot", rules)}

    # -- everything ----------------------------------------------------------------------------------
    def slots(self) -> Dict[str, List[Block]]:
        out: Dict[str, List[Block]] = {}
        for part in (self.catalog, self.home, self.sources, self.map, self.similarity, self.coverage, self.workflows,
                     self.inspector, self.filter_menu, self.activity, self.shots):
            out.update(part())
        out.update(self.evaluation(run=False))
        return out


def _code(sp: Dict[str, Any]) -> str:
    lines = (sp.get("text") or "").split("\n")
    shown = lines[:CODE_LINES]
    body = "\n".join(f"{sp['start'] + i:>4}  {l}" for i, l in enumerate(shown)) + ("\n   …" if len(lines) > CODE_LINES else "")
    why = "; ".join(sp.get("why", []))
    sym = ", ".join(sp.get("symbols") or ([sp["symbol"]] if sp.get("symbol") else []))
    label = f"{sp.get('path', sp['file'])}:{sp['start']}-{sp.get('shown_end', sp['end'])} · {sp['role']}" + (f" · {sym}" if sym else "")
    return tx("div", label + (f" · {why}" if why else ""), "span-head") + tx("pre", body, "code")


def search_blocks(res: Dict[str, Any]) -> List[Block]:
    q = res["query"]
    described = [f for f in ("summary", "workflow", "task", "data", "stage", "mechanism", "field") if q.get(f)]
    # Each block says which part of the Search lens it belongs to (data-part): the
    # request, what came back, or the code for each step.
    out = [(tx("p", f"For: {q.get('request') or '(query card only)'}", "muted"), "head"),
           (tx("p", f"Described as {', '.join(described) if described else 'nothing (searching on the words)'} · {res['embedder']}", "faint small"), "head")]

    def result(h: Dict[str, Any], label: str) -> str:
        bits = [el("h3", btn(esc(f"{label} {h['title']}"), "nb", data_pick=f"b:{h['id']}") + tx("span", f" · score {num(h['score'])}", "faint small")),
                tx("p", f"{h.get('field', '')} · {h.get('kind', '')} build", "muted small"),
                tx("p", "  ".join(f"{k} {num(v)}" for k, v in (h.get("by") or {}).items()), "faint small"),
                tx("p", h.get("summary", ""))]
        m = h.get("workflow_match")
        if h.get("workflow"):
            bits.append(tx("p", "Workflow: " + h["workflow"].get("name", ""), "small"))
        if m:
            same = [s for s in m["shared"] if not s.get("common")]
            if same:
                bits.append(tx("p", "Same steps", "small"))
                for s in same:
                    bits.append(el("div", esc(s["step"]) + (tx("div", "yours: " + s["a"], "here") if s.get("a") else "")
                                   + (tx("div", "theirs: " + s["b"], "here") if s.get("b") else ""), "same"))
            if m["only_b"]:
                bits.append(tx("p", "Only theirs: " + "; ".join(s["step"] for s in m["only_b"]), "small"))
            if m["only_a"]:
                bits.append(tx("p", "Only yours: " + "; ".join(s["step"] for s in m["only_a"]), "small"))
            if m["b_distinctive"]:
                bits.append(tx("p", "Particular to theirs: " + joined(m["b_distinctive"]), "small"))
            if m["a_needs"]:
                bits.append(tx("p", "Your needs: " + "; ".join(n["need"] + (" (likely met)" if n["covered"] else " (check)") for n in m["a_needs"]), "small"))
        return el("div", "".join(bits), "result")

    for i, h in enumerate(res.get("results", []), 1):
        out.append((result(h, f"{i}."), "match"))
    if res.get("far"):
        out.append((tx("h3", "From another field, same structure"), "match"))
        out.append((result(res["far"], ""), "match"))
    if res.get("steps_code"):
        out.append((tx("h3", "Code for each of your steps"), "code"))
        for i, st in enumerate(res["steps_code"], 1):
            bits = [tx("p", f"{i}. {st['step']}", "stephead")]
            if st.get("here"):
                bits.append(tx("p", st["here"], "here"))
            if not st["from"]:
                bits.append(tx("p", "No build does this step yet.", "warn small"))
            for src in st["from"]:
                bits.append(tx("p", f"From {src['title']}{' (a move most builds have)' if src.get('common') else ''}: {src['their_here'] or src['their_step']}", "small"))
                for sl in src["slices"][:2]:
                    own = [sp for sp in sl["spans"] if "the card" in sp.get("why", [])][:3]
                    code = "".join(_code(sp) for sp in own)
                    extra = len(sl["spans"]) - len(own)
                    tail = tx("p", f"{extra} more span(s) in the full slice: astaui slice {sl['build']} {sl['part']}", "faint small") if extra > 0 else ""
                    bits.append(el("details", tx("summary", f"{sl['title']}: {sl['lines']} lines") + code + tail))
            block = el("div", "".join(bits), "result")
            if len(block) > BLOCK_LIMIT:
                block = el("div", "".join(bits[:3]) + tx("p", "The code is too long to show here; see astaui slice.", "faint small"), "result")
            out.append((block, "code"))
    return [(f"kb-sr-{n}", _with_id(h, f"kb-sr-{n}", part=part)) for n, (h, part) in enumerate(out, 1)]


def _with_id(markup: str, bid: str, part: Optional[str] = None) -> str:
    """Give a block's outer element its id, and the part of its lens it belongs to."""
    m = re.match(r"<([a-zA-Z][\w-]*)", markup)
    extra = f' data-part="{esc(part)}"' if part else ""
    return markup[: m.end()] + f' data-marble-id="{bid}"' + extra + markup[m.end():]
