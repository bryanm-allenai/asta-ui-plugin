"""Filing a build: copying what a scientist made into the knowledge base.

A build is the prompts, the code and (if there is one) a screenshot. Prompts can
come from a text file, from the command line, or straight from a Claude Code
session log, which keeps every prompt typed in a project.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .kb import KB, KBError, check_id, write_json, write_jsonl

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "env", "dist", "build", ".next", ".cache",
             ".idea", ".vscode", "coverage", ".pytest_cache", ".mypy_cache", "site-packages", "target", ".marble"}
SKIP_FILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "uv.lock", "Cargo.lock", ".DS_Store"}
CODE_EXT = {".html", ".htm", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".vue", ".svelte", ".css", ".scss",
            ".py", ".r", ".jl", ".ipynb", ".json", ".md", ".mrbl", ".toml", ".yaml", ".yml", ".sql", ".sh", ".swift",
            ".kt", ".java", ".go", ".rs", ".rb", ".php", ".txt", ".csv", ".tsv", ".svg"}
MAX_FILE = 1_500_000
MAX_TOTAL = 6_000_000
SOURCES = ("prompt log", "repo", "skill file", "Claude artifact", "Marble app")
KINDS = ("seed", "study", "contributed", "paper")
CONSENT = ("synthetic", "team", "public")


def read_prompt_file(path: Path) -> List[Dict[str, Any]]:
    """Prompts from a file: JSONL (one {"text": ...} per line) or plain text with a
    blank line between prompts."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".jsonl":
        turns = []
        for line in text.splitlines():
            line = line.strip()
            if line:
                row = json.loads(line)
                turns.append(row if isinstance(row, dict) else {"text": str(row)})
        return turns
    chunks = [c.strip() for c in re.split(r"\n\s*\n", text) if c.strip()]
    return [{"text": c} for c in chunks]


# -- Claude Code sessions ---------------------------------------------------------

def _claude_projects() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")) / "projects"


def _project_slug(path: Path) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", str(path.resolve()))


NOISE = re.compile(r"^\s*(<command-|<local-command-|<system-reminder>|<bash-|Caveat:|\[Request interrupted)")


def _user_text(entry: Dict[str, Any]) -> Optional[str]:
    if entry.get("type") != "user" or entry.get("isMeta") or entry.get("isSidechain"):
        return None
    msg = entry.get("message") or {}
    if msg.get("role") != "user":
        return None
    content = msg.get("content")
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
            return None
        text = "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    else:
        return None
    text = re.sub(r"<system-reminder>.*?</system-reminder>", "", text, flags=re.S).strip()
    if not text or NOISE.match(text):
        return None
    return text


def session_prompts(path: Path) -> List[Dict[str, Any]]:
    """The prompts a person typed in one Claude Code session, in order."""
    turns: List[Dict[str, Any]] = []
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            text = _user_text(entry)
            if text:
                at = (entry.get("timestamp") or "")[:10] or None
                turns.append({"text": text, **({"at": at} if at else {})})
    return turns


def this_session(cwd: Optional[Path] = None) -> Optional[Path]:
    """The log of the Claude Code session running this command, for when the
    interface was built in the same conversation that files it."""
    running = os.environ.get("CLAUDE_CODE_SESSION_ID")
    root = _claude_projects()
    if not running or not root.is_dir():
        return None
    here = root / _project_slug(cwd or Path.cwd()) / f"{running}.jsonl"
    if here.is_file():
        return here
    return next(iter(root.glob(f"*/{running}.jsonl")), None)


