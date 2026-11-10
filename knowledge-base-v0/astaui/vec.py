"""Vector arithmetic in plain Python, with numpy used when it is installed.

Vectors are stored normalised to length 1, so cosine similarity is a dot product.
Comparing one vector with many, or many with each other, goes through ``VecSet``:
a numpy matrix when numpy is installed; without it, sparse rows and an inverted
index when the vectors are mostly zeros (the lexical embedder's are), and plain
loops when they are not. Every way gives the same similarities, so a knowledge
base searches alike on any machine, only faster on some.
"""

from __future__ import annotations

import math
import random
from array import array
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

try:  # optional
    import numpy as _np  # type: ignore
except Exception:  # pragma: no cover - depends on the machine
    _np = None

Vector = List[float]


def normalize(v: Sequence[float]) -> Vector:
    n = math.sqrt(sum(x * x for x in v))
    if n == 0:
        return [0.0] * len(v)
    return [x / n for x in v]


def dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


Sparse = Dict[int, float]
SPARSE_SHARE = 0.25  # below this share of non-zero entries, plain Python works on the non-zeros


def sparse(v: Sequence[float]) -> Sparse:
    return {i: x for i, x in enumerate(v) if x}


def sparse_dot(a: Sparse, b: Sparse) -> float:
    if len(a) > len(b):
        a, b = b, a
    get = b.get
    return sum(x * get(i, 0.0) for i, x in a.items())


class VecSet:
    """Many vectors, for similarity one against all (``scores``) and all against all
    (``pairs_above``), and between any two of them (``sim``)."""

    def __init__(self, vectors: Sequence[Vector]):
        self.vectors = list(vectors)
        self.n = len(self.vectors)
        self.mode = "dense"
        self._m = None
        self._rows: List[Sparse] = []
        self._post: Dict[int, List[Tuple[int, float]]] = {}
        if not self.n:
            return
        if _np is not None:
            self.mode = "numpy"
            self._m = _np.asarray(self.vectors, dtype=_np.float64)
            return
        rows = [sparse(v) for v in self.vectors]
        dim = max(1, len(self.vectors[0]))
        if sum(len(r) for r in rows) / (self.n * dim) <= SPARSE_SHARE:
            self.mode = "sparse"
            self._rows = rows
            for i, r in enumerate(rows):
                for d, x in r.items():
                    self._post.setdefault(d, []).append((i, x))

    def __len__(self) -> int:
        return self.n

    def sim(self, i: int, j: int) -> float:
        if self.mode == "sparse":
            return sparse_dot(self._rows[i], self._rows[j])
        if self.mode == "numpy":
            return float(self._m[i] @ self._m[j])  # type: ignore[index]
        return dot(self.vectors[i], self.vectors[j])

    def scores(self, q: Sequence[float]) -> List[float]:
        """The similarity of q with every vector, in order."""
        if not self.n:
            return []
        if self.mode == "numpy":
            return (self._m @ _np.asarray(q, dtype=_np.float64)).tolist()  # type: ignore[operator]
        if self.mode == "sparse":
            acc = [0.0] * self.n
            for d, x in enumerate(q):
                if x:
                    for i, y in self._post.get(d, ()):
                        acc[i] += x * y
            return acc
        return [dot(q, v) for v in self.vectors]

    def pairs_above(self, tau: float, groups: Optional[Sequence[int]] = None,
                    block: int = 512) -> Iterable[Tuple[int, int, float]]:
        """Every pair i < j with similarity at least tau, skipping pairs in the same
        group when groups are given. Never holds more than one block of rows in memory."""
        if self.mode == "numpy":
            g = _np.asarray(groups) if groups is not None else None
            for start in range(0, self.n, block):
                sims = self._m[start:start + block] @ self._m.T  # type: ignore[index]
                ii, jj = _np.nonzero(sims >= tau)
                for i, j in zip(ii.tolist(), jj.tolist()):
                    i += start
                    if j <= i or (g is not None and g[i] == g[j]):
                        continue
                    yield i, j, float(sims[i - start, j])
            return
        if self.mode == "sparse":
            for i, row in enumerate(self._rows):
                acc: Dict[int, float] = {}
                for d, x in row.items():
                    for j, y in self._post[d]:
                        if j > i:
                            acc[j] = acc.get(j, 0.0) + x * y
                for j, s in acc.items():
                    if s >= tau and (groups is None or groups[i] != groups[j]):
                        yield i, j, s
            return
        for i in range(self.n):
            for j in range(i + 1, self.n):
                if groups is not None and groups[i] == groups[j]:
                    continue
                s = dot(self.vectors[i], self.vectors[j])
                if s >= tau:
                    yield i, j, s

    def gram(self) -> List[List[float]]:
        """Every similarity, as a full matrix."""
        if self.mode == "numpy":
            return (self._m @ self._m.T).tolist()  # type: ignore[operator]
        out = [[0.0] * self.n for _ in range(self.n)]
        for i in range(self.n):
            out[i][i] = self.sim(i, i)
            for j in range(i + 1, self.n):
                out[i][j] = out[j][i] = self.sim(i, j)
        return out


