"""Where the builds come from, and how a scientist sends one in.

A scientist files an interface they built with the plugin's ui-to-workflow
skill and sends it back one of two ways. If the owner has made an Add only link
to a page in their Marble drive (Builds sent in), the line carries it, and the
build is added to that page as one row (send): the link can add a row and
nothing else, so it cannot read what others sent, and sending needs no access
to the repository. Otherwise they push it from a clone of this repository as a
branch named add-<its id>.

The link travels in the line, never in the plugin, so the plugin can be
public. The first build sent through it leaves it in the scientist's own
astaui settings, and later ones go there without being given it again. The
plugin may install from a public copy of this repository (kb.json's
"plugin"), which holds the code, the skills and the invented builds only.

This module writes the one line that does all of that from a terminal
(share_line), lists the builds the page and those branches carry that this
knowledge base lacks or has an older copy of (incoming), copies the knowledge
base with one of them in it, so it can be checked without touching this one
(review), and brings it in once it passes (take). On the owner's computer,
intake does the last two by itself for everything sent to the page; the
console's hourly run calls it, so a build is in the knowledge base and its
index within the hour. Only send, fetch and checking a link reach the network.
"""

from __future__ import annotations

import base64
import hashlib
import html
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import __version__
from .kb import ID_RE, KB, KBError, check_id, read_json, set_user_config, user_config, write_json

BRANCH_PREFIX = "add-"
SKILL = "ui-to-workflow"
ASK = "File the app I built in this folder into AstaUI with the {plugin}:{skill} skill."
# The line for any coding agent: a request the person pastes into the agent
# they use, which runs the installer (it needs only Python) and then files.
ANY_AGENT = ("Set up AstaUI by running `curl -fsSL {raw}/install.py | python3 - --link {link}`, then follow its "
             "ui-to-workflow skill (~/.agents/skills/ui-to-workflow/SKILL.md) to file the app I built in this folder.")
SEND = " Send it to {link}"
# The page in the owner's drive that builds are sent to, and the list on it a
# row is added to. An Add only link may add only to the end of a list the page
# marks as open to changes, so the page marks this one.
INBOX = "Builds sent in.mrbl"
INBOX_LIST = "sent-builds"
# The drive takes 16 MB in one request, and base64 makes the packed build a
# third bigger, so a build packs to 12 MB at most.
INBOX_MAX = 12 * 1024 * 1024
# What a build unpacks to, at most, on the owner's side: a row is whatever
# someone with the link chose to send.
UNPACK_MAX = 200 * 1024 * 1024
LINK_RE = re.compile(r"^(https?://[^/\s?#]+)/s/([A-Za-z0-9_-]{38})/?$")
AGENT = f"astaui/{__version__}"
# What the line lets the session run without asking: the astaui tool, wherever
# the plugin manager put it.
ALLOW = "Bash(python3 *astaui_cli.py*)"
# What the owner's computer remembers of the builds it took from the drive, so
# a build sent again replaces the one it took, and one that cannot be taken
# says why. A cache beside the index: losing it loses no build.
INTAKE = ".intake.json"


def _git(repo: Path, *args: str, timeout: int = 30, check: bool = True) -> str:
    try:
        r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        if check:
            raise KBError(f"git {' '.join(args)}: {e}") from e
        return ""
    if r.returncode != 0:
        if check:
            raise KBError(f"git {' '.join(args)}: {(r.stderr or r.stdout).strip()}")
        return ""
    return r.stdout