def list_sessions(cwd: Optional[Path] = None, limit: int = 15) -> List[Dict[str, Any]]:
    """Recent Claude Code sessions, for the project folder ``cwd`` if given. The
    session running this command is left out: when an agent files a build from
    the folder it was built in, the newest session there is the filing itself."""
    root = _claude_projects()
    if not root.is_dir():
        return []
    dirs = [root / _project_slug(cwd)] if cwd else [d for d in root.iterdir() if d.is_dir()]
    running = os.environ.get("CLAUDE_CODE_SESSION_ID")
    found = []
    for d in dirs:
        if not d.is_dir():
            continue
        for p in d.glob("*.jsonl"):
            if p.stem != running:
                found.append(p)
    found.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    out = []
    for p in found[:limit]:
        turns = session_prompts(p)
        if not turns:
            continue
        out.append({
            "path": str(p),
            "project": p.parent.name,
            "prompts": len(turns),
            "first": turns[0]["text"][:140],
            "modified": date.fromtimestamp(p.stat().st_mtime).isoformat(),
        })
    return out


# -- code -----------------------------------------------------------------------

def _walk(src: Path) -> Iterable[Path]:
    if src.is_file():
        yield src
        return
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(filenames):
            if name in SKIP_FILES or name.startswith("."):
                continue
            yield Path(dirpath) / name


def collect_code(sources: List[Path], dest: Path) -> List[str]:
    """Copy interface code into ``dest``. Skips dependencies, build output and
    anything large or binary; returns what was skipped, in words."""
    skipped: List[str] = []
    total = 0
    dest.mkdir(parents=True, exist_ok=True)
    for src in sources:
        src = src.expanduser().resolve()
        if not src.exists():
            raise KBError(f"{src} does not exist")
        base = src.parent if src.is_file() else src
        for f in _walk(src):
            rel = f.relative_to(base)
            size = f.stat().st_size
            if f.suffix.lower() not in CODE_EXT:
                skipped.append(f"{rel} (not code)")
                continue
            if size > MAX_FILE:
                skipped.append(f"{rel} ({size // 1000} KB, too large)")
                continue
            if total + size > MAX_TOTAL:
                skipped.append(f"{rel} (the build is over {MAX_TOTAL // 1_000_000} MB)")
                continue
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, target)
            total += size
    return skipped