def threshold_clusters(vectors: Sequence[Vector], tau: float) -> List[int]:
    """Group vectors so each sits with the ones it is like: a cluster id per vector.

    Pass one walks the vectors in order; each joins the most similar leader it is at
    least tau from, or becomes a leader itself. Pass two moves every vector to the
    nearest cluster centre (the normalised mean of its members), so the result
    depends less on the order. The work grows with vectors times clusters, never
    with every pair."""
    n = len(vectors)
    if not n:
        return []
    leaders: List[int] = []
    assign = [0] * n
    if _np is not None:
        m = _np.asarray(vectors, dtype=_np.float64)
        lead = _np.empty_like(m)
        for i in range(n):
            if leaders:
                sims = lead[: len(leaders)] @ m[i]
                k = int(sims.argmax())
                if sims[k] >= tau:
                    assign[i] = k
                    continue
            lead[len(leaders)] = m[i]
            assign[i] = len(leaders)
            leaders.append(i)
    else:
        dense = sum(1 for x in vectors[0] if x) / max(1, len(vectors[0])) > SPARSE_SHARE
        rows = [sparse(v) for v in vectors]
        post: Dict[int, List[Tuple[int, float]]] = {}
        for i in range(n):
            best, best_k = None, -1
            if dense:
                for k, li in enumerate(leaders):
                    s = dot(vectors[i], vectors[li])
                    if best is None or s > best:
                        best, best_k = s, k
            else:
                acc: Dict[int, float] = {}
                for d, x in rows[i].items():
                    for k, y in post.get(d, ()):
                        acc[k] = acc.get(k, 0.0) + x * y
                for k, s in acc.items():
                    if best is None or s > best or (s == best and k < best_k):
                        best, best_k = s, k
            if best is not None and best >= tau:
                assign[i] = best_k
                continue
            k = len(leaders)
            leaders.append(i)
            assign[i] = k
            if not dense:
                for d, x in rows[i].items():
                    post.setdefault(d, []).append((k, x))
    # Pass two: every vector to its nearest centre.
    dim = len(vectors[0])
    sums = [[0.0] * dim for _ in leaders]
    for i, k in enumerate(assign):
        row = sums[k]
        for d, x in enumerate(vectors[i]):
            if x:
                row[d] += x
    centres = VecSet([normalize(c) for c in sums])
    out = []
    for i in range(n):
        scores = centres.scores(vectors[i])
        k = max(range(len(scores)), key=lambda c: (scores[c], -c))
        out.append(k if scores[k] >= tau else assign[i])
    # Number the clusters in order of first appearance, so ids are stable.
    renum: Dict[int, int] = {}
    return [renum.setdefault(k, len(renum)) for k in out]


def to_bytes(v: Sequence[float]) -> bytes:
    return array("f", v).tobytes()


def from_bytes(b: bytes) -> Vector:
    """A stored vector as a compact float array: a quarter of a list's memory, and it
    reads, iterates and zips like one."""
    a = array("f")
    a.frombytes(b)
    return a  # type: ignore[return-value]


def similarity_matrix(vectors: List[Vector]) -> List[List[float]]:
    return VecSet(vectors).gram()


