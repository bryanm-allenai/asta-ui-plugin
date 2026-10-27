"""The console as a Marble document: a workbench in the drive for looking at the
knowledge base, finding anything in it, and changing it by hand.

It is laid out like the drive's own apps, panes on a well, and like the tools
people already curate collections with: a catalog of the knowledge base's objects
on the left (builds, words, test requests, judged pairs), a lens in the middle
(Home, where the builds come from, the map, the similarity grid, word
coverage, workflows, evaluation, search), and an inspector on the right for
whatever is picked. No lens scrolls: Home fits its pane (marble_home_fit), and
every other lens is two panes, a bar
with what to know and what to choose, and a stage its picture is sized to
(marble_stage); where a lens has more than one table, the bar switches between
them. The map draws each build as a dot, coloured by default by where it sits
(marble_map), so it holds a few hundred. One selection and
one filter hold across every lens, so a build picked in the list is the point on
the map, the row in the grid and the card in the inspector. Find (Ctrl or Cmd K)
jumps to anything. Changes made in the inspector wait at its foot until Apply
makes them, all or none. On a narrower page the panes fold: the list and the
inspector share a column, and on a phone one pane shows at a time.

A Marble document cannot run Python, so the page holds what it shows as its own
markup, and its buttons carry briefs the Drive runs: Refresh, Search, Run the
evaluation and Apply each start an agent that runs one command from here and lands
what it prints with apply_ops.

    astaui marble-doc --out "Ai2/AstaUI/AstaUI Console.mrbl"     the whole page, once
    astaui marble-ops refresh --doc "<the page>"                  what changed since, and any part
                                                                  of the skeleton the page lacks
    astaui manage apply --doc "<the page>"                        make the queued changes

The skeleton below has slots, and every slot holds blocks with stable ids
(marble_views.py), so a refresh compares each slot with what it should hold
(mdiff.py) and lands only the difference. What is open, picked and filtered are
attributes on small elements, set by the page and filed as looks; the rules that
follow them are generated here, in state_css().
"""

from __future__ import annotations

import html as _html
import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import mdiff
from .atlas import CHANNELS, COLOURS, TERM_LISTS
from .marble_views import APPLY, CLI, DOC, DOC_HINT, Block, Views, esc, search_blocks

HERE = Path(__file__).parent

# The lenses, in the order of the view switch: (key, its name, its heading, what to know to read it)
LENSES: List[Tuple[str, str, str, str]] = [
    ("home", "Home", "What needs a decision", ""),
    ("sources", "Collection", "Where the builds come from",
     "Once a scientist has run the line below, what they build with Claude Code comes here by itself."),
    ("map", "Map", "The embedding space",
     "Near means alike. Place the builds by what they share, and pick one to see its true nearest neighbours, which a flat map only approximates."),
    ("similar", "Similarity", "How alike every pair is",
     "Brighter green is more alike, and alike builds sit together. Pick a cell to compare two builds and judge them by eye."),
    ("coverage", "Coverage", "Which builds use which words",
     "Each word of a list against every build. Pick a word to see what it means and to rename, merge, retire or reassign it."),
    ("workflows", "Workflows", "Workflow families, step by step",
     "Builds whose workflows share their moves, lined up: the same step on one row, how each build does it in its column."),
    ("eval", "Evaluation", "How well search finds what it should",
     "Where each representation puts the builds every test request should find, and how well similarity agrees with pairs judged by eye."),
    ("search", "Search", "Try a request",
     "An agent describes your request as a query card, runs the plugin's search, and writes below what came back, with the code for each step."),
]
# Each lens's button keeps the number it was given when it joined, wherever it sits.
LENS_NUM = {"home": 0, "map": 1, "similar": 2, "coverage": 3, "workflows": 4, "eval": 5, "search": 6, "sources": 7}
# Lenses that joined after pages were written keep the rules for showing them in
# their own kept block (Collection: marble_sources.css), so a refresh brings them.
OWN_RULES = ("sources",)
CATALOGS: List[Tuple[str, str]] = [("builds", "Builds"), ("words", "Words"), ("reqs", "Requests"), ("pairs", "Pairs")]
LISTS = [(f"{f}-{l}", label) for f, l, label, _ in TERM_LISTS]
KINDS = [("b", "Build"), ("t", "Word"), ("p", "Two builds"), ("q", "Test request")]
# What the stage of a lens with more than one thing to show switches between, first the default.
COV_PARTS = [("words", "Words"), ("weights", "Weights"), ("changes", "Changes")]
EVAL_PARTS = [("reps", "By representation"), ("pairs", "Pairs judged by eye"), ("requests", "Request by request")]
SEARCH_PARTS = [("match", "Results"), ("code", "Code for each step"), ("log", "Plugin searches")]
SOURCE_PARTS = [("ask", "Coming in"), ("all", "Every build")]
FAMILIES_AT_MOST = 16
# Who may see a build the owner adds: the skill's two answers, the narrower first.
CONSENTS = [("team", "People on this project"), ("public", "Anyone")]