def add_build(
    kb: KB,
    build_id: str,
    title: str,
    prompts: List[Dict[str, Any]],
    code: List[Path],
    screenshot: Optional[Path] = None,
    author: Optional[Dict[str, str]] = None,
    sources: Optional[List[str]] = None,
    kind: str = "contributed",
    consent: str = "team",
    origin: str = "",
    forked_from: Optional[str] = None,
    entry: Optional[str] = None,
    notes: str = "",
    replace: bool = False,
    source: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    check_id(build_id, "build id")
    if kind not in KINDS:
        raise KBError(f"kind must be one of {', '.join(KINDS)}")
    if consent not in CONSENT:
        raise KBError(f"consent must be one of {', '.join(CONSENT)}")
    if not prompts and kind != "paper":
        raise KBError("a build needs its prompts (--prompts FILE, --prompt TEXT or --session LOG)")
    if not code:
        raise KBError("a build needs its code (--code PATH, repeatable)")
    path = kb.builds_dir / build_id
    if path.exists():
        if not replace:
            raise KBError(f"{build_id!r} already exists; pick another id, or pass --replace")
        shutil.rmtree(path)
    path.mkdir(parents=True)
    try:
        skipped = collect_code(code, path / "code")
        files = sorted(str(p.relative_to(path)) for p in (path / "code").rglob("*") if p.is_file())
        if not files:
            raise KBError("none of the --code paths held any code")
        if entry is None:
            html = [f for f in files if f.endswith((".html", ".htm", ".mrbl"))]
            entry = (html or files)[0]
        turns = []
        for i, t in enumerate(prompts, 1):
            row = {"turn": i, "text": t.get("text", "").strip()}
            if t.get("at"):
                row["at"] = t["at"]
            turns.append(row)
        write_jsonl(path / "prompts.jsonl", turns)
        if screenshot:
            shot = Path(screenshot).expanduser()
            if not shot.is_file():
                raise KBError(f"{shot} does not exist")
            shutil.copy2(shot, path / ("screenshot" + shot.suffix.lower()))
        meta = {
            "id": build_id,
            "title": title,
            "author": author or {"name": "anonymous"},
            "created": date.today().isoformat(),
            "sources": [s for s in (sources or ["prompt log"])],
            "provenance": {"kind": kind, "origin": origin, "forked_from": forked_from, "consent": consent},
            "entry": entry,
            "notes": notes,
        }
        if source:
            meta["source"] = source
        write_json(path / "build.json", meta)
    except Exception:
        shutil.rmtree(path, ignore_errors=True)
        raise
    return {"id": build_id, "path": str(path), "files": files, "skipped": skipped, "prompts": len(turns)}


def check_build(kb: KB, build_id: str) -> List[str]:
    """Problems with a build's folder, in words."""
    problems: List[str] = []
    try:
        b = kb.build(build_id)
    except KBError as e:
        return [str(e)]
    meta = b.meta
    if meta.get("id") != build_id:
        problems.append(f"build.json id is {meta.get('id')!r}, but the folder is {build_id!r}")
    if not meta.get("title"):
        problems.append("build.json has no title")
    prov = meta.get("provenance") or {}
    if prov.get("kind") not in KINDS:
        problems.append(f"provenance.kind should be one of {', '.join(KINDS)}")
    if prov.get("consent") not in CONSENT:
        problems.append(f"provenance.consent should be one of {', '.join(CONSENT)}")
    for s in meta.get("sources") or []:
        if s not in SOURCES:
            problems.append(f"source {s!r} is not one of {', '.join(SOURCES)}")
    if not b.prompts and prov.get("kind") != "paper":
        problems.append("prompts.jsonl is empty")
    for i, t in enumerate(b.prompts, 1):
        if not isinstance(t.get("text"), str) or not t["text"].strip():
            problems.append(f"prompt {i} has no text")
    files = b.code_files()
    if not files:
        problems.append("code/ is empty")
    entry = meta.get("entry")
    if entry and not (b.path / entry).is_file():
        problems.append(f"entry {entry!r} does not exist")
    return problems


def slim_build(kb: KB, build_id: str, force: bool = False, dry_run: bool = False) -> Dict[str, Any]:
    """Keep only the files a build's card points at (and its entry), for builds from
    big repositories. The dropped files are listed in build.json with their sizes and
    fingerprints, beside the repository and commit the full code can be fetched from,
    so describing the build again stays possible."""
    from .cards import part_spans

    b = kb.build(build_id)
    source = b.meta.get("source") or {}
    if not source.get("repo") and not force:
        raise KBError(f"{build_id} records no source repository, so its full code could not be fetched again; "
                      "file it with --repo and --commit, or pass --force")
    card = kb.card(build_id)
    keep = {b.meta.get("entry")} if b.meta.get("entry") else set()
    for part in card.get("parts", []):
        keep.update(sp["file"] for sp in part_spans(part))
    kept, dropped, size = [], [], 0
    for f in b.code_files():
        rel = str(f.relative_to(b.path))
        if rel in keep:
            kept.append(rel)
            continue
        data = f.read_bytes()
        dropped.append({"file": rel, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()[:16]})
        size += len(data)
        if not dry_run:
            f.unlink()
    if not dry_run and dropped:
        meta = dict(b.meta)
        meta["slimmed"] = {"at": date.today().isoformat(), "kept": sorted(kept),
                           "dropped": (b.meta.get("slimmed") or {}).get("dropped", []) + dropped}
        write_json(b.path / "build.json", meta)
        for d in sorted((b.path / "code").rglob("*"), reverse=True):
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()
    where = source.get("repo", "nowhere recorded") + (f" @ {source['commit']}" if source.get("commit") else "")
    return {"id": build_id, "kept": sorted(kept), "dropped": dropped, "dropped_bytes": size, "source": where}
