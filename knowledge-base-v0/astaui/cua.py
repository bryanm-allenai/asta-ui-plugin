"""Workflow checks: how well a computer-use agent works out an interface's
workflow from using it alone, judged by the person who built it.

    astaui cua setup                       Playwright and its Chromium, once
    astaui cua run --url http://127.0.0.1:8000/ [--files DIR] [--name NAME]
    astaui cua review latest               the page where the person grades the tree
    astaui cua send latest                 the graded check, to the project's drive
    astaui cua list | summary RUN | line | received

A run is the collection's own explore stage (same brief, same browser, same
model), started on someone's app instead of a public repository: Claude Code in
print mode with a browser and no other tools, so it knows only what the
interface shows. Its record is a folder in ~/.astaui/checks/<name>-<time>/:
run.json, brief.md, tree.json, transcript.jsonl (images left out), trace.jsonl,
screens/, and review.json once the person grades it.
"""

from __future__ import annotations

import base64
import html
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tarfile
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
CHECKS = Path(os.environ.get("ASTAUI_CHECKS", Path.home() / ".astaui" / "checks"))
# The collection's explore stage: Opus 5.5 at high effort, about 60 actions.
MODEL = os.environ.get("ASTAUI_CUA_MODEL", "claude-opus-5-5")
EFFORT = os.environ.get("ASTAUI_CUA_EFFORT", "high")
ACTIONS = 60
BUDGET = 20.0
PLAYWRIGHT = "playwright@^1.50"
# The line someone pastes into their coding agent, in the folder of their app.
LINE = ("Set up AstaUI by running `curl -fsSL {raw}/install.py | python3 - --link {link}`, then follow its "
        "workflow-check skill (~/.agents/skills/workflow-check/SKILL.md) to test how well AstaUI's computer-use agent "
        "works out the workflow of the app in this folder from using it alone.")
GRADES = ("right", "partly", "wrong")


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
            "playwright": str(home) if _playwright_ok(home) else None, "checks": str(CHECKS)}


