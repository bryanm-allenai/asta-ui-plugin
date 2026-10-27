"""Cards: what a build is, in the ontology's terms.

``check_card`` is the gate every card goes through, whoever wrote it: an agent
following ``astaui extract``'s instructions, the API extractor, or a person by hand.
It returns the cleaned card and a list of problems, each in words that say how
to fix it.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .kb import Build, KBError
from .ontology import FACETS, LISTS, PART_LISTS, Ontology, norm_word

SCHEMA = "astaui.card/1"
LEVELS = ("view", "component")
ROLES = ("markup", "style", "logic", "data", "other")
ROLE_OF_KIND = {"element": "markup", "css": "style", "function": "logic", "method": "logic", "class": "logic", "data": "data", "block": "other"}
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def slug(text: str, fallback: str = "part") -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (s[:48].rstrip("-") or fallback)


def _text(v: Any) -> str:
    return v.strip() if isinstance(v, str) else ""


class CardCheck:
    def __init__(self) -> None:
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.proposed: List[Dict[str, str]] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    @property
    def ok(self) -> bool:
        return not self.errors


def _facet(ont: Ontology, facet: str, raw: Any, chk: CardCheck, where: str, required: bool) -> Dict[str, Any]:
    raw = raw if isinstance(raw, dict) else ({} if raw is None else {"text": raw} if isinstance(raw, str) else {})
    out: Dict[str, Any] = {"text": _text(raw.get("text"))}
    if facet == "data":
        out["item"] = _text(raw.get("item"))
    for lst in LISTS[facet]:
        words, proposed = ont.normalize(facet, lst, raw.get(lst))
        out[lst] = words
        for p in proposed:
            if not ont.is_open(facet, lst):
                chk.proposed.append({"facet": facet, "list": lst, "term": p})
    if facet == "field" and not out["disciplines"]:
        out["disciplines"] = infer_disciplines(ont, out["terms"], out["text"])
    if required:
        has_words = any(out[lst] for lst in LISTS[facet])
        if not out["text"] and not has_words:
            chk.error(f"{where}.{facet} is empty: give it a sentence in `text` and words in `{LISTS[facet][0]}`")
        elif not has_words and facet != "field":
            chk.warn(f"{where}.{facet} has no {', '.join(LISTS[facet])}: pick words from the ontology so filters and tag matching work")
    return out


def infer_disciplines(ont: Ontology, terms: List[str], text: str) -> List[str]:
    """The broad discipline a field's own words point to, when the card names none:
    "cscw" and "usability testing" are both hci. The first word that matches wins."""
    candidates = list(terms)
    words = norm_word(text).split()
    for n in (3, 2, 1):
        candidates += [" ".join(words[i : i + n]) for i in range(len(words) - n + 1)]
    for c in candidates:
        name, known = ont.canonical("field", "disciplines", c)
        if known and any(t.name == name for t in ont.terms("field", "disciplines")):
            return [name]
    return []


def _check_private(text: str, where: str, chk: CardCheck) -> None:
    if EMAIL_RE.search(text):
        chk.error(f"{where} contains an email address; a card describes structure, not people")


def check_app(ont: Ontology, raw: Dict[str, Any], chk: CardCheck, where: str = "app", query: bool = False) -> Dict[str, Any]:
    app: Dict[str, Any] = {}
    if not query:
        app["title"] = _text(raw.get("title"))
        if not app["title"]:
            chk.error(f"{where}.title is missing")
    summary = _text(raw.get("summary"))
    if not query and not summary:
        chk.error(f"{where}.summary is missing: write the workflow in two to four plain sentences")
    elif summary and len(summary) < 40 and not query:
        chk.warn(f"{where}.summary is very short; say what a person does with it, in order")
    if summary:
        app["summary"] = summary
        _check_private(summary, f"{where}.summary", chk)
    for facet in FACETS:
        if query and facet not in raw:
            continue
        app[facet] = _facet(ont, facet, raw.get(facet), chk, where, required=not query)
        _check_private(app[facet].get("text", ""), f"{where}.{facet}.text", chk)
    return app


def check_workflow(raw: Any, chk: CardCheck, where: str, part_ids: Optional[set] = None, query: bool = False) -> Optional[Dict[str, Any]]:
    """The workflow: a general name, ordered steps, and what is particular to this case.

    Each step is said twice. ``step`` is the general move, in words any science
    could use; ``here`` is how this build (or this request) does it. Matching runs
    on the general steps; the specifics and ``distinctive`` say how cases differ."""
    if raw is None:
        if not query:
            chk.error(f"{where}.workflow is missing: name the workflow, list its steps in order, and say what is distinctive about this case")
        return None
    if not isinstance(raw, dict):
        chk.error(f"{where}.workflow must be an object with name, steps and distinctive")
        return None
    name = _text(raw.get("name"))
    steps: List[Dict[str, Any]] = []
    raw_steps = raw.get("steps") or []
    if not isinstance(raw_steps, list):
        chk.error(f"{where}.workflow.steps must be a list")
        raw_steps = []
    for i, rs in enumerate(raw_steps, 1):
        rs = {"step": rs} if isinstance(rs, str) else rs if isinstance(rs, dict) else {}
        step = {"step": _text(rs.get("step")), "here": _text(rs.get("here"))}
        if not step["step"]:
            chk.error(f"{where}.workflow.steps[{i - 1}] has no `step`: the general move, in words any science could use")
        parts = [slug(p) for p in (rs.get("parts") or []) if isinstance(p, str) and p.strip()]
        if part_ids is not None:
            for p in parts:
                if p not in part_ids:
                    chk.error(f"{where}.workflow.steps[{i - 1}] names part {p!r}, which is not one of the card's parts")
        if not query:
            step["parts"] = parts
        for k in ("step", "here"):
            _check_private(step[k], f"{where}.workflow.steps[{i - 1}].{k}", chk)
        steps.append(step)
    distinctive = [_text(d) for d in (raw.get("distinctive") or []) if _text(d)]
    for d in distinctive:
        _check_private(d, f"{where}.workflow.distinctive", chk)
    _check_private(name, f"{where}.workflow.name", chk)
    if not query:
        if not name:
            chk.error(f"{where}.workflow.name is missing: the general workflow in a few words, with no field words")
        if len(steps) < 2:
            chk.error(f"{where}.workflow needs at least two steps, in the order a person does them")
        if any(not st["here"] for st in steps):
            chk.warn(f"{where}.workflow has steps without `here`: say how this build does each step")
        if not distinctive:
            chk.warn(f"{where}.workflow.distinctive is empty: say what is particular to this case, that another build with the same workflow would not have")
    elif not (name or steps or distinctive):
        return None
    return {"name": name, "steps": steps, "distinctive": distinctive}


def _line_count(build: Build, rel: str) -> Optional[int]:
    try:
        return build.read_code(rel).count("\n") + 1
    except (FileNotFoundError, IsADirectoryError, KBError):
        return None


def _resolve_file(build: Optional[Build], rel: str) -> Tuple[str, Optional[int]]:
    rel = (rel or "").strip().lstrip("./")
    if build is None:
        return rel, None
    for cand in (rel, f"code/{rel}"):
        n = _line_count(build, cand) if cand else None
        if n is not None:
            return cand, n
    return rel, None


def _norm_lines(lines: List[str]) -> str:
    return "\n".join(l.strip() for l in lines)


def span_anchor(lines: List[str]) -> str:
    """A fingerprint of a span's code, blind to indentation, so a card notices when
    the code it points at has changed."""
    return hashlib.sha1(_norm_lines(lines).encode("utf-8")).hexdigest()[:12]


def _first_line(lines: List[str]) -> str:
    return next((l.strip() for l in lines if l.strip()), "")[:120]


def _relocate(file_lines: List[str], first: str, length: int, anchor: str) -> Optional[int]:
    """Where a span has moved to, if its code is still there unchanged: same first
    line, same length, same fingerprint."""
    if not first:
        return None
    for i, line in enumerate(file_lines):
        if line.strip()[:120] == first and span_anchor(file_lines[i : i + length]) == anchor:
            return i + 1
    return None


def check_spans(raw: Any, build: Optional[Build], chk: CardCheck, where: str, symbols: Optional[list]) -> List[Dict[str, Any]]:
    """A part's code: one or more spans, each a file and a line range (or a symbol from
    the build's symbol index), with the role it plays. Each span is fingerprinted so
    later checks can tell when the code moved or changed."""
    from .symbols import find

    if not isinstance(raw, list):
        chk.error(f"{where}: spans must be a list")
        return []
    out: List[Dict[str, Any]] = []
    for k, rs in enumerate(raw):
        w = f"{where} span {k + 1}"
        if not isinstance(rs, dict):
            chk.error(f"{w} must be an object with file and start and end (or symbol)")
            continue
        rel, n = _resolve_file(build, str(rs.get("file") or ""))
        sym_name = _text(rs.get("symbol"))
        start, end = rs.get("start"), rs.get("end")
        sym = None
        if sym_name and symbols is not None:
            hint = _text(rs.get("role")).lower() or None
            sym = find(symbols, sym_name, rel or None, hint) or (find(symbols, sym_name, None, hint) if not rel else None)
            if sym is None and start not in (None, "") and end not in (None, ""):
                # The span already has its lines: the symbol may only have been renamed
                # (section.box became section.box:1); find it by where it starts.
                at = [x for x in symbols if x.start == int(start) and (not rel or x.file == rel)
                      and x.name.split(":")[0] == sym_name.split(":")[0]]
                sym = at[0] if at else None
                if sym is None:
                    chk.warn(f"{w}: no symbol {sym_name!r} any more; the span keeps its lines")
                    sym_name = ""
            if sym is None and sym_name:
                chk.error(f"{w}: no symbol {sym_name!r} in {rel or 'the build'}; `astaui symbols {build.id if build else '<id>'}` lists them")
                continue
            if not rel or n is None:
                rel, n = _resolve_file(build, sym.file)
            if start in (None, "") or end in (None, ""):
                start, end = sym.start, sym.end
        if not rel:
            chk.error(f"{w} names no file")
            continue
        try:
            start, end = int(start), int(end)
        except (TypeError, ValueError):
            chk.error(f"{w} needs whole-number start and end lines, or a symbol")
            continue
        if build is not None and n is None:
            chk.error(f"{w}: {rel!r} is not in the build's folder")
            continue
        if start < 1 or end < start or (n is not None and end > n):
            limit = f" (the file has {n} lines)" if n else ""
            chk.error(f"{w}: lines {start}-{end} are not a range inside {rel}{limit}")
            continue
        role = _text(rs.get("role")).lower()
        if not role:
            role = ROLE_OF_KIND.get(sym.kind, "other") if sym else "other"
        if role not in ROLES:
            chk.error(f"{w}: role {role!r} is not one of {', '.join(ROLES)}")
            continue
        span: Dict[str, Any] = {"file": rel, "start": start, "end": end, "role": role}
        if sym_name:
            span["symbol"] = sym.name if sym else sym_name
        if build is not None:
            file_lines = build.read_code(rel).splitlines()
            lines = file_lines[start - 1 : end]
            anchor = span_anchor(lines)
            old = _text(rs.get("anchor"))
            if old and old != anchor:
                moved = _relocate(file_lines, _text(rs.get("first")), end - start + 1, old)
                if moved:
                    shift = moved - start
                    start, end = moved, end + shift
                    span.update(start=start, end=end)
                    lines = file_lines[start - 1 : end]
                    anchor = old
                    chk.warn(f"{w}: the code moved to lines {start}-{end}; `astaui card refresh` saves the new place")
                else:
                    chk.error(f"{w}: the code at {rel}:{start}-{end} is no longer what the card described; describe this part again")
                    continue
            span["anchor"] = anchor
            span["first"] = _first_line(lines)
        if end - start > 300:
            chk.warn(f"{w} is {end - start + 1} lines; a span that long is probably several")
        out.append(span)
    code_spans = [sp for sp in out if sp["role"] != "style"]
    if len(code_spans) > 8:
        chk.warn(f"{where} has {len(code_spans)} markup, script and data spans; a part that needs that many is probably several parts")
    return out


def part_spans(part: Dict[str, Any]) -> List[Dict[str, Any]]:
    """A part's spans, from the current format or the older single `code` range."""
    if part.get("spans"):
        return part["spans"]
    code = part.get("code")
    if isinstance(code, dict) and code.get("file"):
        return [dict(code, role=code.get("role", "logic"))]
    return []


