"""What the console's Check Runs lens reads: one small file per public run, and
an index of them all, made from the computer-use collection's run records.

The lens loads these when it is opened and when an app is picked, so the
console page itself never holds the runs (it is 11 MB already). Each app's file
has what the agent documented (its tree, features and what it could not do),
what it actually did (every browser call in order, the words it wrote before
each, the screens it kept, where it clicked), the replay, the reviewer's
judgement, and what each stage cost.

The owner's verdicts live in the console (kb-ck-marks, one item per app). This
also copies them out beside the records: owner-verdict.json in each run's
folder and verdicts.jsonl in pilot/public.

    python3 -m astaui.checkruns            # write pilot/public/inspect/
    python3 -m astaui.checkruns --verdicts # only copy the verdicts out
"""
from __future__ import annotations

import argparse
import gzip
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

KB = Path(__file__).resolve().parent.parent
PUBLIC = KB / "pilot" / "public"
RUNS = PUBLIC / "runs"
OUT = PUBLIC / "inspect"
CONSOLE = KB.parent / "AstaUI Console.mrbl"
# The path the page asks the drive for, from the drive's root.
DRIVE_PATH = "Ai2/AstaUI/knowledge-base-v0/pilot/public"
VIEWPORT = (1280, 800)
# Calls that change what the page shows: a screen taken before one of these no
# longer shows where a later click landed.
MOVES = {"click", "double_click", "right_click", "type", "press_key", "scroll", "drag", "select_option", "navigate",
         "upload", "select_text", "hover", "resize", "zoom", "navigate_back", "evaluate", "fill_form", "handle_dialog"}