def setup(say=print) -> Dict[str, Any]:
    """Install Playwright and its Chromium into ~/.astaui/cua, unless they are there."""
    st = status()
    if not st["node"] or not st["npm"]:
        raise KBError("The agent's browser needs Node.js 18 or later (node and npm), which this computer does not have. "
                      "Install it from https://nodejs.org, then run `astaui cua setup` again.")
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
    feature one ("f1"), so a grade stays with its node."""
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


def run(url: str, files: Optional[str] = None, about: Optional[str] = None, name: Optional[str] = None,
        actions: int = ACTIONS, model: Optional[str] = None, quiet: bool = False, say=print) -> Dict[str, Any]:
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
        raise KBError("The agent's browser is not installed yet: run `astaui cua setup` first.")
    origin = _origin(url)
    problem = _reachable(url)
    if problem:
        raise KBError(f"Nothing answers at {url} ({problem}). Start the app first, and give the address it prints.")
    folder = None
    if files:
        folder = Path(files).expanduser().resolve()
        if not folder.is_dir():
            raise KBError(f"{files} is not a folder. --files takes a folder of test files the app may be given.")

    name = _slug(name or Path.cwd().name)
    run_dir = CHECKS / f"{name}-{datetime.now():%Y%m%d-%H%M%S}"
    for d in ("screens", "downloads"):
        (run_dir / d).mkdir(parents=True, exist_ok=True)
    if folder is None:
        folder = run_dir / "no-files"
        folder.mkdir()
    listed = sorted(p.name for p in folder.iterdir() if p.is_file() and not p.name.startswith("."))

    about_text = (f"What the person who built it says it is for, in one line: {about.strip()}" if about and about.strip()
                  else "")
    brief = (HERE / "cua_explore.md").read_text(encoding="utf-8")
    for k, v in {"{URL}": url, "{ORIGIN}": origin, "{ACTIONS}": str(actions), "{ABOUT}": about_text,
                 "{DATA}": ", ".join(listed) if listed else "there are none"}.items():
        brief = brief.replace(k, v)
    brief = re.sub(r"\n{3,}", "\n\n", brief)
    (run_dir / "brief.md").write_text(brief, encoding="utf-8")

    env_mcp = {"PILOT_SCREENS": str(run_dir / "screens"), "PILOT_DOWNLOADS": str(run_dir / "downloads"),
               "PILOT_FILES": str(folder), "PILOT_ORIGIN": origin, "PILOT_TRACE": str(run_dir / "trace.jsonl"),
               "PILOT_SHOT": "jpeg", "ASTAUI_PLAYWRIGHT": str(home)}
    mcp = {"mcpServers": {"browser": {"command": _which("node"), "args": [str(HERE / "cua_browser.mjs")], "env": env_mcp}}}
    (run_dir / "mcp.json").write_text(json.dumps(mcp, indent=1))

    model = model or MODEL
    meta: Dict[str, Any] = {"kind": "workflow-check", "astaui": __version__, "name": name, "url": url, "origin": origin,
                            "about": about or None, "files": listed, "model": model, "effort": EFFORT,
                            "actions_asked": actions, "started": datetime.now().astimezone().isoformat(timespec="seconds"),
                            "status": "running", "folder": str(Path.cwd())}
    (run_dir / "run.json").write_text(json.dumps(meta, indent=1))

    flags = _claude_flags(claude)
    cmd = [claude, "-p", brief, "--model", model, "--tools", "", "--mcp-config", str(run_dir / "mcp.json"),
           "--strict-mcp-config", "--allowedTools", "mcp__browser__*", "--permission-mode", "dontAsk",
           "--output-format", "stream-json", "--verbose"]
    for flag, extra in (("--effort", [EFFORT]), ("--no-session-persistence", []), ("--disable-slash-commands", []),
                        ("--max-budget-usd", [str(BUDGET)])):
        if not flags or flag in flags:
            cmd += [flag, *extra]
    env = {**os.environ, "MCP_TIMEOUT": "400000"}

    say(f"The agent is exploring {url}. It takes about 10 to 20 minutes; its record goes in {run_dir}.")
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
            meta.update(status="stopped", seconds=round(time.time() - started))
            (run_dir / "run.json").write_text(json.dumps(meta, indent=1))
            raise KBError(f"The run was stopped; what it did so far is in {run_dir}.")

    meta.update(seconds=round(time.time() - started), browser_calls=calls,
                screens=len(list((run_dir / "screens").glob("*"))))
    text = (result or {}).get("result") or ""
    if result:
        meta.update(cost_usd=result.get("total_cost_usd"), turns=result.get("num_turns"))
    tree = last_json(text) if text else None
    if not tree or not isinstance(tree.get("tree"), dict):
        meta["status"] = "failed"
        why = (text.strip()[:400] or (run_dir / "agent.log").read_text(errors="replace").strip()[-400:]
               or "the agent ended without an answer")
        meta["error"] = why
        (run_dir / "run.json").write_text(json.dumps(meta, indent=1))
        raise KBError(f"The agent did not write a workflow tree. What it said: {why}\nIts record is in {run_dir}.")
    number(tree)
    (run_dir / "tree.json").write_text(json.dumps(tree, indent=1))
    meta.update(status="done", finished=datetime.now().astimezone().isoformat(timespec="seconds"),
                title=(tree.get("interface") or {}).get("title"), **shape(tree))
    (run_dir / "run.json").write_text(json.dumps(meta, indent=1))
    return {"run": str(run_dir), **meta}


# -- finding runs ---------------------------------------------------------------------------------

def runs() -> List[Path]:
    if not CHECKS.is_dir():
        return []
    return sorted((p for p in CHECKS.iterdir() if (p / "run.json").is_file()), key=lambda p: p.name[-15:])


def resolve(which: Optional[str]) -> Path:
    """A run folder from a path, a folder name in ~/.astaui/checks, `latest`, or
    `latest` of one app's name."""
    which = which or "latest"
    p = Path(which).expanduser()
    if (p / "run.json").is_file():
        return p.resolve()
    if (CHECKS / which / "run.json").is_file():
        return CHECKS / which
    done = [r for r in runs() if (r / "tree.json").is_file()]
    if which == "latest":
        if done:
            return done[-1]
        raise KBError(f"There is no finished run in {CHECKS} yet: `astaui cua run --url …` makes one.")
    named = [r for r in done if r.name.rsplit("-", 2)[0] == _slug(which)]
    if named:
        return named[-1]
    raise KBError(f"No run called {which} in {CHECKS}; `astaui cua list` shows them.")