def check_parts(ont: Ontology, raw_parts: Any, build: Optional[Build], chk: CardCheck) -> List[Dict[str, Any]]:
    from .symbols import index_build

    symbols = index_build(build) if build is not None else None
    if raw_parts is None:
        chk.warn("no parts: name the views and components inside the app, with the lines that make each one")
        return []
    if not isinstance(raw_parts, list):
        chk.error("parts must be a list")
        return []
    parts: List[Dict[str, Any]] = []
    seen: Dict[str, int] = {}
    for i, rp in enumerate(raw_parts):
        where = f"parts[{i}]"
        if not isinstance(rp, dict):
            chk.error(f"{where} must be an object")
            continue
        title = _text(rp.get("title"))
        pid = slug(_text(rp.get("id")) or title, f"part-{i + 1}")
        if pid in seen:
            seen[pid] += 1
            pid = f"{pid}-{seen[pid]}"
        else:
            seen[pid] = 1
        level = _text(rp.get("level")).lower() or "view"
        if level not in LEVELS:
            chk.error(f"{where}.level is {level!r}; use one of {', '.join(LEVELS)}")
        part: Dict[str, Any] = {
            "id": pid,
            "level": level,
            "parent": _text(rp.get("parent")) or None,
            "title": title,
            "summary": _text(rp.get("summary")),
        }
        if not title:
            chk.error(f"{where}.title is missing")
        if not part["summary"]:
            chk.warn(f"{where} ({pid}) has no summary")
        for lst in PART_LISTS:
            words, proposed = ont.normalize("mechanism", lst, rp.get(lst))
            part[lst] = words
            for p in proposed:
                chk.proposed.append({"facet": "mechanism", "list": lst, "term": p})
        raw_spans = rp.get("spans")
        if raw_spans is None and rp.get("code") is not None:
            raw_spans = rp["code"] if isinstance(rp["code"], list) else [rp["code"]]
        spans = check_spans(raw_spans or [], build, chk, f"{where} ({pid})", symbols)
        if spans:
            part["spans"] = spans
        else:
            chk.warn(f"{where} ({pid}) does not point at its code: give it spans (markup, style, logic), by symbol or by lines")
        parts.append(part)
    ids = {p["id"] for p in parts}
    for p in parts:
        if p["parent"] is not None:
            parent = slug(p["parent"])
            if parent not in ids:
                chk.error(f"part {p['id']} names parent {p['parent']!r}, which is not one of the parts")
            elif parent == p["id"]:
                chk.error(f"part {p['id']} is its own parent")
            p["parent"] = parent
    return parts


