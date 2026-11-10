"""Compare Two: what the console's Compare lens reads to line up two builds'
workflow trees and say which features could move between them.

Every build an agent has run has a tree (tree.json): a goal, the phases of the
work, the tasks in each, and the actions that did them, each said in general
words any field would use and in this build's own. It also names the features
it found, each with the tasks it serves. This writes, beside the console's other
data (console-data/compare, out of the drive's scan):

  index.json          every build with a tree: title, field, screenshot, how many
                      tasks and features, and its nearest builds by workflow; the
                      thresholds the page matches with; and how the closeness of
                      every pair is spread, so the page can say where a pair sits
  b/<id>.json         one build: its tree and features, cut to what the page
                      draws, and a vector for the goal, each phase, task and
                      feature (int8, base64), which the page compares
  gather/<id>.json    the map's Line up: one build's workflow as stations in
                      order, and the builds whose workflows are closest to it,
                      each with where along those stations its own tasks fall

The page aligns any two builds itself from those vectors, so no pair is
precomputed and the files grow with builds, not with pairs. Line up is the
one exception: it needs every build against one, which the page would have to
fetch whole, so gather/ keeps that answer per build, cut to the closest.

**Vectors.** The general words of each node are embedded with a sentence model
(all-mpnet-base-v2, run through uv with CPU torch, offline once it is in the
Hugging Face cache; it told matching steps from look-alikes better than
all-MiniLM-L6-v2 and bge-base-en-v1.5 on a hand-checked set); trees are written in different fields' words, and matching words alone
misses steps that mean the same. Without uv or the model it falls back to the
knowledge base's own embedder, and index.json says which was used. Vectors are
cached by text, so a rerun embeds only what is new.

**When two nodes match.** Like workflows.py's step types, the threshold is set by
the knowledge base: of all pairs of tasks from different builds, two tasks are the
*same move* when they are as close as the closest SAME_PCT percent, and *alike*
as the closest ALIKE_PCT percent. (A spread in standard deviations let too much
through: this model's similarities have a long upper tail.) Features are matched
the same way, against features.

**How close two workflows are.** For each task of one build, its best match in
the other; the mean of that both ways is the pair's closeness. index.json keeps
its quantiles over every pair, and each build's nearest builds.

    python3 -m astaui.compare                 from knowledge-base-v0
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import marble_data

KB_DIR = Path(__file__).resolve().parent.parent
MODEL = "sentence-transformers/all-mpnet-base-v2"
SAME_PCT = 0.2
ALIKE_PCT = 1.0
NEAR = 12
SERVES_FLOOR = 0.3   # a feature's "serves" line is tied to its closest task when at least this close
UV_RUN = ["uv", "run", "--quiet", "--no-project", "--python", "3.12", "--with", "sentence-transformers", "--with", "torch",
          "--index", "https://download.pytorch.org/whl/cpu", "--index-strategy", "unsafe-best-match", "python", "-c"]
_ST = r"""
import json, sys
import numpy as np
from sentence_transformers import SentenceTransformer
texts = json.load(open(sys.argv[1]))
m = SentenceTransformer(sys.argv[3], device='cpu')
v = m.encode(texts, normalize_embeddings=True, batch_size=128, show_progress_bar=False)
np.save(sys.argv[2], v.astype('float32'))
"""


def out_dir(kb_dir: Path = KB_DIR) -> Path:
    return marble_data.folder(kb_dir / "kb") / "compare"


# -- the trees --------------------------------------------------------------------------------------

def _title(kb_dir: Path, bid: str, tree: Dict[str, Any]) -> str:
    card = kb_dir / "kb" / "cards" / f"{bid}.json"
    try:
        t = json.loads(card.read_text(encoding="utf-8"))["app"].get("title")
        if t:
            return t
    except (OSError, ValueError, KeyError):
        pass
    try:
        return json.loads((kb_dir / "kb" / "builds" / bid / "build.json").read_text(encoding="utf-8")).get("title") or bid
    except (OSError, ValueError):
        return (tree.get("interface") or {}).get("title") or bid


def _screen(kb_dir: Path, bid: str, at: Optional[str], ref: str) -> Optional[str]:
    """A screen's path in the drive: filed beside the build, or where the run kept it."""
    here = kb_dir / "kb" / "builds" / bid / ref
    if here.exists():
        return marble_data.drive_path(here)
    if at:
        there = kb_dir / at / ref
        if there.exists():
            return marble_data.drive_path(there)
    return None