def _read(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


# -- what the person said --------------------------------------------------------------------------

def _nodes(tree: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    def walk(n):
        out.append(n)
        for c in n.get("children") or []:
            walk(c)
    if isinstance(tree.get("tree"), dict):
        walk(tree["tree"])
    return out


def summary(run_dir: Path) -> Dict[str, Any]:
    """The person's grades in numbers: per kind, how many they marked right,
    partly or wrong, what it missed, and their overall answers."""
    tree = _read(run_dir / "tree.json", {}) or {}
    review = _read(run_dir / "review.json", {}) or {}
    grades = review.get("grades") or {}
    kinds: Dict[str, List[Dict[str, Any]]] = {"goal": [], "phase": [], "task": [], "feature": []}
    for n in _nodes(tree):
        if n.get("kind") in kinds:
            kinds[n["kind"]].append(n)
    kinds["feature"] = list(tree.get("features") or [])
    out: Dict[str, Any] = {"by_kind": {}}
    for kind, items in kinds.items():
        c = {"total": len(items), "right": 0, "partly": 0, "wrong": 0}
        for n in items:
            g = (grades.get(n.get("id")) or {}).get("grade")
            if g in GRADES:
                c[g] += 1
        graded = c["right"] + c["partly"] + c["wrong"]
        c["graded"] = graded
        c["accuracy"] = round((c["right"] + 0.5 * c["partly"]) / graded, 3) if graded else None
        out["by_kind"][kind] = c
    missed = [m for m in review.get("missed") or [] if (m.get("text") or "").strip()]
    out["missed_tasks"] = sum(1 for m in missed if m.get("kind") != "feature")
    out["missed_features"] = sum(1 for m in missed if m.get("kind") == "feature")
    t = out["by_kind"]["task"]
    # Of the tasks the interface really supports (the ones it got right or
    # partly, and the ones the person added), how many the agent found.
    found = t["right"] + 0.5 * t["partly"]
    out["task_recall"] = round(found / (t["right"] + t["partly"] + out["missed_tasks"]), 3) \
        if (t["right"] + t["partly"] + out["missed_tasks"]) else None
    out["overall"] = review.get("overall") or {}
    limits = review.get("limits") or {}
    out["limits"] = {"interface": sum(1 for v in limits.values() if v == "interface"),
                     "agent": sum(1 for v in limits.values() if v == "agent")}
    out["done"] = bool(review.get("done"))
    return out


def summary_words(s: Dict[str, Any]) -> str:
    t, ph, f = s["by_kind"]["task"], s["by_kind"]["phase"], s["by_kind"]["feature"]
    parts = []
    if t["graded"]:
        parts.append(f"tasks {t['right']} right, {t['partly']} partly, {t['wrong']} wrong of {t['total']}")
    if ph["graded"]:
        parts.append(f"phases {ph['right']}/{ph['total']} right")
    if f["graded"]:
        parts.append(f"features {f['right']}/{f['total']} right")
    if s["missed_tasks"] or s["missed_features"]:
        mt, mf = s["missed_tasks"], s["missed_features"]
        parts.append(f"missed {mt} task{'' if mt == 1 else 's'}, {mf} feature{'' if mf == 1 else 's'}")
    o = s.get("overall") or {}
    if o.get("point"):
        parts.append(f"purpose {o['point']}/5")
    if o.get("coverage"):
        parts.append(f"coverage {o['coverage']}/5")
    return "; ".join(parts) or "not graded yet"


# -- the review page ------------------------------------------------------------------------------

def page() -> str:
    text = (HERE / "cua_review.html").read_text(encoding="utf-8")
    return text.replace("/*__ASTA__*/", (HERE / "asta.css").read_text(encoding="utf-8"))


SCREEN_RE = re.compile(r"^[A-Za-z0-9_.-]+\.(?:jpe?g|png|webp)$")


def _handler(run_dir: Path, link: Optional[str]):
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj: Any):
            self._send(code, json.dumps(obj).encode("utf-8"), "application/json")

        def do_GET(self):
            path = urllib.parse.urlparse(self.path).path
            if path in ("/", "/index.html"):
                return self._send(200, page().encode("utf-8"), "text/html; charset=utf-8")
            if path == "/data":
                run = _read(run_dir / "run.json", {})
                return self._json(200, {"run": run, "tree": _read(run_dir / "tree.json", {}),
                                        "review": _read(run_dir / "review.json", {}),
                                        "brief": (run_dir / "brief.md").read_text(encoding="utf-8") if (run_dir / "brief.md").is_file() else "",
                                        "can_send": bool(link), "summary": summary(run_dir)})
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
            if path == "/review":
                if not isinstance(body, dict):
                    return self._json(400, {"error": "a review is an object"})
                with lock:
                    body["saved"] = datetime.now().astimezone().isoformat(timespec="seconds")
                    tmp = run_dir / "review.json.tmp"
                    tmp.write_text(json.dumps(body, indent=1), encoding="utf-8")
                    tmp.replace(run_dir / "review.json")
                return self._json(200, {"ok": True, "saved": body["saved"], "summary": summary(run_dir)})
            if path == "/send":
                try:
                    with lock:
                        res = send(run_dir, link)
                except KBError as e:
                    return self._json(200, {"ok": False, "error": str(e)})
                return self._json(200, {"ok": True, **res})
            return self._json(404, {"error": "no such thing"})

    return Handler


def serve(run_dir: Path, port: int = 0, open_browser: bool = True, link: Optional[str] = None, say=print) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), _handler(run_dir, link))
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    (run_dir / "review-address.txt").write_text(url)
    say(f"The review page for {run_dir.name} is at {url}")
    say("Grades are saved as they are made, into review.json in that folder. Stop this with Ctrl-C when you are done.")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


