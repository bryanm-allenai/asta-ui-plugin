"""Workflows: what two builds share, and how each one is its own.

Every card files its build under a workflow: a general name, ordered steps, and
what is distinctive about the case. Each step is said twice, in general words
("decide keep or drop for each item, with a reason") and as this build does it
("k keeps a frame; r waits for a numbered reason: trail, cloud, blur").

**When two steps are the same move.** Every general step in the knowledge base
belongs to a step type: the steps whose similarity stands out from all the
comparisons between builds (``STEP_SD`` standard deviations above their mean).
The threshold is set by the knowledge base itself, so the same rule holds for
word matching and for neural embedders, whose similarities sit on different
scales. Two steps of the knowledge base are the same move when they are of the
same type; a request's steps are matched to a build's when they clear the same
threshold. Grouping steps into types, rather than linking every pair, keeps the
work in step with the number of steps, so it holds at thousands of builds.

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

import bisect
import hashlib
import heapq
import json
import math
import random
from collections.abc import Mapping
from collections.abc import Sequence as _Sequence
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Set, Tuple

from .cards import here_text, step_text
from .index import Index
from .vec import Vector, VecSet, dot, threshold_clusters

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


class _CrossPairs(_Sequence):
    """Every (group, item, other group, other item) with the groups different, in a
    fixed order, without listing them: item k is worked out on demand. Sampling from
    it draws exactly what sampling from the full list would, at any size."""

    def __init__(self, sizes: List[int]):
        self.sizes = sizes
        self.prefix = [0]
        for n in sizes:
            self.prefix.append(self.prefix[-1] + n)
        total = self.prefix[-1]
        # Row g holds every pair with g first: |g| times everything after it.
        self.rows = [n * (total - self.prefix[g + 1]) for g, n in enumerate(sizes)]
        self.row_start = [0]
        for r in self.rows:
            self.row_start.append(self.row_start[-1] + r)

    def __len__(self) -> int:
        return self.row_start[-1]

    def __getitem__(self, k: int) -> Tuple[int, int, int, int]:
        if k < 0:
            k += len(self)
        if not 0 <= k < len(self):
            raise IndexError(k)
        g = bisect.bisect_right(self.row_start, k) - 1
        r = k - self.row_start[g]
        ng = self.sizes[g]
        base = self.prefix[g + 1]
        h = bisect.bisect_right(self.prefix, base + r // ng) - 1
        rem = r - ng * (self.prefix[h] - base)
        nh = self.sizes[h]
        return g, rem // nh, h, rem % nh


def _background(groups: List[List[Vector]], seed: int = 11) -> List[float]:
    """Similarities between vectors of different groups (cards), sampled if many."""
    pairs: Sequence[Tuple[int, int, int, int]] = _CrossPairs([len(g) for g in groups])
    if len(pairs) > MAX_PAIRS:
        pairs = random.Random(seed).sample(pairs, MAX_PAIRS)
    return [dot(groups[g][i], groups[h][j]) for g, i, h, j in pairs]


class _Lazy(Mapping):
    """A mapping whose values are made the first time each is asked for."""

    def __init__(self, keys: Iterable[str], make: Callable[[str], Any]):
        self._keys = list(keys)
        self._has = set(self._keys)
        self._make = make
        self._made: Dict[str, Any] = {}

    def __getitem__(self, key: str) -> Any:
        if key not in self._has:
            raise KeyError(key)
        if key not in self._made:
            self._made[key] = self._make(key)
        return self._made[key]

    def __contains__(self, key: object) -> bool:
        return key in self._has

    def __iter__(self) -> Iterator[str]:
        return iter(self._keys)

    def __len__(self) -> int:
        return len(self._keys)


class _StepFacts(Mapping):
    """A read-only view of one fact about every step, (build, step) -> value, that reads
    a build's steps only when one of them is asked for."""

    def __init__(self, space: "StepSpace", which: int):
        self._space = space
        self._which = which  # 0: the step's type, 1: how many other builds share it

    def __getitem__(self, key: Tuple[str, int]) -> int:
        cid, i = key
        fact = self._space.facts(cid).get(i) if cid in self._space.counts else None
        if fact is None or (self._which == 0 and fact[0] is None):
            raise KeyError(key)
        return fact[self._which]  # type: ignore[return-value]

    def __contains__(self, key: object) -> bool:
        try:
            self[key]  # type: ignore[index]
            return True
        except (KeyError, TypeError, ValueError):
            return False

    def __iter__(self) -> Iterator[Tuple[str, int]]:
        self._space.load_all_facts()
        for cid, steps in self._space._facts.items():
            for i, fact in steps.items():
                if self._which == 1 or fact[0] is not None:
                    yield (cid, i)

    def __len__(self) -> int:
        return sum(1 for _ in self)