# The owner's home folder, as the briefs name paths on their computer.
HOME = str(Path.home())
BRIEFS = {
    "add": ("File an interface the owner built into the AstaUI knowledge base, as the asta-ui:ui-to-workflow skill says "
            "(Ai2/AstaUI/knowledge-base-v0/skills/ui-to-workflow/SKILL.md; read it first), with what is written in this console's "
            "Add a build panel. Read kb-add-what, kb-add-title, kb-add-name, kb-add-role and kb-add-who with read_document. "
            "kb-add-what names the interface: a document in this drive, whose file is its code, or a folder. If it is empty, say so "
            "and change nothing. kb-add-who's data-consent says who may see it (none means team); kb-add-name is how to name the "
            "owner (empty means a pseudonym such as P01); kb-add-role is their role and field. Its prompts are what the owner wrote "
            "to the drive's agents that built it: the type \"user\" events with no from, in order and as written, in "
            ".marble/agents/*/events.jsonl whose context.target is that document (or a name or path it had before); write them to "
            "a file with a blank line between prompts. Pick an id from what it is (lowercase words and hyphens). From the drive's "
            f"folder run `{CLI} add <id> --title \"<what it is>\" --prompts <file> --code <path> --author \"<name>\" "
            "--role \"<role>\" --field \"<field>\" --kind contributed --consent <team or public> --source \"Marble app\"`, then "
            f"`{CLI} lint <id> --strip`. Then read the prompts and the code yourself and take out what must not leave this computer: "
            "real people's names, the titles, text and authors of papers under review, what a review says, data values and anything "
            "else confidential, with neutral placeholders in their place and the structure kept. If you can, take a screenshot "
            "of that stripped copy running, never of the original, since a picture keeps what the text strip took out. The "
            "browser tool shows a picture but cannot save one, so from Bash: copy its entry file into a temporary folder as "
            "index.html; for a Marble document (.mrbl) also copy the Marble runtime "
            f"({HOME}/.local/share/marble-drive/app/current/marble-drive/node_modules/@bdhmin/marble/runtime/marble.js) "
            "into that folder and put <script src=\"marble.js\" data-marble-app=\"x\"></script> before </body> in index.html, so "
            "its scripts draw what they draw in the drive; then load its file:// URL with headless Playwright "
            f"({HOME}/Development/marble/node_modules/playwright/index.mjs) at 1280 by 800, wait for document.fonts.ready, "
            "and save page.screenshot as kb/builds/<id>/screenshot.png. Write the card: run "
            f"`{CLI} extract <id> --out /tmp/astaui-card.json`, write the card as it says, then `{CLI} card put <id> "
            f"/tmp/astaui-card.json` until it is saved, then `{CLI} index`. Do not commit or push. Then refresh this console: run "
            f"`{CLI} marble-ops refresh {DOC}`. {APPLY} Last, set the text of kb-add-note to one or two sentences: the build's id "
            "and title, the workflow family it joined, and what was taken out. Then answer in one sentence."),
    "look": ("Take in the builds scientists have sent. From the drive's folder run `{cli} intake`: it takes every build sent to this "
             "drive's Builds sent in page that passes the checks into the knowledge base and its index, and says which it held and why. "
             f"Then run `{CLI} incoming --fetch`, which looks on the AstaUI repository too. Then refresh this console: run "
             f"`{CLI} marble-ops refresh {DOC}`. {APPLY} Do not commit or push. Then answer in one sentence: which builds came in "
             "and which are waiting, by name, or that none did.").replace("{cli}", CLI),
    "refresh": f"Refresh this console from the AstaUI knowledge base. From the drive's folder run `{CLI} marble-ops refresh {DOC}`. "
               f"{APPLY} Then answer in one sentence.",
    "apply": f"Apply the changes waiting in this console's queue to the AstaUI knowledge base. From the drive's folder run "
             f"`{CLI} manage apply {DOC}`. It makes every change or none, and when it makes them it refreshes the page too. "
             f"{APPLY} Then answer in one sentence: what was applied, or what stopped it.",
    "eval": f"Run the AstaUI evaluation and show it in this console. From the drive's folder run `{CLI} marble-ops eval --run {DOC}`. "
            f"{APPLY} Then answer in one sentence.",
    "search": ("Search the AstaUI knowledge base for the request written in this document's element kb-q (read it with "
               "read_document; if it is empty, say so and change nothing). Describe the request as a query card: from the "
               f"drive's folder run `{CLI} describe \"<the request>\"`, follow the instructions it prints, and write the card JSON "
               f"to /tmp/astaui-console-query.json. Then run `{CLI} marble-ops search --request \"<the request>\" "
               f"--card /tmp/astaui-console-query.json {DOC}`. {APPLY} Then answer in one sentence."),
}


# -- the rules that follow the looks ------------------------------------------------------------------

def _when(el: str, attr: str, value: str, default: Optional[str], scope: str = "") -> List[str]:
    """Selectors for 'this element's attribute has this value', counting a missing
    attribute as the default. With a scope, the element is looked for anywhere in it."""
    sels = [f'#{el}[{attr}="{value}"]']
    if value == default:
        sels.append(f"#{el}:not([{attr}])")
    return [f"{scope}:has({s})" for s in sels] if scope else sels


def _rule(prefixes: Sequence[str], tail: str, body: str) -> str:
    return ", ".join(p + tail for p in prefixes) + " { " + body + " }"


# The pressed segment, as Asta's spec sheet draws it: green, with extra-dark-teal words.
PRESSED = "background: var(--green); color: var(--color-extra-dark-teal);"

# The map's colour when none is picked: Place, each dot coloured by where it sits.
# It is not one of COLOURS (it needs no slots): its rules are in marble_map.css, its
# key in Views.map().
COLOUR_DEFAULT = "n"


def state_css() -> str:
    """The rules that make the page follow its looks. Each look is one attribute on
    one small element; a missing attribute means the default."""
    r: List[str] = ["  /* Generated with the page: each look below is one attribute on one element. */"]
    for key, _, _, _ in LENSES:
        if key in OWN_RULES:
            continue
        p = _when("kb-lens", "data-view", key, "home", ".app")
        r.append(_rule(p, f" #kb-v-{key}", "display: block;"))
        r.append(_rule(p, f' [data-set="view"][data-to="{key}"]', PRESSED))
        r.append(_rule(p, f' .lname[data-v="{key}"]', "display: inline;"))
    for key, _ in CATALOGS:
        p = _when("kb-cat", "data-cat", key, "builds", ".app")
        r.append(_rule(p, f' .list[data-c="{key}"]', "display: block;"))
        r.append(_rule(p, f' [data-set="cat"][data-to="{key}"]', PRESSED))
    r.append(_rule(_when("kb-cat", "data-cat", "words", "builds", ".app"), " .wpick", "display: flex;"))
    for key, _ in LISTS:
        p = _when("kb-cat", "data-list", key, "data-shapes", ".app")
        r.append(_rule(p, f' .wlist[data-l="{key}"], .tlist[data-l="{key}"]', "display: block;"))
        r.append(_rule(p, f' [data-set="list"][data-to="{key}"]', "background: var(--picked); color: var(--color-cream);"))
    for key, label in KINDS:
        r.append(_rule([f'#kb-sel[data-sel^="{key}:"]'], f' .k-{key}', "display: inline;"))
    for key, _, label, _ in CHANNELS:
        p = _when("kb-map-tools", "data-channel", key, "c")
        r.append(_rule(p, " ~ .plotwrap :is(.pt, .rq)", f"--x: var(--{key}x); --y: var(--{key}y);"))
        r.append(_rule(p, f' ~ .plotwrap .rq:not([data-in*="{key}"])', "display: none;"))
        r.append(_rule(p, f' ~ .plotwrap .pt[data-l{key}="l"] .lab', "left: auto; right: 23px;"))
        r.append(_rule(p, f' ~ .plotwrap .pt[data-l{key}="a"] .lab', "left: 50%; top: -1.05rem; transform: translateX(-50%);"))
        r.append(_rule(p, f' ~ .plotwrap .pt[data-l{key}="b"] .lab', "left: 50%; top: 23px; transform: translateX(-50%);"))
        r.append(_rule(p, f' ~ #kb-map-chan .cap[data-k="{key}"]', "display: block;"))
        r.append(_rule(p, f' [data-set="channel"][data-to="{key}"]', PRESSED))
        r.append(_rule(_when("kb-map-tools", "data-channel", key, "c", ".app"), f' .near tr[data-k="{key}"] th', "color: var(--text); font-weight: 600;"))
        p = _when("kb-mx-tools", "data-channel", key, "w")
        r.append(_rule(p, " ~ .mxbody .cell", f"--v: var(--v{key});"))
        r.append(_rule(p, f' ~ .mlgs .mlg[data-k="{key}"]', "display: flex;"))
        r.append(_rule(p, f' [data-set="channel"][data-to="{key}"]', PRESSED))
    for opt, _ in COLOURS:
        p = _when("kb-map-tools", "data-colour", opt, COLOUR_DEFAULT)
        for n in (1, 2, 3):
            r.append(_rule(p, f' ~ .plotwrap .pt[data-s{opt}="{n}"]', f"--pc: var(--cat{n});"))
        r.append(_rule(p, f' [data-set="colour"][data-to="{opt}"]', PRESSED))
    r.append(_rule(['#kb-map-tools[data-req="on"]'], " ~ .plotwrap .rq", "display: block;"))
    r.append(_rule(['#kb-wf-tools[data-common="hide"]'], ' ~ #kb-wf-body tr[data-kind="common"]', "display: none;"))
    on = "color: var(--text);"
    check = "background: var(--color-interactive-default); box-shadow: none;"
    for el, attr, val, name in (("kb-map-tools", "data-req", "on", "req"), ("kb-wf-tools", "data-common", "hide", "common")):
        r.append(_rule([f'#{el}[{attr}="{val}"]'], f' [data-set="{name}"]', on))
        r.append(_rule([f'#{el}[{attr}="{val}"]'], f' [data-set="{name}"]::before', check))
    for key in ("lens", "list"):
        p = _when("kb-thumb", "data-pane", key, "lens", ".app")
        r.append(_rule(p, f' #kb-thumb [data-to="{key}"]', "color: var(--link); font-weight: 600;"))
    return "\n  ".join(r) + "\n"


