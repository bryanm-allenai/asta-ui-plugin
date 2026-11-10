"""The console's data, kept beside the page instead of in it.

The console page holds what people do in it: which view is open, what is
picked, the changes waiting, the notes and verdicts they write, and the
buttons that start an agent. What the knowledge base says (the map's points,
the word lists, every build's card, run tree and pair comparisons) grows with
every build filed, so it lives in files the page reads when it needs them:

  <kb>/console-data/                     a link to ~/astaui-console-data, out of the drive's scan
    current.json                         which generation to read, and what is in it
    g-<stamp>/groups/<group>.json        {slot id: markup} for the slots one view needs
    g-<stamp>/picks/<kind>/<key>.json    {slot id: markup} for one picked build, pair or request

A slot is the page element a Views part fills. A slot in GROUPS is drawn
whole when its view first opens; a slot in PICKS holds only the blocks of
whatever is picked. On the page both are empty and data-marble-transient: the
page's own script (marble_data.js) fills them, and nothing it draws is filed.
A refresh writes a new generation and points current.json at it; open pages
notice and draw it again. Two generations are kept, so a page that read the
older one a moment ago can still finish reading it.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .atlas import TERM_LISTS

Block = Tuple[str, str]

# Slots drawn whole, by the view that shows them. "boot" is drawn at once: the
# list down the side and the screenshots' rules every view uses.
GROUPS: Dict[str, Tuple[str, ...]] = {
    "boot": ("kb-cat-builds", "kb-cat-reqs", "kb-cat-pairs", "kb-shots"),
    "home": ("kb-home-make", "kb-home-code"),
    "map": ("kb-map-pts", "kb-map-pos", "kb-map-gpos"),
    "coverage": tuple(f"kb-cov-{f}-{l}-rows" for f, l, _, _ in TERM_LISTS),
    "workflows": ("kb-wf-fams", "kb-wf-body"),
    "runs": ("kb-ru-all", "kb-ru-rules"),
    "sources": ("kb-so-rows",),
    "features": ("kb-fe-groups", "kb-fe-heads", "kb-fe-cards", "kb-fe-rules"),
}
# The view each group belongs to, where it is not the group's own name.
VIEWS: Dict[str, str] = {}
# Picking a word draws its panel from the coverage rows, so a word needs them.
NEEDS: Dict[str, str] = {"t": "coverage"}
# Slots that hold only what is picked: each block names its pick in data-for
# (b:<id>, p:<a>|<b>, q:<id>) or, in Agent Runs, the build in data-b.
PICKS: Tuple[str, ...] = ("kb-insp-b", "kb-insp-q", "kb-insp-p", "kb-ru-heads", "kb-ru-tree", "kb-ru-feats", "kb-ru-gaps")

GROUP_OF: Dict[str, str] = {sid: g for g, sids in GROUPS.items() for sid in sids}
DATA = frozenset(GROUP_OF) | frozenset(PICKS)
KEEP_GENERATIONS = 2
LINK = "console-data"


_FOR = re.compile(r'^<[a-zA-Z][\w-]*\b[^>]*?\sdata-(for|b)="([^"]*)"')


def is_data(sid: str) -> bool:
    return sid in DATA


def pick_of(markup: str) -> Optional[str]:
    """What a block in a pick slot belongs to: its data-for, or b:<data-b>."""
    m = _FOR.match(markup)
    if not m:
        return None
    return m.group(2) if m.group(1) == "for" else f"b:{m.group(2)}"


def pick_file(pick: str) -> str:
    """Where a pick's blocks are kept, under the generation. marble_data.js
    makes the same name: the kind, then the rest with anything but a letter,
    digit or hyphen written as _ and its code in hex (the | of a pair is _7c)."""
    kind, _, rest = pick.partition(":")
    name = re.sub(r"[^A-Za-z0-9-]", lambda m: f"_{ord(m.group(0)):x}", rest)
    return f"picks/{kind}/{name}.json"


def folder(kb_root: Path) -> Path:
    """The data folder beside the knowledge base: console-data, next to kb/. On
    the owner's computer it is a link to ~/astaui-console-data, so its thousands
    of files stay out of the drive's scan; with $ASTAUI_CONSOLE_DATA set, a
    missing folder is made as a link there. Otherwise it is a plain folder."""
    root = Path(kb_root)
    link = (root.parent if root.name == "kb" else root) / LINK
    if not link.exists():
        if link.is_symlink():
            link.unlink()
        target = os.environ.get("ASTAUI_CONSOLE_DATA")
        if target:
            Path(target).mkdir(parents=True, exist_ok=True)
            link.symlink_to(Path(target), target_is_directory=True)
        else:
            link.mkdir(parents=True)
    return link


def drive_path(path: Path) -> Optional[str]:
    """The path the drive serves a file at: from the folder holding .marble,
    without following the link, so it stays inside the drive."""
    p = Path(os.path.abspath(path))
    for d in p.parents:
        if (d / ".marble").is_dir():
            return p.relative_to(d).as_posix()
    return None


def _write_json(path: Path, obj: Any) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    path.write_text(text, encoding="utf-8")
    return len(text)


def write(slots: Dict[str, List[Block]], kb_root: Path, builds: int = 0) -> Dict[str, Any]:
    """Write every data slot's markup as a new generation and point current.json
    at it. Returns the manifest."""
    root = folder(kb_root)
    gen = "g-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    out = root / gen
    groups: Dict[str, List[str]] = {}
    sizes: Dict[str, int] = {}
    for g, sids in GROUPS.items():
        have = {sid: "".join(h for _, h in slots[sid]) for sid in sids if sid in slots}
        if have:
            groups[g] = list(have)
            sizes[g] = _write_json(out / "groups" / f"{g}.json", have)
    picks: Dict[str, Dict[str, str]] = {}
    for sid in PICKS:
        for _, h in slots.get(sid, []):
            key = pick_of(h)
            if key:
                picks.setdefault(key, {})
                picks[key][sid] = picks[key].get(sid, "") + h
    kinds: Dict[str, int] = {}
    for key, have in picks.items():
        _write_json(out / pick_file(key), have)
        kinds[key.split(":", 1)[0]] = kinds.get(key.split(":", 1)[0], 0) + 1
    manifest = {"gen": gen, "made": datetime.now().astimezone().isoformat(timespec="seconds"), "builds": builds,
                "groups": groups, "views": {g: VIEWS.get(g, g) for g in groups}, "picks": [s for s in PICKS if s in slots],
                "needs": NEEDS, "counts": kinds, "sizes": sizes}
    tmp = root / "current.json.tmp"
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, root / "current.json")
    olds = sorted(p for p in root.iterdir() if p.is_dir() and p.name.startswith("g-") and p.name != gen)
    for p in olds[: max(0, len(olds) - (KEEP_GENERATIONS - 1))]:
        shutil.rmtree(p, ignore_errors=True)
    return manifest


def script(kb_root: Path) -> str:
    """marble_data.js, told where the data folder is in the drive."""
    where = drive_path(folder(kb_root)) or LINK
    js = Path(__file__).with_name("marble_data.js").read_text(encoding="utf-8")
    return js.replace("__DATA_DIR__", where.replace("\\", "\\\\").replace("'", "\\'"))
