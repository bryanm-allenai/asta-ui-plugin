"""Deriving an interface's workflow, and showing it to the person who built it.

    astaui derive setup                    Playwright and its Chromium, once (for --from ui)
    astaui derive brief code               what a coding agent is told to read the code for
    astaui derive put FILE --from code     keep a workflow written from the code
    astaui derive run --url ADDRESS        a computer-use agent uses the app and writes one
    astaui derive brief merge latest       how to merge the two into one
    astaui derive put FILE --from both     keep the merged one
    astaui derive show latest              the page where the person reads, checks and corrects it
    astaui derive outline latest           the same workflow as a plain outline
    astaui derive export latest --to DIR   workflow.json and workflow.md, wherever they want them
    astaui derive send latest              the checked workflow, marks and notes, to the knowledge base's owner
    astaui derive received                 (the owner) take in the workflows sent, and keep each with its build
    astaui derive attach latest --build ID keep a checked workflow with a build in the knowledge base
    astaui derive list | line

A workflow is a goal, the phases and tasks of the work under it, the actions a
person takes, and the features (a component with the few steps a person takes
with it) that carry those tasks. It can come from two places:

- the code: the coding agent the person is using reads the app's files and
  writes the tree, citing file and line for each part;
- the interface: AstaUI's computer-use agent (the collection's explore stage:
  Claude Code in print mode with a headless browser and no other tools) uses the
  running app and writes the tree, citing the screenshots it took.

With both, the coding agent merges them, and each part says where it came from.
Each derivation is a folder in ~/.astaui/workflows/<name>-<time>/: run.json,
code.json and ui.json (each source as it was written), workflow.json (the one
the page shows and the person corrects), workflow.md (the same as an outline),
and for a ui run brief.md, transcript.jsonl (images left out), trace.jsonl and
screens/.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import __version__
from .kb import KBError

HERE = Path(__file__).resolve().parent
CUA_HOME = Path(os.environ.get("ASTAUI_CUA_HOME", Path.home() / ".astaui" / "cua"))
WORKFLOWS = Path(os.environ.get("ASTAUI_WORKFLOWS", Path.home() / ".astaui" / "workflows"))
# The collection's explore stage: Opus 5.5 at high effort, about 60 actions.
MODEL = os.environ.get("ASTAUI_CUA_MODEL", "claude-opus-5-5")
EFFORT = os.environ.get("ASTAUI_CUA_EFFORT", "high")
ACTIONS = 60
BUDGET = 20.0
PLAYWRIGHT = "playwright@^1.50"
# The line someone pastes into their coding agent, in the folder of their app.
LINE = ("Set up AstaUI by running `curl -fsSL {raw}/install.py | python3 -{link}`, then follow its derive-workflow skill "
        "(~/.agents/skills/derive-workflow/SKILL.md) to work out the workflow of the app in this folder, from its code "
        "and from using it, and show it to me so I can check it and send it to the AstaUI team.")
SOURCES = ("code", "ui")
KINDS = ("goal", "phase", "task", "action")
CHECKS = ("right", "wrong")  # what the person can mark a part

# -- setup ----------------------------------------------------------------------------------------

def playwright_home() -> Path:
    return Path(os.environ.get("ASTAUI_PLAYWRIGHT") or CUA_HOME)


def _which(cmd: str) -> Optional[str]:
    return shutil.which(cmd)


def _playwright_ok(home: Path) -> bool:
    node = _which("node")
    if not node:
        return False
    probe = ("const r=require('module').createRequire(process.argv[1]+'/package.json');"
             "r.resolve('playwright/package.json');")
    return subprocess.run([node, "-e", probe, str(home)], capture_output=True).returncode == 0


def _chromium_ok(home: Path) -> bool:
    """Whether Playwright's Chromium is downloaded: launch it once."""
    node = _which("node")
    script = ("const r=require('module').createRequire(process.argv[1]+'/package.json');"
              "const {chromium}=r('playwright');"
              "chromium.launch({headless:true}).then(b=>b.close()).then(()=>process.exit(0),()=>process.exit(1));")
    try:
        return subprocess.run([node, "-e", script, str(home)], capture_output=True, timeout=90).returncode == 0
    except subprocess.TimeoutExpired:
        return False


def status() -> Dict[str, Any]:
    home = playwright_home()
    return {"node": _which("node"), "npm": _which("npm"), "claude": _which("claude"),
            "playwright": str(home) if _playwright_ok(home) else None, "workflows": str(WORKFLOWS)}


def setup(say=print) -> Dict[str, Any]:
    """Install Playwright and its Chromium into ~/.astaui/cua, unless they are there."""
    st = status()
    if not st["node"] or not st["npm"]:
        raise KBError("The agent's browser needs Node.js 18 or later (node and npm), which this computer does not have. "
                      "Install it from https://nodejs.org, then run `astaui derive setup` again.")
    home = playwright_home()
    if not st["playwright"]:
        if os.environ.get("ASTAUI_PLAYWRIGHT"):
            raise KBError(f"ASTAUI_PLAYWRIGHT names {home}, which has no Playwright in its node_modules.")
        home.mkdir(parents=True, exist_ok=True)
        pkg = home / "package.json"
        if not pkg.exists():
            pkg.write_text(json.dumps({"name": "astaui-cua", "private": True, "description": "The browser AstaUI's computer-use agent works in"}, indent=1))
        say(f"Installing Playwright into {home} …")
        r = subprocess.run([st["npm"], "install", "--no-audit", "--no-fund", "--loglevel", "error", PLAYWRIGHT], cwd=home)
        if r.returncode:
            raise KBError("npm could not install Playwright; its message is above.")
    if not _chromium_ok(home):
        say("Downloading Playwright's Chromium (about 150 MB, once) …")
        cli = home / "node_modules" / "playwright" / "cli.js"
        r = subprocess.run([st["node"], str(cli), "install", "chromium"], cwd=home)
        if r.returncode or not _chromium_ok(home):
            raise KBError("Playwright could not download or start Chromium; its message is above. "
                          "On Linux, `npx playwright install-deps chromium` adds the system libraries it needs.")
    st = status()
    if not st["claude"]:
        say("The agent itself runs in Claude Code, which is not on this computer's PATH: "
            "install it from https://claude.com/claude-code and sign in before a run.")
    return st


