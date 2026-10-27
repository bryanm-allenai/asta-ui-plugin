"""Workflows: what two builds share, and how each one is its own.

Every card files its build under a workflow: a general name, ordered steps, and
what is distinctive about the case. Each step is said twice, in general words
("decide keep or drop for each item, with a reason") and as this build does it
("k keeps a frame; r waits for a numbered reason: trail, cloud, blur").

**When two steps are the same move.** Every general step in the knowledge base is
compared with every step on every other card. Two steps count as the same move
when their similarity stands out from all those comparisons (``STEP_SD`` standard
deviations above their mean). The threshold is set by the knowledge base itself,
so the same rule holds for word matching and for neural embedders, whose
similarities sit on different scales; and it is the same for every pair, so two
unrelated workflows share nothing rather than their least-unlike steps.

**Common moves.** A step that most builds have ("export the result", "open one
item in detail") says little about which workflow a build serves. Each step is
weighted by how rare it is across the knowledge base, and steps that at least
half of the other builds share are marked common, so a match or a family rests
on the steps that define it.

**Families.** Builds are grouped by average linkage: a build joins a family only
when it is close to the family as a whole, never through a chain of neighbours.
Each member is then described by what is its own: the steps no other member has,
and what is particular to its case.
"""

from __future__ import annotations

import math
import random
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .cards import here_text, step_text
from .index import Index
from .vec import Vector, dot

FLOOR = 0.1
STEP_SD = 1.5        # how far above the mean a pair of steps must be to be the same move
SPECIFIC_SD = 3.0    # how far above the mean a need and another build's specifics must be to call it likely met
FAMILY_SD = 1.0      # how far above the mean two workflows must be to share a family
COMMON_SHARE = 0.5   # a step at least this share of other builds have is a common move
MAX_PAIRS = 20000    # sample the background above this many comparisons

StepVecs = List[Tuple[Optional[Vector], Optional[Vector]]]


def _stats(values: Sequence[float]) -> Tuple[float, float]:
    if not values:
        return 0.0, 0.0
    mean = sum(values) / len(values)
    return mean, math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))


