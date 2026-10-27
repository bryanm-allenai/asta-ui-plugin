"""The atlas: what the knowledge base looks like, computed once for every view.

Everything the console's visual views draw comes from here: where each build
sits in the embedding space under each representation, how alike every pair of
builds is, which types of data (and tasks, views, patterns…) each build carries,
how the workflows of a family line up step by step, and what the knowledge base
is made of. Nothing here draws; the renderer turns it into markup.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .cards import card_text, facet_text, part_spans, slug, structure_text, workflow_text
from .index import Index
from .kb import KB
from .ontology import FACETS, LISTS, Ontology
from .vec import Vector, dot, place_by_neighbours, project_2d

# The representations a build can be placed by, with the short key each is stored under.
CHANNELS: List[Tuple[str, str, str, str]] = [
    ("c", "card", "Card", "The whole card: summary, workflow and the five facets"),
    ("w", "workflow", "Workflow", "The general workflow: its name and steps, in words any science could use"),
    ("s", "structure", "Structure", "The ontology's words for task, data, stage and mechanism, with nothing from the field"),
    ("d", "data", "Data", "The data facet: what the data is and what one item is"),
    ("t", "task", "Task", "The task facet"),
    ("m", "mechanism", "Mechanism", "Views, interactions and patterns"),
    ("r", "raw", "Prompts and code", "The prompts and the code as they are, before any describing"),
    ("p", "prompt", "Prompts", "The prompts alone"),
]
KEY = {name: key for key, name, _, _ in CHANNELS}

# The lists of words a card is described with, as the Types view shows them.
TERM_LISTS: List[Tuple[str, str, str, str]] = [
    ("data", "shapes", "Data shapes", "What shape the data has"),
    ("task", "verbs", "Tasks", "What the interface is for"),
    ("stage", "terms", "Stages", "Where in the work it is used"),
    ("mechanism", "views", "Views", "What the person looks at"),
    ("mechanism", "interactions", "Interactions", "What the person does to it"),
    ("mechanism", "patterns", "Patterns", "Known design patterns it uses"),
    ("field", "disciplines", "Disciplines", "The broad science it comes from"),
]

# Colour options for the map. Each build gets a slot 1–3 for the three most
# common values of the option, and 0 for everything else ("Other").
COLOURS: List[Tuple[str, str]] = [
    ("f", "Workflow family"), ("d", "Discipline"), ("s", "Data shape"), ("t", "Task"), ("g", "Stage"), ("k", "Where it came from"),
]


def _round(x: float) -> float:
    return round(x, 3)


def rotation_to(ref: Sequence[Tuple[float, float]], pts: Sequence[Tuple[float, float]]):
    """The turn (and, if it fits better, mirror) that brings a layout closest to a
    reference layout of the same items: orthogonal Procrustes in two dimensions.
    Returns a function that carries any point of the layout through it."""
    n = len(pts)
    cx = sum(p[0] for p in pts) / n
    cy = sum(p[1] for p in pts) / n
    rx = sum(p[0] for p in ref) / n
    ry = sum(p[1] for p in ref) / n
    a = b = c = d = 0.0
    for (px, py), (qx, qy) in zip(pts, ref):
        px, py, qx, qy = px - cx, py - cy, qx - rx, qy - ry
        a += px * qx
        b += px * qy
        c += py * qx
        d += py * qy
    if math.hypot(a + d, c - b) >= math.hypot(a - d, b + c):
        th = math.atan2(c - b, a + d)
        m = ((math.cos(th), -math.sin(th)), (math.sin(th), math.cos(th)))
    else:
        th = math.atan2(b + c, a - d)
        m = ((math.cos(th), math.sin(th)), (math.sin(th), -math.cos(th)))
    return lambda p: ((p[0] - cx) * m[0][0] + (p[1] - cy) * m[1][0], (p[0] - cx) * m[0][1] + (p[1] - cy) * m[1][1])


def fit_box(pts: Sequence[Tuple[float, float]], margin: float = 0.06) -> List[Tuple[float, float]]:
    """Scale a layout into the unit square with a margin, keeping its proportions."""
    if not pts:
        return []
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    span = max(max(xs) - min(xs), max(ys) - min(ys)) or 1.0
    mx = (max(xs) + min(xs)) / 2
    my = (max(ys) + min(ys)) / 2
    inner = 1 - 2 * margin
    return [(0.5 + (x - mx) / span * inner, 0.5 + (y - my) / span * inner) for x, y in pts]


def cluster_order(ids: List[str], sim: Dict[Tuple[str, str], float]) -> List[str]:
    """An order for the similarity matrix that puts alike builds next to each other:
    average-linkage clustering, read off leaf by leaf."""
    def s(a: str, b: str) -> float:
        return sim.get((a, b), sim.get((b, a), 0.0))

    clusters: List[List[str]] = [[i] for i in ids]
    while len(clusters) > 1:
        best = None
        for x in range(len(clusters)):
            for y in range(x + 1, len(clusters)):
                avg = sum(s(a, b) for a in clusters[x] for b in clusters[y]) / (len(clusters[x]) * len(clusters[y]))
                if best is None or avg > best[0]:
                    best = (avg, x, y)
        _, x, y = best
        merged = clusters[x] + clusters[y]
        clusters = [c for k, c in enumerate(clusters) if k not in (x, y)] + [merged]
    return clusters[0] if clusters else []


class Atlas:
    def __init__(self, kb: KB, index: Index, space=None):
        from .workflows import StepSpace

        self.kb = kb
        self.index = index
        index.ensure()
        self.ont = Ontology.load(kb.root / "ontology.json")
        self.cards = {c["id"]: c for c in kb.cards()}
        self.builds = {b.id: b for b in kb.builds()}
        self.ids = sorted(self.builds)
        self.space = space or StepSpace(index, self.cards)
        self._families = None

    # -- families --------------------------------------------------------------------------
    def families(self) -> Dict[str, Any]:
        from .workflows import families

        if self._families is None:
            self._families = families(self.space) if self.cards else {"families": [], "common_moves": [], "threshold": 0, "step_threshold": 0}
        return self._families

    def family_of(self) -> Dict[str, str]:
        out = {}
        for f in self.families()["families"]:
            for m in f["members"]:
                out[m["id"]] = f["name"] if len(f["members"]) > 1 else ""
        return out

    # -- the map ------------------------------------------------------------------------------
    def layouts(self) -> Dict[str, Dict[str, Tuple[float, float]]]:
        """Every build's place under every representation. Each layout is turned to sit
        as close as it can to the card's, so switching representation moves the
        builds that really move and does not spin the whole picture."""
        out: Dict[str, Dict[str, Tuple[float, float]]] = {}
        ref: Optional[Dict[str, Tuple[float, float]]] = None
        for key, name, _, _ in CHANNELS:
            vecs = self.index.channel(name)
            ids = [i for i in self.ids if i in vecs]
            if len(ids) < 2:
                continue
            pts, _ = project_2d([vecs[i] for i in ids])
            if ref is not None:
                common = [k for k, i in enumerate(ids) if i in ref]
                if len(common) >= 3:
                    turn = rotation_to([ref[ids[k]] for k in common], [pts[k] for k in common])
                    pts = [turn(p) for p in pts]
            pts = fit_box(pts)
            layout = {i: (_round(p[0]), _round(p[1])) for i, p in zip(ids, pts)}
            out[key] = layout
            if ref is None:
                ref = layout
        return out

    def neighbours(self, k: int = 5) -> Dict[str, Dict[str, List[Tuple[str, float]]]]:
        out: Dict[str, Dict[str, List[Tuple[str, float]]]] = {}
        for key, name, _, _ in CHANNELS:
            vecs = self.index.channel(name)
            for i in self.ids:
                if i not in vecs:
                    continue
                sims = sorted(((dot(vecs[i], vecs[j]), j) for j in self.ids if j != i and j in vecs), reverse=True)[:k]
                out.setdefault(i, {})[key] = [(j, _round(s)) for s, j in sims]
        return out

    def requests(self, layouts: Dict[str, Dict[str, Tuple[float, float]]]) -> List[Dict[str, Any]]:
        """The test requests, placed among the builds the way the search would see them."""
        from .cards import check_query

        out = []
        for q in self.kb.queries():
            prepared, _ = check_query(self.ont, {**(q.get("card") or {}), "request": q.get("request", "")})
            texts = {
                "c": card_text(prepared) or prepared.get("request", ""),
                "w": workflow_text(prepared),
                "s": structure_text(prepared),
                "d": facet_text(prepared, "data"),
                "t": facet_text(prepared, "task"),
                "m": facet_text(prepared, "mechanism"),
                "r": prepared.get("request", ""),
                "p": prepared.get("request", ""),
            }
            keys = [k for k, t in texts.items() if t]
            vecs = dict(zip(keys, self.index.embed_queries([texts[k] for k in keys]))) if keys else {}
            pos: Dict[str, Tuple[float, float]] = {}
            nearest: Dict[str, str] = {}
            for key, name, _, _ in CHANNELS:
                if key not in vecs or key not in layouts:
                    continue
                chan = self.index.channel(name)
                ids = [i for i in layouts[key] if i in chan]
                sims = [dot(vecs[key], chan[i]) for i in ids]
                at = place_by_neighbours(sims, [layouts[key][i] for i in ids], k=3)
                if at:
                    pos[key] = (_round(at[0]), _round(at[1]))
                    nearest[key] = ids[max(range(len(sims)), key=lambda n: sims[n])]
            out.append({"id": q.get("id"), "request": q.get("request", ""), "wanted": q.get("wanted", []),
                        "pos": pos, "nearest": nearest})
        return out

    def faithfulness(self, layouts: Dict[str, Dict[str, Tuple[float, float]]], k: int = 3) -> Dict[str, float]:
        """How much of the full space each flat map keeps: the share of every build's k
        nearest neighbours (by similarity) that are also among its k nearest on the map."""
        out = {}
        for key, name, _, _ in CHANNELS:
            if key not in layouts:
                continue
            vecs = self.index.channel(name)
            ids = [i for i in layouts[key] if i in vecs]
            if len(ids) <= k:
                continue
            kept = 0
            for i in ids:
                full = sorted((j for j in ids if j != i), key=lambda j: -dot(vecs[i], vecs[j]))[:k]
                xi, yi = layouts[key][i]
                flat = sorted((j for j in ids if j != i), key=lambda j: (layouts[key][j][0] - xi) ** 2 + (layouts[key][j][1] - yi) ** 2)[:k]
                kept += len(set(full) & set(flat))
            out[key] = round(kept / (k * len(ids)), 3)
        return out

    def facts(self) -> Dict[str, Dict[str, List[str]]]:
        """What each build is, in the words the views filter and colour by: its workflow
        family (f), discipline (d), where it came from (k), consent (c), data shapes (s),
        tasks (t), stages (g) and patterns (p)."""
        fam = self.family_of()
        out: Dict[str, Dict[str, List[str]]] = {}
        for i in self.ids:
            c = self.cards.get(i)
            app = c["app"] if c else {}

            def words(facet: str, lst: str) -> List[str]:
                return list((app.get(facet) or {}).get(lst) or [])

            b = self.builds[i]
            out[i] = {
                "f": [fam.get(i) or "no close relative"],
                "d": words("field", "disciplines")[:1] or ["none"],
                "k": [b.kind or "unknown"],
                "c": [(b.meta.get("provenance") or {}).get("consent", "unknown")],
                "s": words("data", "shapes"),
                "t": words("task", "verbs"),
                "g": words("stage", "terms"),
                "p": words("mechanism", "patterns"),
            }
        return out

    def pair_steps(self, a: str, b: str) -> Dict[str, Any]:
        """Two builds' workflows lined up: the steps they share (each as both say it)
        and how many each has of its own."""
        wa = [s for s in (self.cards[a]["app"].get("workflow") or {}).get("steps") or [] if s.get("step")]
        wb = [s for s in (self.cards[b]["app"].get("workflow") or {}).get("steps") or [] if s.get("step")]
        va, vb = self.space.vecs.get(a, []), self.space.vecs.get(b, [])
        pairs = self.space.align(va, vb) if va and vb else []
        shared = []
        for i, j, sim in sorted(pairs):
            shared.append({"a": wa[i]["step"], "b": wb[j]["step"], "a_here": wa[i].get("here", ""), "b_here": wb[j].get("here", ""),
                           "common": self.space.common(self.space.df.get((b, j), 0)), "similarity": _round(sim)})
        return {"shared": shared, "only_a": len(wa) - len(pairs), "only_b": len(wb) - len(pairs),
                "overlap": _round(self.space.overlap(a, b)) if va and vb else 0.0}

    # -- the matrix --------------------------------------------------------------------------
    def matrix(self) -> Dict[str, Any]:
        """Every pair's similarity under every representation, each scaled to 0–1 across
        the knowledge base so the colours mean the same thing in every view."""
        raw: Dict[str, Dict[Tuple[str, str], float]] = {}
        for key, name, _, _ in CHANNELS:
            vecs = self.index.channel(name)
            vals = {}
            for i in self.ids:
                for j in self.ids:
                    if i < j and i in vecs and j in vecs:
                        vals[(i, j)] = dot(vecs[i], vecs[j])
            raw[key] = vals
        scaled: Dict[str, Dict[Tuple[str, str], float]] = {}
        for key, vals in raw.items():
            if not vals:
                continue
            lo, hi = min(vals.values()), max(vals.values())
            scaled[key] = {p: (v - lo) / (hi - lo) if hi > lo else 0.5 for p, v in vals.items()}
        base = raw.get("w") or raw.get("c") or {}
        order = cluster_order([i for i in self.ids if any(i in p for p in base)] or self.ids, base)
        order += [i for i in self.ids if i not in order]
        return {"order": order, "raw": raw, "scaled": scaled}

    # -- the types of data ------------------------------------------------------------------------
    def terms(self) -> List[Dict[str, Any]]:
        """For every list of words: each word, what it means, its other words, and which
        builds carry it; words cards used that the ontology lacks; words nobody uses yet."""
        out = []
        for facet, lst, label, says in TERM_LISTS:
            used: Dict[str, List[str]] = {}
            for cid in self.ids:
                card = self.cards.get(cid)
                if not card:
                    continue
                for w in (card["app"].get(facet) or {}).get(lst) or []:
                    used.setdefault(w, []).append(cid)
            vocab = {t.name: t for t in self.ont.terms(facet, lst)}
            rows = []
            for name, t in vocab.items():
                rows.append({"term": name, "means": t.means, "also": t.also, "builds": used.get(name, []), "status": "vocab"})
            for w, b in used.items():
                if w not in vocab:
                    rows.append({"term": w, "means": "", "also": [], "builds": b, "status": "proposed"})
            rows.sort(key=lambda r: (r["status"] == "vocab" and not r["builds"], -len(r["builds"]), r["term"]))
            out.append({"facet": facet, "list": lst, "label": label, "says": says, "rows": rows,
                        "open": self.ont.is_open(facet, lst)})
        return out

    # -- workflows ---------------------------------------------------------------------------------
    def alignments(self) -> List[Dict[str, Any]]:
        """Each family's workflows side by side: one row per step, one column per build,
        each cell how that build does the step, or empty where it has no such step."""
        out = []
        for fam in self.families()["families"]:
            members = [m["id"] for m in fam["members"]]
            central = fam["central"]
            steps_of = {m: [s for s in (self.cards[m]["app"].get("workflow") or {}).get("steps") or [] if s.get("step")] for m in members}
            rows: List[Dict[str, Any]] = []
            # Rows start from the central build's steps; every other member is lined up against them.
            for i, st in enumerate(steps_of[central]):
                common = self.space.common(self.space.df.get((central, i), 0))
                rows.append({"step": st["step"], "cells": {central: st.get("here", "")}, "common": common, "anchor": (central, i)})
            for m in members:
                if m == central:
                    continue
                pairs = {i: j for i, j, _ in self.space.align(self.space.vecs.get(central, []), self.space.vecs.get(m, []))}
                taken = set()
                for i, j in pairs.items():
                    rows[i]["cells"][m] = steps_of[m][j].get("here", "")
                    taken.add(j)
                for j, st in enumerate(steps_of[m]):
                    if j in taken:
                        continue
                    # A step only this member has, unless another member's own row already matches it.
                    placed = False
                    for row in rows:
                        if row["anchor"][0] != central and m not in row["cells"]:
                            a, ai = row["anchor"]
                            av = self.space.vecs.get(a, [])[ai][0] if self.space.vecs.get(a) else None
                            bv = self.space.vecs.get(m, [])[j][0] if self.space.vecs.get(m) else None
                            if av is not None and bv is not None and dot(av, bv) >= self.space.tau:
                                row["cells"][m] = st.get("here", "")
                                placed = True
                                break
                    if not placed:
                        rows.append({"step": st["step"], "cells": {m: st.get("here", "")},
                                     "common": self.space.common(self.space.df.get((m, j), 0)), "anchor": (m, j)})
            for row in rows:
                n = len(row["cells"])
                row["kind"] = "common" if row["common"] else ("shared" if n == len(members) and n > 1 else "some" if n > 1 else "own")
                del row["anchor"]
            out.append({"name": fam["name"], "central": central, "members": members, "rows": rows,
                        "distinctive": {m: list((self.cards[m]["app"].get("workflow") or {}).get("distinctive") or []) for m in members}})
        return out

    # -- composition -------------------------------------------------------------------------------
    def composition(self) -> Dict[str, Any]:
        """What the knowledge base is made of: how many builds have each value of each
        fact, and how much code each build has, by role, against the size of the slice
        a search hands back for one part."""
        from .slices import slice_part
        from .symbols import index_build

        facts = self.facts()

        def count(key: str) -> List[Tuple[str, List[str]]]:
            buckets: Dict[str, List[str]] = {}
            for i in self.ids:
                for v in facts[i][key]:
                    buckets.setdefault(v, []).append(i)
            return sorted(buckets.items(), key=lambda kv: (-len(kv[1]), kv[0]))

        code = []
        for i in self.ids:
            b = self.builds[i]
            entry = b.path / b.meta["entry"] if b.meta.get("entry") else None
            lines = entry.read_text(encoding="utf-8", errors="replace").count("\n") + 1 if entry and entry.is_file() else 0
            roles: Dict[str, int] = {}
            sizes: List[int] = []
            card = self.cards.get(i)
            if card:
                syms = index_build(b)
                seen = set()
                for p in card.get("parts", []):
                    for sp in part_spans(p):
                        for n in range(sp["start"], sp["end"] + 1):
                            if (sp["file"], n) not in seen:
                                seen.add((sp["file"], n))
                                roles[sp["role"]] = roles.get(sp["role"], 0) + 1
                    sizes.append(slice_part(self.kb, i, p, symbols=syms)["lines"])
            sizes.sort()
            code.append({"id": i, "lines": lines, "roles": roles, "slice_median": sizes[len(sizes) // 2] if sizes else 0,
                         "parts": len(card.get("parts", [])) if card else 0})
        return {key: count(key) for key in ("d", "f", "k", "c", "s", "t", "g", "p")} | {"code": code}

    # -- colours --------------------------------------------------------------------------------------
    def colour_slots(self) -> Dict[str, Dict[str, Any]]:
        """For each colour option: every build's value, and the slot (1–3, or 0 for Other)
        its value takes, the three most common values getting the three hues. A build
        with no close relative has no family, so it is Other."""
        facts = self.facts()
        out = {}
        for opt, label in COLOURS:
            key = {"f": "f", "d": "d", "s": "s", "t": "t", "g": "g", "k": "k"}[opt]
            values = {i: (facts[i][key][:1] or [""])[0] for i in self.ids}
            if opt == "f":
                values = {i: ("" if v == "no close relative" else v) for i, v in values.items()}
            counts: Dict[str, int] = {}
            for v in values.values():
                if v and v != "none":
                    counts[v] = counts.get(v, 0) + 1
            top = [v for v, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])) if n > 1 or len(counts) <= 3][:3]
            slot = {i: (top.index(v) + 1 if v in top else 0) for i, v in values.items()}
            out[opt] = {"label": label, "top": top, "other": sum(1 for i in self.ids if slot[i] == 0),
                        "slot": slot, "value": values, "count": {v: counts[v] for v in top}}
        return out