def stage_css() -> str:
    """The rules that follow the looks the lens stages added: which part of a lens
    shows, which word list, which workflow family. They live in their own style
    block (kb-stage-looks), so a page that predates them takes them as one insert."""
    r: List[str] = ["  /* Generated with the page, beside marble_stage.css: which key and which part show. */"]
    # (the switch, its lens, the parts with what each shows and how, said from the lens)
    parts = [
        ("kb-cov-part", "kb-v-coverage", COV_PARTS, {
            "words": [(" > .chips", "flex"), (" > .tlg", "flex"), (" > div:has(> .tlist)", "grid")],
            "weights": [(" #kb-cov-weights", "grid")],
            "changes": [(" #kb-cov-log", "grid")]}),
        ("kb-ev-part", "kb-v-eval", EVAL_PARTS, {
            key: [(f' #kb-eval-body > [data-part="{key}"]', "block")] for key, _ in EVAL_PARTS}),
        ("kb-sr-part", "kb-v-search", SEARCH_PARTS, {
            "match": [(" #kb-search-results", "grid"), (' #kb-search-results > :is([data-part="head"], [data-part="match"])', "block")],
            "code": [(" #kb-search-results", "grid"), (' #kb-search-results > :is([data-part="head"], [data-part="code"])', "block")],
            "log": [(" > .lede", "block"), (" #kb-activity-body", "grid")]}),
    ]
    for switch, lens, options, shows in parts:
        default = options[0][0]
        for key, _ in options:
            p = _when(switch, "data-part", key, default, f"#{lens}")
            for tail, display in shows[key]:
                r.append(_rule(p, tail, f"display: {display};"))
            r.append(_rule(_when(switch, "data-part", key, default), f' > [data-to="{key}"]', PRESSED))
    # The map's colour key sits in the bar under Colour by: the key for the colour picked,
    # and the test requests' key while they show.
    for opt, _ in COLOURS:
        r.append(_rule(_when("kb-map-tools", "data-colour", opt, COLOUR_DEFAULT), f' .lgs .lg[data-o="{opt}"]', "display: flex;"))
    r.append(_rule(['#kb-map-tools[data-req="on"]'], " .lgs .lg-req", "display: flex;"))
    # Coverage shows one word list at a time: the one picked by the chips (and the Words list).
    for key, _ in LISTS:
        r.append(_rule(_when("kb-cat", "data-list", key, "data-shapes", ".app"), f' #kb-v-coverage .tlist[data-l="{key}"]', "display: grid;"))
    # Workflows shows one family at a time, by its number; past the last, the first.
    for n in range(1, FAMILIES_AT_MOST + 1):
        p = _when("kb-wf-tools", "data-fam", str(n), "1", "#kb-v-workflows")
        r.append(_rule(p, f' .family[data-fi="{n}"]', "display: grid;"))
        r.append(_rule(_when("kb-wf-tools", "data-fam", str(n), "1"), f' [data-set="fam"][data-to="{n}"]', PRESSED))
        if n > 1:
            r.append(f'#kb-v-workflows:has(#kb-wf-tools[data-fam="{n}"]):not(:has(.family[data-fi="{n}"])) .family[data-fi="1"] {{ display: grid; }}')
    return "\n  ".join(r) + "\n"


# -- the skeleton ------------------------------------------------------------------------------------

def _seg(where: str, set_: str, options: Sequence[Tuple[str, str]], default: str, tools: str = "",
         nums: Optional[Dict[str, int]] = None) -> str:
    t = f' data-tools-id="{tools}"' if tools else ""
    return "".join(f'<button type="button" data-marble-id="kb-{where}-{set_}-{k}-{nums[k] if nums else n}" data-set="{set_}" data-to="{k}"{t}'
                   + (" data-default" if k == default else "") + f">{esc(label)}</button>"
                   for n, (k, label) in enumerate(options))


def _run(key: str, label: str, scope: str, idx: str, cls: str = "run", on: str = "press") -> str:
    return (f'<button type="button" class="{cls}" data-marble-id="{idx}" data-marble-on="{esc(on)}" '
            f'data-marble-scope="{scope}" data-marble-run="{esc(BRIEFS[key])}">{esc(label)}</button>')


