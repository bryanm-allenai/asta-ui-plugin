"""Checking that it works, the two ways the Architecture board and the Workspace ask.

**Queries with wanted matches** (``eval/queries.jsonl``). Each request is run
through several representations, and the report says how often the build you
wanted came back first, in the top three, and how high on average:

- ``raw``: the request against each build's prompts and code, embedded as they are;
- ``prompt``: the request against each build's prompts;
- ``summary``: the workflow description against each card's summary;
- ``card``: the full search, facet by facet;
- ``data``: the data facet alone.

**Pairs judged by eye** (``eval/pairs.jsonl``). For each representation, how well
the similarity of two builds agrees with what you said about them (same job,
related, different). Whichever agrees with you more is the first finding.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from .cards import check_query, facet_text, structure_text, workflow_text
from .search import Searcher
from .workflows import query_vectors
from .vec import auc, dot, spearman

MODES = {
    "raw": "request vs prompts and code, as they are",
    "prompt": "request vs prompts",
    "summary": "workflow description vs card summaries",
    "card": "the full search: query card facet by facet, plus prompts and shared words",
    "data": "data facet alone",
    "structure": "ontology words for task, data, stage and mechanism; no field words",
    "workflow": "the general workflow: its name and steps in general words",
}
PAIR_CHANNELS = ("raw", "prompt", "card", "workflow", "specifics", "structure", "summary", "data", "task", "mechanism", "stage")
JUDGED = {"same": 2, "related": 1, "different": 0}


def _rank_by_channel(s: Searcher, text: str, channel: str, ids: Optional[Sequence[str]] = None) -> List[str]:
    qv = s.index.embed_queries([text])[0]
    vecs = s.index.channel(channel)
    pool = [i for i in vecs if ids is None or i in ids]
    return sorted(pool, key=lambda i: dot(qv, vecs[i]), reverse=True)


def run_queries(s: Searcher, queries: List[Dict[str, Any]], modes: Sequence[str] = tuple(MODES)) -> Dict[str, Any]:
    carded = set(s.cards)
    per_query = []
    for q in queries:
        wanted = set(q.get("wanted") or [])
        if not wanted:
            continue
        raw = dict(q.get("card") or {})
        raw.setdefault("request", q.get("request", ""))
        prepared, _ = check_query(s.ont, raw)
        row: Dict[str, Any] = {"id": q.get("id"), "request": q.get("request", ""), "wanted": sorted(wanted),
                               "described": any(f in (q.get("card") or {}) for f in ("task", "data", "mechanism")), "ranks": {}, "top": {}}
        for mode in modes:
            ranking: List[str] = []
            if mode in ("raw", "prompt"):
                # Only builds with cards compete, so every mode ranks the same pool.
                ranking = _rank_by_channel(s, prepared.get("request", ""), mode, carded)
            elif mode == "summary":
                text = prepared.get("summary") or prepared.get("request", "")
                ranking = _rank_by_channel(s, text, "summary")
            elif mode == "card":
                ranking = [h.id for h in s.rank(prepared)]
            elif mode == "workflow":
                wt = workflow_text(prepared)
                if not wt:
                    continue
                ranking = _rank_by_channel(s, wt, "workflow")
            elif mode == "structure":
                st = structure_text(prepared)
                if not st:
                    continue
                ranking = _rank_by_channel(s, st, "structure")
            elif mode == "data":
                if not facet_text(prepared, "data"):
                    continue
                ranking = [h.id for h in s.rank(prepared, facets_only=["data"])]
            pos = next((i + 1 for i, b in enumerate(ranking) if b in wanted), None)
            row["ranks"][mode] = pos
            row["top"][mode] = ranking[:3]
        if prepared.get("workflow") and "card" in modes:
            # Code for each step: did a step get code, and from a build the request wanted?
            qsteps = query_vectors(s.index, prepared["workflow"])
            sc = s.code_for_steps(prepared, qsteps)
            row["steps"] = len(sc)
            row["steps_with_code"] = sum(1 for st in sc if st["from"])
            row["steps_from_wanted"] = sum(1 for st in sc if st["from"] and st["from"][0]["build"] in wanted)
        if q.get("far") and "card" in modes:
            hits = s.rank(prepared)
            far = s.far(prepared, hits, hits[0] if hits else None)
            row["far_wanted"] = q["far"]
            row["far_got"] = far.id if far else None
        per_query.append(row)
    summary: Dict[str, Dict[str, Any]] = {}
    for mode in modes:
        ranks = [r["ranks"][mode] for r in per_query if mode in r["ranks"]]
        if not ranks:
            continue
        n = len(ranks)
        summary[mode] = {
            "queries": n,
            "top1": sum(1 for r in ranks if r == 1) / n,
            "top3": sum(1 for r in ranks if r is not None and r <= 3) / n,
            "mrr": sum(1.0 / r for r in ranks if r) / n,
        }
    step_rows = [r for r in per_query if r.get("steps")]
    steps = None
    if step_rows:
        total = sum(r["steps"] for r in step_rows)
        with_code = sum(r["steps_with_code"] for r in step_rows)
        steps = {"queries": len(step_rows), "steps": total, "with_code": with_code / total if total else 0.0,
                 "from_wanted": (sum(r["steps_from_wanted"] for r in step_rows) / with_code) if with_code else 0.0}
    far_rows = [r for r in per_query if "far_wanted" in r]
    far = None
    if far_rows:
        far = {"queries": len(far_rows), "hit": sum(1 for r in far_rows if r["far_got"] in r["far_wanted"]) / len(far_rows)}
    return {"modes": summary, "far": far, "steps": steps, "queries": per_query}


def run_pairs(s: Searcher, pairs: List[Dict[str, Any]], channels: Sequence[str] = PAIR_CHANNELS) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    usable = [p for p in pairs if p.get("judgment") in JUDGED]
    for ch in channels:
        vecs = s.index.channel(ch)
        xs, ys, by = [], [], {"same": [], "related": [], "different": []}
        for p in usable:
            a, b = vecs.get(p["a"]), vecs.get(p["b"])
            if a is None or b is None:
                continue
            sim = dot(a, b)
            xs.append(JUDGED[p["judgment"]])
            ys.append(sim)
            by[p["judgment"]].append(sim)
        if len(xs) < 2:
            continue
        mean = {k: (sum(v) / len(v) if v else None) for k, v in by.items()}
        out[ch] = {
            "pairs": len(xs),
            "spearman": spearman(xs, ys),
            "auc": auc(by["same"] + by["related"], by["different"]),
            "mean": mean,
        }
    return {"channels": out, "pairs": len(usable)}


def _pct(x: Optional[float]) -> str:
    return "–" if x is None else f"{100 * x:.0f}%"


def _num(x: Optional[float]) -> str:
    return "–" if x is None else f"{x:.2f}"


def report(qres: Optional[Dict[str, Any]], pres: Optional[Dict[str, Any]], embedder: str, n_cards: int) -> str:
    lines = [f"# Evaluation", "", f"Embedder `{embedder}`, {n_cards} builds with cards.", ""]
    if qres and qres["modes"]:
        lines += ["## Queries with wanted matches", "",
                  "| Representation | Queries | First | Top 3 | Mean reciprocal rank |", "|---|---|---|---|---|"]
        for mode, m in qres["modes"].items():
            lines.append(f"| {mode}: {MODES[mode]} | {m['queries']} | {_pct(m['top1'])} | {_pct(m['top3'])} | {_num(m['mrr'])} |")
        best = max(qres["modes"].items(), key=lambda kv: (kv[1]["mrr"], kv[1]["top1"]))
        lines += ["", f"The `{best[0]}` representation put the wanted build highest on average."]
        if qres.get("far"):
            lines.append(f"The far match was one you listed for {_pct(qres['far']['hit'])} of the {qres['far']['queries']} queries that list one.")
        if qres.get("steps"):
            st = qres["steps"]
            lines.append(f"Code for each step: {_pct(st['with_code'])} of the {st['steps']} steps in {st['queries']} described requests got code; "
                         f"{_pct(st['from_wanted'])} of that came from a build the request wanted (the rest from another build that does the step).")
        misses = [r for r in qres["queries"] if r["ranks"].get("card") not in (1,)]
        if misses:
            lines += ["", "### Where the full search missed first place", ""]
            for r in misses:
                got = ", ".join(r["top"].get("card", []))
                lines.append(f"- {r['id']}: wanted {', '.join(r['wanted'])}, got {got} (rank {r['ranks'].get('card') or 'none'})")
        lines.append("")
    if pres and pres["channels"]:
        lines += ["## Pairs judged by eye", "",
                  f"{pres['pairs']} pairs. Spearman is how well the similarity follows your judgement (same > related > different); "
                  "separation is how often a same-or-related pair scores above a different one.", "",
                  "| Representation | Spearman | Separation | Same | Related | Different |", "|---|---|---|---|---|---|"]
        for ch, m in pres["channels"].items():
            mean = m["mean"]
            lines.append(f"| {ch} | {_num(m['spearman'])} | {_pct(m['auc'])} | {_num(mean['same'])} | {_num(mean['related'])} | {_num(mean['different'])} |")
        ranked = sorted(((ch, m) for ch, m in pres["channels"].items() if m["spearman"] is not None), key=lambda kv: kv[1]["spearman"], reverse=True)
        if ranked:
            top, raw = ranked[0], pres["channels"].get("raw")
            line = f"The `{top[0]}` representation agrees with your judgements most (Spearman {_num(top[1]['spearman'])})"
            if raw and raw.get("spearman") is not None and top[0] != "raw":
                line += f"; the raw prompts and code reach {_num(raw['spearman'])}."
            else:
                line += "."
            lines += ["", line]
    return "\n".join(lines).rstrip() + "\n"