def _has(repo: Path, obj: str) -> bool:
    try:
        return subprocess.run(["git", "-C", str(repo), "cat-file", "-e", obj], capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _json_at(repo: Path, obj: str) -> Optional[Dict[str, Any]]:
    text = _git(repo, "show", obj, check=False)
    try:
        data = json.loads(text) if text else None
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def repo_of(kb: KB) -> Optional[Path]:
    """The git repository the knowledge base is in, or None (a plugin manager's copy is in none)."""
    top = _git(kb.root, "rev-parse", "--show-toplevel", check=False).strip()
    return Path(top) if top else None


def _rel(kb: KB, repo: Path) -> str:
    return kb.root.resolve().relative_to(repo.resolve()).as_posix()


def github_slug(url: str) -> Optional[str]:
    """owner/repo from a GitHub remote, over https or ssh (an ssh host alias included)."""
    m = re.search(r"[:/]([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", (url or "").strip())
    return f"{m.group(1)}/{m.group(2)}" if m else None


def plugin_branch(repo: Path) -> Optional[str]:
    """The branch a plugin manager should take the plugin from: none when the
    repository's default branch has the marketplace, else the branch this
    checkout follows, or the one it is on."""
    marketplace = ".claude-plugin/marketplace.json"
    head = _git(repo, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD", check=False).strip()
    if head and _has(repo, f"{head}:{marketplace}"):
        return None
    up = _git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", check=False).strip()
    if up.startswith("origin/") and _has(repo, f"{up}:{marketplace}"):
        return up[len("origin/"):]
    return _git(repo, "branch", "--show-current", check=False).strip() or None


def share_line(kb: KB) -> Dict[str, Any]:
    """The line a scientist pastes into a terminal in the folder of an app they
    built: it installs the plugin from GitHub (from the branch that has it, while
    the default branch does not) and starts Claude Code on the filing skill.
    Running it again is harmless: both installs answer that they are done."""
    repo = repo_of(kb)
    plugin_root = kb.root.parent
    plugin = _read_json(plugin_root / ".claude-plugin" / "plugin.json")
    market = _read_json((repo or plugin_root.parent) / ".claude-plugin" / "marketplace.json")
    plugin_name = ((market.get("plugins") or [{}])[0] or {}).get("name") or plugin.get("name") or "asta-ui"
    market_name = market.get("name") or plugin_name
    slug = branch = None
    public = kb.config.get("plugin") or {}
    if public.get("repo"):
        # A public copy of the plugin: anyone can install it, so nobody needs access.
        slug, branch = public["repo"], public.get("branch")
    elif repo:
        slug = github_slug(_git(repo, "remote", "get-url", "origin", check=False))
        branch = plugin_branch(repo) if slug else None
    slug = slug or github_slug(plugin.get("repository") or "")
    link = inbox_link(kb)
    if not slug:
        return {"line": None, "repo": None, "branch": None, "url": None, "access": None, "link": link}
    if public.get("repo") and link:
        # Any agent: the person pastes the request into the agent they use.
        raw = f"https://raw.githubusercontent.com/{slug}/{branch or 'main'}"
        return {"line": ANY_AGENT.format(raw=raw, link=link), "any_agent": True, "repo": slug, "branch": branch,
                "url": f"https://github.com/{slug}", "access": None, "link": link}
    ask = ASK.format(plugin=plugin_name, skill=SKILL) + (SEND.format(link=link) if link else "")
    # Adding and installing again are harmless; the two updates bring a copy
    # installed before up to the one on GitHub. The prompt goes before
    # --allowedTools, which takes every word after it.
    plugin_id = f"{plugin_name}@{market_name}"
    line = (f"claude plugin marketplace add {slug}{'#' + branch if branch else ''} && "
            f"claude plugin marketplace update {market_name} && claude plugin install {plugin_id} && "
            f"claude plugin update {plugin_id} && claude \"{ask}\" --allowedTools \"{ALLOW}\"")
    return {"line": line, "any_agent": False, "repo": slug, "branch": branch, "url": f"https://github.com/{slug}",
            "access": None if public.get("repo") else f"https://github.com/{slug}/settings/access", "link": link}


# -- the owner's drive ---------------------------------------------------------------------------

def drive_root(path: Path) -> Optional[Path]:
    """The Marble drive a folder is in (the folder above it that holds .marble), or None."""
    for d in [path.resolve(), *path.resolve().parents]:
        if (d / ".marble").is_dir():
            return d
    return None


def inbox_link(kb: Optional[KB] = None) -> Optional[str]:
    """The Add only link builds are sent through: the one this computer has (the
    owner's, or the one a scientist's first build went through), or else one
    the knowledge base names."""
    return user_config().get("inbox-link") or ((kb.config.get("inbox") or None) if kb else None)


def inbox_file(kb: KB) -> Optional[Path]:
    """The page builds are sent to, as a file on this computer: the one the link
    was checked against, or else Builds sent in in the nearest folder above the
    knowledge base, inside the drive it is in."""
    named = user_config().get("inbox")
    if named and Path(named).is_file():
        return Path(named)
    root = drive_root(kb.root)
    if root is None:
        return None
    for d in [kb.root.resolve(), *kb.root.resolve().parents]:
        if (d / INBOX).is_file():
            return d / INBOX
        if d == root:
            break
    return None


def inbox_page(kb: KB) -> Optional[str]:
    """The inbox's path in the drive, as an /a/ address opens it, or None."""
    f = inbox_file(kb)
    root = drive_root(f.parent) if f else None
    if not f or not root:
        return None
    return f.relative_to(root).with_suffix("").as_posix()


def public_link(link: str, public: Optional[str] = None) -> str:
    """The link as someone off this computer opens it. The drive's Share panel
    hands out its own address, which is 127.0.0.1 when it is open on this
    computer; `public` is the address it answers at from outside."""
    m = LINK_RE.match((link or "").strip())
    if not m:
        raise KBError("That is not a share link from a Marble drive: it looks like https://<the drive>/s/<38 letters and digits>")
    host = urllib.parse.urlsplit(m.group(1)).hostname or ""
    if host in ("127.0.0.1", "localhost", "::1") or host.startswith("127."):
        if not public:
            raise KBError("That link works only on this computer. Give the address the drive answers at from outside with --public.")
        return f"{public.rstrip('/')}/s/{m.group(2)}"
    return f"{m.group(1)}/s/{m.group(2)}"


class _Stay(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # the redirect is the answer, not a page to follow
        return None


def open_link(link: str) -> Dict[str, str]:
    """Trade an Add only link for what adding through it takes: the drive's
    address, the page it adds to, and the cookie the drive hands for it. The
    drive answers a link with a redirect to its page and the cookie; a link
    that is off answers 404."""
    m = LINK_RE.match((link or "").strip())
    if not m:
        raise KBError("That is not a share link from a Marble drive: it looks like https://<the drive>/s/<38 letters and digits>")
    origin = m.group(1)
    req = urllib.request.Request(link.strip(), headers={"User-Agent": AGENT, "Accept": "application/json"})
    try:
        res = urllib.request.build_opener(_Stay).open(req, timeout=30)
        status, headers = res.status, res.headers
    except urllib.error.HTTPError as e:
        status, headers = e.code, e.headers
        e.close()
    except (urllib.error.URLError, OSError) as e:
        raise KBError(f"Could not reach {origin}: {getattr(e, 'reason', e)}") from e
    where = headers.get("Location") or ""
    if status not in (301, 302, 303, 307, 308) or not where.startswith("/a/"):
        raise KBError("The link opens nothing: whoever made it may have turned it off. Ask for the line again.")
    cookie = "; ".join(c.split(";", 1)[0] for c in (headers.get_all("Set-Cookie") or []))
    page = urllib.parse.unquote(where[3:].split("?", 1)[0].split("#", 1)[0])
    return {"origin": origin, "page": page, "cookie": cookie}


def _plain(info: tarfile.TarInfo) -> Optional[tarfile.TarInfo]:
    """Files and folders only, owned by nobody in particular."""
    if not (info.isfile() or info.isdir()):
        return None
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    return info


def pack(kb: KB, build_id: str) -> bytes:
    """A filed build and its card, as one gzipped tar: builds/<id>/… and cards/<id>.json."""
    check_id(build_id, "build id")
    folder = kb.builds_dir / build_id
    if not (folder / "build.json").is_file():
        raise KBError(f"There is no build {build_id} in {kb.root}: file it with `astaui add` first")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        t.add(folder, arcname=f"builds/{build_id}", filter=_plain)
        card = kb.card_path(build_id)
        if card.is_file():
            t.add(card, arcname=f"cards/{build_id}.json", filter=_plain)
    return buf.getvalue()


def _row(build_id: str, meta: Dict[str, Any], packed: bytes, sent: datetime) -> str:
    """The row a sent build is on the owner's page: what it is, who sent it and
    when, for the owner to read, and the build itself, packed, out of sight.
    Nothing in it may be markup the scientist wrote: the drive refuses a row
    with a tag it did not expect, and escaping keeps their words words."""
    a = meta.get("author") or {}
    who = ", ".join(str(x) for x in (a.get("name"), a.get("role"), a.get("field")) if x) or "No name given"
    see = {"team": "the project team", "public": "anyone"}.get((meta.get("provenance") or {}).get("consent"), "")
    size = f"{max(1, round(len(packed) / 1024))} KB"
    when = f"{sent:%b} {sent.day}, {sent:%H:%M}"
    e = lambda v: html.escape(str(v), quote=True)  # noqa: E731
    return (f'<li data-marble-removable data-build="{e(build_id)}" data-sent="{e(sent.isoformat(timespec="seconds"))}">'
            f'<b>{e(meta.get("title") or build_id)}</b><span class="when">{e(when)}</span>'
            f'<span class="who">{e(who)}{" · for " + e(see) if see else ""}</span>'
            f'<span class="id">{e(build_id)} · {e(size)}</span>'
            f'<pre class="bundle" hidden>{base64.b64encode(packed).decode("ascii")}</pre></li>')


def send(kb: KB, build_id: str, link: Optional[str] = None) -> Dict[str, Any]:
    """Add a filed build to the owner's page through their Add only link (the
    one the plugin carries, unless another is given)."""
    link = link or inbox_link(kb)
    if not link:
        raise KBError("There is no link to send it to yet. The line from the knowledge base's owner has one: "
                      "send this build with --to <that link> once, and later builds go there by themselves.")
    packed = pack(kb, build_id)
    if len(packed) > INBOX_MAX:
        raise KBError(f"{build_id} packs to {len(packed) // (1024 * 1024)} MB, more than the drive takes at once. "
                      f"`astaui slim {build_id}` keeps only the files its card points at.")
    try:
        meta = json.loads((kb.builds_dir / build_id / "build.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise KBError(f"{build_id}'s build.json does not read: {e}") from e
    door = open_link(link)
    op = {"type": "insert", "parentId": INBOX_LIST, "beforeId": None,
          "html": _row(build_id, meta, packed, datetime.now().astimezone())}
    url = f"{door['origin']}/ops?app={urllib.parse.quote(door['page'], safe='')}"
    req = urllib.request.Request(url, data=json.dumps([op]).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "Cookie": door["cookie"],
                                          "Origin": door["origin"], "User-Agent": AGENT})
    try:
        answer = json.loads(urllib.request.urlopen(req, timeout=300).read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            said = json.loads(e.read() or b"{}").get("error")
        except (ValueError, OSError):
            said = None
        e.close()
        raise KBError(f"The drive turned the build away ({e.code}): {said or e.reason}") from e
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise KBError(f"Could not send it to {door['origin']}: {getattr(e, 'reason', e)}") from e
    if not answer.get("ok"):
        raise KBError(f"The drive did not take the build: {answer.get('error') or answer}")
    remember_filed(build_id)
    if user_config().get("inbox-link") != link and not user_config().get("inbox"):
        # A scientist's computer: later builds go where this one went. (The
        # owner's computer keeps the link it was given with its page.)
        set_user_config("inbox-link", link)
    return {"id": build_id, "bytes": len(packed), "page": door["page"], "drive": door["origin"]}


def remember_filed(build_id: str, folder: Optional[Path] = None) -> None:
    """Note which build this folder was filed as, so filing it again sends a newer
    copy of the same build instead of a second one."""
    filed = dict(user_config().get("filed") or {})
    filed[str((folder or Path.cwd()).resolve())] = build_id
    set_user_config("filed", filed)


def filed_as(folder: Optional[Path] = None) -> Optional[str]:
    """The build this folder was filed as before, if it was."""
    return (user_config().get("filed") or {}).get(str((folder or Path.cwd()).resolve()))


class _Rows(HTMLParser):
    """The rows on the owner's page: each sent build's id, when it came, and its packed text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: List[Dict[str, Any]] = []
        self._row: Optional[Dict[str, Any]] = None
        self._packed = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "li" and a.get("data-build"):
            self._row = {"id": a["data-build"], "sent": a.get("data-sent") or "", "packed": []}
            self.rows.append(self._row)
        elif tag == "pre" and self._row is not None and "bundle" in (a.get("class") or "").split():
            self._packed = True

    def handle_endtag(self, tag):
        if tag == "pre":
            self._packed = False
        elif tag == "li":
            self._row = None

    def handle_data(self, data):
        if self._packed and self._row is not None:
            self._row["packed"].append(data)


def _sent_rows(path: Path) -> List[Dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    p = _Rows()
    p.feed(text)
    p.close()
    return [{**r, "packed": "".join(r["packed"]).strip()} for r in p.rows]


def _unpack(packed: str, build_id: str) -> Dict[str, bytes]:
    """The files a row carries, by their path in a knowledge base: builds/<id>/…
    and cards/<id>.json, and nothing else, however the row was made."""
    try:
        raw = base64.b64decode(packed, validate=True)
        t = tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz")
    except (ValueError, tarfile.TarError, OSError) as e:
        raise KBError(f"{build_id} did not arrive whole: {e}") from e
    out: Dict[str, bytes] = {}
    total = 0
    with t:
        for m in t.getmembers():
            name = m.name[2:] if m.name.startswith("./") else m.name
            if not m.isfile() or ".." in Path(name).parts or Path(m.name).is_absolute():
                continue
            if not (name.startswith(f"builds/{build_id}/") or name == f"cards/{build_id}.json"):
                continue
            total += m.size
            if total > UNPACK_MAX:
                raise KBError(f"{build_id} unpacks to more than {UNPACK_MAX // (1024 * 1024)} MB")
            src = t.extractfile(m)
            out[name] = src.read() if src else b""
    if f"builds/{build_id}/build.json" not in out:
        raise KBError(f"{build_id} arrived without its build.json")
    return out


def _when(text: str) -> datetime:
    """A row's sent time, comparable across rows (they carry their sender's offset)."""
    try:
        t = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=timezone.utc)
    return t if t.tzinfo else t.astimezone()


def _state(kb: KB) -> Dict[str, Dict[str, Any]]:
    """What intake remembers: the builds it took from the page ("taken": the id
    each was sent as, by whom and when) and the ones it could not ("held": why)."""
    path = kb.root / INTAKE
    try:
        data = read_json(path) if path.is_file() else {}
    except KBError:
        data = {}
    return {"taken": dict(data.get("taken") or {}), "held": dict(data.get("held") or {})}


def _who(meta: Dict[str, Any]) -> str:
    return str((meta.get("author") or {}).get("name") or "").strip()


def _sent(kb: KB, have: set) -> Dict[str, Dict[str, Any]]:
    """The builds on the owner's page that this knowledge base lacks, or has an
    older copy of, newest first. A build is its id and who sent it: the newest
    row of each is the one that counts. One sent again replaces the copy intake
    took; one that takes an id someone else's build has comes in as <id>-2."""
    path = inbox_file(kb)
    if path is None:
        return {}
    state = _state(kb)
    taken, held = state["taken"], state["held"]
    # The newest row of each build, in the order the builds first came, so the
    # first to send an id keeps it.
    latest: Dict[tuple, Dict[str, Any]] = {}
    for n, r in enumerate(_sent_rows(path)):
        i = r["id"]
        if not ID_RE.match(i):
            continue
        try:
            files = _unpack(r["packed"], i)
            meta = json.loads(files[f"builds/{i}/build.json"].decode("utf-8"))
        except (KBError, ValueError):
            continue
        if not isinstance(meta, dict):
            continue
        key = (i, _who(meta))
        first = latest[key]["first"] if key in latest else n
        latest[key] = {"row": r, "meta": meta, "card": f"cards/{i}.json" in files, "first": first, "n": n}
    found: Dict[str, Dict[str, Any]] = {}
    claimed = set(have)
    for (i, who), got in sorted(latest.items(), key=lambda kv: kv[1]["first"]):
        r, meta = got["row"], got["meta"]
        digest = hashlib.sha256(r["packed"].encode("ascii", "replace")).hexdigest()[:16]
        mine = next((k for k, t in taken.items() if t.get("id", k) == i and t.get("author", "") == who), None)
        if mine is not None:
            was, now = _when(taken[mine].get("sent", "")), _when(r["sent"])
            # Sent in the same second as the one taken counts if it is not the same build.
            if now < was or (now == was and digest == taken[mine].get("digest")):
                claimed.add(mine)
                continue
            target = mine
        else:
            target, n = i, 2
            while target in claimed:
                target = f"{i[:60]}-{n}"
                n += 1
        claimed.add(target)
        hold = held.get(target) or {}
        same = hold.get("sent") == r["sent"] and hold.get("digest", digest) == digest
        found[target] = {"id": target, "as": i, "replaces": target if target in have else None,
                         "via": "drive", "branch": None, "ref": None, "page": inbox_page(kb) or path.stem,
                         "sent": (r["sent"] or "")[:10], "sent_at": r["sent"], "digest": digest, "title": meta.get("title") or i,
                         "author": meta.get("author") or {}, "provenance": meta.get("provenance") or {},
                         "created": meta.get("created"), "card": got["card"],
                         "held": hold.get("why") if same else None, "_n": got["n"]}
    order = sorted(found.values(), key=lambda w: -w.pop("_n"))
    return {w["id"]: w for w in order}


def looked(repo: Path) -> Optional[datetime]:
    """When this checkout last fetched from its remote, or None if it never has."""
    path = _git(repo, "rev-parse", "--git-path", "FETCH_HEAD", check=False).strip()
    if not path:
        return None
    p = Path(path) if os.path.isabs(path) else repo / path
    try:
        return datetime.fromtimestamp(p.stat().st_mtime).astimezone()
    except OSError:
        return None


def incoming(kb: KB, fetch: bool = False) -> Dict[str, Any]:
    """The builds sent to the owner's page and on add-* branches of the remote
    that this knowledge base lacks, newest first, the page's first. With fetch,
    the branches are fetched first (and ones deleted on the remote are let go);
    the page is a file here, so it is always read as it is."""
    repo = repo_of(kb)
    have = set(kb.build_ids())
    found = _sent(kb, have)
    inbox = inbox_file(kb)
    if repo is None:
        return {"repo": None, "inbox": str(inbox) if inbox else None,
                "looked": datetime.now().astimezone() if inbox else None, "waiting": list(found.values())}
    if fetch:
        _git(repo, "fetch", "--prune", "origin", f"+refs/heads/{BRANCH_PREFIX}*:refs/remotes/origin/{BRANCH_PREFIX}*", timeout=180)
    rel = _rel(kb, repo)
    refs = _git(repo, "for-each-ref", "--sort=-committerdate", "--format=%(refname:short)\t%(committerdate:short)",
                f"refs/remotes/origin/{BRANCH_PREFIX}*", check=False)
    for line in refs.splitlines():
        ref, _, sent = line.partition("\t")
        if not ref:
            continue
        for i in _git(repo, "ls-tree", "--name-only", f"{ref}:{rel}/builds", check=False).split():
            if i in have or i in found:
                continue
            meta = _json_at(repo, f"{ref}:{rel}/builds/{i}/build.json")
            if meta is None:
                continue
            found[i] = {"id": i, "via": "branch", "branch": ref.split("/", 1)[1], "ref": ref, "sent": sent,
                        "title": meta.get("title") or i, "author": meta.get("author") or {},
                        "provenance": meta.get("provenance") or {}, "created": meta.get("created"),
                        "card": _has(repo, f"{ref}:{rel}/cards/{i}.json")}
    # The page is read every time, so with one the console has looked just now.
    when = datetime.now().astimezone() if inbox else looked(repo)
    return {"repo": str(repo), "inbox": str(inbox) if inbox else None, "looked": when, "waiting": list(found.values())}


def _waiting(kb: KB, build_id: str) -> Dict[str, Any]:
    for w in incoming(kb)["waiting"]:
        if w["id"] == build_id:
            return w
    raise KBError(f"No build {build_id!r} is waiting: `astaui incoming --fetch` looks for new ones")


def _extract(kb: KB, w: Dict[str, Any], into: Path) -> List[str]:
    """Write the waiting build's folder and card, as its branch or its row has
    them, into a knowledge base folder. Returns the paths written, from that folder."""
    if w.get("via") == "drive":
        path = inbox_file(kb)
        sent_as = w.get("as") or w["id"]
        row = next((r for r in reversed(_sent_rows(path)) if r["id"] == sent_as and r["sent"] == w.get("sent_at", r["sent"])
                    and (not w.get("digest") or hashlib.sha256(r["packed"].encode("ascii", "replace")).hexdigest()[:16] == w["digest"])),
                   None) if path else None
        if row is None:
            raise KBError(f"{w['id']} is no longer on {w.get('page') or 'the page it was sent to'}")
        written = []
        for name, data in sorted(_renamed(_unpack(row["packed"], sent_as), sent_as, w["id"]).items()):
            dest = into / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            written.append(name)
        return written
    repo = Path(repo_of(kb) or kb.root)
    rel = _rel(kb, repo)
    paths = [f"{rel}/builds/{w['id']}"] + ([f"{rel}/cards/{w['id']}.json"] if w["card"] else [])
    try:
        tar = subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", w["ref"], "--", *paths],
                             capture_output=True, timeout=120, check=True).stdout
    except (OSError, subprocess.SubprocessError) as e:
        raise KBError(f"Could not read {w['id']} from {w['branch']}: {e}") from e
    written = []
    with tarfile.open(fileobj=io.BytesIO(tar)) as t:
        for m in t.getmembers():
            name = m.name[len(rel) + 1:] if m.name.startswith(rel + "/") else None
            if not name or not (m.isfile() or m.isdir()) or ".." in Path(name).parts:
                continue
            dest = into / name
            if m.isdir():
                dest.mkdir(parents=True, exist_ok=True)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            src = t.extractfile(m)
            dest.write_bytes(src.read() if src else b"")
            written.append(name)
    return written


def _renamed(files: Dict[str, bytes], old: str, new: str) -> Dict[str, bytes]:
    """A sent build's files under the id it takes here, when that is not the one it was sent as."""
    if old == new:
        return files
    out: Dict[str, bytes] = {}
    for name, data in files.items():
        if name in (f"builds/{old}/build.json", f"cards/{old}.json"):
            try:
                d = json.loads(data.decode("utf-8"))
            except ValueError:
                d = None
            if isinstance(d, dict) and d.get("id") == old:
                d["id"] = new
                data = (json.dumps(d, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        if name.startswith(f"builds/{old}/"):
            name = f"builds/{new}/" + name[len(f"builds/{old}/"):]
        elif name == f"cards/{old}.json":
            name = f"cards/{new}.json"
        out[name] = data
    return out


def review(kb: KB, build_id: str) -> Path:
    """A copy of this knowledge base with the waiting build in it, in a folder of
    its own, to run the checks on. The knowledge base itself is not touched."""
    w = _waiting(kb, build_id)
    dest = Path(tempfile.gettempdir()) / "astaui-review" / build_id / "kb"
    if dest.parent.exists():
        shutil.rmtree(dest.parent)
    shutil.copytree(kb.root, dest, ignore=shutil.ignore_patterns(".index", ".usage", ".out"))
    _extract(kb, w, dest)
    return dest


def take(kb: KB, build_id: str) -> Dict[str, Any]:
    """Bring a waiting build and its card into this knowledge base, as files
    nothing has committed yet. A newer copy of a build taken from the page
    replaces the older one."""
    w = _waiting(kb, build_id)
    if (kb.builds_dir / build_id).exists():
        if not w.get("replaces"):
            raise KBError(f"{build_id} is already in the knowledge base")
        shutil.rmtree(kb.builds_dir / build_id)
        kb.card_path(build_id).unlink(missing_ok=True)
    files = _extract(kb, w, kb.root)
    if w.get("via") == "drive":
        state = _state(kb)
        before = state["taken"].get(build_id) or {}
        state["taken"][build_id] = {"id": w.get("as") or build_id, "author": _who(w), "sent": w.get("sent_at") or "",
                                    "digest": w.get("digest"), "at": datetime.now().astimezone().isoformat(timespec="seconds"),
                                    "copies": (before.get("copies") or 1) + 1 if w.get("replaces") else 1}
        state["held"].pop(build_id, None)
        write_json(kb.root / INTAKE, state)
    return {"id": build_id, "branch": w["branch"], "page": w.get("page"), "via": w.get("via"), "files": files,
            "card": w["card"], "replaced": bool(w.get("replaces"))}


def arrivals(kb: KB, limit: int = 8) -> List[Dict[str, Any]]:
    """The builds intake took from the owner's page that are still in the
    knowledge base, the latest to join first: when each was sent and joined,
    and how many copies of it have come."""
    have = set(kb.build_ids())
    out = []
    for i, t in _state(kb)["taken"].items():
        if i not in have:
            continue
        meta = kb.build(i).meta
        out.append({"id": i, "title": meta.get("title") or i, "author": meta.get("author") or {},
                    "provenance": meta.get("provenance") or {}, "sent": t.get("sent") or "", "at": t.get("at") or "",
                    "copies": t.get("copies") or 1})
    out.sort(key=lambda a: _when(a["at"]), reverse=True)
    return out[:limit]


def problems(kb: KB, w: Dict[str, Any]) -> List[str]:
    """What stops a waiting build joining by itself, in words: the checks a pull
    request runs, on a knowledge base of just this build beside this one's
    vocabulary, after keys, emails and home paths are swapped for placeholders.
    What a program cannot see (a real name in a prompt) is review-publish's."""
    from .cli import build_problems
    from .privacy import strip_build
    consent = (w.get("provenance") or {}).get("consent")
    if consent not in ("team", "public"):
        return [f"It is marked for {consent or 'no one'}, so it cannot join a knowledge base the project team shares."]
    if not w.get("card"):
        return ["It came without a card, so the knowledge base cannot say what it is."]
    with tempfile.TemporaryDirectory(prefix="astaui-intake-") as tmp:
        root = Path(tmp)
        for name in ("kb.json", "ontology.json"):
            shutil.copyfile(kb.root / name, root / name)
        _extract(kb, w, root)
        one = KB.open(str(root))
        strip_build(one.build(w["id"]))
        return [p.split(": ", 1)[1] if p.startswith(("build ", "card ")) else p for p in build_problems(one, w["id"])]


def intake(kb: KB, index: bool = True) -> Dict[str, Any]:
    """Take in every build sent to the owner's page that passes the checks, swap
    keys, emails and home paths in it for placeholders, and bring the index up
    to date. One that does not pass waits, with what stopped it. Builds on
    add-* branches are left to be checked by hand: they came without the link."""
    from .privacy import strip_build
    with _one_at_a_time(kb):
        return _intake(kb, index, strip_build)


class _one_at_a_time:
    """Intake runs on the console's hourly run and when the owner presses it, so
    two can meet: the second waits for the first, then finds nothing new."""

    def __init__(self, kb: KB):
        self.path = kb.root / ".intake.lock"
        self.f = None

    def __enter__(self):
        try:
            import fcntl
        except ImportError:  # not on Windows; intake runs on the owner's computer
            return self
        self.f = self.path.open("w")
        fcntl.flock(self.f, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        if self.f:
            self.f.close()


def _intake(kb: KB, index: bool, strip_build) -> Dict[str, Any]:
    state = _state(kb)
    taken: List[Dict[str, Any]] = []
    held: List[Dict[str, Any]] = []
    for w in incoming(kb)["waiting"]:
        if w.get("via") != "drive":
            continue
        why = problems(kb, w)
        if why:
            state["held"][w["id"]] = {"sent": w.get("sent_at") or "", "digest": w.get("digest"), "why": why}
            write_json(kb.root / INTAKE, state)
            held.append({**w, "held": why})
            continue
        got = take(kb, w["id"])
        state = _state(kb)
        got["stripped"] = strip_build(kb.build(w["id"]))
        taken.append({**w, **got})
    if taken and index:
        from .index import Index
        Index(kb).build()
    return {"taken": taken, "held": held}