def skeleton(slots: Dict[str, List[Block]], stamp: str) -> str:
    def slot(sid: str, tag: str = "div", cls: str = "", extra: str = "") -> str:
        inner = "".join(h for _, h in slots.get(sid, []))
        c = f' class="{cls}"' if cls else ""
        return f'<{tag}{c} id="{sid}" data-marble-id="{sid}"{extra}>{inner}</{tag}>'

    def head(key: str, tools: str = "", extra: str = "") -> str:
        _, _, h, lede = next(v for v in LENSES if v[0] == key)
        lede_html = f'<p class="lede" data-marble-id="kb-l-{key}">{esc(lede)}</p>' if lede else ""
        return (f'<div class="lhead" data-marble-id="kb-lh-{key}"><div class="lhtext" data-marble-id="kb-lht-{key}">'
                f'<h2 data-marble-id="kb-h-{key}">{esc(h)}</h2>{lede_html}</div>{extra}</div>{tools}')

    lens_seg = _seg("lens", "view", [(k, n) for k, n, _, _ in LENSES], "home", nums=LENS_NUM)
    lens_menu = _seg("lmenu", "view", [(k, n) for k, n, _, _ in LENSES], "home", tools="kb-lens", nums=LENS_NUM)
    lnames = "".join(f'<span class="lname" data-marble-id="kb-ln-{k}" data-v="{k}">{esc(n)}</span>' for k, n, _, _ in LENSES)
    cat_seg = _seg("cat", "cat", CATALOGS, "builds")
    list_chips = _seg("wl", "list", LISTS, "data-shapes", tools="kb-cat")
    cov_chips = _seg("cl", "list", LISTS, "data-shapes", tools="kb-cat")
    channels = [(k, label) for k, _, label, _ in CHANNELS]
    word_lists = "".join(slot(f"kb-cw-{k}", cls="wlist", extra=f' data-l="{k}"') for k, _ in LISTS)
    cov_lists = "".join(
        f'<section class="tlist" id="kb-cov-{k}" data-marble-id="kb-cov-{k}" data-l="{k}">{slot(f"kb-cov-{k}-head")}'
        f'<div class="tgrid" data-marble-id="kb-cov-{k}-grid">{slot(f"kb-cov-{k}-rows")}</div></section>' for k, _ in LISTS)
    kinds = "".join(f'<span class="kind k-{k}" data-marble-id="kb-kind-{k}">{esc(n)}</span>' for k, n in KINDS)
    logo = (HERE / "asta-logo.svg").read_text(encoding="utf-8").strip().replace("<svg ", '<svg aria-hidden="true" ', 1)
    # Home fits its panel: its own style and script, kept apart from the page's
    # so a page that predates them can take them as two inserts.
    fit_css = (HERE / "marble_home_fit.css").read_text(encoding="utf-8")
    fit_js = (HERE / "marble_home_fit.js").read_text(encoding="utf-8")
    # Every other lens is a bar and a stage the picture fits: the layout, then the
    # rules that follow its parts' looks.
    stage = (HERE / "marble_stage.css").read_text(encoding="utf-8")
    stage_tables = (HERE / "marble_stage_tables.css").read_text(encoding="utf-8")
    stage_looks = stage_css()
    # The map's points: dots alone, and Place, the colour they take by default. It
    # leads Colour by; the facets keep their places and ids after it.
    map_css = (HERE / "marble_map.css").read_text(encoding="utf-8")
    add_css = (HERE / "marble_add.css").read_text(encoding="utf-8")
    # Collection: its layout and the rules that show it, and the Copy button's script.
    sources_css = (HERE / "marble_sources.css").read_text(encoding="utf-8")
    copy_js = (HERE / "marble_copy.js").read_text(encoding="utf-8")
    place = (f'<button type="button" data-marble-id="kb-map-colour-{COLOUR_DEFAULT}" data-set="colour" '
             f'data-to="{COLOUR_DEFAULT}" data-default>Place</button>')
    return f"""
<div class="app" data-marble-id="kb-console">
  <header class="top" data-marble-id="kb-top">
    <h1 data-marble-id="kb-title">{logo}AstaUI</h1>
    <nav class="seg lenses" id="kb-lens" data-marble-id="kb-lens" data-tools aria-label="Views">{lens_seg}</nav>
    <div class="popwrap lensmenu" data-marble-id="kb-lmw">
      <button type="button" class="quiet menubtn" id="kb-lens-btn" data-marble-id="kb-lens-btn" aria-haspopup="true">{lnames}<i class="chev" data-marble-id="kb-lens-chev"></i></button>
      <div class="pop" id="kb-lens-pop" data-marble-id="kb-lens-pop">{lens_menu}</div>
    </div>
    <div class="popwrap" data-marble-id="kb-fw">
      <button type="button" class="quiet" id="kb-filter-btn" data-marble-id="kb-filter-btn" aria-haspopup="true">Filter<i class="mark" data-marble-id="kb-filter-mark"></i></button>
      <div class="pop fpop" id="kb-filter-pop" data-marble-id="kb-filter-pop">
        <div class="fhead" data-marble-id="kb-fhead"><p class="fnow" data-marble-id="kb-fnow"></p><button type="button" class="link" data-marble-id="kb-fall" data-filter="">Show every build</button></div>
        {slot("kb-filter-menu", cls="fgroups")}
      </div>
    </div>
    <span class="spacer" data-marble-id="kb-top-sp"></span>
    <span class="status" data-marble-id="kb-updated">Refreshed {esc(stamp)}</span>
    <button type="button" class="quiet find" id="kb-find" data-marble-id="kb-find" aria-keyshortcuts="Control+K Meta+K">Find</button>
    {_run("refresh", "Refresh", "kb-console", "kb-run-refresh", "run")}
  </header>

  <section class="pane cat" id="kb-catp" data-marble-id="kb-catp" aria-label="The knowledge base, listed">
    <div class="pbar" id="kb-cat" data-marble-id="kb-cat" data-tools><div class="seg" data-marble-id="kb-cat-seg">{cat_seg}</div></div>
    <div class="wpick" data-marble-id="kb-wpick">{list_chips}</div>
    <div class="cfilter" data-marble-id="kb-cfw"><input type="search" id="kb-cat-q" data-marble-id="kb-cat-q" placeholder="Filter this list" enterkeyhint="search" autocomplete="off" spellcheck="false"></div>
    <div class="pbody" data-marble-id="kb-cat-body">
      {slot("kb-cat-builds", cls="list", extra=' data-c="builds"')}
      <div class="list" data-c="words" data-marble-id="kb-cat-words">{word_lists}</div>
      {slot("kb-cat-reqs", cls="list", extra=' data-c="reqs"')}
      {slot("kb-cat-pairs", cls="list", extra=' data-c="pairs"')}
    </div>
    <div class="cfoot" data-marble-id="kb-cat-foot"><button type="button" class="quiet addb" id="kb-add-open" data-marble-id="kb-add-open" data-pick="add:build">Add a build of your own</button></div>
  </section>

  <main class="pane lens" id="kb-lensp" data-marble-id="kb-lensp">
    <div class="pbody" id="kb-lens-body" data-marble-id="kb-lens-body">
      <div class="filterline" id="kb-filterline" data-marble-id="kb-filterline"></div>

      <nav class="seg" id="kb-home-pages" data-marble-id="kb-home-pages" aria-label="Pages of Home"><button type="button" data-marble-id="kb-hp-decide">Decisions</button><button type="button" data-marble-id="kb-hp-make">Made of</button><button type="button" data-marble-id="kb-hp-code">Code and stores</button></nav>

      <section class="view" id="kb-v-home" data-marble-id="kb-v-home">
        {head("home")}
        {slot("kb-home-attn", cls="attn")}
        <h2 class="sub" data-marble-id="kb-home-h2">At a glance</h2>
        {slot("kb-home-glance", cls="tiles")}
        <h2 class="sub" data-marble-id="kb-home-h3">What it is made of</h2>
        <p class="lede" data-marble-id="kb-home-l3">Press a bar to show only those builds, in every view.</p>
        {slot("kb-home-make", cls="charts")}
        <h3 class="sub" data-marble-id="kb-home-h4">How much code, and how much a search hands back</h3>
        {slot("kb-home-code", cls="codechart")}
        <h2 class="sub" data-marble-id="kb-home-h5">What it keeps, and where</h2>
        {slot("kb-home-keeps", cls="kinds")}
      </section>

      <section class="view" id="kb-v-sources" data-marble-id="kb-v-sources">
        {head("sources")}
        <div class="seg vpart" id="kb-so-part" data-marble-id="kb-so-part" data-tools aria-label="Show">{_seg("so", "part", SOURCE_PARTS, "ask")}</div>
        <div class="soask" id="kb-so-ask" data-marble-id="kb-so-ask">
          <div class="sohead" data-marble-id="kb-so-wait-hd"><h3 data-marble-id="kb-so-wait-h">Coming in</h3>{_run("look", "Take in now", "kb-v-sources", "kb-run-look", "run outline", on=LOOK_EVERY)}<button type="button" class="run outline sopause" data-marble-id="kb-run-look-pause" data-marble-pause="kb-run-look" aria-pressed="false"><span class="c0">Pause</span><span class="c1">Paused</span></button></div>
          {slot("kb-so-wait", cls="sowait")}
          <h3 data-marble-id="kb-so-ask-h">Send a scientist this line</h3>
          {slot("kb-so-line", cls="soline")}
        </div>
        <div class="soall" id="kb-so-all" data-marble-id="kb-so-all">
          <h3 data-marble-id="kb-so-all-h">Where every build came from</h3>
          {slot("kb-so-rows", cls="sorows", extra=' role="table" aria-label="Where every build came from"')}
        </div>
      </section>

      <section class="view" id="kb-v-map" data-marble-id="kb-v-map">
        {head("map")}
        <div class="tools" id="kb-map-tools" data-marble-id="kb-map-tools" data-tools>
          <div class="grp" data-marble-id="kb-map-g1"><span class="tl" data-marble-id="kb-map-l1">Placed by</span><div class="seg" data-marble-id="kb-map-s1">{_seg("map", "channel", channels, "c")}</div></div>
          <div class="grp" data-marble-id="kb-map-g2"><span class="tl" data-marble-id="kb-map-l2">Colour by</span><div class="seg" data-marble-id="kb-map-s2">{place}{_seg("map", "colour", COLOURS, COLOUR_DEFAULT)}</div>{slot("kb-map-legend", cls="lgs")}</div>
          <button type="button" class="toggle" data-marble-id="kb-map-req" data-set="req" data-to="on" data-toggle>Show test requests</button>
        </div>
        <div class="plotwrap" data-marble-id="kb-map-wrap">{slot("kb-map-pts", cls="plot")}</div>
        {slot("kb-map-chan")}
        {slot("kb-map-pos", extra=" hidden")}
      </section>

      <section class="view" id="kb-v-similar" data-marble-id="kb-v-similar">
        {head("similar")}
        <div class="tools" id="kb-mx-tools" data-marble-id="kb-mx-tools" data-tools>
          <div class="grp" data-marble-id="kb-mx-g1"><span class="tl" data-marble-id="kb-mx-l1">Alike by</span><div class="seg" data-marble-id="kb-mx-s1">{_seg("mx", "channel", channels, "w")}</div></div>
        </div>
        {slot("kb-mx-legend", cls="mlgs")}
        <div class="mxbody" data-marble-id="kb-mx-body">
          <div class="mxwrap" data-marble-id="kb-mx-wrap" role="grid" aria-label="How alike every two builds are">{slot("kb-mx-grid")}</div>
          <p class="jlg" data-marble-id="kb-mx-jlg"><span data-marble-id="kb-mx-j0">Judged by eye:</span><span data-marble-id="kb-mx-j1"><i class="same" data-marble-id="kb-mx-j1i"></i>the same</span><span data-marble-id="kb-mx-j2"><i class="related" data-marble-id="kb-mx-j2i"></i>related</span><span data-marble-id="kb-mx-j3"><i class="different" data-marble-id="kb-mx-j3i"></i>different</span></p>
        </div>
        {slot("kb-mx-vals", extra=" hidden")}
      </section>

      <section class="view" id="kb-v-coverage" data-marble-id="kb-v-coverage">
        {head("coverage")}
        <div class="seg vpart" id="kb-cov-part" data-marble-id="kb-cov-part" data-tools aria-label="Show">{_seg("cov", "part", COV_PARTS, "words")}</div>
        <div class="chips" data-marble-id="kb-cov-chips">{cov_chips}</div>
        <p class="tlg" data-marble-id="kb-cov-lg"><span data-marble-id="kb-cov-lg1"><i class="sw s1" data-marble-id="kb-cov-lg1i"></i>the build has the word</span><span data-marble-id="kb-cov-lg2"><i class="sw s2" data-marble-id="kb-cov-lg2i"></i>a card proposed the word; the list lacks it</span></p>
        <div data-marble-id="kb-cov-lists">{cov_lists}</div>
        <h2 class="sub" data-marble-id="kb-cov-wh">How much each part of a card counts in search</h2>
        {slot("kb-cov-weights", cls="weights")}
        <h2 class="sub" data-marble-id="kb-cov-logh">What changed in the ontology</h2>
        {slot("kb-cov-log", tag="ol", cls="log")}
      </section>

      <section class="view" id="kb-v-workflows" data-marble-id="kb-v-workflows">
        {head("workflows")}
        <div class="tools" id="kb-wf-tools" data-marble-id="kb-wf-tools" data-tools>
          {slot("kb-wf-fams", cls="wfams", extra=' aria-label="Family"')}
          <button type="button" class="toggle" data-marble-id="kb-wf-hide" data-set="common" data-to="hide" data-toggle>Hide the moves most builds have</button>
        </div>
        {slot("kb-wf-body")}
      </section>

      <section class="view" id="kb-v-eval" data-marble-id="kb-v-eval">
        {head("eval", extra=_run("eval", "Run the evaluation", "kb-v-eval", "kb-run-eval"))}
        <div class="seg vpart" id="kb-ev-part" data-marble-id="kb-ev-part" data-tools aria-label="Show">{_seg("ev", "part", EVAL_PARTS, "reps")}</div>
        {slot("kb-eval-body")}
      </section>

      <section class="view" id="kb-v-search" data-marble-id="kb-v-search">
        {head("search")}
        <p class="ask" data-marble-id="kb-q" data-marble-editable="write" data-ph="What do you want to build? Say it the way a scientist would."></p>
        <div class="actions" data-marble-id="kb-search-actions">
          {_run("search", "Search", "kb-v-search", "kb-run-search")}
          <span class="faint small" data-marble-id="kb-search-when">Not searched yet</span>
        </div>
        <div class="seg vpart" id="kb-sr-part" data-marble-id="kb-sr-part" data-tools aria-label="Show">{_seg("sr", "part", SEARCH_PARTS, "match")}</div>
        {slot("kb-search-results")}
        <h2 class="sub" data-marble-id="kb-activity-h">Searches run through the plugin</h2>
        <p class="lede" data-marble-id="kb-activity-l">Newest first, with whether what came back helped. The log stays on this machine.</p>
        {slot("kb-activity-body")}
      </section>
    </div>
  </main>

  <aside class="pane insp" id="kb-inspp" data-marble-id="kb-inspp" aria-label="The picked build, word, pair or request">
    <div class="pbar" id="kb-sel" data-marble-id="kb-sel">
      <button type="button" class="quiet back" id="kb-back" data-marble-id="kb-back">Back</button>
      {kinds}<span class="kind k-add" data-marble-id="kb-kind-add">Add a build</span>
      <span class="spacer" data-marble-id="kb-sel-sp"></span>
      <button type="button" class="quiet" id="kb-close" data-marble-id="kb-close">Close</button>
    </div>
    <div class="pbody ibody" id="kb-insp-body" data-marble-id="kb-insp-body">
      <p class="empty" data-marble-id="kb-insp-empty">Pick a build, a word, a pair or a test request, in the list or in any view, to see it here.</p>
      {slot("kb-insp-b")}
      {slot("kb-insp-q")}
      {slot("kb-insp-p")}
      <section class="addp" data-for="add:build" data-marble-id="kb-add" aria-label="Add a build of your own">
        <header class="ih" data-marble-id="kb-add-hd"><h2 data-marble-id="kb-add-h">Add a build of your own</h2><p class="meta" data-marble-id="kb-add-m">An interface you built, filed beside the others</p></header>
        <p class="small muted" data-marble-id="kb-add-l">An agent gathers what you asked the agents that built it and the interface's code, takes out anything private, describes it in the ontology's words and refreshes this console, so it shows on the map. It stays on this computer: sharing it is a separate step.</p>
        <div class="fld" data-marble-id="kb-add-f1"><span class="flab" data-marble-id="kb-add-f1l">The interface</span><p class="ask" id="kb-add-what" data-marble-id="kb-add-what" data-marble-editable="write" data-ph="A document in this drive, or a folder"></p></div>
        <div class="fld" data-marble-id="kb-add-f2"><span class="flab" data-marble-id="kb-add-f2l">What it is</span><p class="ask" id="kb-add-title" data-marble-id="kb-add-title" data-marble-editable="write" data-ph="A few words, such as: reviewing my conference papers"></p></div>
        <div class="fld" data-marble-id="kb-add-f3"><span class="flab" data-marble-id="kb-add-f3l">How to name you</span><p class="ask" id="kb-add-name" data-marble-id="kb-add-name" data-marble-editable="write" data-ph="A pseudonym such as P01, unless you write your name"></p></div>
        <div class="fld" data-marble-id="kb-add-f4"><span class="flab" data-marble-id="kb-add-f4l">Your role and field</span><p class="ask" id="kb-add-role" data-marble-id="kb-add-role" data-marble-editable="write" data-ph="Such as: PhD student, human-computer interaction"></p></div>
        <div class="fld" data-marble-id="kb-add-f5"><span class="flab" data-marble-id="kb-add-f5l">Who may see it</span><div class="seg" id="kb-add-who" data-marble-id="kb-add-who" data-tools>{_seg("add", "consent", CONSENTS, "team")}</div></div>
        <div class="actions" data-marble-id="kb-add-acts">{_run("add", "File it", "kb-add", "kb-run-add")}</div>
        <p class="small" id="kb-add-note" data-marble-id="kb-add-note"></p>
      </section>
    </div>
  </aside>

  <aside class="tray" id="kb-tray" data-marble-id="kb-tray" aria-label="Changes waiting">
    <div class="tbar" id="kb-tray-bar" data-marble-id="kb-tray-bar">
      <span class="countfb" data-marble-id="kb-tray-fb">Changes</span>
      <span class="spacer" data-marble-id="kb-tray-sp"></span>
      <button type="button" class="quiet waiting" id="kb-tray-toggle" data-marble-id="kb-tray-toggle"><span class="show" data-marble-id="kb-tray-show">Review</span><span class="hide" data-marble-id="kb-tray-hide">Hide</span></button>
      {_run("apply", "Apply changes", "kb-console", "kb-run-apply", "run primary waiting")}
    </div>
    <div class="noterow" data-marble-id="kb-noterow"><p id="kb-apply-note" data-marble-id="kb-apply-note"></p><button type="button" class="quiet" id="kb-note-done" data-marble-id="kb-note-done">Done</button></div>
    <div class="tlist" data-marble-id="kb-tray-list"><ol class="queue" id="kb-queue" data-marble-id="kb-queue" aria-label="Changes waiting to be applied"></ol></div>
  </aside>

  <nav class="thumb" id="kb-thumb" data-marble-id="kb-thumb" data-tools aria-label="Show">
    <button type="button" data-marble-id="kb-thumb-lens" data-set="pane" data-to="lens" data-default>View</button>
    <button type="button" data-marble-id="kb-thumb-list" data-set="pane" data-to="list">List</button>
  </nav>
  {slot("kb-shots", extra=" hidden")}
<style data-marble-id="kb-home-fit">
{fit_css}</style>
<style data-marble-id="kb-stage">
{stage}</style>
<style data-marble-id="kb-stage-tables">
{stage_tables}</style>
<style data-marble-id="kb-stage-looks">
{stage_looks}</style>
<style data-marble-id="kb-map-dots">
{map_css}</style>
<style data-marble-id="kb-adding">
{add_css}</style>
<style data-marble-id="kb-sources">
{sources_css}</style>
<script data-marble-id="kb-home-fitter">
{fit_js}</script>
<script data-marble-id="kb-copier">
{copy_js}</script>
</div>"""


