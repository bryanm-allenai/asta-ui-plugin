"""The features agents named in the builds they ran, grouped across builds.

A run's tree.json lists the features the agent saw: a widget or component with
the small workflow around it (a range slider that moves an interval and updates
its table, a canvas whose layout algorithm can be switched). Each has a name, a
general description in words any field would use, and this build's own words.

kb/features.json groups them: a list of groups, each with a key, a name, what
its features let a person do, and where its edge with the nearest group runs,
and an assignment of every feature (by "build/feature id") to one group. The
groups are by what the widget does for a person, not by field, so a heatmap of
protein mutations and one of gene expression sit together. A feature the file
does not assign (a build filed after the grouping was made) is "not grouped
yet" until `astaui features todo` and `astaui features put` give it a group.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import runs as _runs

SCHEMA = "astaui.features/1"
UNGROUPED = "not-grouped"


@dataclass
class Feature:
    key: str            # "build/f1"
    build: str
    run: Any            # the runs.Run it came from
    data: Dict[str, Any]

    @property
    def name(self) -> str:
        return str(self.data.get("name") or "")

    @property
    def general(self) -> str:
        return str(self.data.get("general") or self.data.get("what_it_does") or "")

    @property
    def check(self) -> str:
        return str(self.data.get("check") or "")

    def screen(self) -> Optional[Path]:
        """The first screenshot it cites that the build kept."""
        for ref in self.data.get("screens") or []:
            p = self.run.screen(ref)
            if p:
                return p
        return None


@dataclass
class Group:
    key: str
    name: str
    about: str = ""
    edges: str = ""
    members: List[Feature] = field(default_factory=list)

    def builds(self) -> List[str]:
        return list(dict.fromkeys(f.build for f in self.members))


def path(kb_root: Path) -> Path:
    """kb/features.json, or $ASTAUI_FEATURES_AT to try a grouping before it is filed."""
    return Path(os.environ.get("ASTAUI_FEATURES_AT") or Path(kb_root) / "features.json")


def read(kb_root: Path) -> Dict[str, Any]:
    p = path(kb_root)
    if not p.is_file():
        return {"schema": SCHEMA, "groups": [], "assign": {}}
    return json.loads(p.read_text(encoding="utf-8"))


def write(kb_root: Path, data: Dict[str, Any]) -> None:
    data = dict(data, schema=SCHEMA)
    data["assign"] = dict(sorted(data.get("assign", {}).items()))
    path(kb_root).write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def every(kb_root: Path, builds: Optional[set] = None) -> List[Feature]:
    """Every feature of every build's latest run, in build order."""
    out: List[Feature] = []
    for b, r in sorted(_runs.latest(Path(kb_root)).items()):
        if builds is not None and b not in builds:
            continue
        for n, f in enumerate(r.features, 1):
            out.append(Feature(f"{b}/{f.get('id') or f'f{n}'}", b, r, f))
    return out


def groups(kb_root: Path, builds: Optional[set] = None) -> List[Group]:
    """The groups in the file's order, each holding its features; the features the
    file does not place come last, as a group of their own, if there are any."""
    data = read(kb_root)
    out = [Group(g["key"], g["name"], g.get("about", ""), g.get("edges", "")) for g in data.get("groups", [])]
    by = {g.key: g for g in out}
    loose = Group(UNGROUPED, "Not grouped yet", "Features from builds filed after the groups were made. "
                  "`astaui features todo` lists them for an agent to place.")
    assign = data.get("assign", {})
    for f in every(kb_root, builds):
        by.get(assign.get(f.key, ""), loose).members.append(f)
    return [g for g in out if g.members] + ([loose] if loose.members else [])


def todo(kb_root: Path) -> Dict[str, Any]:
    """What an agent needs to place the features no group holds yet."""
    data = read(kb_root)
    assign = data.get("assign", {})
    loose = [{"k": f.key, "name": f.name, "general": f.general} for f in every(kb_root) if f.key not in assign]
    return {"instructions": ("Place each feature below in the one group whose `about` says what it lets a person do; "
                             "`edges` says where neighbouring groups divide. Write a JSON object mapping each feature's k "
                             "to a group key, then run `astaui features put <file>`."),
            "groups": [{k: g.get(k, "") for k in ("key", "name", "about", "edges")} for g in data.get("groups", [])],
            "features": loose}


def put(kb_root: Path, assign: Dict[str, str]) -> Dict[str, Any]:
    """Merge an assignment into the file; refuses keys of groups it does not have."""
    data = read(kb_root)
    known = {g["key"] for g in data.get("groups", [])}
    bad = sorted({v for v in assign.values() if v not in known})
    if bad:
        raise ValueError(f"no such group: {', '.join(bad)}")
    data.setdefault("assign", {}).update(assign)
    data["made"] = dict(data.get("made") or {}, updated=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    write(kb_root, data)
    return {"placed": len(assign), "total": len(data["assign"])}