class StepSpace:
    """Every workflow step in the knowledge base, with the thresholds and weights
    that say when two steps are the same move and how much a shared step means.

    Steps are grouped into **step types**: each general step joins the type it is
    most like, when that is at least the step threshold, or starts a new one. Two
    steps of the knowledge base are the same move when they are of the same type,
    and a step is as common as the number of builds its type spans. The types are
    worked out once, when the index is built, and kept beside the vectors they came
    from, so a search reads them instead of comparing every step with every other.
    A request's steps, which are not in the knowledge base, are still compared with
    the steps they meet one by one."""

    VERSION = 5

    def __init__(self, index: Index, cards: Mapping[str, Dict[str, Any]]):
        self.index = index
        self.cards = cards
        # Workflows and step vectors are read for a build only when something asks for
        # it, so a search over a large knowledge base reads the few builds it shows.
        self.workflows: Mapping[str, Dict[str, Any]] = _Lazy(cards, lambda cid: self.cards[cid]["app"].get("workflow") or {})
        kept = self._kept()
        counts = kept["steps"] if kept is not None else \
            {cid: len(_steps(self.workflows[cid])) for cid in cards if _steps(self.workflows[cid])}
        # How many steps each build with a workflow has.
        self.counts: Dict[str, int] = counts
        self.vecs: Mapping[str, StepVecs] = _Lazy(counts, lambda cid: card_vectors(index, cid, self.workflows[cid]))
        self.n = len(counts)
        self._rows: Optional[List[Tuple[str, int]]] = None
        self._row_of: Optional[Dict[Tuple[str, int], int]] = None
        self._set: Optional[VecSet] = None
        # Each step's type and how many other builds share it, read a build at a time.
        self._facts: Dict[str, Dict[int, Tuple[Optional[int], int]]] = {}
        self._all_facts = False
        if kept is None:
            kept = self._work_out()
        self.tau, self.tau_specific = kept["tau"], kept["tau_specific"]
        # type_of[(build, step)] = its step type; df[(build, step)] = how many other builds share it.
        self.type_of: Mapping[Tuple[str, int], int] = _StepFacts(self, 0)
        self.df: Mapping[Tuple[str, int], int] = _StepFacts(self, 1)
        self._members: Optional[Dict[int, List[Tuple[str, int]]]] = None
        self._linked: Optional[Dict[str, Set[str]]] = None
        self._by_type: Dict[str, Dict[int, List[int]]] = {}
        self._w: Dict[str, Tuple[List[float], float]] = {}

    @property
    def rows(self) -> List[Tuple[str, int]]:
        """Every general step, flattened, with the build it belongs to. Reads every
        build's step vectors."""
        if self._rows is None:
            self._rows = [(cid, i) for cid, vs in self.vecs.items() for i, (g, _) in enumerate(vs) if g is not None]
        return self._rows

    @property
    def row_of(self) -> Dict[Tuple[str, int], int]:
        if self._row_of is None:
            self._row_of = {key: r for r, key in enumerate(self.rows)}
        return self._row_of

    def _sim(self, a_id: str, i: int, b_id: str, j: int) -> float:
        """The similarity of two steps of the knowledge base."""
        if self._set is not None:
            return self._set.sim(self.row_of[(a_id, i)], self.row_of[(b_id, j)])
        return dot(self.vecs[a_id][i][0], self.vecs[b_id][j][0])  # type: ignore[arg-type]

    def steps_by_type(self, cid: str) -> Dict[int, List[int]]:
        """A build's steps grouped by step type: {type: [step, ...]}."""
        if cid not in self._by_type:
            out: Dict[int, List[int]] = {}
            for i in range(self.counts.get(cid, 0)):
                t = self.type_of.get((cid, i))
                if t is not None:
                    out.setdefault(t, []).append(i)
            self._by_type[cid] = out
        return self._by_type[cid]

    def matched(self, a_id: str, b_id: str) -> List[Tuple[int, int]]:
        """The steps two builds of the knowledge base share, one to one, as (i, j):
        what ``align`` pairs, without working out similarities where a type holds
        one step on each side, which is nearly always."""
        ta, tb = self.steps_by_type(a_id), self.steps_by_type(b_id)
        if len(ta) > len(tb):
            pairs = [(i, j) for j, i in self.matched(b_id, a_id)]
            return sorted(pairs)
        out: List[Tuple[int, int]] = []
        for t, ia in ta.items():
            jb = tb.get(t)
            if not jb:
                continue
            if len(ia) == 1 and len(jb) == 1:
                out.append((ia[0], jb[0]))
                continue
            ranked = sorted(((self._sim(a_id, i, b_id, j), i, j) for i in ia for j in jb), reverse=True)
            used_a, used_b = set(), set()
            for _, i, j in ranked:
                if i in used_a or j in used_b:
                    continue
                used_a.add(i)
                used_b.add(j)
                out.append((i, j))
        return sorted(out)

    @property
    def set(self) -> VecSet:
        """Every general step as one VecSet, in the order of ``rows``."""
        if self._set is None:
            self._set = VecSet([self.vecs[cid][i][0] for cid, i in self.rows])  # type: ignore[misc]
        return self._set

    def facts(self, cid: str) -> Dict[int, Tuple[Optional[int], int]]:
        """One build's steps: {step: (type, how many other builds share it)}."""
        if cid not in self._facts:
            got: Dict[int, Tuple[Optional[int], int]] = {i: (None, 0) for i in range(self.counts.get(cid, 0))}
            if not self._all_facts:
                for _, i, t, df in self.index.step_facts(cid):
                    got[i] = (t, df)
            self._facts[cid] = got
        return self._facts[cid]

    def load_all_facts(self) -> None:
        if not self._all_facts:
            rows: Dict[str, Dict[int, Tuple[Optional[int], int]]] = {cid: {i: (None, 0) for i in range(n)}
                                                                      for cid, n in self.counts.items()}
            for cid, i, t, df in self.index.step_facts():
                if cid in rows:
                    rows[cid][i] = (t, df)
            self._facts = rows
            self._all_facts = True

    @property
    def members(self) -> Dict[int, List[Tuple[str, int]]]:
        """members[type] = every (build, step) of that type."""
        if self._members is None:
            self.load_all_facts()
            members: Dict[int, List[Tuple[str, int]]] = {}
            for cid, steps in self._facts.items():
                for i, (t, _) in steps.items():
                    if t is not None:
                        members.setdefault(t, []).append((cid, i))
            self._members = members
        return self._members

    @property
    def builds_of(self) -> Dict[int, Set[str]]:
        return {t: {cid for cid, _ in m} for t, m in self.members.items()}

    @property
    def linked(self) -> Dict[str, Set[str]]:
        """For each build, the builds it shares a step type with that is not a common move.
        Builds that share only common moves never make a family, so they are left out,
        and the pairs stay few however large the knowledge base grows."""
        if self._linked is None:
            linked: Dict[str, Set[str]] = {}
            for t, members in self.members.items():
                builds = {cid for cid, _ in members}
                if len(builds) < 2 or self.common(len(builds) - 1):
                    continue
                for a in builds:
                    linked.setdefault(a, set()).update(builds - {a})
            self._linked = linked
        return self._linked

    # -- worked out once, kept in the index ---------------------------------------------
    def _signature(self) -> str:
        ids = hashlib.sha1(",".join(sorted(self.cards)).encode("utf-8")).hexdigest()
        return f"{self.VERSION}:{STEP_SD}:{SPECIFIC_SD}:{FLOOR}:{MAX_PAIRS}:{self.index.generation()}:{ids}"

    def _kept(self) -> Optional[Dict[str, Any]]:
        try:
            value = self.index.derived("steps", self._signature())
        except Exception:
            return None
        return json.loads(value) if value else None

    def _work_out(self) -> Dict[str, Any]:
        general = [[v[0] for v in vs if v[0] is not None] for vs in self.vecs.values()]
        specific = [[v[1] for v in vs if v[1] is not None] for vs in self.vecs.values()]
        mean, sd = _stats(_background([g for g in general if g]))
        tau = max(FLOOR, mean + STEP_SD * sd) if sd else 0.9
        mean, sd = _stats(_background([s for s in specific if s]))
        tau_specific = max(FLOOR, mean + SPECIFIC_SD * sd) if sd else 0.9
        types = threshold_clusters(self.set.vectors, tau)
        type_of = dict(zip(self.rows, types))
        spans: Dict[int, Set[str]] = {}
        for (cid, _), t in type_of.items():
            spans.setdefault(t, set()).add(cid)
        facts = {cid: {i: (type_of.get((cid, i)), len(spans[type_of[(cid, i)]] - {cid}) if (cid, i) in type_of else 0)
                       for i in range(n)} for cid, n in self.counts.items()}
        self._facts, self._all_facts = facts, True
        out = {"tau": tau, "tau_specific": tau_specific, "steps": dict(self.counts)}
        try:
            self.index.keep_steps(self._signature(), json.dumps(out),
                                  [(cid, i, t, df) for cid, steps in facts.items() for i, (t, df) in steps.items() if t is not None])
        except Exception:
            pass  # a read-only knowledge base still searches; it works this out each time
        return out

    def _count(self, v: Optional[Vector], skip: Optional[str] = None) -> int:
        """How many builds (other than skip) have a step that is the same move as v."""
        if v is None:
            return 0
        found = {self.rows[r][0] for r, s in enumerate(self.set.scores(v))
                 if s >= self.tau - 1e-9 and dot(v, self.set.vectors[r]) >= self.tau}
        found.discard(skip)  # type: ignore[arg-type]
        return len(found)

    def common(self, df: int) -> bool:
        others = max(1, self.n - 1)
        return self.n >= 4 and df / others >= COMMON_SHARE

    def weight(self, df: int) -> float:
        """Rare steps weigh more: log((builds + 1) / (builds that share it + 1))."""
        return math.log((self.n + 1) / (df + 1)) + 0.05

    def align(self, a: StepVecs, b: StepVecs, a_id: Optional[str] = None,
              b_id: Optional[str] = None) -> List[Tuple[int, int, float]]:
        """Pairs (i, j, similarity) of steps that are the same move, one to one, best first.
        Two builds of the knowledge base, named by id, pair the steps of the same type;
        anything else pairs the steps at least the step threshold alike."""
        if a_id is not None and b_id is not None and a is self.vecs.get(a_id) and b is self.vecs.get(b_id):
            ta = self.type_of
            ranked = sorted(((self._sim(a_id, i, b_id, j), i, j)
                             for i in range(len(a)) for j in range(len(b))
                             if (a_id, i) in ta and ta[(a_id, i)] == ta.get((b_id, j))), reverse=True)
            floor = -2.0
        else:
            ranked = sorted(((dot(x[0], y[0]), i, j) for i, x in enumerate(a) for j, y in enumerate(b)
                             if x[0] is not None and y[0] is not None), reverse=True)
            floor = self.tau
        used_a, used_b, pairs = set(), set(), []
        for s, i, j in ranked:
            if s < floor:
                break
            if i in used_a or j in used_b:
                continue
            used_a.add(i)
            used_b.add(j)
            pairs.append((i, j, s))
        return sorted(pairs)

    def same_move(self, a_id: str, i: int, b_id: str, j: int) -> bool:
        """Whether step i of one build and step j of another are the same move."""
        t = self.type_of.get((a_id, i))
        return t is not None and t == self.type_of.get((b_id, j))

    def overlap(self, a_id: str, b_id: str) -> float:
        """How much two builds' workflows share, by their steps, rare steps weighing more:
        a weighted cosine over matched steps, from 0 (nothing) to 1 (the same steps)."""
        if not self.counts.get(a_id) or not self.counts.get(b_id):
            return 0.0
        wa, na = self._weights(a_id)
        wb, nb = self._weights(b_id)
        shared = sum(math.sqrt(wa[i] * wb[j]) for i, j in self.matched(a_id, b_id))
        return shared / math.sqrt(na * nb)

    def _weights(self, cid: str) -> Tuple[List[float], float]:
        if cid not in self._w:
            w = [self.weight(self.df[(cid, i)]) for i in range(self.counts.get(cid, 0))]
            self._w[cid] = (w, sum(w))
        return self._w[cid]


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
    pairs = space.align(a_vecs, b_vecs, a_id, b_id)
    matched_a = {i for i, _, _ in pairs}
    matched_b = {j for _, j, _ in pairs}

    def df_b(j: int) -> int:
        if b_id and (b_id, j) in space.df:
            return space.df[(b_id, j)]
        return space._count(b_vecs[j][0], skip=b_id)

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