def check_card(ont: Ontology, raw: Dict[str, Any], build: Optional[Build], made: Optional[Dict[str, Any]] = None) -> Tuple[Dict[str, Any], CardCheck]:
    """Clean and check a card. ``raw`` may be a whole card or just the app's facets."""
    chk = CardCheck()
    if not isinstance(raw, dict):
        chk.error("a card must be a JSON object")
        return {}, chk
    app_raw = raw.get("app") if isinstance(raw.get("app"), dict) else raw
    app = check_app(ont, app_raw, chk)
    parts = check_parts(ont, raw.get("parts", app_raw.get("parts")), build, chk)
    workflow = check_workflow(app_raw.get("workflow", raw.get("workflow")), chk, "app", {p["id"] for p in parts})
    if workflow is not None:
        app["workflow"] = workflow
    card: Dict[str, Any] = {
        "schema": SCHEMA,
        "id": build.id if build else _text(raw.get("id")),
        "ontology": ont.version,
        "made": made or raw.get("made") or {"by": "unknown"},
        "app": app,
        "parts": parts,
    }
    card["made"].setdefault("at", datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"))
    if chk.proposed:
        uniq = []
        for p in chk.proposed:
            if p not in uniq:
                uniq.append(p)
        card["proposed"] = uniq
    return card, chk


def check_query(ont: Ontology, raw: Dict[str, Any]) -> Tuple[Dict[str, Any], CardCheck]:
    """A query card: a request, and whichever facets could be inferred from it."""
    chk = CardCheck()
    if isinstance(raw, str):
        raw = {"request": raw}
    request = _text(raw.get("request"))
    app_raw = raw.get("app") if isinstance(raw.get("app"), dict) else raw
    q = check_app(ont, app_raw, chk, where="query", query=True)
    q["request"] = request or _text(app_raw.get("request"))
    workflow = check_workflow(app_raw.get("workflow"), chk, "query", query=True)
    if workflow is not None:
        q["workflow"] = workflow
    if not q["request"] and not any(f in q for f in FACETS) and not q.get("summary") and not q.get("workflow"):
        chk.error("a query needs a request or at least one facet")
    return q, chk


# -- text for embedding ---------------------------------------------------------

def _join(words: List[str]) -> str:
    return ", ".join(words)


def facet_text(app: Dict[str, Any], facet: str) -> str:
    """The words a facet is embedded as. Empty when the facet says nothing."""
    if facet == "summary":
        bits = [app.get("title", ""), app.get("summary", "")]
        return ". ".join(b for b in bits if b).strip()
    f = app.get(facet)
    if not isinstance(f, dict):
        return ""
    bits: List[str] = []
    if f.get("text"):
        bits.append(f["text"])
    if facet == "data" and f.get("item"):
        bits.append(f"One item is {f['item']}")
    for lst in LISTS[facet]:
        if f.get(lst):
            label = {"verbs": "Task", "shapes": "Data", "views": "Views", "interactions": "Interactions", "patterns": "Patterns"}.get(lst, "")
            bits.append((f"{label}: " if label else "") + _join(f[lst]))
    return ". ".join(b.rstrip(".") for b in bits if b).strip()


def workflow_text(app: Dict[str, Any]) -> str:
    """The general workflow: its name and its steps in general words, without the
    specifics. Two builds that do the same job in different sciences read alike here."""
    wf = app.get("workflow") or {}
    steps = [s["step"] for s in wf.get("steps") or [] if s.get("step")]
    bits = [wf.get("name", "")] + steps
    return ". ".join(b.rstrip(".") for b in bits if b)


def step_text(step: Dict[str, Any]) -> str:
    return step.get("step", "")


def here_text(step: Dict[str, Any]) -> str:
    """How one step is done in this case, with its general move for context."""
    return ". ".join(b.rstrip(".") for b in (step.get("step", ""), step.get("here", "")) if b)


def specifics_text(app: Dict[str, Any]) -> str:
    """Everything particular to this case: how each step is done, and what is distinctive."""
    wf = app.get("workflow") or {}
    bits = [s.get("here", "") for s in wf.get("steps") or []] + list(wf.get("distinctive") or [])
    return ". ".join(b.rstrip(".") for b in bits if b)


def card_text(app: Dict[str, Any]) -> str:
    """The whole card as one text: the 'describe first, then embed' representation."""
    parts = [facet_text(app, "summary"), workflow_text(app), specifics_text(app)] + [facet_text(app, f) for f in FACETS]
    return "\n".join(p for p in parts if p)


STRUCTURE = ("task", "data", "stage", "mechanism")


def structure_text(app: Dict[str, Any]) -> str:
    """The card's structure with every field word taken out: only the ontology's
    words for task, data, stage and mechanism. Two builds from different sciences
    that work the same way read almost the same here."""
    bits: List[str] = []
    for facet in STRUCTURE:
        f = app.get(facet) or {}
        for lst in LISTS[facet]:
            if f.get(lst):
                bits.append(f"{lst}: {_join(f[lst])}")
    return ". ".join(bits)


def part_text(part: Dict[str, Any]) -> str:
    bits = [part.get("title", ""), part.get("summary", "")]
    for lst in PART_LISTS:
        if part.get(lst):
            bits.append(f"{lst.capitalize()}: {_join(part[lst])}")
    return ". ".join(b.rstrip(".") for b in bits if b)


def tags(app: Dict[str, Any]) -> Dict[str, List[str]]:
    """Every ontology word on the card, by facet, for filters and tag overlap."""
    out: Dict[str, List[str]] = {}
    for facet in FACETS:
        f = app.get(facet) or {}
        words: List[str] = []
        for lst in LISTS[facet]:
            words.extend(f.get(lst) or [])
        if words:
            out[facet] = words
    return out


FILTER_KEYS = {
    "verb": ("task", "verbs"), "task": ("task", "verbs"),
    "shape": ("data", "shapes"), "data": ("data", "shapes"),
    "stage": ("stage", "terms"),
    "view": ("mechanism", "views"), "interaction": ("mechanism", "interactions"), "pattern": ("mechanism", "patterns"),
    "field": ("field", "terms"), "discipline": ("field", "disciplines"),
}


def matches_filter(card: Dict[str, Any], key: str, value: str, ont: Ontology, kind: str = "") -> bool:
    """``key=value`` filters: verb, shape, stage, view, interaction, pattern, field, kind."""
    key = key.strip().lower()
    if key == "kind":
        return kind == value.strip().lower()
    if key not in FILTER_KEYS:
        raise KBError(f"Unknown filter {key!r}; use one of {', '.join(sorted(set(FILTER_KEYS) | {'kind'}))}")
    facet, lst = FILTER_KEYS[key]
    want, _ = ont.canonical(facet, lst, value)
    have = (card.get("app", {}).get(facet) or {}).get(lst) or []
    if facet == "field":
        f = card.get("app", {}).get("field") or {}
        d, _ = ont.canonical("field", "disciplines", value)
        return (want in have or d in (f.get("disciplines") or [])
                or norm_word(value) in norm_word(f.get("text", "")))
    return want in have