# -- sending it to the project ---------------------------------------------------------------------

def _who() -> str:
    try:
        name = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        name = ""
    return name or "No name given"


def pack(run_dir: Path) -> bytes:
    """The check as one gzipped tar: what the agent was told, what it wrote, the
    screens it cites, and the person's grades. Not the transcript or the trace,
    which can hold the app's own data."""
    tree = _read(run_dir / "tree.json", {}) or {}
    cited = set()

    def cite(obj):
        if isinstance(obj, dict):
            for v in obj.values():
                cite(v)
        elif isinstance(obj, list):
            for v in obj:
                cite(v)
        elif isinstance(obj, str) and obj.startswith("screens/"):
            cited.add(obj[len("screens/"):])
    cite(tree)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for name in ("run.json", "brief.md", "tree.json", "review.json"):
            f = run_dir / name
            if f.is_file():
                if name == "run.json":
                    run = _read(f, {})
                    run.pop("folder", None)  # a path on their computer
                    data = json.dumps(run, indent=1).encode("utf-8")
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    t.addfile(info, io.BytesIO(data))
                else:
                    t.add(f, arcname=name)
        for name in sorted(cited):
            f = run_dir / "screens" / name
            if SCREEN_RE.match(name) and f.is_file():
                t.add(f, arcname=f"screens/{name}")
    return buf.getvalue()