def _average_linkage(ids: List[str], sim: Dict[Tuple[str, str], float], theta: float) -> List[List[str]]:
    """Average-linkage clusters: repeatedly join the two clusters whose members are
    most alike on average, while that average is at least theta. Only clusters with
    some similarity between them are ever compared, so the work grows with the links,
    not with every pair. Each cluster lists its members in the order they joined,
    and clusters keep the place of their first member."""
    members: Dict[int, List[str]] = {k: [i] for k, i in enumerate(ids)}
    total: Dict[int, Dict[int, float]] = {k: {} for k in members}
    at = {i: k for k, i in enumerate(ids)}
    for (a, b), v in sim.items():
        x, y = at[a], at[b]
        total[x][y] = total[x].get(y, 0.0) + v
        total[y][x] = total[y].get(x, 0.0) + v
    stamp = {k: 0 for k in members}
    heap: List[Tuple[float, int, int, int, int]] = []

    def push(x: int, y: int) -> None:
        if x > y:
            x, y = y, x
        avg = total[x][y] / (len(members[x]) * len(members[y]))
        if avg >= theta:
            heapq.heappush(heap, (-avg, x, y, stamp[x], stamp[y]))

    for x in total:
        for y in total[x]:
            if x < y:
                push(x, y)
    while heap:
        _, x, y, sx, sy = heapq.heappop(heap)
        if x not in members or y not in members or stamp[x] != sx or stamp[y] != sy:
            continue
        # The earlier cluster takes the later one in.
        members[x] = members[x] + members.pop(y)
        stamp[x] += 1
        for z, v in total.pop(y).items():
            total[z].pop(y, None)
            if z != x:
                total[x][z] = total[x].get(z, 0.0) + v
                total[z][x] = total[x][z]
        total[x].pop(y, None)
        for z in list(total[x]):
            push(x, z)
    return [members[k] for k in sorted(members)]


