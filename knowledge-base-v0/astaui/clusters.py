"""Clusters of the embedding space, and a map that shows them.

The flat map places every build by all of its neighbours at once, and with
more than a hundred builds that reads as one cloud. The groups are there in the
embedding, though, so they are found there: each build is joined to its ten
most alike builds under one representation, and the communities of that graph
(two passes of Louvain's method, which needs no number of clusters up front)
are the clusters. Each is named by the words its cards share most and the rest
of the knowledge base lacks: the data shape, task, field and pattern with the
highest share times lift.

`islands` lays the clusters out as discs, one per cluster, sized by how many
builds it holds and placed where its builds sit on the flat map, pushed apart
until no two overlap. Inside a disc the builds most typical of the cluster
(most alike the rest of it) sit at the centre and the least at the rim.
Everything here is plain Python and deterministic: the same knowledge base
gives the same clusters, names and places.
"""

from __future__ import annotations

import math
import random
from collections import Counter, defaultdict
from typing import Callable, Dict, List, Optional, Sequence, Tuple

Sim = Callable[[str, str], float]
NEIGHBOURS = 10
SMALLEST = 3
# The words a cluster is named by, in the order a tie is broken.
NAME_FACETS = ("s", "t", "d", "p")
GOLDEN = math.pi * (3 - math.sqrt(5))


def knn_graph(ids: Sequence[str], sim: Sim, k: int = NEIGHBOURS) -> Dict[Tuple[str, str], float]:
    """Each build joined to its k most alike, weighted by how alike (never below 0)."""
    w: Dict[Tuple[str, str], float] = {}
    for i in ids:
        near = sorted((j for j in ids if j != i), key=lambda j: (-sim(i, j), j))[:k]
        for j in near:
            e = (i, j) if i < j else (j, i)
            w[e] = max(w.get(e, 0.0), max(sim(i, j), 0.0))
    return w


def louvain_pass(nodes: Sequence, w: Dict[Tuple, float], resolution: float = 1.0, seed: int = 7) -> Dict:
    """One pass of Louvain's local moving: each node joins the neighbouring
    community that raises modularity most, until none moves."""
    adj: Dict = defaultdict(dict)
    for (a, b), x in w.items():
        adj[a][b] = adj[a].get(b, 0.0) + x
        adj[b][a] = adj[b].get(a, 0.0) + x
    m2 = sum(sum(v.values()) for v in adj.values()) or 1.0
    deg = {n: sum(adj[n].values()) for n in nodes}
    comm = {n: n for n in nodes}
    tot = dict(deg)
    order = list(nodes)
    random.Random(seed).shuffle(order)
    moved = True
    while moved:
        moved = False
        for n in order:
            c0 = comm[n]
            tot[c0] -= deg[n]
            links: Dict = defaultdict(float)
            for j, x in adj[n].items():
                if j != n:
                    links[comm[j]] += x
            best, gain = c0, links.get(c0, 0.0) - resolution * tot[c0] * deg[n] / m2
            for c in sorted(links, key=str):
                g = links[c] - resolution * tot[c] * deg[n] / m2
                if g > gain + 1e-12:
                    best, gain = c, g
            comm[n] = best
            tot[best] = tot.get(best, 0.0) + deg[n]
            if best != c0:
                moved = True
    return comm


def find(ids: Sequence[str], sim: Sim, k: int = NEIGHBOURS, resolution: float = 1.0) -> List[List[str]]:
    """The clusters, largest first: two passes of Louvain on the k-nearest graph,
    then any cluster smaller than SMALLEST folded into the one it is most like."""
    ids = sorted(ids)
    if len(ids) <= SMALLEST:
        return [list(ids)] if ids else []
    w = knn_graph(ids, sim, k)
    first = louvain_pass(ids, w, resolution)
    groups: Dict = defaultdict(list)
    for n in ids:
        groups[first[n]].append(n)
    level = sorted(groups.values(), key=lambda g: (-len(g), g[0]))
    at = {n: g for g, members in enumerate(level) for n in members}
    w2: Dict[Tuple[int, int], float] = defaultdict(float)
    for (a, b), x in w.items():
        ga, gb = at[a], at[b]
        w2[(min(ga, gb), max(ga, gb))] += x
    second = louvain_pass(list(range(len(level))), dict(w2), resolution)
    merged: Dict = defaultdict(list)
    for g, members in enumerate(level):
        merged[second[g]] += members
    out = [sorted(g) for g in merged.values()]
    big = [g for g in out if len(g) >= SMALLEST]
    if not big:
        return [list(ids)]
    for g in [g for g in out if len(g) < SMALLEST]:
        for n in g:
            home = max(big, key=lambda b: (sum(sim(n, j) for j in b) / len(b), -len(b)))
            home.append(n)
    return sorted((sorted(g) for g in big), key=lambda g: (-len(g), g[0]))