# What a person owns on the page, kept when the page is written anew: the looks
# (which lens, list and word list are open, what is picked and filtered, how the
# map and grid are set), the changes waiting, the request typed into Search, and
# what Apply said last.
LOOKS = {"kb-lens": ("data-view",), "kb-cat": ("data-cat", "data-list"), "kb-sel": ("data-sel",),
         "kb-filter-btn": ("data-filter",), "kb-map-tools": ("data-channel", "data-colour", "data-req"),
         "kb-mx-tools": ("data-channel",), "kb-wf-tools": ("data-common", "data-fam"), "kb-tray-bar": ("data-open",),
         "kb-cov-part": ("data-part",), "kb-ev-part": ("data-part",), "kb-sr-part": ("data-part",), "kb-add-who": ("data-consent",),
         "kb-so-part": ("data-part",),
         "kb-thumb": ("data-pane",)}
OWNED = ("kb-queue", "kb-q", "kb-apply-note", "kb-add-what", "kb-add-title", "kb-add-name", "kb-add-role", "kb-add-note")


def carry(page: str, old: str) -> str:
    """The new page, holding what the person put into the old one."""
    import re

    was = mdiff.index(old)
    now = mdiff.index(page)
    edits = []
    for eid, names in LOOKS.items():
        if eid in was and eid in now:
            n = now[eid]
            tag = page[n.start:n.inner_start]
            for name in names:
                if name in was[eid].attrs and name not in n.attrs:
                    tag = re.sub(r"^<([a-zA-Z][\w-]*)", lambda m: f'{m.group(0)} {name}="{esc(was[eid].attrs[name])}"', tag, count=1)
            edits.append((n.start, n.inner_start, tag))
    for eid in OWNED:
        if eid in was and eid in now:
            edits.append((now[eid].inner_start, now[eid].inner_end, mdiff.inner(old, was[eid])))
    for start, end, text in sorted(edits, reverse=True):
        page = page[:start] + text + page[end:]
    return page