# -- running the agent ----------------------------------------------------------------------------

def _origin(url: str) -> str:
    p = urllib.parse.urlparse(url)
    if p.scheme not in ("http", "https") or not p.netloc:
        raise KBError(f"{url} is not an http(s) address. Start the app and give the address it answers at.")
    return f"{p.scheme}://{p.netloc}"


def _reachable(url: str, wait: int = 30) -> Optional[str]:
    """None if the app answers within `wait` seconds, else what went wrong."""
    end, last = time.time() + wait, "no answer"
    while time.time() < end:
        try:
            urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": f"astaui/{__version__}"}), timeout=10).close()
            return None
        except urllib.error.HTTPError:
            return None  # it answered, even if with an error page
        except (urllib.error.URLError, OSError) as e:
            last = str(getattr(e, "reason", e))
        time.sleep(2)
    return last


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:40] or "app"


def _claude_flags(claude: str) -> set:
    try:
        text = subprocess.run([claude, "--help"], capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.TimeoutExpired):
        return set()
    return set(re.findall(r"--[a-z][a-z-]+", text))


def last_json(text: str) -> Optional[Dict[str, Any]]:
    """The largest whole JSON object in a reply, fenced or not (brace counting,
    since a nested object defeats a pattern)."""
    best, best_len, i = None, 0, 0
    while i < len(text):
        if text[i] != "{":
            i += 1
            continue
        depth, quoted, escaped, done = 0, False, False, None
        for j in range(i, len(text)):
            ch = text[j]
            if escaped:
                escaped = False
            elif quoted and ch == "\\":
                escaped = True
            elif ch == '"':
                quoted = not quoted
            elif not quoted and ch == "{":
                depth += 1
            elif not quoted and ch == "}":
                depth -= 1
                if depth == 0:
                    done = j
                    break
        if done is None:
            break
        chunk = text[i:done + 1]
        try:
            got = json.loads(chunk)
        except ValueError:
            i += 1
            continue
        if isinstance(got, dict) and len(chunk) >= best_len:
            best, best_len = got, len(chunk)
        i = done + 1
    return best


def number(tree: Dict[str, Any]) -> Dict[str, Any]:
    """Give every node of the tree a path id ("g", "1", "1.2", "1.2.3") and every
    feature one ("f1"), so a check stays with its part. Parts the person adds on
    the page get ids of their own, so these never move."""
    def walk(node, path):
        node["id"] = path or "g"
        for k, child in enumerate(node.get("children") or [], 1):
            walk(child, f"{path}.{k}" if path else str(k))
    if isinstance(tree.get("tree"), dict):
        walk(tree["tree"], "")
    for k, f in enumerate(tree.get("features") or [], 1):
        f["id"] = f"f{k}"
    return tree


def shape(tree: Dict[str, Any]) -> Dict[str, int]:
    counts = {"phases": 0, "tasks": 0, "actions": 0}

    def walk(node):
        kind = node.get("kind")
        if kind in ("phase", "task", "action"):
            counts[kind + "s"] += 1
        for c in node.get("children") or []:
            walk(c)
    if isinstance(tree.get("tree"), dict):
        walk(tree["tree"])
    counts["features"] = len(tree.get("features") or [])
    return counts


