"""Slices: the code for one feature, pulled out of a build so it can be lifted.

A card's part names the spans that make a feature: its markup, its style rules,
its script, its data, across files. A slice is those spans plus what they lean on
elsewhere in the build, found through the symbol index:

- functions and data the script calls or reads, defined outside the spans;
- elements the script reaches for by id;
- style rules for the ids and classes the markup and script use.

Spans that touch or overlap in a file are merged, and the slice is cut at a line
budget: the card's own spans first, then what they depend on, with anything left
out listed by name. Nobody has to read the whole build to take one feature from it.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from .cards import part_spans
from .kb import KB, Build, KBError
from .symbols import Symbol, css_for, index_build, references

ROLE_ORDER = {"markup": 0, "style": 1, "logic": 2, "data": 3, "other": 4}
MAX_DEPS = 14
HUB_CALLS = 4
DEPTH = 2     # how many levels of helpers to follow  # a helper that calls this many other functions is an orchestrator, not a helper
MAX_DEP_LINES = 120
SLICE_LINES = 300


def _inside(sym: Symbol, spans: Sequence[Dict[str, Any]]) -> bool:
    return any(sym.file == s["file"] and s["start"] <= sym.start and sym.end <= s["end"] for s in spans)


def _overlaps(sym: Symbol, spans: Sequence[Dict[str, Any]]) -> bool:
    return any(sym.file == s["file"] and not (sym.end < s["start"] or sym.start > s["end"]) for s in spans)


def dependencies(build: Build, spans: List[Dict[str, Any]], symbols: List[Symbol]):
    """What the spans use from elsewhere in the build, one level deep, and the
    orchestrating functions that were named but left out."""
    texts = []
    for s in spans:
        lines = build.read_code(s["file"]).splitlines()
        texts.append("\n".join(lines[s["start"] - 1 : s["end"]]))
    refs = references("\n".join(texts))
    deps: List[Dict[str, Any]] = []
    skipped: List[str] = []
    seen = set()

    def add(sym: Symbol, role: str, why: str) -> None:
        key = (sym.file, sym.start, sym.end)
        if key in seen or _overlaps(sym, spans):
            return
        seen.add(key)
        deps.append({"file": sym.file, "start": sym.start, "end": sym.end, "role": role, "symbol": sym.name, "why": why})

    functions = {s.name for s in symbols if s.kind in ("function", "class")}

    def text_of(sym: Symbol) -> str:
        lines = build.read_code(sym.file).splitlines()
        return "\n".join(lines[sym.start - 1 : sym.end])

    # Follow calls DEPTH levels down: the part's code, then the helpers it calls,
    # then theirs. A function like render() that calls every view would drag the
    # whole interface in, so it is named as a dependency and its code left out.
    calls, words = set(refs["calls"]), set(refs["words"])
    skipped_names = set()
    for level in range(DEPTH):
        new_calls: set = set()
        for sym in symbols:
            if sym.kind not in ("function", "class") or sym.name not in calls or _inside(sym, spans):
                continue
            if sym.name in skipped_names or any(d.get("symbol") == sym.name for d in deps):
                continue
            more = references(text_of(sym))
            fan = (set(more["calls"]) & functions) - {sym.name}
            if len(fan) >= HUB_CALLS:
                skipped_names.add(sym.name)
                skipped.append(f"{sym.name}() ({sym.file}:{sym.start}-{sym.end}; calls {len(fan)} other functions, so left out)")
                continue
            add(sym, "logic", f"called: {sym.name}()" if level == 0 else f"called by a helper: {sym.name}()")
            new_calls |= set(more["calls"])
            words |= set(more["words"])
        calls = new_calls
        if not calls:
            break
    for sym in symbols:
        if sym.kind == "data" and sym.name in words and not _inside(sym, spans):
            add(sym, "data", f"reads: {sym.name}")
    # The elements and styles a feature needs include those its helpers reach for:
    # a class toggled inside a called function still has to come with the feature.
    ids, classes = set(refs["ids"]), set(refs["classes"])
    for d in [d for d in deps if d["role"] == "logic"]:
        lines = build.read_code(d["file"]).splitlines()
        more = references("\n".join(lines[d["start"] - 1 : d["end"]]))
        ids |= set(more["ids"])
        classes |= set(more["classes"])
    for sym in symbols:
        if sym.kind == "element" and sym.name.startswith("#") and sym.name[1:] in ids and not _inside(sym, spans):
            add(sym, "markup", f"element {sym.name}")
    for sym in css_for(symbols, sorted(ids), sorted(classes)):
        add(sym, "style", f"styles {sym.name}")
    return deps, skipped


def _merge(spans: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge spans that touch or overlap in the same file, keeping every reason."""
    out: List[Dict[str, Any]] = []
    for s in sorted(spans, key=lambda x: (x["file"], x["start"], x["end"])):
        if out and out[-1]["file"] == s["file"] and s["start"] <= out[-1]["end"] + 1:
            last = out[-1]
            last["end"] = max(last["end"], s["end"])
            last["why"] = sorted(set(last["why"]) | set(s["why"]))
            last["role"] = min(last["role"], s["role"], key=lambda r: ROLE_ORDER.get(r, 9))
            if s.get("symbol") and s["symbol"] not in last["symbols"]:
                last["symbols"].append(s["symbol"])
        else:
            out.append({**s, "why": list(s["why"]), "symbols": [s["symbol"]] if s.get("symbol") else []})
    return out