def document(console, embedder: Optional[str] = None, keep: Optional[str] = None) -> str:
    """The whole console page: skeleton, every slot filled, the rules its looks
    follow, and its scripts. With `keep` (an older page's source), what a person
    put into that page comes along."""
    views = Views(console, embedder)
    slots = views.slots()
    stamp = datetime.now().astimezone().strftime("%b %-d, %H:%M")
    # Asta first (tokens, fonts, parts), then how the console wears them, then the looks.
    style = (HERE / "asta.css").read_text(encoding="utf-8") + (HERE / "marble_page.css").read_text(encoding="utf-8") + state_css()
    scripts = [(HERE / name).read_text(encoding="utf-8") for name in ("marble_affordances.js", "marble_app.js", "marble_view.js")]
    body = skeleton(slots, stamp)
    page = ("<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n<title>AstaUI Console</title>\n"
            f"<style>\n{style}</style>\n</head>\n<body>{body}\n"
            + "".join(f"<script>\n{s}</script>\n" for s in scripts)
            + "</body>\n</html>\n")
    return carry(page, keep) if keep else page


# -- bringing a page up to date ----------------------------------------------------------------------

def _stamp(word: str) -> str:
    return f"{word} {datetime.now().astimezone().strftime('%b %-d, %H:%M')}"