def _strip_images(obj: Any) -> Any:
    """A transcript line without the screenshots' base64 (they are in screens/)."""
    if isinstance(obj, dict):
        if obj.get("type") == "image":
            return {"type": "image", "left_out": True}
        return {k: _strip_images(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_strip_images(v) for v in obj]
    return obj


def _tell(block: Dict[str, Any]) -> Optional[str]:
    """One short line for a browser call, for the person watching the terminal."""
    name = (block.get("name") or "").replace("mcp__browser__browser_", "")
    if not name or not (block.get("name") or "").startswith("mcp__browser__"):
        return None
    a = block.get("input") or {}
    what = a.get("url") or a.get("text") or a.get("key") or a.get("values") or a.get("names") or a.get("ref") or ""
    if not what and "x" in a:
        what = f"at {a.get('x')},{a.get('y')}"
    what = str(what).replace("\n", " ")
    return f"{name} {what[:70]}".rstrip()

# -- folders --------------------------------------------------------------------------------------

def _read(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write(path: Path, obj: Any) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def new_folder(name: Optional[str] = None, app: Optional[Path] = None) -> Path:
    """A fresh derivation folder for the app in `app` (default: this folder)."""
    app = (app or Path.cwd()).resolve()
    name = _slug(name or app.name)
    run_dir = WORKFLOWS / f"{name}-{datetime.now():%Y%m%d-%H%M%S}"
    while run_dir.exists():
        time.sleep(1)
        run_dir = WORKFLOWS / f"{name}-{datetime.now():%Y%m%d-%H%M%S}"
    run_dir.mkdir(parents=True)
    _write(run_dir / "run.json", {"kind": "derived-workflow", "astaui": __version__, "name": name, "folder": str(app),
                                  "started": datetime.now().astimezone().isoformat(timespec="seconds"), "sources": {}})
    return run_dir


def runs() -> List[Path]:
    if not WORKFLOWS.is_dir():
        return []
    return sorted((p for p in WORKFLOWS.iterdir() if (p / "run.json").is_file()), key=lambda p: p.name[-15:])


def resolve(which: Optional[str]) -> Path:
    """A derivation folder from a path, a folder name in ~/.astaui/workflows,
    `latest`, or `latest` of one app's name."""
    which = which or "latest"
    p = Path(which).expanduser()
    if (p / "run.json").is_file():
        return p.resolve()
    if (WORKFLOWS / which / "run.json").is_file():
        return WORKFLOWS / which
    every = runs()
    if which == "latest":
        if every:
            return every[-1]
        raise KBError(f"There is no workflow in {WORKFLOWS} yet: `astaui derive put … --from code` or "
                      "`astaui derive run --url …` makes one.")
    named = [r for r in every if r.name.rsplit("-", 2)[0] == _slug(which)]
    if named:
        return named[-1]
    raise KBError(f"No workflow called {which} in {WORKFLOWS}; `astaui derive list` shows them.")


def _target(into: Optional[str], name: Optional[str]) -> Path:
    return resolve(into) if into else new_folder(name)


def _note_source(run_dir: Path, source: str, tree: Dict[str, Any], extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    meta = _read(run_dir / "run.json", {}) or {}
    meta.setdefault("sources", {})[source] = {
        "at": datetime.now().astimezone().isoformat(timespec="seconds"), **shape(tree), **(extra or {})}
    title = (tree.get("interface") or {}).get("title")
    if title and (source == "both" or not meta.get("title")):
        meta["title"] = title
    _write(run_dir / "run.json", meta)
    return meta


# -- the shape of a workflow ----------------------------------------------------------------------

def _nodes(tree: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    def walk(n):
        out.append(n)
        for c in n.get("children") or []:
            walk(c)
    if isinstance(tree.get("tree"), dict):
        walk(tree["tree"])
    return out


def problems(tree: Any) -> List[str]:
    """What is wrong with a workflow's shape, in words an agent can fix it by."""
    if not isinstance(tree, dict):
        return ["a workflow is one JSON object"]
    out: List[str] = []
    root = tree.get("tree")
    if not isinstance(root, dict) or root.get("kind") != "goal":
        return ['"tree" must be an object with "kind": "goal"']

    def walk(n, where, parent):
        kind = n.get("kind")
        if kind not in KINDS:
            out.append(f"{where}: kind must be one of {', '.join(KINDS)}, not {kind!r}")
            return
        if kind == "goal" and parent is not None:
            out.append(f"{where}: only the top of the tree is a goal")
        words = n.get("label") if kind == "action" else n.get("general")
        if not isinstance(words, str) or not words.strip():
            out.append(f"{where}: needs {'label' if kind == 'action' else 'general'} words")
        for key in ("screens", "code", "from"):
            if key in n and not (isinstance(n[key], list) and all(isinstance(s, str) for s in n[key])):
                out.append(f"{where}: {key} must be a list of strings")
        kids = n.get("children") or []
        if not isinstance(kids, list):
            out.append(f"{where}: children must be a list")
            return
        if kind == "action" and kids:
            out.append(f"{where}: an action is a leaf")
        for k, c in enumerate(kids, 1):
            if not isinstance(c, dict):
                out.append(f"{where}.{k}: each child is an object")
                continue
            walk(c, f"{where}.{k}" if where != "goal" else str(k), kind)
    walk(root, "goal", None)
    feats = tree.get("features", [])
    if not isinstance(feats, list):
        out.append('"features" must be a list')
    else:
        for k, f in enumerate(feats, 1):
            if not isinstance(f, dict) or not str(f.get("name") or "").strip():
                out.append(f"feature {k}: needs a name")
    return out


def _tag(tree: Dict[str, Any], source: str) -> None:
    """Say where each part came from, unless the merge already said."""
    for n in _nodes(tree) + list(tree.get("features") or []):
        if not n.get("from"):
            n["from"] = ["ui", "code"] if source == "both" else [source]


def keep(run_dir: Path, tree: Dict[str, Any], source: str, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Keep a workflow from one source (code or ui) or from both, and make it the
    one shown: a single source is shown until both are in, then the merge is."""
    if source not in ("code", "ui", "both"):
        raise KBError("--from is code, ui or both")
    bad = problems(tree)
    if bad:
        raise KBError("The workflow does not have the right shape:\n  " + "\n  ".join(bad[:20]))
    number(tree)
    _tag(tree, source)
    tree["derived_from"] = source
    if source in SOURCES:
        _write(run_dir / f"{source}.json", tree)
    else:
        _write(run_dir / "both.json", tree)
    meta = _note_source(run_dir, source, tree, extra)
    have = [s for s in SOURCES if (run_dir / f"{s}.json").is_file()]
    shown = _read(run_dir / "workflow.json", {}) or {}
    # The merge wins once there is one; until then the newest single source.
    if source == "both" or shown.get("derived_from") != "both":
        _write(run_dir / "workflow.json", tree)
        (run_dir / "workflow.md").write_text(outline(tree, meta), encoding="utf-8")
    return {"run": str(run_dir), "have": have, "shown": _read(run_dir / "workflow.json", {}).get("derived_from"), **shape(tree)}


def put(run_dir: Path, text: str, source: str) -> Dict[str, Any]:
    tree = last_json(text)
    if tree is None:
        raise KBError("That file holds no JSON object.")
    return keep(run_dir, tree, source)


# -- what the coding agent is told ----------------------------------------------------------------

def brief(kind: str, run_dir: Optional[Path] = None) -> str:
    if kind == "code":
        return (HERE / "derive_code.md").read_text(encoding="utf-8")
    if kind == "merge":
        if run_dir is None:
            raise KBError("Say which workflow to merge: astaui derive brief merge latest")
        missing = [s for s in SOURCES if not (run_dir / f"{s}.json").is_file()]
        if missing:
            raise KBError(f"{run_dir.name} has no {' or '.join(missing)} workflow yet, so there is nothing to merge.")
        text = (HERE / "derive_merge.md").read_text(encoding="utf-8")
        return text.replace("{UI}", str(run_dir / "ui.json")).replace("{CODE}", str(run_dir / "code.json"))
    raise KBError("astaui derive brief takes code or merge")


# -- the outline ----------------------------------------------------------------------------------

SAID = {"ui": "seen in use", "code": "in the code", "person": "added by you"}


def _where(n: Dict[str, Any]) -> str:
    f = n.get("from") or []
    if "ui" in f and "code" in f:
        return "seen in use and in the code"
    return " and ".join(SAID.get(x, x) for x in f)


def outline(tree: Dict[str, Any], meta: Optional[Dict[str, Any]] = None) -> str:
    """The workflow as Markdown a person can read top to bottom."""
    iface = tree.get("interface") or {}
    root = tree.get("tree") or {}
    title = iface.get("title") or (meta or {}).get("name") or "Workflow"
    lines = [f"# {title}", ""]
    if iface.get("what_it_is_for"):
        lines += [iface["what_it_is_for"], ""]
    facts = [f"{k}: {iface[v]}" for k, v in (("Field", "field"), ("Stage of the work", "stage_of_work")) if iface.get(v)]
    if facts:
        lines += [*(f"- {f}" for f in facts), ""]
    lines += [f"**Goal.** {root.get('general', '')}" + (f" ({root['specific']})" if root.get("specific") else ""), ""]

    def mark(n):
        c = n.get("check")
        return " [checked]" if c == "right" else (" [needs a fix" + (f": {n['note']}" if n.get("note") else "") + "]") if c == "wrong" else ""

    def walk(n, path, depth):
        kids = [c for c in n.get("children") or [] if c.get("kind") != "action"]
        acts = [c for c in n.get("children") or [] if c.get("kind") == "action"]
        for k, c in enumerate(kids, 1):
            p = f"{path}.{k}" if path else str(k)
            word = "Phase" if c.get("kind") == "phase" else "Task"
            extra = f" ({c['specific']})" if c.get("specific") else ""
            branch = f" [{c['branch']}]" if c.get("branch") else ""
            if depth == 0 and c.get("kind") == "phase":
                lines.extend([f"## {word} {p}. {c.get('general', '')}{branch}{mark(c)}", ""])
                if c.get("specific"):
                    lines.extend([c["specific"], ""])
                walk(c, p, depth + 1)
                lines.append("")
            else:
                lines.append(f"{'  ' * max(0, depth - 1)}- {word} {p}. {c.get('general', '')}{extra}{branch}{mark(c)}")
                walk(c, p, depth + 1)
        if acts and depth:
            for a in acts:
                lines.append(f"{'  ' * depth}- {a.get('label', '')}")
    walk(root, "", 0)
    feats = tree.get("features") or []
    if feats:
        lines += ["", "## Features", ""]
        for f in feats:
            lines.append(f"- **{f.get('name', '')}**{mark(f)}: {f.get('general') or f.get('specific') or ''}")
            for s in f.get("steps") or []:
                lines.append(f"  - {s}")
    gaps = list(tree.get("not_done") or []) + list(tree.get("screens_never_reached") or [])
    if gaps:
        lines += ["", "## Not reached", ""] + [f"- {g}" for g in gaps]
    return "\n".join(lines).rstrip() + "\n"


def tally(tree: Dict[str, Any]) -> Dict[str, int]:
    parts = [n for n in _nodes(tree) if n.get("kind") != "action"] + list(tree.get("features") or [])
    return {"parts": len(parts), "right": sum(1 for n in parts if n.get("check") == "right"),
            "wrong": sum(1 for n in parts if n.get("check") == "wrong")}


# -- using the interface --------------------------------------------------------------------------

def run(url: str, files: Optional[str] = None, about: Optional[str] = None, name: Optional[str] = None,
        actions: int = ACTIONS, model: Optional[str] = None, into: Optional[str] = None, quiet: bool = False,
        say=print) -> Dict[str, Any]:
    say0 = say

    def say(msg: str) -> None:  # noqa: F811 - each line as it happens, even into a file
        say0(msg)
        sys.stdout.flush()

    claude = _which("claude")
    if not claude:
        raise KBError("The agent runs in Claude Code, which is not on this computer's PATH. "
                      "Install it from https://claude.com/claude-code, sign in, and run this again.")
    home = playwright_home()
    if not _playwright_ok(home):
        raise KBError("The agent's browser is not installed yet: run `astaui derive setup` first.")
    origin = _origin(url)
    problem = _reachable(url)
    if problem:
        raise KBError(f"Nothing answers at {url} ({problem}). Start the app first, and give the address it prints.")
    folder = None
    if files:
        folder = Path(files).expanduser().resolve()
        if not folder.is_dir():
            raise KBError(f"{files} is not a folder. --files takes a folder of test files the app may be given.")

    run_dir = _target(into, name)
    if (run_dir / "ui.json").is_file():
        raise KBError(f"{run_dir.name} already has a workflow from using the app. Leave out --into to start a new one.")
    for d in ("screens", "downloads"):
        (run_dir / d).mkdir(parents=True, exist_ok=True)
    if folder is None:
        folder = run_dir / "no-files"
        folder.mkdir(exist_ok=True)
    listed = sorted(p.name for p in folder.iterdir() if p.is_file() and not p.name.startswith("."))

    about_text = (f"What the person who built it says it is for, in one line: {about.strip()}" if about and about.strip()
                  else "")
    text = (HERE / "cua_explore.md").read_text(encoding="utf-8")
    for k, v in {"{URL}": url, "{ORIGIN}": origin, "{ACTIONS}": str(actions), "{ABOUT}": about_text,
                 "{DATA}": ", ".join(listed) if listed else "there are none"}.items():
        text = text.replace(k, v)
    text = re.sub(r"\n{3,}", "\n\n", text)
    (run_dir / "brief.md").write_text(text, encoding="utf-8")

    env_mcp = {"PILOT_SCREENS": str(run_dir / "screens"), "PILOT_DOWNLOADS": str(run_dir / "downloads"),
               "PILOT_FILES": str(folder), "PILOT_ORIGIN": origin, "PILOT_TRACE": str(run_dir / "trace.jsonl"),
               "PILOT_SHOT": "jpeg", "ASTAUI_PLAYWRIGHT": str(home)}
    mcp = {"mcpServers": {"browser": {"command": _which("node"), "args": [str(HERE / "cua_browser.mjs")], "env": env_mcp}}}
    (run_dir / "mcp.json").write_text(json.dumps(mcp, indent=1))

    model = model or MODEL
    ui: Dict[str, Any] = {"url": url, "origin": origin, "about": about or None, "files": listed, "model": model,
                          "effort": EFFORT, "actions_asked": actions, "status": "running",
                          "started": datetime.now().astimezone().isoformat(timespec="seconds")}
    meta = _read(run_dir / "run.json", {}) or {}
    meta["ui_run"] = ui
    _write(run_dir / "run.json", meta)

    flags = _claude_flags(claude)
    cmd = [claude, "-p", text, "--model", model, "--tools", "", "--mcp-config", str(run_dir / "mcp.json"),
           "--strict-mcp-config", "--allowedTools", "mcp__browser__*", "--permission-mode", "dontAsk",
           "--output-format", "stream-json", "--verbose"]
    for flag, extra in (("--effort", [EFFORT]), ("--no-session-persistence", []), ("--disable-slash-commands", []),
                        ("--max-budget-usd", [str(BUDGET)])):
        if not flags or flag in flags:
            cmd += [flag, *extra]
    env = {**os.environ, "MCP_TIMEOUT": "400000"}

    def note(**kw):
        m = _read(run_dir / "run.json", {}) or {}
        m.setdefault("ui_run", {}).update(kw)
        _write(run_dir / "run.json", m)

    say(f"The agent is using {url}. It takes about 10 to 20 minutes; its record goes in {run_dir}.")
    started, result, calls = time.time(), None, 0
    with open(run_dir / "transcript.jsonl", "w", encoding="utf-8") as out, \
            open(run_dir / "agent.log", "w", encoding="utf-8") as errlog:
        proc = subprocess.Popen(cmd, cwd=run_dir, env=env, stdout=subprocess.PIPE, stderr=errlog, text=True, bufsize=1)
        try:
            for line in proc.stdout:
                try:
                    m = json.loads(line)
                except ValueError:
                    continue
                out.write(json.dumps(_strip_images(m)) + "\n")
                if m.get("type") == "result":
                    result = m
                if m.get("type") == "assistant":
                    for b in (m.get("message") or {}).get("content") or []:
                        if b.get("type") == "tool_use":
                            calls += 1
                            told = _tell(b)
                            if told and not quiet:
                                say(f"  {calls:3}  {told}")
            proc.wait(timeout=3900)
        except (KeyboardInterrupt, subprocess.TimeoutExpired):
            proc.kill()
            note(status="stopped", seconds=round(time.time() - started))
            raise KBError(f"The run was stopped; what it did so far is in {run_dir}.")

    done = {"seconds": round(time.time() - started), "browser_calls": calls,
            "screens": len(list((run_dir / "screens").glob("*")))}
    reply = (result or {}).get("result") or ""
    if result:
        done.update(cost_usd=result.get("total_cost_usd"), turns=result.get("num_turns"))
    tree = last_json(reply) if reply else None
    if not tree or problems(tree):
        why = (reply.strip()[:400] or (run_dir / "agent.log").read_text(errors="replace").strip()[-400:]
               or "the agent ended without an answer")
        note(status="failed", error=why, **done)
        raise KBError(f"The agent did not write a workflow. What it said: {why}\nIts record is in {run_dir}.")
    note(status="done", finished=datetime.now().astimezone().isoformat(timespec="seconds"), **done)
    kept = keep(run_dir, tree, "ui", done)
    return {**kept, **done}


# -- the page -------------------------------------------------------------------------------------

def page() -> str:
    text = (HERE / "derive_view.html").read_text(encoding="utf-8")
    return text.replace("/*__ASTA__*/", (HERE / "asta.css").read_text(encoding="utf-8"))


SCREEN_RE = re.compile(r"^[A-Za-z0-9_.-]+\.(?:jpe?g|png|webp)$")
CODE_REF = re.compile(r"^(?P<path>[^:]+?)(?::(?P<a>\d+)(?:-(?P<b>\d+))?)?$")
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next"}


def code_lines(app: Path, ref: str, around: int = 6, most: int = 400) -> Dict[str, Any]:
    """The lines a code reference points at, from the app's own folder only."""
    m = CODE_REF.match(ref.strip())
    if not m:
        raise KBError("not a file:line reference")
    root = app.resolve()
    f = (root / m.group("path")).resolve()
    if root not in f.parents or not f.is_file() or any(p in SKIP_DIRS for p in f.relative_to(root).parts[:-1]):
        raise KBError(f"{m.group('path')} is not a file in the app's folder")
    if f.stat().st_size > 8 * 1024 * 1024:
        raise KBError(f"{m.group('path')} is too big to show")
    text = f.read_text(encoding="utf-8", errors="replace").splitlines()
    a = int(m.group("a") or 1)
    b = int(m.group("b") or (a if m.group("a") else min(len(text), 40)))
    a, b = max(1, min(a, b)), min(len(text), max(a, b))
    lo, hi = max(1, a - around), min(len(text), b + around, max(a, b) + most)
    return {"path": m.group("path"), "from": a, "to": b, "first": lo,
            "lines": [line[:400] for line in text[lo - 1:hi]], "of": len(text)}


def _handler(run_dir: Path):
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str, name: Optional[str] = None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            if name:
                self.send_header("Content-Disposition", f'attachment; filename="{name}"')
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj: Any):
            self._send(code, json.dumps(obj).encode("utf-8"), "application/json")

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            path, q = u.path, urllib.parse.parse_qs(u.query)
            if path in ("/", "/index.html"):
                return self._send(200, page().encode("utf-8"), "text/html; charset=utf-8")
            if path == "/data":
                meta = _read(run_dir / "run.json", {}) or {}
                return self._json(200, {"run": meta, "workflow": _read(run_dir / "workflow.json", {}),
                                        "have": [s for s in SOURCES if (run_dir / f"{s}.json").is_file()],
                                        "send": {"ready": can_send() and not meta.get("received"), "sent": meta.get("sent"),
                                                 "received": meta.get("received"), "build": meta.get("build"),
                                                 "name": meta.get("checked_by") or _who(),
                                                 "screens": len(_screens_in(_read(run_dir / "workflow.json", {}) or {}))},
                                        "folder": run_dir.name, "files": {"json": str(run_dir / "workflow.json"),
                                                                          "md": str(run_dir / "workflow.md")}})
            if path == "/code":
                app = Path((_read(run_dir / "run.json", {}) or {}).get("folder") or "/nonexistent")
                try:
                    return self._json(200, code_lines(app, (q.get("ref") or [""])[0]))
                except (KBError, OSError, ValueError) as e:
                    return self._json(200, {"error": str(e)})
            if path == "/workflow.json":
                return self._send(200, (run_dir / "workflow.json").read_bytes(), "application/json", "workflow.json")
            if path == "/workflow.md":
                return self._send(200, (run_dir / "workflow.md").read_bytes(), "text/markdown; charset=utf-8", "workflow.md")
            if path.startswith("/screens/"):
                name = path[len("/screens/"):]
                f = run_dir / "screens" / name
                if SCREEN_RE.match(name) and f.is_file():
                    ctype = "image/png" if name.endswith(".png") else "image/webp" if name.endswith(".webp") else "image/jpeg"
                    return self._send(200, f.read_bytes(), ctype)
            return self._send(404, b"not found", "text/plain")

        def _origin_ok(self) -> bool:
            # Only the page itself may save: a page on another site cannot
            # post into this one.
            o = self.headers.get("Origin")
            host = self.headers.get("Host") or ""
            return o is None or urllib.parse.urlparse(o).netloc == host

        def do_POST(self):
            path = urllib.parse.urlparse(self.path).path
            if not self._origin_ok():
                return self._json(403, {"error": "not from this page"})
            n = int(self.headers.get("Content-Length") or 0)
            if n > 4 * 1024 * 1024:
                return self._json(413, {"error": "too big"})
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._json(400, {"error": "not JSON"})
            if path == "/workflow":
                bad = problems(body)
                if bad:
                    return self._json(200, {"ok": False, "error": bad[0]})
                with lock:
                    body["saved"] = datetime.now().astimezone().isoformat(timespec="seconds")
                    _write(run_dir / "workflow.json", body)
                    (run_dir / "workflow.md").write_text(outline(body, _read(run_dir / "run.json", {})), encoding="utf-8")
                return self._json(200, {"ok": True, "saved": body["saved"], **tally(body)})
            if path == "/send":
                name = body.get("name")
                try:
                    with lock:
                        res = send(run_dir, author=str(name).strip()[:120] if isinstance(name, str) else None)
                except KBError as e:
                    return self._json(200, {"ok": False, "error": str(e)})
                return self._json(200, {"ok": True, **res, "sent": (_read(run_dir / "run.json", {}) or {}).get("sent")})
            return self._json(404, {"error": "no such thing"})

    return Handler


def serve(run_dir: Path, port: int = 0, open_browser: bool = True, say=print) -> None:
    if not (run_dir / "workflow.json").is_file():
        raise KBError(f"{run_dir.name} has no workflow yet.")
    server = ThreadingHTTPServer(("127.0.0.1", port), _handler(run_dir))
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    (run_dir / "page-address.txt").write_text(url)
    say(f"The workflow for {run_dir.name} is at {url}")
    say(f"What is checked or changed there is saved as it happens, into {run_dir / 'workflow.json'} "
        "(and workflow.md beside it). Stop this with Ctrl-C when you are done.")
    sys.stdout.flush()
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def export(run_dir: Path, to: Path) -> Dict[str, str]:
    """workflow.json and workflow.md into a folder (or json to a file path, md beside it)."""
    to = to.expanduser()
    if to.suffix.lower() == ".json":
        dest_json, dest_md = to, to.with_suffix(".md")
    else:
        to.mkdir(parents=True, exist_ok=True)
        dest_json, dest_md = to / "workflow.json", to / "workflow.md"
    dest_json.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(run_dir / "workflow.json", dest_json)
    shutil.copyfile(run_dir / "workflow.md", dest_md)
    return {"json": str(dest_json), "md": str(dest_md)}


# -- sending it to the AstaUI team, and keeping it with the build ---------------------------------
#
# A checked workflow (the tree with every Right / Needs a fix the person marked,
# their notes and their corrections) goes to the knowledge base's owner the way
# a filed build does: as one row added to the end of the list on their drive
# page, through the Add only link the line carries. The row is a
# <li data-workflow> (never data-build, so build intake passes it by) with the
# workflow packed out of sight. The owner's intake unpacks it into their own
# ~/.astaui/workflows, where `astaui derive show` opens the same page with the
# person's marks, and copies it into the build it describes (builds/<id>/derived/),
# so filing, sending and publishing a build carry its ratings with it.

DERIVED = "derived"           # the folder in a build that holds its checked workflow
SENT_SCREENS_MAX = 9 * 1024 * 1024   # screenshots ride along while the row stays under the drive's limit
TAKEN = ".derived-intake.json"  # what the owner's intake took, kept beside the knowledge base


def _who() -> str:
    try:
        name = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        name = ""
    return name


def _screens_in(tree: Dict[str, Any]) -> List[str]:
    seen: List[str] = []
    for n in _nodes(tree) + list(tree.get("features") or []):
        for s in n.get("screens") or []:
            if isinstance(s, str) and s.startswith("screens/") and SCREEN_RE.match(s[len("screens/"):]) and s not in seen:
                seen.append(s)
    return seen


def about(run_dir: Path, author: Optional[str] = None) -> Dict[str, Any]:
    """What travels with a checked workflow: where it came from, how far it was
    checked and by whom. The app's folder goes by its name only, never its path."""
    meta = _read(run_dir / "run.json", {}) or {}
    wf = _read(run_dir / "workflow.json", {}) or {}
    ui = meta.get("ui_run") or {}
    return {"kind": "checked-workflow", "astaui": __version__, "name": run_dir.name,
            "title": (wf.get("interface") or {}).get("title") or meta.get("title") or meta.get("name"),
            "app": Path(meta.get("folder") or meta.get("app") or run_dir.name).name,
            "build": meta.get("build"), "derived_from": wf.get("derived_from"),
            "sources": {k: {x: v.get(x) for x in ("at", "phases", "tasks", "features") if x in v}
                        for k, v in (meta.get("sources") or {}).items()},
            "ui_run": {k: ui[k] for k in ("model", "seconds", "screens", "actions") if k in ui},
            "checked_by": author if author is not None else (meta.get("checked_by") or ""),
            "saved": wf.get("saved"), **tally(wf)}


def pack_workflow(run_dir: Path, author: Optional[str] = None) -> bytes:
    """A checked workflow as one gzipped tar: workflow.json, workflow.md,
    about.json, and the screenshots its parts rest on while they fit."""
    import io
    import tarfile
    if not (run_dir / "workflow.json").is_file():
        raise KBError(f"{run_dir.name} has no workflow yet.")
    wf = _read(run_dir / "workflow.json", {}) or {}
    info = about(run_dir, author)
    room = SENT_SCREENS_MAX
    shots = []
    for s in _screens_in(wf):
        f = run_dir / s
        if f.is_file() and f.stat().st_size <= room:
            shots.append(s)
            room -= f.stat().st_size
    info["screens_sent"] = len(shots)
    buf = io.BytesIO()

    def add(name: str, data: bytes) -> None:
        ti = tarfile.TarInfo(f"workflow/{name}")
        ti.size, ti.mtime, ti.mode = len(data), int(time.time()), 0o644
        t.addfile(ti, io.BytesIO(data))
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        add("workflow.json", (run_dir / "workflow.json").read_bytes())
        add("workflow.md", (run_dir / "workflow.md").read_bytes() if (run_dir / "workflow.md").is_file()
            else outline(wf).encode("utf-8"))
        add("about.json", json.dumps(info, indent=1, ensure_ascii=False).encode("utf-8"))
        for s in shots:
            add(s, (run_dir / s).read_bytes())
    return buf.getvalue()


def unpack_workflow(packed: str) -> Dict[str, bytes]:
    """The files a workflow row carries, by their name in a derivation folder,
    and nothing else, however the row was made."""
    import base64
    import io
    import tarfile
    try:
        t = tarfile.open(fileobj=io.BytesIO(base64.b64decode(packed, validate=True)), mode="r:gz")
    except (ValueError, tarfile.TarError, OSError) as e:
        raise KBError(f"the workflow did not arrive whole: {e}") from e
    out: Dict[str, bytes] = {}
    total = 0
    with t:
        for m in t.getmembers():
            if not m.isfile() or not m.name.startswith("workflow/"):
                continue
            name = m.name[len("workflow/"):]
            if not (name in ("workflow.json", "workflow.md", "about.json")
                    or (name.startswith("screens/") and SCREEN_RE.match(name[len("screens/"):]))):
                continue
            total += m.size
            if total > 64 * 1024 * 1024:
                raise KBError("the workflow unpacks to more than 64 MB")
            src = t.extractfile(m)
            out[name] = src.read() if src else b""
    if "workflow.json" not in out:
        raise KBError("the workflow arrived without its workflow.json")
    return out


def _link(link: Optional[str]) -> Optional[str]:
    """The Add only link: the one given, or the one this computer keeps (from
    `astaui setup --link`, the owner's config, or the first build sent)."""
    from .sources import inbox_link
    return link or inbox_link(None)


def can_send(link: Optional[str] = None) -> bool:
    return bool(_link(link))


def _row(run_dir: Path, info: Dict[str, Any], packed: bytes, sent: datetime) -> str:
    """The row a sent workflow is on the owner's page. Nothing in it is markup
    the sender wrote: the drive refuses a tag it did not expect."""
    import base64
    import html
    e = lambda v: html.escape(str(v), quote=True)  # noqa: E731
    checked = info["right"] + info["wrong"]
    how = f"{checked} of {info['parts']} parts checked" + (f", {info['wrong']} need a fix" if info["wrong"] else "")
    size = f"{max(1, round(len(packed) / 1024))} KB"
    when = f"{sent:%b} {sent.day}, {sent:%H:%M}"
    build = info.get("build")
    return (f'<li data-marble-removable data-workflow="{e(run_dir.name)}" data-sent="{e(sent.isoformat(timespec="seconds"))}"'
            + (f' data-for="{e(build)}"' if build else "") + ">"
            f'<b>Workflow: {e(info.get("title") or info["app"])}</b><span class="when">{e(when)}</span>'
            f'<span class="who">{e(info.get("checked_by") or "No name given")} · {e(how)}</span>'
            f'<span class="id">{e(run_dir.name)}{" · build " + e(build) if build else ""} · {e(size)}</span>'
            f'<pre class="bundle" hidden>{base64.b64encode(packed).decode("ascii")}</pre></li>')


def send(run_dir: Path, link: Optional[str] = None, author: Optional[str] = None) -> Dict[str, Any]:
    """Send a checked workflow, with every mark and note, to the knowledge base
    owner's drive page through their Add only link. Sending again sends the
    newer copy, which replaces the older one there."""
    from .sources import INBOX_MAX, filed_as, post_row, set_user_config, user_config
    link = _link(link)
    if not link:
        raise KBError("There is no link to send it to. The line you were given has one: run "
                      "`astaui setup --link <that link>` once, or pass --to <that link>.")
    meta = _read(run_dir / "run.json", {}) or {}
    if not meta.get("build") and meta.get("folder"):
        bid = filed_as(Path(meta["folder"]))
        if bid:
            meta["build"] = bid
    who = author if author is not None else (meta.get("checked_by") or _who())
    meta["checked_by"] = who
    _write(run_dir / "run.json", meta)
    packed = pack_workflow(run_dir, who)
    if len(packed) > INBOX_MAX:
        raise KBError(f"The workflow packs to {len(packed) // (1024 * 1024)} MB, more than the drive takes at once.")
    info = json.loads(_unpack_about(packed))
    now = datetime.now().astimezone()
    where = post_row(link, _row(run_dir, info, packed, now), "workflow")
    meta = _read(run_dir / "run.json", {}) or {}
    meta["sent"] = {"at": now.isoformat(timespec="seconds"), "saved": info.get("saved"), **where}
    _write(run_dir / "run.json", meta)
    if user_config().get("inbox-link") != link and not user_config().get("inbox"):
        set_user_config("inbox-link", link)  # later workflows and builds go where this one went
    return {"workflow": run_dir.name, "bytes": len(packed), "screens": info.get("screens_sent", 0),
            "right": info["right"], "wrong": info["wrong"], "parts": info["parts"], "build": info.get("build"), **where}


def _unpack_about(packed: bytes) -> str:
    import io
    import tarfile
    with tarfile.open(fileobj=io.BytesIO(packed), mode="r:gz") as t:
        return t.extractfile("workflow/about.json").read().decode("utf-8")


# -- the owner's side -----------------------------------------------------------------------------

def _rows(path: Path) -> List[Dict[str, Any]]:
    """The workflow rows on the owner's page: name, when, the build it is for, packed text."""
    from html.parser import HTMLParser

    class Rows(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.rows, self.row, self.packed = [], None, False

        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            if tag == "li" and a.get("data-workflow") and not a.get("data-build"):
                self.row = {"name": a["data-workflow"], "sent": a.get("data-sent") or "", "for": a.get("data-for") or "", "packed": []}
                self.rows.append(self.row)
            elif tag == "pre" and self.row is not None and "bundle" in (a.get("class") or "").split():
                self.packed = True

        def handle_endtag(self, tag):
            if tag == "pre":
                self.packed = False
            elif tag == "li":
                self.row = None

        def handle_data(self, d):
            if self.packed and self.row is not None:
                self.row["packed"].append(d)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    p = Rows()
    p.feed(text)
    p.close()
    return [{**r, "packed": "".join(r["packed"]).strip()} for r in p.rows]


NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}-\d{8}-\d{6}$")


def received(kb) -> List[Dict[str, Any]]:
    """The workflows sent to the owner's page, the newest copy of each, newest first."""
    from .sources import inbox_file
    path = inbox_file(kb)
    if path is None:
        return []
    latest: Dict[str, Dict[str, Any]] = {}
    for r in _rows(path):
        if NAME_RE.match(r["name"]):
            latest[r["name"]] = r  # a later row is a newer copy
    return sorted(latest.values(), key=lambda r: r["sent"], reverse=True)


def take_received(kb) -> List[Dict[str, Any]]:
    """Unpack every workflow sent to the owner's page that is new, or newer than
    the copy taken before, into ~/.astaui/workflows/<its name>, where
    `astaui derive show <name>` opens it with the sender's marks, and keep it
    with the build it describes."""
    import hashlib
    state_path = kb.root / TAKEN
    state = _read(state_path, {}) or {}
    got: List[Dict[str, Any]] = []
    for r in received(kb):
        digest = hashlib.sha256(r["packed"].encode("ascii", "replace")).hexdigest()[:16]
        if (state.get(r["name"]) or {}).get("digest") == digest:
            continue
        try:
            files = unpack_workflow(r["packed"])
            info = json.loads(files.get("about.json", b"{}").decode("utf-8") or "{}")
            wf = json.loads(files["workflow.json"].decode("utf-8"))
        except (KBError, ValueError) as e:
            state[r["name"]] = {"digest": digest, "sent": r["sent"], "held": str(e)}
            continue
        bad = problems(wf)
        if bad:
            state[r["name"]] = {"digest": digest, "sent": r["sent"], "held": bad[0]}
            continue
        dest = WORKFLOWS / r["name"]
        if dest.exists():
            shutil.rmtree(dest)
        for name, data in files.items():
            f = dest / name
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(data)
        build = r["for"] if r["for"] and re.match(r"^[a-z0-9][a-z0-9-]*$", r["for"]) else (info.get("build") or None)
        _write(dest / "run.json", {"kind": "derived-workflow", "astaui": info.get("astaui"), "name": r["name"],
                                   "title": info.get("title"), "app": info.get("app"), "build": build,
                                   "sources": info.get("sources") or {}, "ui_run": info.get("ui_run") or {},
                                   "checked_by": info.get("checked_by") or "",
                                   "received": {"sent": r["sent"], "at": datetime.now().astimezone().isoformat(timespec="seconds")},
                                   "started": r["sent"]})
        state[r["name"]] = {"digest": digest, "sent": r["sent"], "build": build, "who": info.get("checked_by") or "",
                            "at": datetime.now().astimezone().isoformat(timespec="seconds")}
        got.append({"name": r["name"], "title": info.get("title"), "build": build, "who": info.get("checked_by") or "",
                    **tally(wf)})
    if state != (_read(state_path, {}) or {}):
        _write(state_path, state)
    attach_received(kb)
    return got


def attach(kb, build_id: str, run_dir: Path) -> Dict[str, Any]:
    """Keep a checked workflow in a build's folder (builds/<id>/derived/): its
    tree with every mark and note, its outline, and about.json. The screenshots
    stay with the derivation; filing, sending and publishing the build carry
    the rest."""
    folder = kb.builds_dir / build_id
    if not (folder / "build.json").is_file():
        raise KBError(f"There is no build {build_id} in {kb.root}.")
    wf = _read(run_dir / "workflow.json")
    if not isinstance(wf, dict):
        raise KBError(f"{run_dir.name} has no workflow yet.")
    meta = _read(run_dir / "run.json", {}) or {}
    info = about(run_dir)
    info.update({"build": build_id, "sent": (meta.get("received") or {}).get("sent") or (meta.get("sent") or {}).get("at")})
    out = folder / DERIVED
    out.mkdir(exist_ok=True)
    _write(out / "workflow.json", wf)
    (out / "workflow.md").write_text(outline(wf, meta), encoding="utf-8")
    _write(out / "about.json", info)
    return {"build": build_id, "folder": str(out), "workflow": run_dir.name, **tally(wf)}


def _stamp(info: Dict[str, Any]) -> str:
    return str(info.get("sent") or info.get("saved") or "")


def attach_received(kb) -> List[Dict[str, Any]]:
    """Copy each received workflow into the build it names, unless the build
    already holds a copy as new (a build re-sent replaces its folder, so this
    puts the workflow back)."""
    done = []
    have = set(kb.build_ids())
    for run_dir in runs():
        meta = _read(run_dir / "run.json", {}) or {}
        bid = meta.get("build")
        if not meta.get("received") or bid not in have:
            continue
        there = _read(kb.builds_dir / bid / DERIVED / "about.json", {}) or {}
        if there and _stamp(there) >= str(meta["received"].get("sent") or ""):
            continue
        done.append(attach(kb, bid, run_dir))
    return done


def for_folder(folder: Path) -> Optional[Path]:
    """The newest derivation of the app in this folder that has a workflow."""
    folder = folder.resolve()
    for r in reversed(runs()):
        meta = _read(r / "run.json", {}) or {}
        if meta.get("folder") and Path(meta["folder"]).resolve() == folder and (r / "workflow.json").is_file():
            return r
    return None