def slice_part(kb: KB, build_id: str, part: Dict[str, Any], deps: bool = True, max_lines: int = SLICE_LINES,
               symbols: Optional[List[Symbol]] = None) -> Dict[str, Any]:
    build = kb.build(build_id)
    own = [dict(s, why=["the card"]) for s in part_spans(part)]
    if not own:
        return {"build": build_id, "part": part.get("id"), "title": part.get("title", ""), "spans": [], "needs": [],
                "lines": 0, "truncated": False}
    symbols = symbols if symbols is not None else index_build(build)
    found_raw, hubs = dependencies(build, own, symbols) if deps else ([], [])
    found = [dict(d, why=[d["why"]]) for d in found_raw]
    small = [d for d in found if d["end"] - d["start"] + 1 <= MAX_DEP_LINES][:MAX_DEPS]
    needs = list(hubs) + [f"{d['symbol']} ({d['file']}:{d['start']}-{d['end']})" for d in found if d not in small]
    chosen = own + small
    merged = _merge(chosen)
    # Card spans first (by role), then dependencies, within the line budget.
    merged.sort(key=lambda s: ("the card" not in s["why"], ROLE_ORDER.get(s["role"], 9), s["file"], s["start"]))
    total, out, truncated = 0, [], False
    for s in merged:
        n = s["end"] - s["start"] + 1
        if total + n > max_lines and "the card" not in s["why"]:
            needs.append(f"{', '.join(s['symbols']) or s['role']} ({s['file']}:{s['start']}-{s['end']})")
            truncated = True
            continue
        lines = build.read_code(s["file"]).splitlines()
        shown_end = s["end"]
        if total + n > max_lines:
            shown_end = s["start"] + max(0, max_lines - total) - 1
            truncated = True
        text = "\n".join(lines[s["start"] - 1 : max(shown_end, s["start"] - 1)])
        out.append({**s, "path": str((build.path / s["file"]).relative_to(kb.root)), "text": text,
                    "shown_end": shown_end})
        total += max(0, shown_end - s["start"] + 1)
    return {"build": build_id, "part": part.get("id"), "title": part.get("title", ""), "summary": part.get("summary", ""),
            "spans": out, "needs": needs, "lines": total, "truncated": truncated}


def find_part(kb: KB, build_id: str, part_id: str) -> Dict[str, Any]:
    card = kb.card(build_id)
    part = next((p for p in card.get("parts", []) if p["id"] == part_id), None)
    if part is None:
        raise KBError(f"{build_id} has no part {part_id!r}; it has {', '.join(p['id'] for p in card.get('parts', []))}")
    return part


def format_slice(sl: Dict[str, Any], numbers: bool = True, max_lines: Optional[int] = None) -> str:
    out = [f"{sl['title']}  [{sl['build']} / {sl['part']}]"]
    if sl.get("summary"):
        out.append(sl["summary"])
    shown = 0
    for s in sl["spans"]:
        label = ", ".join(s.get("symbols") or []) or ""
        out.append("")
        out.append(f"── {s['path']}:{s['start']}-{s['shown_end']} · {s['role']}" + (f" · {label}" if label else "")
                   + f" · {'; '.join(s['why'])}")
        width = len(str(s["shown_end"]))
        for i, line in enumerate(s["text"].splitlines(), s["start"]):
            if max_lines is not None and shown >= max_lines:
                out.append("   …")
                break
            out.append(f"{str(i).rjust(width)}| {line}" if numbers else line)
            shown += 1
    if sl.get("needs"):
        out.append("")
        out.append("Also uses, not shown: " + "; ".join(sl["needs"]))
    return "\n".join(out) + "\n"