def page_ops(source: str, slots: Dict[str, List[Block]], texts: Optional[Dict[str, str]] = None) -> List[mdiff.Op]:
    """The edits that make each given slot hold what it should, and each given
    element say what it should."""
    nodes = mdiff.index(source)
    ops: List[mdiff.Op] = []
    for sid, blocks in slots.items():
        ops += mdiff.diff_slot(source, nodes, sid, blocks)
    for eid, text in (texts or {}).items():
        n = nodes.get(eid)
        if n is None:
            raise mdiff.PageError(f"the page has no {eid!r}; rebuild it with `astaui marble-doc`")
        if mdiff.text_of(source, n) != text:
            ops.append(mdiff.Op({"type": "setText", "id": eid, "text": text}, [eid], n.end - n.start))
    return ops


# The most one insert carries: setInner's cap and a little for the element's own tag.
INSERT_LIMIT = mdiff.INNER_LIMIT + 400
# How often the Drive takes in sent builds (`astaui intake`) and brings this
# page up to date by itself: as often as a Drive runs anything.
LOOK_EVERY = "hourly"
# What a trigger's own words are: a refresh brings these up to date on a page
# an older astaui wrote, and leaves data-marble-paused, which is the owner's.
RUN_ATTRS = ("data-marble-run", "data-marble-on", "data-marble-scope")
# The console's own style and script blocks: a refresh keeps their text current.
KEPT = ("kb-home-fit", "kb-home-fitter", "kb-stage", "kb-stage-tables", "kb-stage-looks", "kb-map-dots", "kb-adding",
        "kb-sources", "kb-copier")


