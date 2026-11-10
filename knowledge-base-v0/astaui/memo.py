"""What the console works out about each build, kept between refreshes.

A refresh draws every build, and most of what it needs about one build (the
privacy scan of its code, its card checked against the ontology, the size of
each part's slice, its folder checked) depends only on that build's own files,
its card and the ontology. Those answers are kept in <kb>/.cache/memo.json
under a fingerprint of the files they came from, so a refresh works them out
again only for a build that is new or has changed. A knowledge base that cannot
be written to still works: it just keeps nothing.
"""
from __future__ import annotations

import atexit
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .kb import KB, Build

VERSION = 1
_open: Dict[str, "Memo"] = {}


def _stat(p: Path) -> Tuple[int, int]:
    try:
        st = p.stat()
        return st.st_mtime_ns, st.st_size
    except OSError:
        return 0, -1


class Memo:
    def __init__(self, kb: KB):
        self.kb = kb
        self.path = kb.root / ".cache" / "memo.json"
        self.data: Dict[str, Dict[str, Any]] = {}
        self.prints: Dict[str, str] = {}
        self.dirty = False
        try:
            got = json.loads(self.path.read_text(encoding="utf-8"))
            if got.get("version") == VERSION:
                self.data = got.get("builds") or {}
        except (OSError, ValueError):
            pass

    def fingerprint(self, b: Build) -> str:
        """Every file under the build's folder, by path, time and size, with its card
        and the ontology: what any answer kept here could depend on."""
        if b.id in self.prints:
            return self.prints[b.id]
        h = hashlib.sha1()
        for top, dirs, files in os.walk(b.path):
            dirs.sort()
            for f in sorted(files):
                p = os.path.join(top, f)
                st = os.stat(p)
                h.update(f"{os.path.relpath(p, b.path)}\0{st.st_mtime_ns}\0{st.st_size}\n".encode())
        for p in (self.kb.card_path(b.id), self.kb.root / "ontology.json"):
            h.update(f"{p.name}\0{_stat(p)}\n".encode())
        self.prints[b.id] = h.hexdigest()
        return self.prints[b.id]

    def get(self, b: Build, name: str, work: Callable[[], Any]) -> Any:
        fp = self.fingerprint(b)
        entry = self.data.get(b.id)
        if not entry or entry.get("fp") != fp:
            entry = self.data[b.id] = {"fp": fp}
        if name not in entry:
            entry[name] = work()
            self.dirty = True
        return entry[name]

    def save(self) -> None:
        if not self.dirty or self.kb.read_only:
            return
        keep = set(self.kb.build_ids())
        out = {"version": VERSION, "builds": {k: v for k, v in self.data.items() if k in keep}}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            os.replace(tmp, self.path)
            self.dirty = False
        except OSError:
            pass


def memo(kb: KB) -> Memo:
    key = str(kb.root.resolve())
    if key not in _open:
        if not _open:
            atexit.register(save_all)
        _open[key] = Memo(kb)
    return _open[key]


def save_all() -> None:
    for m in _open.values():
        m.save()


# -- the answers kept ------------------------------------------------------------------------------

def findings(kb: KB, b: Build) -> List[Any]:
    """privacy.scan_build, kept."""
    from .privacy import Finding, scan_build

    rows = memo(kb).get(b, "scan", lambda: [f.__dict__ for f in scan_build(b)])
    return [Finding(**r) for r in rows]


def card_check(kb: KB, ont, card: Dict[str, Any], b: Build) -> Tuple[List[str], List[str]]:
    """The errors and warnings check_card finds in a build's card, kept."""
    from .cards import check_card

    def work():
        _, chk = check_card(ont, card, b, made=card.get("made"))
        return [list(chk.errors), list(chk.warnings)]
    errors, warnings = memo(kb).get(b, "card", work)
    return errors, warnings


def slice_lines(kb: KB, b: Build, card: Dict[str, Any]) -> List[int]:
    """How many lines the slice of each of the card's parts has, in the card's order, kept."""
    from .slices import slice_part
    from .symbols import index_build

    def work():
        syms = index_build(b)
        return [slice_part(kb, b.id, p, symbols=syms)["lines"] for p in card.get("parts", [])]
    return memo(kb).get(b, "slices", work)

