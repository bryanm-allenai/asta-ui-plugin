"""Builds set aside: kept on disk, left out of the knowledge base by default.

A public build comes with a run (run.json): what a computer-use agent did in it
and what a reviewing model thought of the tree it wrote. Some of those trees are
too thin or too padded to stand for the work, so kb.json's ``set_aside`` says
which runs to leave out, by rule:

    "set_aside": {"depth": ["shallow", "deep"]}

``KB.builds()``, its cards, the index, search and the console then see only the
builds the rules keep. Nothing is deleted: ``KB.open(..., everything=True)``
(``astaui --with-set-aside``, or ``ASTAUI_WITH_SET_ASIDE=1``) sees them all, and
``astaui aside`` shows what each rule would leave out.

Builds without a run (a scientist's own, a seed) are never set aside by a rule;
name one under ``builds`` to set it aside by hand.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# Each rule: what it reads, how it is written in kb.json, and what it means.
RULES: Dict[str, str] = {
    "depth": "the reviewer said the tree's nesting is (shallow, deep)",
    "verdict": "the reviewer's filing verdict is (yes, fix, no)",
    "point_below": "the reviewer's overall point (1-5) is below N",
    "coverage_below": "the reviewer's coverage score (1-5) is below N",
    "replayed_below": "a second agent replayed less than this share of the tasks (0-1)",
    "data": "the run used this kind of data (none, synthetic, example, stock, public)",
    "builds": "these builds by id, each with why",
}


def quality(run: Dict[str, Any]) -> Dict[str, Any]:
    """What the rules read from a build's run.json."""
    review = run.get("review") or {}
    rep = str((run.get("replay") or {}).get("tasks_replayed") or "")
    share = None
    if "/" in rep:
        a, b = rep.split("/", 1)
        try:
            share = int(a) / max(1, int(b))
        except ValueError:
            pass
    return {"depth": review.get("depth"), "verdict": review.get("verdict"), "point": review.get("point"),
            "coverage": review.get("coverage"), "replayed": share,
            "data": (run.get("data") or {}).get("source")}


def reasons(build_id: str, q: Optional[Dict[str, Any]], rules: Dict[str, Any]) -> List[str]:
    """Why these rules set this build aside; empty when they keep it."""
    out: List[str] = []
    named = rules.get("builds") or {}
    if build_id in named:
        out.append(f"set aside by hand: {named[build_id]}" if isinstance(named, dict) else "set aside by hand")
    if q is None:
        return out

    def below(key: str, value: Any, word: str) -> None:
        if rules.get(key) is not None and value is not None and value < rules[key]:
            out.append(f"{word} {round(value, 2)} is below {rules[key]}")

    if q["depth"] and q["depth"] in (rules.get("depth") or ()):
        out.append(f"tree is {q['depth']}")
    if q["verdict"] and q["verdict"] in (rules.get("verdict") or ()):
        out.append(f"reviewer said file: {q['verdict']}")
    if q["data"] and q["data"] in (rules.get("data") or ()):
        out.append(f"data was {q['data']}")
    below("point_below", q["point"], "point")
    below("coverage_below", q["coverage"], "coverage")
    below("replayed_below", q["replayed"], "replayed share")
    return out


def read_quality(builds_dir: Path, ids: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
    out: Dict[str, Optional[Dict[str, Any]]] = {}
    for b in ids:
        p = builds_dir / b / "run.json"
        try:
            out[b] = quality(json.loads(p.read_text(encoding="utf-8"))) if p.is_file() else None
        except (OSError, ValueError):
            out[b] = None
    return out


def set_aside(builds_dir: Path, ids: List[str], rules: Dict[str, Any]) -> Dict[str, List[str]]:
    """{build id: reasons} for every build these rules leave out."""
    if not rules:
        return {}
    qs = read_quality(builds_dir, ids)
    return {b: r for b in ids if (r := reasons(b, qs[b], rules))}


def parse(words: List[str]) -> Dict[str, Any]:
    """Rules from the command line: depth=shallow,deep point_below=4 ..."""
    out: Dict[str, Any] = {}
    for w in words:
        if "=" not in w:
            raise ValueError(f"a rule is key=value, e.g. depth=shallow,deep (got {w!r})")
        k, v = w.split("=", 1)
        if k not in RULES or k == "builds":
            raise ValueError(f"no rule called {k!r}; the rules are " + ", ".join(x for x in RULES if x != "builds"))
        if k.endswith("_below"):
            out[k] = float(v) if "." in v else int(v)
        else:
            out[k] = [x.strip() for x in v.split(",") if x.strip()]
    return out


def tally(builds_dir: Path, ids: List[str]) -> List[Tuple[str, str, int]]:
    """For each one-key rule worth trying, how many builds it alone would leave out."""
    qs = read_quality(builds_dir, ids)
    tries = [("depth", ["shallow", "deep"]), ("depth", ["shallow"]), ("verdict", ["no"]),
             ("point_below", 4), ("coverage_below", 3), ("coverage_below", 4),
             ("replayed_below", 0.8), ("replayed_below", 0.5), ("data", ["none"]), ("data", ["synthetic"])]
    out = []
    for k, v in tries:
        rules = {k: v}
        n = sum(1 for b in ids if reasons(b, qs[b], rules))
        out.append((k, ",".join(v) if isinstance(v, list) else str(v), n))
    return out
