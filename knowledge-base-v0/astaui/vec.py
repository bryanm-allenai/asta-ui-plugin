"""Vector arithmetic in plain Python, with numpy used when it is installed.

Vectors are stored normalised to length 1, so cosine similarity is a dot product.
A knowledge base of a few hundred cards is small enough that none of this needs
an index structure; a brute-force scan takes milliseconds.
"""

from __future__ import annotations

import math
import random
from array import array
from typing import List, Optional, Sequence, Tuple

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


def to_bytes(v: Sequence[float]) -> bytes:
    return array("f", v).tobytes()


def from_bytes(b: bytes) -> Vector:
    a = array("f")
    a.frombytes(b)
    return a.tolist()


def similarity_matrix(vectors: List[Vector]) -> List[List[float]]:
    if _np is not None and vectors:
        m = _np.asarray(vectors, dtype=float)
        return (m @ m.T).tolist()
    n = len(vectors)
    s = [[0.0] * n for _ in range(n)]
    for i in range(n):
        s[i][i] = dot(vectors[i], vectors[i])
        for j in range(i + 1, n):
            s[i][j] = s[j][i] = dot(vectors[i], vectors[j])
    return s


def _power_iteration(m: List[List[float]], iters: int = 300, seed: int = 7) -> Tuple[float, Vector]:
    n = len(m)
    rng = random.Random(seed)
    v = normalize([rng.random() - 0.5 for _ in range(n)])
    lam = 0.0
    for _ in range(iters):
        w = [sum(m[i][j] * v[j] for j in range(n)) for i in range(n)]
        norm = math.sqrt(sum(x * x for x in w))
        if norm == 0:
            return 0.0, v
        w = [x / norm for x in w]
        lam = sum(w[i] * sum(m[i][j] * w[j] for j in range(n)) for i in range(n))
        if sum(abs(a - b) for a, b in zip(v, w)) < 1e-9:
            v = w
            break
        v = w
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