def upgrade_ops(source: str, page: str, slot_ids: Sequence[str]) -> Tuple[List[mdiff.Op], List[mdiff.Op], set]:
    """What a page written by an older astaui lacks of this skeleton: each part it
    has gained, inserted whole where it belongs (a slot comes filled; a part too
    big for one edit comes with its slots empty, then a block at a time), and the
    console's own style and script blocks, new or changed. Returns the parts, the
    styles and scripts (to land last, once what they lay out is there), and every
    id the inserts bring. What the slots already there hold is page_ops' to bring
    up to date."""
    have, want = mdiff.index(source), mdiff.index(page)
    slots = set(slot_ids)

    def in_slot(eid: str) -> bool:
        p = want[eid].parent
        while p is not None:
            if p in slots:
                return True
            p = want[p].parent
        return False

    def within(eid: str, part: str) -> bool:
        p = want[eid].parent
        while p is not None and p != part:
            p = want[p].parent
        return p == part

    parts: List[mdiff.Op] = []
    looks: List[mdiff.Op] = []
    brought: set = set()
    for eid, n in want.items():
        if eid in have or n.parent is None or n.parent not in have or not n.direct or in_slot(eid):
            continue
        sibs = want[n.parent].children
        before = next((s for s in sibs[sibs.index(eid) + 1:] if s in have and have[s].parent == n.parent), None)
        markup = mdiff.outer(page, n)
        fills: List[mdiff.Op] = []
        if len(markup) > INSERT_LIMIT:
            # Too big for one edit (a new lens, filled): the part with its slots
            # empty, then each slot's blocks one at a time.
            inside = [s for s in slot_ids if s in want and within(s, eid)]
            for s in sorted(inside, key=lambda s: want[s].inner_start, reverse=True):
                a, b = want[s].inner_start - n.start, want[s].inner_end - n.start
                markup = markup[:a] + markup[b:]
            for s in sorted(inside, key=lambda s: want[s].inner_start):
                for c in want[s].children:
                    fills.append(mdiff.Op({"type": "insert", "parentId": s, "beforeId": None, "html": mdiff.outer(page, want[c])}, [], 0))
                    brought.update(mdiff.index(fills[-1].op["html"]))
            if len(markup) > INSERT_LIMIT:
                raise mdiff.PageError(f"{eid!r} is {len(markup)} characters, more than one edit can carry")
        brought.update(mdiff.index(markup))
        op = mdiff.Op({"type": "insert", "parentId": n.parent, "beforeId": before, "html": markup}, [], 0)
        (looks if n.tag in ("style", "script") else parts).extend([op] + fills)
    for eid, n in want.items():
        if eid not in have or "data-marble-run" not in n.attrs or in_slot(eid):
            continue
        for name in RUN_ATTRS:
            if n.attrs.get(name) != have[eid].attrs.get(name):
                parts.append(mdiff.Op({"type": "setAttr", "id": eid, "name": name, "value": n.attrs.get(name)}, [eid],
                                      have[eid].end - have[eid].start))
        label = mdiff.inner(page, n)
        if not n.children and "<" not in label and label != mdiff.inner(source, have[eid]):
            parts.append(mdiff.Op({"type": "setText", "id": eid, "text": _html.unescape(label)}, [eid], have[eid].end - have[eid].start))
    # Headings, the line under a lens's heading and the labels of its choices
    # are the generator's words too.
    for eid, n in want.items():
        if eid not in have or n.children or in_slot(eid) or "data-marble-run" in n.attrs:
            continue
        if not (n.tag in ("h2", "h3") or (n.tag == "p" and "lede" in n.attrs.get("class", "").split())
                or (n.tag == "button" and "data-set" in n.attrs)):
            continue
        words = mdiff.inner(page, n)
        if "<" not in words and words != mdiff.inner(source, have[eid]):
            parts.append(mdiff.Op({"type": "setText", "id": eid, "text": _html.unescape(words)}, [eid], have[eid].end - have[eid].start))
    parts += _reorder(have, want, slots, in_slot)
    for eid in KEPT:
        if eid in have and eid in want:
            new = mdiff.inner(page, want[eid])
            if new != mdiff.inner(source, have[eid]):
                if len(new) > mdiff.INNER_LIMIT:
                    raise mdiff.PageError(f"{eid!r} would hold {len(new)} characters, more than one edit can carry")
                looks.append(mdiff.Op({"type": "setInner", "id": eid, "html": new}, [eid], have[eid].end - have[eid].start))
    return parts, looks, brought


def _reorder(have: Dict[str, mdiff.Node], want: Dict[str, mdiff.Node], slots: set, in_slot) -> List[mdiff.Op]:
    """Moves that put the parts a page already has in the order the skeleton
    now gives them, moving as few as it can: those outside the longest run
    already in order, last first, each before the part that follows it."""
    ops: List[mdiff.Op] = []
    for pid, p in want.items():
        if pid not in have or pid in slots or in_slot(pid):
            continue
        order = [c for c in p.children if c in have and have[c].parent == pid]
        if len(order) < 2:
            continue
        place = {c: i for i, c in enumerate(have[pid].children)}
        pos = [place[c] for c in order]
        if pos == sorted(pos):
            continue
        # the longest run of parts already in order stays put
        best: List[List[int]] = []
        for i, x in enumerate(pos):
            run = max((r for r in best if pos[r[-1]] < x), key=len, default=[])
            best.append(run + [i])
        keep = set(max(best, key=len))
        for i in reversed(range(len(order))):
            if i in keep:
                continue
            c = order[i]
            ops.append(mdiff.Op({"type": "move", "id": c, "parentId": pid, "beforeId": order[i + 1] if i + 1 < len(order) else None},
                                [c], have[c].end - have[c].start))
    return ops


def refresh_ops(console, source: str, embedder: Optional[str] = None) -> List[mdiff.Op]:
    slots = Views(console, embedder).slots()
    parts, looks, brought = upgrade_ops(source, document(console, embedder, keep=source), list(slots))
    held = page_ops(source, {sid: blocks for sid, blocks in slots.items() if sid not in brought}, {"kb-updated": _stamp("Refreshed")})
    return parts + held + looks


def search_ops(console, source: str, request: str, card: Optional[Dict[str, Any]], embedder: Optional[str] = None) -> List[mdiff.Op]:
    res = console.search({"request": request, "card": card, "k": 3, "embedder": embedder})
    return page_ops(source, {"kb-search-results": search_blocks(res)}, {"kb-search-when": _stamp("Searched")})


def eval_ops(console, source: str, run: bool, embedder: Optional[str] = None) -> List[mdiff.Op]:
    return page_ops(source, Views(console, embedder).evaluation(run=run))


def write_batches(ops: List[mdiff.Op], note: str, out: Optional[str] = None) -> Dict[str, Any]:
    """Cut the edits into batches an agent can carry and write each to a file.
    Returns what to print: where the files are and what each holds."""
    batches = mdiff.batches(ops, note)
    folder = Path(out) if out else Path(tempfile.gettempdir()) / "astaui-console" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    folder.mkdir(parents=True, exist_ok=True)
    index = []
    for n, b in enumerate(batches, 1):
        path = folder / f"{n:02d}.json"
        path.write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
        index.append({"file": str(path), "note": b["note"], "reads": len(b["reads"]), "ops": len(b["ops"]), "chars": path.stat().st_size})
    say = (f"{len(batches)} batch{'es' if len(batches) != 1 else ''} to apply, in order." if batches
           else "Nothing to apply: the page already shows the knowledge base as it is.")
    return {"say": say, "batches": index, "ops": len(ops)}
