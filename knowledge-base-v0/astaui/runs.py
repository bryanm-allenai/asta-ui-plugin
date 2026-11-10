"""What a computer-use agent found when it ran a build, as the pilot writes it.

The pilot (knowledge-base-v0/pilot) opens a build in a headless browser and
has an agent use it on its own data. Each run is a folder,
pilot/runs/<build>/<when>/, holding the agent's account as tree.json (the
goal, the phases and tasks under it, the actions that prove each task, the
features it saw and what it could not do), its screenshots under screens/,
and meta.json (how long it took and what it cost). Only the latest run of
each build is read; the others are kept for comparison.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple


@dataclass
class Run:
    build: str
    folder: Path
    when: datetime
    tree: Dict[str, Any]
    meta: Dict[str, Any]
    runs: int = 1

    @property
    def goal(self) -> Dict[str, Any]:
        return self.tree.get("tree") or {}

    @property
    def interface(self) -> Dict[str, Any]:
        return self.tree.get("interface") or {}

    @property
    def data(self) -> Dict[str, Any]:
        return self.tree.get("data") or {}

    @property
    def features(self) -> List[Dict[str, Any]]:
        return [f for f in self.tree.get("features") or [] if isinstance(f, dict)]

    @property
    def not_done(self) -> List[str]:
        return [str(x) for x in self.tree.get("not_done") or [] if str(x).strip()]

    def screen(self, name: Optional[str]) -> Optional[Path]:
        """A screenshot the tree names (screens/003.png), if the run kept it."""
        if not name:
            return None
        p = (self.folder / str(name)).resolve()
        if self.folder.resolve() not in p.parents or not p.is_file():
            return None
        return p

    def screens(self) -> List[Path]:
        d = self.folder / "screens"
        return sorted(p for p in d.iterdir() if p.suffix in (".png", ".webp", ".jpg")) if d.is_dir() else []

    def count(self, kind: str) -> int:
        return sum(1 for n in walk(self.goal) if n.get("kind") == kind)

    def phases(self) -> List[Dict[str, Any]]:
        """The phases at the top of the tree, in order. Tasks the agent put straight
        under the goal make a phase of their own, so every task sits in one."""
        out: List[Dict[str, Any]] = []
        loose: List[Dict[str, Any]] = []
        for c in self.goal.get("children") or []:
            if c.get("kind") == "phase":
                if loose:
                    out.append({"kind": "phase", "label": "Tasks", "children": loose})
                    loose = []
                out.append(c)
            elif c.get("kind") in ("task", "action"):
                loose.append(c)
        if loose:
            out.append({"kind": "phase", "label": "Tasks", "children": loose})
        return out


def walk(node: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
    yield node
    for c in node.get("children") or []:
        if isinstance(c, dict):
            yield from walk(c)


def depth(node: Dict[str, Any]) -> int:
    kids = [c for c in node.get("children") or [] if isinstance(c, dict)]
    return 1 + (max(depth(c) for c in kids) if kids else 0)


def folder(kb_root: Path) -> Path:
    """Where the pilot keeps its runs: beside the knowledge base."""
    return Path(kb_root).parent / "pilot" / "runs"


def _read(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def labelled(node: Dict[str, Any]) -> Dict[str, Any]:
    """A filed tree names each node twice, in general words and in this build's
    own words. Give it the one label the lens draws: the general words for the
    goal and its phases, this build's words for a task."""
    out = dict(node)
    if not out.get("label"):
        first = ("specific", "general") if out.get("kind") == "task" else ("general", "specific")
        out["label"] = next((str(out[k]) for k in first if out.get(k)), "")
    out["children"] = [labelled(c) for c in node.get("children") or [] if isinstance(c, dict)]
    return out


def filed(kb_root: Path) -> Dict[str, Run]:
    """The runs filed with public builds: kb/builds/<id>/tree.json, its screens/
    beside it and run.json for what the run took."""
    out: Dict[str, Run] = {}
    root = Path(kb_root) / "builds"
    if not root.is_dir():
        return out
    for b in sorted(p for p in root.iterdir() if p.is_dir()):
        tree = _read(b / "tree.json")
        if not isinstance(tree, dict) or not isinstance(tree.get("tree"), dict):
            continue
        run = _read(b / "run.json") or {}
        try:
            when = datetime.strptime(Path(str(run.get("run", ""))).name, "%Y%m%d-%H%M%S")
        except ValueError:
            when = datetime.fromtimestamp((b / "tree.json").stat().st_mtime)
        cost = sum(float(x or 0) for x in [run.get("cost_usd")] + list((run.get("filing") or {}).values())[1:])
        meta = {"total_cost_usd": round(cost, 2) if run.get("cost_usd") is not None else None,
                "duration_ms": int(float(run.get("minutes") or 0) * 60000)}
        out[b.name] = Run(b.name, b, when, dict(tree, tree=labelled(tree["tree"])), meta)
    return out


def latest(kb_root: Path) -> Dict[str, Run]:
    """Each build's latest run that finished with a tree, by build id: the pilot's
    own runs first, then the runs filed with public builds."""
    root = folder(kb_root)
    out: Dict[str, Run] = {}
    if not root.is_dir():
        return {**filed(kb_root), **out}
    for b in sorted(p for p in root.iterdir() if p.is_dir()):
        done: List[Tuple[datetime, Path, Dict[str, Any]]] = []
        for r in sorted(p for p in b.iterdir() if p.is_dir()):
            tree = _read(r / "tree.json")
            if not isinstance(tree, dict) or not isinstance(tree.get("tree"), dict):
                continue
            try:
                when = datetime.strptime(r.name, "%Y%m%d-%H%M%S")
            except ValueError:
                when = datetime.fromtimestamp((r / "tree.json").stat().st_mtime)
            done.append((when, r, tree))
        if not done:
            continue
        when, r, tree = max(done, key=lambda x: x[0])
        out[b.name] = Run(b.name, r, when, tree, _read(r / "meta.json") or {}, runs=len(done))
    return {**filed(kb_root), **out}