def read_build(kb_dir: Path, bid: str) -> Optional[Dict[str, Any]]:
    """One build's tree, cut to what the page draws, with the nodes to embed."""
    folder = kb_dir / "kb" / "builds" / bid
    try:
        raw = json.loads((folder / "tree.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    root = raw.get("tree")
    if not isinstance(root, dict):
        return None
    at = raw.get("screens_at")
    shot = next((folder / n for n in ("screenshot.webp", "screenshot.png") if (folder / n).exists()), None)
    texts: Dict[str, str] = {}
    count = {"phase": 0, "task": 0}

    def screens(node: Dict[str, Any]) -> List[str]:
        out = []
        for s in node.get("screens") or []:
            p = _screen(kb_dir, bid, at, s)
            if p and p not in out:
                out.append(p)
        return out[:4]

    def cut(node: Dict[str, Any], key: str) -> Dict[str, Any]:
        kind = node.get("kind") or "task"
        if kind == "action":
            return {"k": "action", "t": node.get("label") or node.get("specific") or node.get("general") or ""}
        nid = "g" if kind == "goal" else f"{kind[0]}{count.setdefault(kind, 0)}"
        if kind != "goal":
            count[kind] += 1
        gen = node.get("general") or node.get("label") or ""
        if gen and kind in ("goal", "phase", "task"):
            texts[nid] = gen
        kids = [cut(c, key) for c in node.get("children") or [] if isinstance(c, dict)]
        out = {"k": kind, "id": nid, "g": gen, "s": node.get("specific") or "", "kids": kids}
        if node.get("id"):
            out["tid"] = node["id"]
        sc = screens(node)
        if sc:
            out["sc"] = sc
        if node.get("branch"):
            out["br"] = node["branch"]
        return out

    tree = cut(root, "")
    feats = []
    for i, f in enumerate(raw.get("features") or []):
        if not isinstance(f, dict):
            continue
        fid = f"f{i}"
        gen = f.get("general") or f.get("name") or ""
        texts[fid] = gen
        feats.append({"id": fid, "fid": f.get("id") or "", "name": f.get("name") or "", "g": gen, "s": f.get("specific") or "",
                      "steps": [s for s in f.get("steps") or [] if isinstance(s, str)][:8],
                      "serves": [s for s in f.get("serves_tasks") or [] if isinstance(s, str)], "sc": screens(f),
                      "check": f.get("check") or ""})
    inter = raw.get("interface") or {}
    return {
        "id": bid, "title": _title(kb_dir, bid, raw), "field": inter.get("field") or "", "stage": inter.get("stage_of_work") or "",
        "for": inter.get("what_it_is_for") or "", "shot": marble_data.drive_path(shot) if shot else None,
        "tree": tree, "feats": feats, "texts": texts,
        "not_done": [s for s in raw.get("not_done") or [] if isinstance(s, str)][:6],
    }


# -- vectors ----------------------------------------------------------------------------------------

def _key(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:20]


def embed(texts: Sequence[str], cache_dir: Path) -> Tuple[Any, str]:
    """Unit vectors for texts (numpy, float32), from the sentence model when it runs,
    else from the knowledge base's embedder. Cached by text in cache_dir."""
    import numpy as np

    cache_dir.mkdir(parents=True, exist_ok=True)
    for name in ("st", "lexical"):
        store = cache_dir / f"vectors-{MODEL.split('/')[-1] if name == 'st' else name}.npz"
        have: Dict[str, Any] = {}
        if store.exists():
            with np.load(store) as z:
                ks, vs = z["k"], z["v"]
            have = {str(k): vs[i] for i, k in enumerate(ks)}
        need = sorted({t for t in texts if _key(t) not in have})
        if need:
            try:
                fresh = _embed_st(need, cache_dir) if name == "st" else _embed_lexical(need)
            except Exception as e:  # noqa: BLE001 - any failure falls back to the next embedder
                print(f"  {name} embedder unavailable ({e}); falling back", file=sys.stderr)
                continue
            for t, v in zip(need, fresh):
                have[_key(t)] = v
            ks = sorted(have)
            tmp = store.with_suffix(".tmp.npz")
            np.savez(tmp, k=np.array(ks), v=np.stack([have[k] for k in ks]).astype("float32"))
            os.replace(tmp, store)
        return np.stack([have[_key(t)] for t in texts]).astype("float32"), (MODEL if name == "st" else "lexical/1")
    raise RuntimeError("no embedder worked")


def _embed_st(texts: List[str], cache_dir: Path):
    import numpy as np

    if not shutil.which("uv"):
        raise RuntimeError("uv is not on the PATH")
    src, dst = cache_dir / "in.json", cache_dir / "out.npy"
    src.write_text(json.dumps(texts), encoding="utf-8")
    env = dict(os.environ, TRANSFORMERS_VERBOSITY="error", TOKENIZERS_PARALLELISM="false")
    r = subprocess.run(UV_RUN + [_ST, str(src), str(dst), MODEL], capture_output=True, text=True, env=env, timeout=1800)
    if r.returncode != 0 or not dst.exists():
        raise RuntimeError((r.stderr or r.stdout).strip().splitlines()[-1:] or "it failed")
    v = np.load(dst)
    src.unlink(missing_ok=True)
    dst.unlink(missing_ok=True)
    return v


def _embed_lexical(texts: List[str]):
    import numpy as np

    from .embed import get_embedder
    return np.array(get_embedder("lexical").embed(list(texts)), dtype="float32")


def _b64(v) -> str:
    import numpy as np

    return base64.b64encode(np.clip(np.round(v * 127), -127, 127).astype("int8").tobytes()).decode("ascii")


# -- the knowledge base's own scale -----------------------------------------------------------------

def _background(groups: List[Any], seed: int = 11, n: int = 60000) -> Dict[str, float]:
    """How close rows of different builds are: the mean, and the thresholds for the
    closest SAME_PCT and ALIKE_PCT percent."""
    import numpy as np

    rng = random.Random(seed)
    nonempty = [g for g in groups if len(g)]
    sims = []
    for _ in range(n):
        a, b = rng.sample(range(len(nonempty)), 2)
        x, y = nonempty[a], nonempty[b]
        sims.append(float(x[rng.randrange(len(x))] @ y[rng.randrange(len(y))]))
    s = np.array(sims)
    return {"mean": round(float(s.mean()), 4), "same": round(float(np.percentile(s, 100 - SAME_PCT)), 4),
            "alike": round(float(np.percentile(s, 100 - ALIKE_PCT)), 4)}


def closeness(groups: List[Any]):
    """For every pair of builds, the mean of each task's best match in the other,
    taken both ways: a builds x builds matrix."""
    import numpy as np

    sizes = np.array([len(g) for g in groups])
    allv = np.concatenate([g for g in groups if len(g)])
    starts = np.concatenate([[0], np.cumsum(sizes)[:-1]])
    nz = sizes > 0
    nb = len(groups)
    best = np.zeros((nb, nb), dtype="float32")   # best[a, b]: mean over a's tasks of the best match in b
    for a, g in enumerate(groups):
        if not len(g):
            continue
        s = g @ allv.T
        mx = np.full((len(g), nb), -1.0, dtype="float32")
        mx[:, nz] = np.maximum.reduceat(s, starts[nz], axis=1)
        best[a] = mx.mean(axis=0)
    c = (best + best.T) / 2
    np.fill_diagonal(c, 1.0)
    c[~nz, :] = 0
    c[:, ~nz] = 0
    return c


# -- Line up: every build against one build's workflow ----------------------------------------------

GATHER = 40        # the builds lined up: the closest workflows
GATHER_MAX = 56    # and any with a same-move task, up to this many in all


def stations(tree: Dict[str, Any]) -> List[Dict[str, Any]]:
    """A build's workflow as stations in order: each phase under the goal, and a
    task the goal holds directly as a station of its own. Each station lists its
    tasks (their ids in the tree) in order."""
    out = []

    def tasks(node: Dict[str, Any]) -> List[Dict[str, Any]]:
        found = []
        for k in node.get("kids") or []:
            if k.get("k") == "task":
                found.append({"id": k["id"], "g": k.get("g") or "", "s": k.get("s") or ""})
            if k.get("k") in ("phase", "task"):
                found += tasks(k)
        return found

    for k in tree.get("kids") or []:
        if k.get("k") == "phase":
            ts = tasks(k)
            if ts:
                out.append({"g": k.get("g") or "", "s": k.get("s") or "", "tasks": ts})
        elif k.get("k") == "task":
            out.append({"g": k.get("g") or "", "s": k.get("s") or "", "tasks": [{"id": k["id"], "g": k.get("g") or "", "s": k.get("s") or ""}] + tasks(k)})
    return out


def task_spots(sts: List[Dict[str, Any]]) -> List[float]:
    """Where each task sits along the line, 0 to 1: every station an equal
    stretch, its tasks spread evenly inside it."""
    n = len(sts)
    spots = []
    for i, st in enumerate(sts):
        m = len(st["tasks"])
        spots += [(i + (j + .5) / m) / n for j in range(m)]
    return spots


def match_one(s, alike: float) -> List[Tuple[int, int, float]]:
    """One-to-one matches between the rows and columns of a similarity matrix,
    best first, each at least alike (as the Compare lens does in the page)."""
    import numpy as np

    out = []
    if not s.size:
        return out
    order = np.argsort(-s, axis=None)
    used_a, used_b = set(), set()
    for flat in order:
        i, j = divmod(int(flat), s.shape[1])
        v = float(s[i, j])
        if v < alike:
            break
        if i in used_a or j in used_b:
            continue
        used_a.add(i)
        used_b.add(j)
        out.append((i, j, v))
    return out


def gather(builds: List[Dict[str, Any]], vec: Dict[Tuple[str, str], Any], c, thresholds: Dict[str, float]) -> Dict[str, Dict[str, Any]]:
    """For each build, its stations and the builds lined up against them: the
    GATHER closest workflows by closeness, then any other build with a task as
    close as a same move, up to GATHER_MAX. Each lined-up build says where along
    the line its matched tasks fall (x, weighted by how close each match is),
    and which of this build's tasks each matches. A build with no task alike
    enough still gets a place, from where its best near-matches fall, and says
    so (loose)."""
    import numpy as np

    alike, same = thresholds["alike"], thresholds["same"]
    order = {b["id"]: [t["id"] for st in stations(b["tree"]) for t in st["tasks"]] for b in builds}
    mats = {bid: np.stack([vec[(bid, t)] for t in ts]) if ts else None for bid, ts in order.items()}
    texts = {b["id"]: {t["id"]: t["g"] for st in stations(b["tree"]) for t in st["tasks"]} for b in builds}
    out = {}
    for n, b in enumerate(builds):
        sts = stations(b["tree"])
        a = mats[b["id"]]
        if a is None:
            continue
        spots = task_spots(sts)
        rows = []
        for m, o in enumerate(builds):
            if m == n or mats[o["id"]] is None:
                continue
            s = a @ mats[o["id"]].T
            hits = match_one(s, alike)
            if hits:
                w = np.array([v - alike + .02 for _, _, v in hits])
                x = float(np.dot(w, [spots[i] for i, _, _ in hits]) / w.sum())
                loose = False
            else:
                best = s.max(axis=1)
                w = np.exp((best - best.max()) / .03)
                x = float(np.dot(w, spots) / w.sum())
                loose = True
            rows.append({"b": o["id"], "c": float(c[n, m]), "x": x, "loose": loose,
                         "same": any(v >= same for _, _, v in hits), "hits": hits})
        rows.sort(key=lambda r: -r["c"])
        keep = rows[:GATHER] + [r for r in rows[GATHER:] if r["same"]][:GATHER_MAX - GATHER]
        out[b["id"]] = {
            "id": b["id"], "title": b["title"],
            "stations": [{"g": st["g"], "s": st["s"], "tasks": [{"id": t["id"], "g": t["g"]} for t in st["tasks"]]} for st in sts],
            "spots": [round(x, 4) for x in spots],
            "alike": alike, "same": same,
            "low": round(rows[min(len(rows), GATHER) - 1]["c"], 4) if rows else 0,
            "top": round(rows[0]["c"], 4) if rows else 0,
            "near": [{"b": r["b"], "c": round(r["c"], 4), "x": round(r["x"], 4), **({"loose": 1} if r["loose"] else {}),
                      "hits": [[i, round(v, 3), texts[r["b"]][order[r["b"]][j]][:160]] for i, j, v in r["hits"]]}
                     for r in keep],
            "n": len(rows),
        }
    return out


def _swap(out: Path, name: str, tmp: Path, stamp: str) -> None:
    """Put a freshly written folder in place of the old one at once."""
    final = out / name
    old = out / f"{name}.old.{stamp}"
    if final.exists():
        os.replace(final, old)
    os.replace(tmp, final)
    shutil.rmtree(old, ignore_errors=True)
    for stale in out.glob(f"{name}.*.tmp"):
        shutil.rmtree(stale, ignore_errors=True)


def run(kb_dir: Path = KB_DIR, quiet: bool = False) -> Dict[str, Any]:
    import numpy as np

    ids = sorted(p.parent.name for p in (kb_dir / "kb" / "builds").glob("*/tree.json"))
    builds = [b for b in (read_build(kb_dir, i) for i in ids) if b]
    out = out_dir(kb_dir)
    order = [(b["id"], k, t) for b in builds for k, t in b["texts"].items()]
    serves = [(b["id"], f["id"], s) for b in builds for f in b["feats"] for s in f["serves"]]
    texts = [t for _, _, t in order] + [s for _, _, s in serves]
    vecs, embedder = embed(texts, out / "cache")
    vec = {(bid, k): vecs[i] for i, (bid, k, _) in enumerate(order)}
    sv = vecs[len(order):]

    # Tie each feature's "serves" lines to its build's tasks.
    for i, (bid, fid, _) in enumerate(serves):
        b = next(x for x in builds if x["id"] == bid)
        tasks = [k for k in b["texts"] if k.startswith("t")]
        if not tasks:
            continue
        sims = [float(sv[i] @ vec[(bid, k)]) for k in tasks]
        j = max(range(len(sims)), key=sims.__getitem__)
        if sims[j] >= SERVES_FLOOR:
            f = next(f for f in b["feats"] if f["id"] == fid)
            f.setdefault("tasks", [])
            if tasks[j] not in f["tasks"]:
                f["tasks"].append(tasks[j])

    task_groups = [np.stack([vec[(b["id"], k)] for k in b["texts"] if k.startswith("t")]) if any(k.startswith("t") for k in b["texts"])
                   else np.zeros((0, vecs.shape[1]), dtype="float32") for b in builds]
    feat_groups = [np.stack([vec[(b["id"], f["id"])] for f in b["feats"]]) if b["feats"] else np.zeros((0, vecs.shape[1]), dtype="float32")
                   for b in builds]
    tb = _background(task_groups)
    fb = _background(feat_groups)
    c = closeness(task_groups)
    iu = np.triu_indices(len(builds), 1)
    pair_vals = c[iu]
    quant = [round(float(q), 4) for q in np.quantile(pair_vals, np.linspace(0, 1, 101))] if len(pair_vals) else []

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    tmp = out / f"b.{stamp}.tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    rows = []
    for n, b in enumerate(builds):
        v = {k: _b64(vec[(b["id"], k)]) for k in b["texts"]}
        doc = {k: b[k] for k in ("id", "title", "field", "stage", "for", "shot", "tree", "feats", "not_done")}
        doc["v"] = v
        (tmp / f"{marble_data.pick_file('b:' + b['id']).split('/')[-1]}").write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        near = [int(j) for j in np.argsort(-c[n]) if j != n][:NEAR]
        rows.append({"id": b["id"], "title": b["title"], "field": b["field"], "shot": b["shot"],
                     "tasks": len(task_groups[n]), "feats": len(b["feats"]),
                     "near": [[builds[j]["id"], round(float(c[n, j]), 4)] for j in near]})
    _swap(out, "b", tmp, stamp)
    gtmp = out / f"gather.{stamp}.tmp"
    gtmp.mkdir(parents=True, exist_ok=True)
    for bid, doc in gather(builds, vec, c, tb).items():
        (gtmp / marble_data.pick_file("b:" + bid).split("/")[-1]).write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    _swap(out, "gather", gtmp, stamp)
    index = {
        "made": datetime.now().astimezone().isoformat(timespec="seconds"),
        "embedder": embedder, "dim": int(vecs.shape[1]),
        "task": tb, "feat": fb,
        "quantiles": quant, "builds": rows,
    }
    t = out / "index.json.tmp"
    t.write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(t, out / "index.json")
    if not quiet:
        print(f"{len(builds)} builds with a tree, {len(order)} nodes embedded with {embedder}; "
              f"tasks match at {index['task']['alike']} (alike) and {index['task']['same']} (same move); written to {out}")
    return index


if __name__ == "__main__":
    run()
