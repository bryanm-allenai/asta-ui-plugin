"""How well used each build is: how often it came back from a search, how often
an agent opened it, whether the agents and scientists who took from it said it
helped, and, for a build from a public repository, its GitHub stars.

Two places hold it:

- ``kb/.usage/usage.jsonl`` is this computer's own log (usage.py writes it, never
  committed): every search with what came back, every ``astaui show`` or
  ``astaui slice`` of a build (a *fetch*), every ``astaui feedback``.
- ``kb/stats.json`` is the shared tally, committed and shipped with the plugin.
  ``astaui stats --write`` folds this computer's log into it and records how far
  it got (``merged``: the log's own id and the time of its last row), so the
  same row is never counted twice. ``astaui stats --stars`` asks GitHub for the
  stars of each build from a public repository and keeps them there too.

What a skill reads is ``standing(kb, build_id)``: the tally plus whatever this
computer logged since it was last folded in, with one line that says, in plain
words, how vetted the build is. A build from a public repository is judged by
its stars; one a scientist sent in by how often it was fetched and approved
(an approval is ``astaui feedback … --helped yes``); an example made for AstaUI
by nobody, and says so.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .kb import KB, KBError, read_json, read_jsonl, write_json

COUNTS = ("retrieved", "fetched", "used", "approved", "unhelpful")
# Stars older than this are asked for again by `astaui stats --stars`.
STARS_MAX_AGE_DAYS = 7
# Where a build stands, by the signal it is judged on.
# Most public builds have no stars at all (median 0, 90th percentile 5 on
# 2026-11-19); 100 or more puts one among the top dozen.
STAR_LEVELS = ((100, "high"), (10, "some"))
APPROVAL_LEVELS = ((3, "high"), (1, "some"))
# The level in words, for a hover line or a card.
LEVEL_WORDS = {"high": "well vetted", "some": "some vetting", "low": "barely vetted"}
GITHUB_REPO = re.compile(r"^https?://github\.com/([^/\s]+)/([^/\s#?]+?)(?:\.git)?/?$")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def path(kb: KB) -> Path:
    return kb.root / "stats.json"


def _empty() -> Dict[str, Any]:
    return {"about": "How well used each build is. `astaui stats` explains; `astaui stats --write` folds a computer's usage log in.",
            "updated": None, "merged": {}, "builds": {}}


def load(kb: KB) -> Dict[str, Any]:
    p = path(kb)
    if not p.is_file():
        return _empty()
    try:
        data = read_json(p)
    except KBError:
        return _empty()
    base = _empty()
    base.update(data if isinstance(data, dict) else {})
    return base


def log_id(kb: KB) -> str:
    """This computer's usage log's own id, made the first time it is asked for."""
    p = kb.usage_dir / "id"
    try:
        got = p.read_text(encoding="utf-8").strip()
        if got:
            return got
    except OSError:
        pass
    got = uuid.uuid4().hex[:12]
    try:
        kb.usage_dir.mkdir(parents=True, exist_ok=True)
        p.write_text(got + "\n", encoding="utf-8")
    except OSError:
        pass
    return got


# -- the log ------------------------------------------------------------------

def log_fetch(kb: KB, build_id: str, how: str) -> None:
    """An agent opened a build: its record and code (`show`) or one of its parts (`slice`)."""
    if os.environ.get("ASTAUI_NO_LOG"):
        return
    from .usage import _path

    rows = read_jsonl(_path(kb)) if _path(kb).exists() else []
    last = next((r for r in reversed(rows) if r.get("event") == "search"), None)
    row = {"event": "fetch", "at": _now(), "build": build_id, "how": how}
    # Opened for the search that just found it, when it is one of that search's builds.
    if last and build_id in {r[0] for r in last.get("results") or []} | {last.get("far")}:
        row["search"] = last.get("id")
    try:
        kb.usage_dir.mkdir(parents=True, exist_ok=True)
        with _path(kb).open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass


def tally(rows: Iterable[Dict[str, Any]], after: Optional[str] = None) -> Tuple[Dict[str, Dict[str, Any]], Optional[str]]:
    """Counts per build from usage rows later than ``after``, and the time of the
    last row read. A build opened several times for one search (or, with no
    search, in one hour) is one fetch; feedback on one build for one search
    counts once, as its latest answer."""
    out: Dict[str, Dict[str, Any]] = {}
    fetched = set()
    answers: Dict[Tuple[str, str], Dict[str, Any]] = {}
    last = None

    def one(b: str) -> Dict[str, Any]:
        return out.setdefault(b, {k: 0 for k in COUNTS})

    for r in rows:
        at = r.get("at") or ""
        if after and at <= after:
            continue
        last = max(last or at, at)
        ev = r.get("event")
        if ev == "search":
            for b in {x[0] for x in r.get("results") or []} | ({r["far"]} if r.get("far") else set()):
                one(b)["retrieved"] += 1
                one(b)["last"] = max(one(b).get("last") or "", at[:10])
        elif ev == "fetch" and r.get("build"):
            key = (r["build"], r.get("search") or at[:13])
            if key not in fetched:
                fetched.add(key)
                one(r["build"])["fetched"] += 1
        elif ev == "feedback" and r.get("build"):
            answers[(r.get("search") or "", r["build"])] = r
    for (_, b), r in answers.items():
        c = one(b)
        c["used"] += 1 if r.get("used") else 0
        c["approved"] += 1 if r.get("helped") is True else 0
        c["unhelpful"] += 1 if r.get("helped") is False else 0
    return out, last


def _add(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    c = dict(a)
    for k in COUNTS:
        c[k] = int(a.get(k) or 0) + int(b.get(k) or 0)
    if b.get("last"):
        c["last"] = max(a.get("last") or "", b["last"])
    return c


def _unmerged(kb: KB, stats: Dict[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], Optional[str], str]:
    from .usage import _path

    lid = log_id(kb)
    rows = read_jsonl(_path(kb)) if _path(kb).exists() else []
    counts, last = tally(rows, after=(stats.get("merged") or {}).get(lid))
    return counts, last, lid


def write(kb: KB) -> Dict[str, Any]:
    """Fold this computer's log into kb/stats.json."""
    stats = load(kb)
    counts, last, lid = _unmerged(kb, stats)
    for b, c in counts.items():
        stats["builds"][b] = _add(stats["builds"].get(b) or {}, c)
    if last:
        stats["merged"][lid] = last
    stats["updated"] = _now()
    stats["builds"] = dict(sorted(stats["builds"].items()))
    write_json(path(kb), stats)
    return {"builds": len(counts), "through": last, "log": lid}