def typical(members: Sequence[str], sim: Sim) -> List[str]:
    """The members, most typical first: the most alike the rest of the cluster."""
    if len(members) < 2:
        return list(members)
    score = {i: sum(sim(i, j) for j in members if j != i) / (len(members) - 1) for i in members}
    return sorted(members, key=lambda i: (-score[i], i))


def name(members: Sequence[str], facts: Dict[str, Dict[str, List[str]]], fallback: str = "") -> Tuple[str, List[str]]:
    """What a cluster is called: its two most telling words (one per facet), and
    every word that tells it apart, for its title. A word tells when at least a
    third of the cluster has it and the cluster has it 1.3 times as often as
    the whole knowledge base, scored by share times the log of that lift."""
    everyone = list(facts)
    found: List[Tuple[float, int, str]] = []
    for rank, fk in enumerate(NAME_FACETS):
        here = Counter(v for m in members for v in set(facts.get(m, {}).get(fk, [])))
        there = Counter(v for m in everyone for v in set(facts[m].get(fk, [])))
        best: Optional[Tuple[float, int, str]] = None
        for v, c in here.items():
            share = c / len(members)
            lift = share / (there[v] / len(everyone))
            if share >= .34 and lift >= 1.3:
                s = share * math.log(lift)
                if best is None or (s, -rank) > (best[0], -best[1]) or (s == best[0] and v < best[2]):
                    best = (s, rank, v)
        if best:
            found.append(best)
    found.sort(key=lambda t: (-t[0], t[1], t[2]))
    words = [v for _, _, v in found]
    if not words:
        return (f"Like {fallback}" if fallback else "Mixed"), []
    label = " · ".join(words[:2])
    return label[:1].upper() + label[1:], words


def islands(groups: Sequence[Sequence[str]], layout: Dict[str, Tuple[float, float]], order: Dict[int, List[str]],
            fill: float = .38, gap: float = .06, margin: float = .06) -> Tuple[List[Tuple[float, float, float]], Dict[str, Tuple[float, float]]]:
    """A disc per cluster, area in proportion to its builds, centred where its
    builds sit on the flat map and pushed apart until none overlap, then fitted
    to the square. Returns each disc (x, y, radius) in order and each build's
    place: the cluster's members in `order`, most typical first, laid on a
    sunflower spiral from the centre out."""
    n = sum(len(g) for g in groups) or 1
    discs: List[List[float]] = []
    for g in groups:
        pts = [layout[i] for i in g if i in layout] or [(.5, .5)]
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        discs.append([cx, cy, math.sqrt(fill * len(g) / (math.pi * n))])
    home = [(d[0], d[1]) for d in discs]
    for _ in range(400):
        moved = 0.0
        for a in range(len(discs)):
            for b in range(a + 1, len(discs)):
                da, db = discs[a], discs[b]
                dx, dy = db[0] - da[0], db[1] - da[1]
                dist = math.hypot(dx, dy) or 1e-6
                need = da[2] + db[2] + gap
                if dist < need:
                    if dist < 1e-5:
                        dx, dy, dist = math.cos(a + b), math.sin(a + b), 1.0
                    push = (need - dist) / 2
                    ux, uy = dx / dist, dy / dist
                    wa = db[2] / (da[2] + db[2])
                    da[0] -= ux * push * 2 * wa
                    da[1] -= uy * push * 2 * wa
                    db[0] += ux * push * 2 * (1 - wa)
                    db[1] += uy * push * 2 * (1 - wa)
                    moved += push
        for d, (hx, hy) in zip(discs, home):
            d[0] += (hx - d[0]) * .01
            d[1] += (hy - d[1]) * .01
        if moved < 1e-6:
            break
    # Fit the whole arrangement inside the square, keeping its shape.
    x0 = min(d[0] - d[2] for d in discs)
    x1 = max(d[0] + d[2] for d in discs)
    y0 = min(d[1] - d[2] for d in discs)
    y1 = max(d[1] + d[2] for d in discs)
    span = max(x1 - x0, y1 - y0) or 1.0
    s = (1 - 2 * margin) / span
    ox = margin + ((1 - 2 * margin) - (x1 - x0) * s) / 2
    oy = margin + ((1 - 2 * margin) - (y1 - y0) * s) / 2
    out = [(ox + (d[0] - x0) * s, oy + (d[1] - y0) * s, d[2] * s) for d in discs]
    places: Dict[str, Tuple[float, float]] = {}
    for g, (cx, cy, r) in enumerate(out):
        members = order.get(g) or list(groups[g])
        for k, i in enumerate(members):
            rad = 0.0 if len(members) == 1 else r * .8 * math.sqrt((k + .5) / len(members))
            places[i] = (cx + rad * math.cos(k * GOLDEN), cy + rad * math.sin(k * GOLDEN))
    return out, places