def _steps(wf: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [s for s in (wf or {}).get("steps") or [] if s.get("step")]


def card_vectors(index: Index, card_id: str, wf: Dict[str, Any]) -> StepVecs:
    stored = index.steps(card_id)
    return [stored.get(i, (None, None)) for i in range(1, len(_steps(wf)) + 1)]


def query_vectors(index: Index, wf: Dict[str, Any]) -> StepVecs:
    steps = _steps(wf)
    if not steps:
        return []
    general = index.embed_queries([step_text(s) for s in steps])
    specific = index.embed_queries([here_text(s) for s in steps])
    return list(zip(general, specific))


def _background(groups: List[List[Vector]], seed: int = 11) -> List[float]:
    """Similarities between vectors of different groups (cards), sampled if many."""
    pairs = [(g, i, h, j) for g in range(len(groups)) for h in range(g + 1, len(groups))
             for i in range(len(groups[g])) for j in range(len(groups[h]))]
    if len(pairs) > MAX_PAIRS:
        pairs = random.Random(seed).sample(pairs, MAX_PAIRS)
    return [dot(groups[g][i], groups[h][j]) for g, i, h, j in pairs]


class StepSpace:
    """Every workflow step in the knowledge base, with the thresholds and weights
    that say when two steps are the same move and how much a shared step means."""

    def __init__(self, index: Index, cards: Dict[str, Dict[str, Any]]):
        self.index = index
        self.cards = cards
        self.workflows = {cid: c["app"].get("workflow") or {} for cid, c in cards.items()}
        self.vecs: Dict[str, StepVecs] = {cid: card_vectors(index, cid, wf) for cid, wf in self.workflows.items() if _steps(wf)}
        general = [[v[0] for v in vs if v[0] is not None] for vs in self.vecs.values()]
        specific = [[v[1] for v in vs if v[1] is not None] for vs in self.vecs.values()]
        mean, sd = _stats(_background([g for g in general if g]))
        self.tau = max(FLOOR, mean + STEP_SD * sd) if sd else 0.9
        mean, sd = _stats(_background([s for s in specific if s]))
        self.tau_specific = max(FLOOR, mean + SPECIFIC_SD * sd) if sd else 0.9
        self.n = len(self.vecs)
        # How many other builds have each step.
        self.df: Dict[Tuple[str, int], int] = {}
        for cid, vs in self.vecs.items():
            for i, (g, _) in enumerate(vs):
                self.df[(cid, i)] = self._count(g, skip=cid)

    def _count(self, v: Optional[Vector], skip: Optional[str] = None) -> int:
        if v is None:
            return 0
        n = 0
        for cid, vs in self.vecs.items():
            if cid == skip:
                continue
            if any(g is not None and dot(v, g) >= self.tau for g, _ in vs):
                n += 1
        return n

    def common(self, df: int) -> bool:
        others = max(1, self.n - 1)
        return self.n >= 4 and df / others >= COMMON_SHARE

    def weight(self, df: int) -> float:
        """Rare steps weigh more: log((builds + 1) / (builds that share it + 1))."""
        return math.log((self.n + 1) / (df + 1)) + 0.05

    def align(self, a: StepVecs, b: StepVecs) -> List[Tuple[int, int, float]]:
        """Pairs (i, j, similarity) of steps that are the same move, one to one, best first."""
        ranked = sorted(((dot(x[0], y[0]), i, j) for i, x in enumerate(a) for j, y in enumerate(b)
                         if x[0] is not None and y[0] is not None), reverse=True)
        used_a, used_b, pairs = set(), set(), []
        for s, i, j in ranked:
            if s < self.tau:
                break
            if i in used_a or j in used_b:
                continue
            used_a.add(i)
            used_b.add(j)
            pairs.append((i, j, s))
        return sorted(pairs)

    def overlap(self, a_id: str, b_id: str) -> float:
        """How much two builds' workflows share, by their steps, rare steps weighing more:
        a weighted cosine over matched steps, from 0 (nothing) to 1 (the same steps)."""
        a, b = self.vecs.get(a_id, []), self.vecs.get(b_id, [])
        if not a or not b:
            return 0.0
        wa = [self.weight(self.df[(a_id, i)]) for i in range(len(a))]
        wb = [self.weight(self.df[(b_id, j)]) for j in range(len(b))]
        shared = sum(math.sqrt(wa[i] * wb[j]) for i, j, _ in self.align(a, b))
        return shared / math.sqrt(sum(wa) * sum(wb))


def _covered(space: StepSpace, needs: List[str], offers: List[str]) -> List[Dict[str, Any]]:
    """For each need, the closest thing the other build has. A similarity cannot tell
    whether a need is truly met ("both export something" is not "exports what I
    need"), so only a near-identical specific is called likely met; every other need
    comes with its closest counterpart for a person or an agent to check in the code."""
    if not needs:
        return []
    if not offers:
        return [{"need": n, "covered": False, "closest": None, "by": None, "similarity": None} for n in needs]
    vecs = space.index.embed_queries(needs + offers)
    nv, ov = vecs[: len(needs)], vecs[len(needs):]
    out = []
    for n, v in zip(needs, nv):
        sims = [dot(v, o) for o in ov]
        j = max(range(len(sims)), key=lambda k: sims[k])
        ok = sims[j] >= space.tau_specific
        out.append({"need": n, "covered": ok, "closest": offers[j], "by": offers[j] if ok else None, "similarity": round(sims[j], 4)})
    return out


def compare(space: StepSpace, a_wf: Dict[str, Any], a_vecs: StepVecs, b_wf: Dict[str, Any], b_vecs: StepVecs,
            a_id: Optional[str] = None, b_id: Optional[str] = None) -> Dict[str, Any]:
    """Line up workflow a with workflow b. Vectors are (general, specific) per step, in order."""
    a_steps, b_steps = _steps(a_wf), _steps(b_wf)
    pairs = space.align(a_vecs, b_vecs)
    matched_a = {i for i, _, _ in pairs}
    matched_b = {j for _, j, _ in pairs}

    def df_b(j: int) -> int:
        return space.df.get((b_id, j), space._count(b_vecs[j][0], skip=b_id)) if b_id else space._count(b_vecs[j][0])

    shared = []
    for i, j, s in pairs:
        ah, bh = a_vecs[i][1], b_vecs[j][1]
        both = a_steps[i].get("here") and b_steps[j].get("here") and ah is not None and bh is not None
        shared.append({
            "step": b_steps[j]["step"],
            "a_step": a_steps[i]["step"],
            "a": a_steps[i].get("here", ""),
            "b": b_steps[j].get("here", ""),
            "parts": b_steps[j].get("parts", []),
            "similarity": round(s, 4),
            "specifics": round(dot(ah, bh), 4) if both else None,
            "common": space.common(df_b(j)),
        })
    # The steps that define the workflow first; moves most builds share last.
    shared.sort(key=lambda x: (x["common"], -x["similarity"]))
    only_a = [{"step": st["step"], "here": st.get("here", "")} for i, st in enumerate(a_steps) if i not in matched_a]
    only_b = [{"step": st["step"], "here": st.get("here", ""), "parts": st.get("parts", [])} for j, st in enumerate(b_steps) if j not in matched_b]
    a_needs = list((a_wf or {}).get("distinctive") or [])
    b_offers = [here_text(st) for st in b_steps if st.get("here")] + list((b_wf or {}).get("distinctive") or [])
    defining = [x for x in shared if not x["common"]]
    return {
        "a_name": (a_wf or {}).get("name", ""),
        "b_name": (b_wf or {}).get("name", ""),
        "shared": shared,
        "only_a": only_a,
        "only_b": only_b,
        "a_distinctive": a_needs,
        "b_distinctive": list((b_wf or {}).get("distinctive") or []),
        "a_needs": _covered(space, a_needs, b_offers),
        "share": round(len(shared) / max(1, len(a_steps)), 4),
        "defining_shared": len(defining),
    }


def compare_cards(space: StepSpace, a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    wa, wb = a["app"].get("workflow") or {}, b["app"].get("workflow") or {}
    va, vb = space.vecs.get(a["id"], []), space.vecs.get(b["id"], [])
    out = compare(space, wa, va, wb, vb, a["id"], b["id"])
    back = compare(space, wb, vb, wa, va, b["id"], a["id"])
    out["b_needs"] = back["a_needs"]
    out["a"], out["b"] = a["id"], b["id"]
    out["overlap"] = round(space.overlap(a["id"], b["id"]), 4)
    return out


def families(space: StepSpace) -> Dict[str, Any]:
    """Builds grouped by the workflows they share, by average linkage, and the moves
    common to most of the knowledge base, listed once."""
    ids = sorted(space.vecs)
    sim = {(a, b): space.overlap(a, b) for a in ids for b in ids if a < b}

    def s(a: str, b: str) -> float:
        return sim[(a, b) if a < b else (b, a)]

    mean, sd = _stats(list(sim.values()))
    theta = max(0.05, mean + FAMILY_SD * sd)
    clusters: List[List[str]] = [[i] for i in ids]
    while len(clusters) > 1:
        best = None
        for x in range(len(clusters)):
            for y in range(x + 1, len(clusters)):
                avg = sum(s(a, b) for a in clusters[x] for b in clusters[y]) / (len(clusters[x]) * len(clusters[y]))
                if best is None or avg > best[0]:
                    best = (avg, x, y)
        if best is None or best[0] < theta:
            break
        _, x, y = best
        clusters[x] = clusters[x] + clusters[y]
        del clusters[y]

    # Moves most builds share, worded by the first card that has them.
    common: List[str] = []
    for (cid, i), df in sorted(space.df.items()):
        if space.common(df):
            text = _steps(space.workflows[cid])[i]["step"]
            vec = space.vecs[cid][i][0]
            if not any(dot(vec, space.index.embed_queries([c])[0]) >= space.tau for c in common):
                common.append(text)

    out: List[Dict[str, Any]] = []
    for members in sorted(clusters, key=lambda m: (-len(m), m)):
        central = max(members, key=lambda m: sum(s(m, o) for o in members if o != m)) if len(members) > 1 else members[0]
        wf_c = space.workflows[central]
        fam: Dict[str, Any] = {"name": wf_c.get("name", ""), "central": central, "members": [], "shared_steps": []}
        shared_idx: Dict[int, int] = {}
        for m in members:
            steps = _steps(space.workflows[m])
            hits = [0] * len(steps)
            for o in members:
                if o == m:
                    continue
                for i, j, _ in space.align(space.vecs[m], space.vecs[o]):
                    hits[i] += 1
                    if m == central:
                        shared_idx[i] = shared_idx.get(i, 0) + 1
            app = space.cards[m]["app"]
            fam["members"].append({
                "id": m,
                "title": app.get("title", m),
                "field": (app.get("field") or {}).get("text", ""),
                "name": space.workflows[m].get("name", ""),
                "overlap": round(s(m, central), 4) if m != central else 1.0,
                "own_steps": [{"step": st["step"], "here": st.get("here", "")} for k, st in enumerate(steps)
                              if hits[k] == 0 and not space.common(space.df[(m, k)])],
                "distinctive": list(space.workflows[m].get("distinctive") or []),
            })
        if len(members) > 1:
            steps_c = _steps(wf_c)
            need = max(1, (len(members) - 1 + 1) // 2)
            fam["shared_steps"] = [steps_c[i]["step"] for i in sorted(shared_idx)
                                   if shared_idx[i] >= need and not space.common(space.df[(central, i)])]
        out.append(fam)
    return {"families": out, "common_moves": common, "threshold": round(theta, 4), "step_threshold": round(space.tau, 4)}


# -- text ---------------------------------------------------------------------------

def _clip(s: str, n: int = 150) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"


def format_diff(d: Dict[str, Any], you: str = "yours", them: str = "theirs", indent: str = "   ") -> List[str]:
    lines: List[str] = []
    if d.get("b_name"):
        lines.append(f"{indent}workflow: {d['b_name']}")
    defining = [s for s in d.get("shared", []) if not s.get("common")]
    common = [s for s in d.get("shared", []) if s.get("common")]
    if defining:
        lines.append(f"{indent}same steps:")
        for s in defining:
            lines.append(f"{indent}  = {s['step']}")
            if s.get("a"):
                lines.append(f"{indent}      {you}: {_clip(s['a'])}")
            if s.get("b"):
                lines.append(f"{indent}      {them}: {_clip(s['b'])}")
    if common:
        lines.append(f"{indent}also both (moves most builds have): " + "; ".join(_clip(s["step"], 60) for s in common))
    if not d.get("shared"):
        lines.append(f"{indent}no steps in common")
    if d.get("only_b"):
        lines.append(f"{indent}only {them}: " + "; ".join(_clip(s["step"], 90) for s in d["only_b"]))
    if d.get("only_a"):
        lines.append(f"{indent}only {you}: " + "; ".join(_clip(s["step"], 90) for s in d["only_a"]))
    if d.get("b_distinctive"):
        lines.append(f"{indent}particular to {them}: " + "; ".join(_clip(x, 110) for x in d["b_distinctive"]))
    needs = d.get("a_needs") or []
    if needs:
        met = [n for n in needs if n["covered"]]
        unmet = [n for n in needs if not n["covered"]]
        if met:
            lines.append(f"{indent}{you} needs it likely meets: " + "; ".join(_clip(n["need"], 90) for n in met))
        if unmet:
            lines.append(f"{indent}{you} needs to check or add (not seen in {them}):")
            for n in unmet:
                closest = f"  (closest in {them}: {_clip(n['closest'], 70)})" if n.get("closest") else ""
                lines.append(f"{indent}  - {_clip(n['need'], 100)}{closest}")
    return lines


def format_families(res: Dict[str, Any]) -> str:
    out: List[str] = []
    fams = res["families"]
    groups = [f for f in fams if len(f["members"]) > 1]
    alone = [f for f in fams if len(f["members"]) == 1]
    if res.get("common_moves"):
        out.append("Moves most builds have, so they do not make a family: " + "; ".join(res["common_moves"]))
        out.append("")
    for f in groups:
        out.append(f"{f['name']}  ({len(f['members'])} builds)")
        if f["shared_steps"]:
            out.append("  shared steps: " + "; ".join(_clip(s, 80) for s in f["shared_steps"]))
        for m in f["members"]:
            out.append(f"  - {m['title']}  [{m['id']}]  {m['field']}")
            if m["own_steps"]:
                out.append("      its own steps: " + "; ".join(_clip(s["step"], 80) for s in m["own_steps"]))
            if m["distinctive"]:
                out.append("      particular to it: " + "; ".join(_clip(x, 100) for x in m["distinctive"]))
        out.append("")
    if alone:
        out.append("Workflows with no close relative yet:")
        for f in alone:
            m = f["members"][0]
            out.append(f"  - {m['title']}  [{m['id']}]: {m['name']}")
    return "\n".join(out).rstrip() + "\n"