def _json(p: Path) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _lines(p: Path) -> List[Dict[str, Any]]:
    if not p.exists():
        return []
    opener = gzip.open if p.suffix == ".gz" else open
    out = []
    try:
        with opener(p, "rt", encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass
    except OSError:
        pass
    return out


def _short(v: Any, n: int = 140) -> str:
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _args(tool: str, a: Dict[str, Any]) -> str:
    """The call's input in a few words: what was clicked, typed, chosen or opened."""
    if not a:
        return ""
    if tool in ("navigate",):
        return a.get("url", "")
    bits = []
    if a.get("element"):
        bits.append(str(a["element"]))
    if "text" in a:
        bits.append(f"“{_short(a['text'], 90)}”")
    if a.get("values") is not None:
        bits.append(_short(a["values"], 90))
    if a.get("key"):
        bits.append(str(a["key"]))
    if a.get("names"):
        bits.append(_short(a["names"], 90))
    if a.get("dy") or a.get("dx"):
        bits.append(f"by {a.get('dx', 0)}, {a.get('dy', 0)}")
    if a.get("width") and tool == "resize":
        bits.append(f"{a['width']} × {a.get('height', '')}")
    if a.get("ref") and not a.get("element"):
        bits.append(f"ref {a['ref']}")
    if "startRef" in a or "endRef" in a:
        bits.append(f"{a.get('startElement') or a.get('startRef', '')} → {a.get('endElement') or a.get('endRef', '')}")
    if not bits:
        rest = {k: v for k, v in a.items() if k not in ("x", "y")}
        if rest:
            bits.append(_short(rest, 120))
    return " · ".join(bits)


def _said_and_results(log: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Each browser call the agent made, in order, with the words it wrote since
    its last call and a short form of what came back."""
    calls: List[Dict[str, Any]] = []
    by_id: Dict[str, Dict[str, Any]] = {}
    said: List[str] = []
    for e in log:
        msg = e.get("message") or {}
        content = msg.get("content")
        if e.get("type") == "assistant" and isinstance(content, list):
            for b in content:
                if b.get("type") == "text" and b.get("text", "").strip():
                    said.append(b["text"].strip())
                elif b.get("type") == "tool_use" and str(b.get("name", "")).startswith("mcp__browser__"):
                    c = {"tool": b["name"].removeprefix("mcp__browser__browser_"), "said": "\n\n".join(said)}
                    said = []
                    calls.append(c)
                    by_id[b.get("id", "")] = c
        elif e.get("type") == "user" and isinstance(content, list):
            for b in content:
                if b.get("type") != "tool_result" or b.get("tool_use_id") not in by_id:
                    continue
                cc = b.get("content")
                text = cc if isinstance(cc, str) else " ".join(x.get("text", "") for x in (cc or []) if x.get("type") == "text")
                by_id[b["tool_use_id"]]["result"] = text
    if said and calls:
        calls[-1]["after"] = "\n\n".join(said)
    elif said:
        calls.append({"tool": "", "said": "\n\n".join(said)})
    return calls


def _result(tool: str, text: str) -> Dict[str, Any]:
    """What is worth showing of a call's answer: a size after a resize, an error,
    events (dialogs, downloads), a short reply. Never a page snapshot."""
    out: Dict[str, Any] = {}
    if not text:
        return out
    try:
        j = json.loads(text)
    except ValueError:
        j = None
    if isinstance(j, dict):
        if tool == "resize" and j.get("width"):
            out["vp"] = [j["width"], j.get("height")]
        if j.get("error"):
            out["err"] = _short(j["error"], 300)
        if j.get("events"):
            out["ev"] = _short(j["events"], 300)
        if tool not in ("snapshot", "take_screenshot") and not out:
            rest = {k: v for k, v in j.items() if k not in ("url", "title", "ok", "saved", "snapshot")}
            if rest:
                out["res"] = _short(rest, 220)
    elif tool not in ("snapshot", "take_screenshot"):
        t = text.strip()
        if t.lower().startswith("error") or "timeout" in t.lower()[:80]:
            out["err"] = _short(t, 300)
        elif t:
            out["res"] = _short(t, 220)
    return out


def _steps(run: Path, trace_name: str, log_name: str, shots: str) -> Dict[str, Any]:
    """Every browser call of one session (the exploration or the replay)."""
    trace = _lines(run / trace_name)
    calls = _said_and_results(_lines(run / log_name))
    browser = [c for c in calls if c["tool"]]
    # The log and the trace list the same calls in the same order, except that
    # a call refused before it reached the browser (a tool that does not exist,
    # bad input) is in the log alone: its words go with the next call that ran.
    pairs: List[Optional[Dict[str, Any]]] = []
    j = 0
    for t in trace:
        want = t.get("tool", "").removeprefix("browser_")
        k = j
        while k < len(browser) and browser[k]["tool"] != want:
            k += 1
        if k == len(browser):
            pairs.append(None)
            continue
        c = dict(browser[k])
        skipped = browser[j:k]
        if skipped:
            c["said"] = "\n\n".join([x["said"] for x in skipped if x.get("said")] + [c["said"]] if c.get("said") else [x["said"] for x in skipped if x.get("said")])
            c["refused"] = [f'{x["tool"]}: {_short(x.get("result", ""), 160)}' for x in skipped]
        pairs.append(c)
        j = k + 1
    paired = sum(1 for c in pairs if c) / len(trace) if trace else 0
    kept = {p.name for p in (run / shots).glob("*.webp")} if (run / shots).is_dir() else set()
    t0 = None
    vp = list(VIEWPORT)
    last_url = None
    last_shot: Optional[int] = None  # index into steps of the screen still showing
    steps: List[Dict[str, Any]] = []
    for i, t in enumerate(trace):
        tool = t.get("tool", "").removeprefix("browser_")
        a = t.get("input") or {}
        try:
            when = datetime.fromisoformat(t["t"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            when = None
        t0 = t0 or when
        s: Dict[str, Any] = {"n": t.get("step", i + 1), "tool": tool}
        if when and t0:
            s["s"] = round((when - t0).total_seconds(), 1)
        words = _args(tool, a)
        if words:
            s["a"] = words
        if t.get("url") and t["url"] != last_url:
            s["url"] = t["url"]
            last_url = t["url"]
        if t.get("error"):
            s["err"] = _short(t["error"], 300)
        if t.get("events"):
            s["ev"] = _short(t["events"], 300)
        c = pairs[i]
        if c:
            if c.get("said"):
                s["said"] = c["said"]
            if c.get("refused"):
                s["refused"] = c["refused"]
            if c.get("after"):
                s["after"] = c["after"]
            r = _result(tool, c.get("result", ""))
            if r.get("vp"):
                vp = [int(r["vp"][0]), int(r["vp"][1] or vp[1])]
            for k in ("err", "ev", "res"):
                if r.get(k) and k not in s:
                    s[k] = r[k]
        elif tool == "resize" and a.get("width"):
            vp = [int(a["width"]), int(a.get("height") or vp[1])]
        if "x" in a and "y" in a:
            s["at"] = [a["x"], a["y"], vp[0], vp[1]]
            if last_shot is not None:
                s["on"] = steps[last_shot]["n"]
        shot = t.get("screen")
        if shot:
            stem = Path(shot).stem
            s["shot"] = stem
            if f"{stem}.webp" in kept:
                s["kept"] = f"{shots}/{stem}.webp"
                s["vp"] = vp[:]
            last_shot = len(steps)
        elif tool in MOVES:
            last_shot = None
        steps.append(s)
    # A screen that came straight after a click shows what the click did.
    for j, s in enumerate(steps):
        if "at" in s and j + 1 < len(steps) and steps[j + 1].get("shot"):
            s["then"] = steps[j + 1]["n"]
    # Words the agent wrote after its last call (its closing account).
    closing = next((c.get("after") for c in reversed(browser) if c.get("after")), None)
    if closing and (closing.lstrip().startswith(("{", "```")) or "\"interface\"" in closing):
        closing = None
    return {"steps": steps, "paired": round(paired, 3), "closing": closing}


def _tools(steps: List[Dict[str, Any]]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for s in steps:
        out[s["tool"]] = out.get(s["tool"], 0) + 1
    return out


def _latest(slug_dir: Path) -> Optional[Path]:
    runs = sorted(p for p in slug_dir.iterdir() if p.is_dir() and re.fullmatch(r"\d{8}-\d{6}", p.name))
    return runs[-1] if runs else None


def _results() -> Dict[str, Dict[str, Any]]:
    last: Dict[str, Dict[str, Any]] = {}
    for r in _lines(PUBLIC / "results.jsonl"):
        if r.get("slug"):
            last[r["slug"]] = r
    return last


def _filed(slug: str) -> bool:
    return (KB / "kb" / "builds" / slug / "build.json").exists()


STATUS = {"explored": "explored", "not usable": "unusable", "inferred from code": "code", "refused": "refused", "failed": "failed"}


def one(slug: str, row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Everything the lens shows for one app, and its row in the index."""
    run = RUNS / slug / row["run"] if row.get("run") else None
    if not run or not run.is_dir():
        run = _latest(RUNS / slug) if (RUNS / slug).is_dir() else None
    if not run:
        return None
    meta = _json(run / "meta.json") or {}
    tree = _json(run / "tree.json") or {}
    review = _json(run / "review.json") or {}
    check = _json(run / "check.json") or {}
    plan = _json(run / "plan.json") or {}
    stages = meta.get("stages") or {}
    outcome = meta.get("outcome") or row.get("outcome") or ("running" if not meta.get("outcome") else "")
    explore = _steps(run, "trace.jsonl", "explore.jsonl.gz", "screens")
    replay = _steps(run, "check/trace.jsonl", "check/replay.jsonl.gz", "check/screens")
    base = f"{DRIVE_PATH}/runs/{slug}/{run.name}"
    iface = tree.get("interface") or {}
    cost = meta.get("cost") if meta.get("cost") is not None else row.get("cost")
    if cost is None:
        cost = round(sum((s or {}).get("cost") or 0 for s in stages.values()), 2)
    failed = row.get("failed") or meta.get("failed")
    if isinstance(failed, dict):
        failed = failed.get("reason") or failed.get("stage") or json.dumps(failed)
    detail = {
        "slug": slug, "run": run.name, "base": base,
        "repo": meta.get("repo") or row.get("repo"), "commit": meta.get("commit"), "subdir": meta.get("subdir"),
        "framework": meta.get("framework") or row.get("framework"), "field": meta.get("field") or row.get("field"),
        "model": meta.get("model"), "outcome": outcome, "failed": failed,
        "cost": cost, "minutes": meta.get("minutes") or row.get("minutes"),
        "stages": {k: {kk: vv for kk, vv in (v or {}).items() if not isinstance(vv, (list, dict)) or kk in ("needs",)}
                   for k, v in stages.items()},
        "plan": {k: plan.get(k) for k in ("goals", "workflow_stated", "data", "needs", "notes") if plan.get(k)},
        "tree": tree, "fixed": (run / "tree.fixed.json").exists(),
        "review": review, "check": check,
        "explore": explore, "replay": replay,
    }
    cov = (review.get("coverage") or {}).get("score")
    row_out = {
        "slug": slug, "run": run.name, "title": iface.get("title") or slug,
        "field": detail["field"], "framework": detail["framework"], "repo": detail["repo"],
        "status": STATUS.get(outcome, outcome or "unknown"),
        "file": review.get("file"), "point": review.get("point"), "cov": cov,
        "depth": (review.get("depth") or {}).get("verdict"), "feat": (review.get("features") or {}).get("score"),
        "words": (review.get("words") or {}).get("score"),
        "cost": cost, "minutes": detail["minutes"],
        "phases": (stages.get("explore") or stages.get("codeonly") or {}).get("phases"),
        "tasks": (stages.get("explore") or stages.get("codeonly") or {}).get("tasks"),
        "features": (stages.get("explore") or stages.get("codeonly") or {}).get("features"),
        "replayed": row.get("replayed") or (stages.get("replay") or {}).get("tasks_replayed"),
        "steps": len(explore["steps"]), "clicks": sum(1 for s in explore["steps"] if s["tool"] in ("click", "double_click", "right_click")),
        "errors": sum(1 for s in explore["steps"] if s.get("err")),
        "kept": sum(1 for s in explore["steps"] if s.get("kept")),
        "filed": _filed(slug), "when": run.name,
    }
    detail["row"] = row_out
    return detail


def build(out: Path = OUT) -> Dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    (out / "apps").mkdir(exist_ok=True)
    results = _results()
    slugs = sorted(set(results) | {p.name for p in RUNS.iterdir() if p.is_dir()} if RUNS.is_dir() else set(results))
    rows = []
    for slug in slugs:
        d = one(slug, results.get(slug, {}))
        if not d:
            continue
        rows.append(d["row"])
        text = json.dumps(d, ensure_ascii=False, separators=(",", ":"))
        p = out / "apps" / f"{slug}.json"
        if not p.exists() or p.read_text(encoding="utf-8") != text:
            p.write_text(text, encoding="utf-8")
    index = {"made": datetime.now(timezone.utc).isoformat(timespec="seconds"), "apps": rows}
    tmp = out / ".index.json.part"
    tmp.write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(out / "index.json")
    return {"apps": len(rows), "out": str(out)}


MARK = re.compile(r'<li\b[^>]*data-marble-id="kb-ck-m-([a-z0-9-]+)"[^>]*>(.*?)</li>', re.S)


def verdicts(console: Path = CONSOLE) -> List[Dict[str, Any]]:
    """The owner's verdicts as the console holds them."""
    src = console.read_text(encoding="utf-8")
    at = src.find('data-marble-id="kb-ck-marks"')
    if at < 0:
        return []
    end = src.find("</ul>", at)
    out = []
    for m in MARK.finditer(src, at, end if end > 0 else len(src)):
        tag = m.group(0)[: m.group(0).index(">") + 1]
        attr = lambda n: (re.search(rf'\b{n}="([^"]*)"', tag) or [None, None])[1]
        note = re.sub(r"<[^>]+>", "", m.group(2))
        out.append({"slug": m.group(1), "run": attr("data-run"), "verdict": attr("data-v"),
                    "at": attr("data-at"), "note": html.unescape(note).strip()})
    return out


def copy_verdicts(console: Path = CONSOLE) -> int:
    marks = verdicts(console)
    lines = "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in marks)
    (PUBLIC / "verdicts.jsonl").write_text(lines, encoding="utf-8")
    for m in marks:
        run = RUNS / m["slug"] / (m["run"] or "")
        if m["run"] and run.is_dir():
            (run / "owner-verdict.json").write_text(json.dumps(m, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return len(marks)


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(prog="python3 -m astaui.checkruns", description=__doc__.split("\n\n")[0])
    ap.add_argument("--verdicts", action="store_true", help="only copy the owner's verdicts out of the console")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)
    said = {}
    if not a.verdicts:
        said.update(build(Path(a.out)))
    if CONSOLE.exists():
        said["verdicts"] = copy_verdicts()
    print(json.dumps(said))


if __name__ == "__main__":
    main()