def families(space: StepSpace) -> Dict[str, Any]:
    """Builds grouped by the workflows they share, by average linkage, and the moves
    common to most of the knowledge base, listed once."""
    ids = sorted(space.vecs)
    # Only builds linked by a shared step can overlap; every other pair is 0.
    sim = {(a, b): space.overlap(a, b) for a in ids for b in space.linked.get(a, ()) if a < b and b in space.vecs}
    sim = {k: v for k, v in sim.items() if v}

    def s(a: str, b: str) -> float:
        return sim.get((a, b) if a < b else (b, a), 0.0)

    pairs_total = len(ids) * (len(ids) - 1) // 2
    if pairs_total:
        mean = sum(sim.values()) / pairs_total
        sd = math.sqrt(max(0.0, sum(v * v for v in sim.values()) / pairs_total - mean * mean))
    else:
        mean = sd = 0.0
    theta = max(0.05, mean + FAMILY_SD * sd)
    clusters = _average_linkage(ids, sim, theta)

    # Moves most builds share, worded by the first card that has them.
    common: List[str] = []
    said: Dict[str, Vector] = {}
    for (cid, i), df in sorted(space.df.items()):
        if space.common(df):
            text = _steps(space.workflows[cid])[i]["step"]
            vec = space.vecs[cid][i][0]
            if not any(dot(vec, said[c]) >= space.tau for c in common):
                common.append(text)
                said[text] = space.index.embed_queries([text])[0]

    out: List[Dict[str, Any]] = []
    for members in sorted(clusters, key=lambda m: (-len(m), m)):
        central = max(members, key=lambda m: sum(s(m, o) for o in members if o != m)) if len(members) > 1 else members[0]
        wf_c = space.workflows[central]
        fam: Dict[str, Any] = {"name": wf_c.get("name", ""), "central": central, "members": [], "shared_steps": []}
        shared_idx: Dict[int, int] = {}
        # How many members have each step type: a step another member also has is shared.
        type_count: Dict[int, int] = {}
        for o in members:
            for t in space.steps_by_type(o):
                type_count[t] = type_count.get(t, 0) + 1
        for m in members:
            steps = _steps(space.workflows[m])
            hits = [0] * len(steps)
            repeated = set()
            for t, ii in space.steps_by_type(m).items():
                if len(ii) == 1:
                    hits[ii[0]] = type_count[t] - 1
                else:
                    repeated.add(t)
            if repeated:
                # A type this build has more than once: pair it one to one with each member's.
                for o in members:
                    if o != m:
                        for i, _ in space.matched(m, o):
                            if space.type_of.get((m, i)) in repeated:
                                hits[i] += 1
            if m == central:
                shared_idx = {i: h for i, h in enumerate(hits) if h}
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