def _power_iteration(m: List[List[float]], iters: int = 300, seed: int = 7) -> Tuple[float, Vector]:
    n = len(m)
    rng = random.Random(seed)
    v = normalize([rng.random() - 0.5 for _ in range(n)])
    w = v
    for _ in range(iters):
        w = [sum(x * y for x, y in zip(row, v)) for row in m]
        norm = math.sqrt(sum(x * x for x in w))
        if norm == 0:
            return 0.0, v
        w = [x / norm for x in w]
        if sum(abs(a - b) for a, b in zip(v, w)) < 1e-9:
            v = w
            break
        v = w
    # The eigenvalue, once, for the vector the loop settled on.
    lam = sum(w[i] * sum(x * y for x, y in zip(m[i], w)) for i in range(n))
    return lam, v


def project_2d(vectors: List[Vector], method: str = "pca", seed: int = 7) -> Tuple[List[Tuple[float, float]], str]:
    """Two coordinates per vector, scaled into [0, 1]. ``method`` is ``pca`` (classical
    MDS on cosine similarity, which is PCA for unit vectors) or ``umap`` when
    umap-learn is installed. Returns the points and the method actually used."""
    n = len(vectors)
    if n == 0:
        return [], method
    if n < 3:
        return [(0.5 + 0.2 * i, 0.5) for i in range(n)], "none"
    used = "pca"
    if method == "umap":
        try:
            import umap  # type: ignore

            reducer = umap.UMAP(n_neighbors=min(10, n - 1), min_dist=0.15, metric="cosine", random_state=seed)
            pts = reducer.fit_transform(_np.asarray(vectors)).tolist()  # type: ignore[union-attr]
            return _scale([(p[0], p[1]) for p in pts]), "umap"
        except Exception:
            used = "pca (umap-learn is not installed)"
    s = similarity_matrix(vectors)
    # Double-centre the similarity matrix: B = J S J.
    row = [sum(r) / n for r in s]
    total = sum(row) / n
    b = [[s[i][j] - row[i] - row[j] + total for j in range(n)] for i in range(n)]
    if _np is not None:
        w, v = _np.linalg.eigh(_np.asarray(b))
        order = w.argsort()[::-1][:2]
        coords = v[:, order] * _np.sqrt(_np.maximum(w[order], 0))
        pts = [(float(x), float(y)) for x, y in coords.tolist()]
    else:
        l1, v1 = _power_iteration(b, seed=seed)
        b2 = [[b[i][j] - l1 * v1[i] * v1[j] for j in range(n)] for i in range(n)]
        l2, v2 = _power_iteration(b2, seed=seed + 1)
        s1, s2 = math.sqrt(max(l1, 0)), math.sqrt(max(l2, 0))
        pts = [(v1[i] * s1, v2[i] * s2) for i in range(n)]
    # Fix the signs so the same data always draws the same way round.
    for axis in (0, 1):
        heavy = max(range(n), key=lambda i: abs(pts[i][axis]))
        if pts[heavy][axis] < 0:
            pts = [(-p[0], p[1]) if axis == 0 else (p[0], -p[1]) for p in pts]
    return _scale(pts), used


def _scale(pts: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    span = max(max(xs) - min(xs), max(ys) - min(ys)) or 1.0
    cx = (max(xs) + min(xs)) / 2
    cy = (max(ys) + min(ys)) / 2
    return [(0.5 + (x - cx) / span, 0.5 + (y - cy) / span) for x, y in pts]


def place_by_neighbours(sims: Sequence[float], points: Sequence[Tuple[float, float]], k: int = 5) -> Optional[Tuple[float, float]]:
    """Where a new item (a query) goes on an existing map: the similarity-weighted
    mean of its nearest neighbours' positions."""
    ranked = sorted(range(len(sims)), key=lambda i: sims[i], reverse=True)[:k]
    weights = [max(sims[i], 0.0) ** 2 for i in ranked]
    total = sum(weights)
    if total == 0:
        return None
    x = sum(points[i][0] * w for i, w in zip(ranked, weights)) / total
    y = sum(points[i][1] * w for i, w in zip(ranked, weights)) / total
    return x, y


def spearman(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    if len(xs) < 3:
        return None

    def ranks(v: Sequence[float]) -> List[float]:
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2 + 1
            i = j + 1
        return r

    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else None


def auc(pos: Sequence[float], neg: Sequence[float]) -> Optional[float]:
    """How often a positive scores above a negative (ties count half)."""
    if not pos or not neg:
        return None
    wins = 0.0
    for p in pos:
        for q in neg:
            wins += 1.0 if p > q else 0.5 if p == q else 0.0
    return wins / (len(pos) * len(neg))
