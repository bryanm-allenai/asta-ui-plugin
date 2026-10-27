"""Search: a request, or a query card, in; the builds worth adapting out.

The steps follow the Architecture board:

1. Filter on tags (``--where shape=table``), exactly.
2. Rank by facet similarity: each facet the query card has is compared with the
   same facet on every card, weighted by ``ontology.json`` (data shape and task
   high, field low). The request's own words are compared with every build's
   prompts, so a prompt can find similar prompts; and the ontology words the two
   share add a little on top.
3. Close and far: the best match, and the best match from another field with the
   same structure.
4. Snippets: the views and components inside the top builds that fit the
   request, with their lines of code.

Every score is broken down by facet, so a person can see why something matched.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .cards import STRUCTURE, check_query, facet_text, matches_filter, structure_text, tags, workflow_text
from .index import Index
from .kb import KB, KBError
from .ontology import FACETS, Ontology, norm_word
from .vec import dot
from .slices import slice_part
from .symbols import index_build
from .workflows import StepSpace, compare, format_diff, query_vectors



@dataclass
class Hit:
    id: str
    title: str
    score: float
    by: Dict[str, float] = dc_field(default_factory=dict)
    shared: Dict[str, List[str]] = dc_field(default_factory=dict)
    field: str = ""
    kind: str = ""
    parts: List[Dict[str, Any]] = dc_field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "title": self.title, "score": round(self.score, 4),
                "by": {k: round(v, 4) for k, v in self.by.items()}, "shared": self.shared,
                "field": self.field, "kind": self.kind, "parts": self.parts}


def _jaccard(a: Sequence[str], b: Sequence[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _field_words(app: Dict[str, Any]) -> set:
    f = app.get("field") or {}
    words = set(norm_word(t) for t in f.get("terms") or [])
    words |= {w for w in norm_word(f.get("text", "")).split() if len(w) > 3}
    return words


def same_field(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """Whether two cards come from the same science, by the words in their field facet."""
    da = set((a.get("field") or {}).get("disciplines") or [])
    db = set((b.get("field") or {}).get("disciplines") or [])
    if da and db:
        return bool(da & db)
    wa, wb = _field_words(a), _field_words(b)
    if not wa or not wb:
        return False
    fa = set((a.get("field") or {}).get("terms") or [])
    fb = set((b.get("field") or {}).get("terms") or [])
    if fa & fb:
        return True
    return len(wa & wb) / max(1, min(len(wa), len(wb))) >= 0.5


class Searcher:
    def __init__(self, kb: KB, embedder: Optional[str] = None, index: Optional[Index] = None):
        self.kb = kb
        self.ont = Ontology.load(kb.root / "ontology.json")
        self.index = index or Index(kb, embedder)
        self.index.ensure()
        self.cards = {c["id"]: c for c in kb.cards()}
        self.kinds = {b.id: b.kind for b in kb.builds()}
        self.titles = {b.id: b.title for b in kb.builds()}
        scfg = kb.config.get("search", {})
        self.prompt_weight = float(scfg.get("prompt_weight", 0.25))
        self._symbols: Dict[str, Any] = {}
        self.tag_weight = float(scfg.get("tag_weight", 0.15))

    # -- the query --------------------------------------------------------------
    def prepare(self, request: str = "", card: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        raw = dict(card or {})
        if request and not raw.get("request"):
            raw["request"] = request
        q, chk = check_query(self.ont, raw)
        if not chk.ok:
            raise KBError("; ".join(chk.errors))
        return q

    def _query_vectors(self, q: Dict[str, Any]) -> Dict[str, Any]:
        keys: List[str] = []
        texts: List[str] = []
        for ch in ("summary",) + FACETS:
            t = facet_text(q, ch) if ch != "summary" else q.get("summary", "")
            if t:
                keys.append(ch)
                texts.append(t)
        if structure_text(q):
            keys.append("structure")
            texts.append(structure_text(q))
        if workflow_text(q):
            keys.append("workflow")
            texts.append(workflow_text(q))
        if q.get("request"):
            keys.append("request")
            texts.append(q["request"])
        vecs = self.index.embed_queries(texts) if texts else []
        return dict(zip(keys, vecs))

    # -- ranking ------------------------------------------------------------------
    def rank(self, q: Dict[str, Any], where: Sequence[str] = (), exclude: Sequence[str] = (),
             facets_only: Optional[Sequence[str]] = None, use_prompt: bool = True, use_tags: bool = True) -> List[Hit]:
        qv = self._query_vectors(q)
        weights = self.ont.weights()
        # The general workflow counts like a facet: matching is by the workflow a build serves.
        facet_keys = [f for f in ("summary", "workflow") + FACETS if f in qv]
        if facets_only is not None:
            facet_keys = [f for f in facet_keys if f in facets_only]
        chans = {ch: self.index.channel(ch) for ch in ("summary", "workflow") + FACETS + ("card", "prompt")}
        qtags = tags(q)
        filters = []
        for w in where:
            if "=" not in w:
                raise KBError(f"--where takes key=value, e.g. shape=table (got {w!r})")
            k, v = w.split("=", 1)
            filters.append((k, v))
        hits: List[Hit] = []
        for cid, card in self.cards.items():
            if cid in exclude:
                continue
            if any(not matches_filter(card, k, v, self.ont, self.kinds.get(cid, "")) for k, v in filters):
                continue
            app = card.get("app", {})
            by: Dict[str, float] = {}
            parts: List[Tuple[float, float]] = []  # (weight, score)
            # Facet against facet.
            if facet_keys:
                fw = sum(weights[f] for f in facet_keys)
                fs = 0.0
                for f in facet_keys:
                    cv = chans[f].get(cid)
                    s = dot(qv[f], cv) if cv else 0.0
                    by[f] = s
                    fs += weights[f] * s
                facet_score = fs / fw if fw else 0.0
            elif "request" in qv and chans["card"].get(cid):
                # No query card: the request against the whole card.
                facet_score = dot(qv["request"], chans["card"][cid])
                by["card"] = facet_score
            else:
                facet_score = 0.0
            # Prompt against prompts.
            pw = self.prompt_weight if (use_prompt and "request" in qv and facets_only is None) else 0.0
            if pw:
                pv = chans["prompt"].get(cid)
                ps = dot(qv["request"], pv) if pv else 0.0
                by["prompt"] = ps
                parts.append((pw, ps))
            # Shared ontology words.
            tw = self.tag_weight if (use_tags and qtags and facets_only is None) else 0.0
            shared: Dict[str, List[str]] = {}
            if tw:
                ctags = tags(app)
                tsum, twsum = 0.0, 0.0
                for f, words in qtags.items():
                    if f == "field":
                        continue
                    common = [w for w in words if w in set(ctags.get(f, []))]
                    if common:
                        shared[f] = common
                    tsum += weights[f] * _jaccard(words, ctags.get(f, []))
                    twsum += weights[f]
                ts = tsum / twsum if twsum else 0.0
                by["tags"] = ts
                parts.append((tw, ts))
            rest = sum(w for w, _ in parts)
            score = (1.0 - rest) * facet_score + sum(w * s for w, s in parts)
            hits.append(Hit(id=cid, title=app.get("title") or self.titles.get(cid, cid), score=score, by=by, shared=shared,
                            field=(app.get("field") or {}).get("text", ""), kind=self.kinds.get(cid, "")))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits

    def far(self, q: Dict[str, Any], hits: List[Hit], close: Optional[Hit],
            where: Sequence[str] = (), exclude: Sequence[str] = ()) -> Optional[Hit]:
        """The best match from another field, judged on structure alone: the
        structure vector (ontology words, no field words), the general workflow
        (steps in words any science could use) and the structure words the two
        share, in equal parts."""
        if close is None:
            return None
        anchor = self.cards[close.id]["app"]
        qfield = q.get("field")
        allowed = {h.id: h for h in hits}  # already filtered and excluded
        qvs = self._query_vectors(q)
        qv, qw = qvs.get("structure"), qvs.get("workflow")
        svecs = self.index.channel("structure")
        wvecs = self.index.channel("workflow")
        qtags = tags(q)
        weights = self.ont.weights()
        best: Optional[Tuple[float, Hit, Dict[str, float], Dict[str, List[str]]]] = None
        for cid, h in allowed.items():
            if cid == close.id:
                continue
            app = self.cards[cid]["app"]
            if same_field(app, anchor) or (qfield and same_field(app, {"field": qfield})):
                continue
            by: Dict[str, float] = {}
            if qv is not None and cid in svecs:
                by["structure"] = dot(qv, svecs[cid])
            if qw is not None and cid in wvecs:
                by["workflow"] = dot(qw, wvecs[cid])
            ctags = tags(app)
            shared: Dict[str, List[str]] = {}
            tsum = twsum = 0.0
            for f in STRUCTURE:
                if f in qtags:
                    common = [w for w in qtags[f] if w in set(ctags.get(f, []))]
                    if common:
                        shared[f] = common
                    tsum += weights[f] * _jaccard(qtags[f], ctags.get(f, []))
                    twsum += weights[f]
            if twsum:
                by["tags"] = tsum / twsum
            if not by:
                by["overall"] = h.score
            score = sum(by.values()) / len(by)
            if best is None or score > best[0]:
                best = (score, h, by, shared)
        if best is None:
            return None
        score, h, by, shared = best
        return Hit(id=h.id, title=h.title, score=score, by=by, shared=shared, field=h.field, kind=h.kind)

    def _space_ready(self) -> StepSpace:
        if getattr(self, "_space", None) is None:
            self._space = StepSpace(self.index, self.cards)
        return self._space

    def _slice(self, card_id: str, part: Dict[str, Any], deps: bool, max_lines: int) -> Dict[str, Any]:
        if card_id not in self._symbols:
            self._symbols[card_id] = index_build(self.kb.build(card_id))
        return slice_part(self.kb, card_id, part, deps=deps, max_lines=max_lines, symbols=self._symbols[card_id])

    def _part_item(self, card_id: str, part: Dict[str, Any], score: float, deps: bool = False, max_lines: int = 60) -> Dict[str, Any]:
        sl = self._slice(card_id, part, deps, max_lines)
        return {"id": part["id"], "title": part.get("title", ""), "level": part.get("level"),
                "summary": part.get("summary", ""), "score": round(score, 4),
                "spans": sl["spans"], "needs": sl["needs"], "truncated": sl["truncated"]}

    def attach_parts(self, q: Dict[str, Any], hit: Hit, n: int, qsteps: Optional[List[Any]] = None) -> None:
        """The parts of a build that fit the request: first the parts that do the
        steps the request shares with it, then the parts closest to what it asked for."""
        hit.parts = []
        if n <= 0:
            return
        card = self.cards[hit.id]
        by_id = {p["id"]: p for p in card.get("parts", [])}
        first: List[str] = []
        if q.get("workflow") and qsteps:
            m = self.workflow_match(q, qsteps, hit.id) or {}
            for st in m.get("shared", []):
                if st.get("common"):
                    continue
                for pid in st.get("parts", []):
                    if pid in by_id and pid not in first:
                        first.append(pid)
        qv = self._query_vectors({k: q[k] for k in ("mechanism", "summary", "request") if q.get(k)})
        anchor = qv.get("mechanism") or qv.get("summary") or qv.get("request")
        vecs = self.index.parts(hit.id)
        scored = {}
        for part in card.get("parts", []):
            v = vecs.get((hit.id, part["id"]))
            scored[part["id"]] = dot(anchor, v) if (anchor and v) else 0.0
        order = first + sorted((pid for pid in by_id if pid not in first), key=lambda pid: scored[pid], reverse=True)
        for pid in order[:n]:
            hit.parts.append(self._part_item(hit.id, by_id[pid], scored[pid]))

    def code_for_steps(self, q: Dict[str, Any], qsteps: List[Any], per_step: int = 1, max_lines: int = 160) -> List[Dict[str, Any]]:
        """For each step of the request's workflow, the code that does that step in
        whichever builds do it best: the parts linked to the matching step, as slices
        with what they depend on. A step no build does yet is said so."""
        wf = q.get("workflow") or {}
        steps = [st for st in wf.get("steps") or [] if st.get("step")]
        if not steps or not qsteps:
            return []
        space = self._space_ready()
        out = []
        for st, (qg, qh) in zip(steps, qsteps):
            cands = []
            for cid, vecs in space.vecs.items():
                best = None
                for j, (g, h) in enumerate(vecs):
                    if g is None or qg is None:
                        continue
                    sim = dot(qg, g)
                    if sim < space.tau:
                        continue
                    # How the step is done counts a little too, so the closest case wins a tie.
                    score = sim + (0.25 * dot(qh, h) if (qh is not None and h is not None and st.get("here")) else 0.0)
                    if best is None or score > best[0]:
                        best = (score, sim, j)
                if best:
                    cands.append((best[0], best[1], cid, best[2]))
            cands.sort(reverse=True)
            entry: Dict[str, Any] = {"step": st["step"], "here": st.get("here", ""), "from": []}
            for score, sim, cid, j in cands[:per_step]:
                cst = (self.cards[cid]["app"].get("workflow") or {}).get("steps", [])[j]
                by_id = {p["id"]: p for p in self.cards[cid].get("parts", [])}
                pids = [pid for pid in cst.get("parts", []) if pid in by_id]
                if not pids and by_id:
                    # The step names no parts: take the part closest to how the step is done.
                    pv = self.index.parts(cid)
                    probe = qh if qh is not None else qg
                    pids = [max(by_id, key=lambda pid: dot(probe, pv[(cid, pid)]) if (cid, pid) in pv else -1)]
                slices = [self._slice(cid, by_id[pid], True, max_lines) for pid in pids[:3]]
                entry["from"].append({
                    "build": cid, "title": self.titles.get(cid, cid), "field": (self.cards[cid]["app"].get("field") or {}).get("text", ""),
                    "their_step": cst.get("step", ""), "their_here": cst.get("here", ""), "similarity": round(sim, 4),
                    "common": space.common(space.df.get((cid, j), 0)), "slices": slices,
                })
            out.append(entry)
        return out

    def pieces(self, q: Dict[str, Any], skip: Sequence[str], n: int = 5) -> List[Dict[str, Any]]:
        """Views and components from anywhere in the knowledge base that fit the request,
        for requests described without a workflow."""
        qv = self._query_vectors({k: q[k] for k in ("mechanism", "summary", "request") if q.get(k)})
        anchor = qv.get("mechanism") or qv.get("summary") or qv.get("request")
        if not anchor:
            return []
        scored = []
        for (cid, pid), v in self.index.parts().items():
            if cid in skip or cid not in self.cards:
                continue
            scored.append((dot(anchor, v), cid, pid))
        scored.sort(reverse=True)
        out = []
        for s, cid, pid in scored[:n]:
            part = next(p for p in self.cards[cid]["parts"] if p["id"] == pid)
            item = self._part_item(cid, part, s)
            item.update(build=cid, build_title=self.titles.get(cid, cid))
            out.append(item)
        return out

    # -- the whole thing --------------------------------------------------------
    def search(self, request: str = "", card: Optional[Dict[str, Any]] = None, k: Optional[int] = None,
               where: Sequence[str] = (), exclude: Sequence[str] = (), parts: Optional[int] = None,
               far: Optional[bool] = None, pieces: int = 4, steps_code_on: bool = True) -> Dict[str, Any]:
        scfg = self.kb.config.get("search", {})
        k = int(k if k is not None else scfg.get("k", 5))
        parts = int(parts if parts is not None else scfg.get("parts_per_build", 2))
        far = bool(scfg.get("far", True) if far is None else far)
        q = self.prepare(request, card)
        hits = self.rank(q, where=where, exclude=exclude)
        top = hits[:k]
        qsteps = query_vectors(self.index, q.get("workflow") or {})
        for h in top:
            self.attach_parts(q, h, parts, qsteps)
        far_hit = self.far(q, hits, top[0] if top else None, where, exclude) if far else None
        if far_hit:
            self.attach_parts(q, far_hit, parts, qsteps)
        shown = [h.id for h in top] + ([far_hit.id] if far_hit else [])
        steps_code = self.code_for_steps(q, qsteps) if steps_code_on else []
        return {
            "query": q,
            "embedder": self.index.embedder.id,
            "results": [self._full(h, q, qsteps) for h in top],
            "far": self._full(far_hit, q, qsteps) if far_hit else None,
            "steps_code": steps_code,
            "pieces": self.pieces(q, skip=shown, n=pieces) if (pieces and not steps_code) else [],
        }

    def workflow_match(self, q: Dict[str, Any], qsteps: List[Any], card_id: str) -> Optional[Dict[str, Any]]:
        """How the request's workflow lines up with a build's: shared steps with how
        each side does them, steps only one side has, and the distinctive needs."""
        cwf = self.cards[card_id]["app"].get("workflow") or {}
        if not q.get("workflow") or not cwf:
            return None
        space = self._space_ready()
        return compare(space, q["workflow"], qsteps, cwf, space.vecs.get(card_id, []), b_id=card_id)

    def _full(self, h: Hit, q: Optional[Dict[str, Any]] = None, qsteps: Optional[List[Any]] = None) -> Dict[str, Any]:
        d = h.as_dict()
        card = self.cards[h.id]
        b = self.kb.build(h.id)
        d["summary"] = card["app"].get("summary", "")
        d["workflow"] = card["app"].get("workflow")
        if q is not None:
            d["workflow_match"] = self.workflow_match(q, qsteps or [], h.id)
        d["card"] = {f: card["app"].get(f) for f in FACETS}
        d["prompts"] = [t.get("text", "") for t in b.prompts]
        d["entry"] = str((b.path / b.meta.get("entry", "")).relative_to(self.kb.root)) if b.meta.get("entry") else None
        d["author"] = (b.meta.get("author") or {}).get("name", "")
        return d


# -- text output ------------------------------------------------------------------

def _bar(x: float, width: int = 10) -> str:
    n = max(0, min(width, round(x * width)))
    return "█" * n + "·" * (width - n)


def format_results(res: Dict[str, Any], show_code: bool = True, prompt_turns: int = 2) -> str:
    out: List[str] = []
    q = res["query"]
    out.append(f"Request: {q.get('request') or '(query card only)'}")
    described = [f for f in ("summary", "workflow") + FACETS if q.get(f)]
    out.append(f"Described as: {', '.join(described) if described else 'nothing yet (searching on the request words)'}   ·   embedder {res['embedder']}")
    out.append("")

    def one(i: str, h: Dict[str, Any]) -> None:
        out.append(f"{i} {h['title']}  [{h['id']}]  score {h['score']:.2f}")
        meta = " · ".join(x for x in (h.get("field"), h.get("kind") and f"{h['kind']} build", h.get("author") and f"by {h['author']}") if x)
        if meta:
            out.append(f"   {meta}")
        if h.get("by"):
            out.append("   " + "  ".join(f"{k} {_bar(v, 6)} {v:.2f}" for k, v in h["by"].items()))
        if h.get("shared"):
            out.append("   shares: " + "; ".join(f"{f}: {', '.join(w)}" for f, w in h["shared"].items()))
        if h.get("summary"):
            out.append(f"   {h['summary']}")
        if h.get("workflow_match"):
            out.extend(format_diff(h["workflow_match"]))
        elif h.get("workflow"):
            wf = h["workflow"]
            out.append(f"   workflow: {wf.get('name', '')}")
            out.append("   steps: " + " → ".join(st["step"] for st in wf.get("steps", [])))
            if wf.get("distinctive"):
                out.append("   particular to it: " + "; ".join(wf["distinctive"]))
        for t in h.get("prompts", [])[:prompt_turns]:
            t = " ".join(t.split())
            out.append(f"   > {t[:220]}{'…' if len(t) > 220 else ''}")
        if h.get("entry"):
            out.append(f"   code: {h['entry']}")
        for p in h.get("parts", []):
            out.append(f"   - {p['title']} ({p['level']}): " + "; ".join(_where(sp) for sp in p.get("spans", [])))
            if p.get("summary"):
                out.append(f"     {p['summary']}")
            if show_code:
                out.extend(_code_lines(p.get("spans", []), 24, "     | "))
        out.append("")

    if not res["results"]:
        out.append("Nothing matched. Check the filters, or that the knowledge base has cards (`astaui status`).")
    for n, h in enumerate(res["results"], 1):
        one(f"{n}.", h)
    if res.get("far"):
        out.append("From another field, same structure:")
        one("↔", res["far"])
    if res.get("steps_code"):
        out.append("Code for each of your steps (`astaui slice <build> <part>` for the whole slice):")
        for n, st in enumerate(res["steps_code"], 1):
            out.append(f"{n}. {st['step']}" + (f"  ({st['here']})" if st.get("here") else ""))
            if not st["from"]:
                out.append("   no build does this step yet")
            for src in st["from"]:
                common = "  (a move most builds have)" if src.get("common") else ""
                out.append(f"   from {src['title']}  [{src['build']}]{common}: {src['their_here'] or src['their_step']}")
                for sl in src["slices"]:
                    out.append(f"   - {sl['title']} [{sl['part']}]: " + "; ".join(_where(sp) for sp in sl["spans"])
                               + (f"; also uses {', '.join(sl['needs'])}" if sl.get("needs") else ""))
                    if show_code:
                        out.extend(_code_lines(sl["spans"], 18, "     | "))
        out.append("")
    if res.get("pieces"):
        out.append("Pieces from elsewhere that fit:")
        for p in res["pieces"]:
            out.append(f"   - {p['title']} ({p['level']}) in {p['build_title']}: " + "; ".join(_where(sp) for sp in p.get("spans", [])))
    return "\n".join(out).rstrip() + "\n"


def _where(sp: Dict[str, Any]) -> str:
    label = ", ".join(sp.get("symbols") or ([sp["symbol"]] if sp.get("symbol") else []))
    return f"{sp.get('path', sp['file'])}:{sp['start']}-{sp.get('shown_end', sp['end'])} {sp['role']}" + (f" ({label})" if label else "")


def _code_lines(spans: List[Dict[str, Any]], limit: int, prefix: str) -> List[str]:
    """The first lines of a slice's own spans, for a quick look."""
    out: List[str] = []
    for sp in spans:
        if "the card" not in sp.get("why", ["the card"]):
            continue
        for line in sp.get("text", "").splitlines():
            if len(out) >= limit:
                out.append(prefix + "…")
                return out
            out.append(prefix + line)
    return out