# -- GitHub stars -------------------------------------------------------------

def github_repo(meta: Dict[str, Any]) -> Optional[str]:
    m = GITHUB_REPO.match(((meta.get("source") or {}).get("repo") or "").strip())
    return f"{m.group(1)}/{m.group(2)}" if m else None


def _token() -> Optional[str]:
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if tok:
        return tok
    if shutil.which("gh"):
        try:
            r = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=10)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    return None


def _stars(repo: str, token: Optional[str]) -> Tuple[Optional[int], str]:
    url = os.environ.get("ASTAUI_GITHUB_API", "https://api.github.com").rstrip("/") + f"/repos/{repo}"
    headers = {"User-Agent": "astaui", "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as r:
            return int(json.load(r).get("stargazers_count") or 0), ""
    except urllib.error.HTTPError as e:
        return None, "not found" if e.code == 404 else f"HTTP {e.code}"
    except (urllib.error.URLError, OSError, ValueError) as e:
        return None, str(getattr(e, "reason", e))


def update_stars(kb: KB, ids: Optional[List[str]] = None, max_age_days: int = STARS_MAX_AGE_DAYS) -> Dict[str, Any]:
    """Ask GitHub for the stars of each build from a public repository whose
    count is missing or older than ``max_age_days`` (0: all of them), and keep
    them in kb/stats.json. Returns what was asked and what failed."""
    stats = load(kb)
    today = _now()[:10]
    todo: List[Tuple[str, str]] = []
    for bid in ids or kb.build_ids():
        try:
            meta = kb.build(bid).meta
        except KBError:
            continue
        repo = github_repo(meta)
        if not repo:
            continue
        have = stats["builds"].get(bid) or {}
        at = have.get("stars_at")
        if at and max_age_days and (datetime.fromisoformat(today) - datetime.fromisoformat(at)).days < max_age_days:
            continue
        todo.append((bid, repo))
    token = _token()
    with ThreadPoolExecutor(max_workers=8) as pool:
        got = list(pool.map(lambda t: (t[0], t[1]) + _stars(t[1], token), todo))
    failed = []
    for bid, repo, n, err in got:
        if n is None:
            failed.append({"build": bid, "repo": repo, "why": err})
            continue
        row = stats["builds"].setdefault(bid, {})
        row["stars"], row["stars_at"] = n, today
    if got:
        stats["updated"] = _now()
        stats["builds"] = dict(sorted(stats["builds"].items()))
        try:
            write_json(path(kb), stats)
        except OSError:
            pass
    return {"asked": len(todo), "failed": failed, "token": bool(token)}


# -- what a skill reads ---------------------------------------------------------

def _level(n: int, levels) -> str:
    return next((name for least, name in levels if n >= least), "low")


def _times(n: int, one: str = "time") -> str:
    return f"{n:,} {one}" + ("" if n == 1 else "s")


def standing(kb: KB, build_id: str, stats: Optional[Dict[str, Any]] = None,
             local: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Where one build stands: its counts, the signal it is judged on, how high
    that is, and a line saying it in words."""
    if stats is None:
        stats = load(kb)
    if local is None:
        local = _unmerged(kb, stats)[0]
    row = _add(stats["builds"].get(build_id) or {}, local.get(build_id) or {})
    meta = kb.build(build_id).meta
    prov = meta.get("provenance") or {}
    counts = {k: row.get(k, 0) for k in COUNTS}
    out: Dict[str, Any] = {"build": build_id, **counts}
    if row.get("last"):
        out["last"] = row["last"]
    repo = github_repo(meta)
    in_astaui = f"fetched {_times(counts['fetched'])} in AstaUI, approved by {counts['approved']:,}"
    if prov.get("kind") == "public" and repo:
        out.update(signal="github", repo=f"https://github.com/{repo}")
        if row.get("stars") is not None:
            n = int(row["stars"])
            out.update(stars=n, stars_at=row.get("stars_at"), level=_level(n, STAR_LEVELS),
                       line=f"{n:,} GitHub star" + ("" if n == 1 else "s"))
        else:
            out.update(stars=None, level="unknown", line="GitHub stars not checked yet")
        out["also"] = in_astaui[0].upper() + in_astaui[1:]
    elif prov.get("kind") == "seed" or prov.get("consent") == "synthetic":
        out.update(signal="example", level="example",
                   line="An example made for AstaUI, not a scientist's own tool")
    else:
        out.update(signal="astaui", level=_level(counts["approved"], APPROVAL_LEVELS))
        if not counts["fetched"] and not counts["approved"]:
            out["line"] = "New to AstaUI: nobody has fetched it yet"
        else:
            out["line"] = in_astaui[0].upper() + in_astaui[1:]
    if out.get("level") in LEVEL_WORDS:
        out["vetted"] = LEVEL_WORDS[out["level"]]
    return out


def standings(kb: KB, ids: List[str]) -> Dict[str, Dict[str, Any]]:
    stats = load(kb)
    local = _unmerged(kb, stats)[0]
    out = {}
    for b in ids:
        try:
            out[b] = standing(kb, b, stats, local)
        except KBError:
            continue
    return out