def send(run_dir: Path, link: Optional[str]) -> Dict[str, Any]:
    from .sources import INBOX_MAX, post_row

    if not link:
        raise KBError("There is no link to send it to. The line from the project has one; "
                      "`astaui config inbox-link <link>` keeps it.")
    review = _read(run_dir / "review.json", {}) or {}
    if not review.get("grades"):
        raise KBError("Nothing is graded yet: grade the tree on the review page first.")
    run = _read(run_dir / "run.json", {}) or {}
    packed = pack(run_dir)
    if len(packed) > INBOX_MAX:
        raise KBError("The check is too big to send at once.")
    s = summary(run_dir)
    sent = datetime.now().astimezone()
    check_id = "check-" + (re.sub(r"[^a-z0-9]+", "-", run_dir.name.lower()).strip("-") or "run")
    e = lambda v: html.escape(str(v), quote=True)  # noqa: E731
    who = review.get("name") or _who()
    title = run.get("title") or run.get("name") or run_dir.name
    row = (f'<li data-marble-removable data-check="{e(check_id)}" data-sent="{e(sent.isoformat(timespec="seconds"))}">'
           f'<b>Workflow check: {e(title)}</b><span class="when">{e(f"{sent:%b} {sent.day}, {sent:%H:%M}")}</span>'
           f'<span class="who">{e(who)} · {e(summary_words(s))}</span>'
           f'<span class="id">{e(check_id)} · {e(max(1, round(len(packed) / 1024)))} KB</span>'
           f'<pre class="bundle" hidden>{base64.b64encode(packed).decode("ascii")}</pre></li>')
    where = post_row(link, row)
    review["sent"] = sent.isoformat(timespec="seconds")
    (run_dir / "review.json").write_text(json.dumps(review, indent=1), encoding="utf-8")
    return {"id": check_id, "bytes": len(packed), **where}


# -- the owner's side -----------------------------------------------------------------------------

def received(inbox: Path, into: Path) -> List[Dict[str, Any]]:
    """Unpack every check sent to the owner's page into `into`/<check id>/, and
    say what each one found."""
    from html.parser import HTMLParser

    class Rows(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.rows, self.row, self.packed = [], None, False

        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            if tag == "li" and a.get("data-check"):
                self.row = {"id": a["data-check"], "sent": a.get("data-sent") or "", "packed": []}
                self.rows.append(self.row)
            elif tag == "pre" and self.row is not None and "bundle" in (a.get("class") or "").split():
                self.packed = True

        def handle_endtag(self, tag):
            if tag == "pre":
                self.packed = False
            elif tag == "li":
                self.row = None

        def handle_data(self, data):
            if self.packed and self.row is not None:
                self.row["packed"].append(data)

    p = Rows()
    p.feed(inbox.read_text(encoding="utf-8"))
    out = []
    for r in p.rows:
        cid = r["id"]
        if not re.match(r"^check-[a-z0-9-]+$", cid):
            continue
        dest = into / cid
        if not (dest / "tree.json").is_file():
            data = base64.b64decode("".join(r["packed"]).strip() or b"")
            dest.mkdir(parents=True, exist_ok=True)
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as t:
                for m in t.getmembers():
                    ok = m.isfile() and (m.name in ("run.json", "brief.md", "tree.json", "review.json")
                                         or (m.name.startswith("screens/") and SCREEN_RE.match(m.name[8:])))
                    if ok and m.size < 20 * 1024 * 1024:
                        (dest / m.name).parent.mkdir(parents=True, exist_ok=True)
                        (dest / m.name).write_bytes(t.extractfile(m).read())
        run = _read(dest / "run.json", {}) or {}
        review = _read(dest / "review.json", {}) or {}
        out.append({"id": cid, "sent": r["sent"], "title": run.get("title"), "who": review.get("name"),
                    "folder": str(dest), "summary": summary(dest)})
    return out
