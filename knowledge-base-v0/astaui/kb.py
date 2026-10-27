"""Finding a knowledge base on disk and reading what is in it.

A knowledge base is a folder with ``kb.json`` in it, next to ``ontology.json``,
``builds/``, ``cards/`` and ``eval/``. The vectors live in ``.index/`` beside them and
are a cache: deleting the folder loses nothing.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
USER_CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "astaui" / "config.json"
BUNDLED = Path(__file__).resolve().parent.parent / "kb"
# Where a scientist's own copy lives, when the knowledge base came with the
# plugin and a plugin manager's copy is read-only.
WORKING = Path(os.environ.get("ASTAUI_HOME", Path.home() / ".astaui")) / "kb"

DEFAULTS: Dict[str, Any] = {
    "name": "AstaUI knowledge base",
    "embedder": "lexical",
    "search": {"k": 5, "parts_per_build": 2, "prompt_weight": 0.25, "tag_weight": 0.15, "far": True},
    "extract": {"provider": "anthropic", "model": "claude-opus-5"},
}


class KBError(Exception):
    """Something about the knowledge base a person has to fix. The message says what."""


def check_id(value: str, what: str = "id") -> str:
    if not ID_RE.match(value or ""):
        raise KBError(f"{what} {value!r} must be lowercase letters, digits and hyphens, starting with a letter or digit")
    return value


def read_json(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise KBError(f"{path} does not exist") from None
    except json.JSONDecodeError as e:
        raise KBError(f"{path} is not valid JSON: line {e.lineno}, column {e.colno}: {e.msg}") from None


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp.replace(path)


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise KBError(f"{path}:{n} is not valid JSON: {e.msg}") from None
    return rows


def write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _merge(base: Dict[str, Any], over: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def user_config() -> Dict[str, Any]:
    if USER_CONFIG.exists():
        try:
            return json.loads(USER_CONFIG.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def set_user_config(key: str, value: Any) -> Path:
    cfg = user_config()
    if value is None:
        cfg.pop(key, None)
    else:
        cfg[key] = value
    write_json(USER_CONFIG, cfg)
    return USER_CONFIG


def _looks_like_kb(path: Path) -> bool:
    return (path / "kb.json").is_file() and (path / "ontology.json").is_file()


def locate(explicit: Optional[str] = None, start: Optional[Path] = None) -> Path:
    """Where the knowledge base is, in this order: the --kb flag, $ASTAUI_KB, the
    user config (``astaui config kb PATH``), a kb folder above the working
    directory, and last the one shipped next to this code."""
    candidates: List[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    elif os.environ.get("ASTAUI_KB"):
        candidates.append(Path(os.environ["ASTAUI_KB"]).expanduser())
    elif user_config().get("kb"):
        candidates.append(Path(user_config()["kb"]).expanduser())
    if candidates:
        path = candidates[0].resolve()
        if _looks_like_kb(path):
            return path
        if _looks_like_kb(path / "kb"):
            return path / "kb"
        raise KBError(f"{path} is not a knowledge base: it needs kb.json and ontology.json (make one with `astaui init {path}`)")
    here = (start or Path.cwd()).resolve()
    for d in [here, *here.parents]:
        for c in (d, d / "kb", d / "knowledge-base-v0" / "kb"):
            if _looks_like_kb(c):
                return c
    if _looks_like_kb(BUNDLED):
        return BUNDLED
    raise KBError("No knowledge base found. Point to one with --kb, $ASTAUI_KB or `astaui config kb PATH`.")


def _installed(root: Path) -> bool:
    """Whether this is the copy a plugin manager installed, which nothing should write to."""
    parts = root.resolve().parts
    managed = any(a == "plugins" and b in ("cache", "marketplaces") for a, b in zip(parts, parts[1:]))
    return managed or (".claude" in parts and "plugins" in parts) or not os.access(root, os.W_OK)


def working_copy(shipped: Path, dest: Optional[Path] = None) -> Path:
    """The scientist's own knowledge base, for when the one the plugin shipped is
    read-only: everything the plugin shipped, brought up to date whenever the
    plugin is, plus the builds they filed themselves, so filing one never stops
    to ask where it should go."""
    dest = dest or WORKING
    mark = dest / ".shipped"
    stamp = "\n".join([str(shipped)] + [str(int((shipped / f).stat().st_mtime)) for f in ("kb.json", "ontology.json")])
    try:
        if mark.read_text(encoding="utf-8") == stamp and _looks_like_kb(dest):
            return dest
    except OSError:
        pass
    for src in sorted(shipped.rglob("*")):
        rel = src.relative_to(shipped)
        if not src.is_file() or any(p.startswith(".") for p in rel.parts):
            continue
        out = dest / rel
        if out.is_file() and out.stat().st_size == src.stat().st_size and out.read_bytes() == src.read_bytes():
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, out)
    mark.write_text(stamp, encoding="utf-8")
    return dest


@dataclass
class Build:
    id: str
    path: Path
    meta: Dict[str, Any]
    prompts: List[Dict[str, Any]]

    @property
    def title(self) -> str:
        return self.meta.get("title") or self.id

    @property
    def kind(self) -> str:
        return (self.meta.get("provenance") or {}).get("kind", "")

    def code_files(self) -> List[Path]:
        code = self.path / "code"
        if not code.is_dir():
            return []
        return sorted(p for p in code.rglob("*") if p.is_file() and not any(part.startswith(".") for part in p.relative_to(code).parts))

    def prompt_text(self, limit: Optional[int] = None) -> str:
        turns = [t.get("text", "").strip() for t in self.prompts if t.get("text")]
        text = "\n\n".join(turns)
        return text if limit is None else text[:limit]

    def read_code(self, rel: str) -> str:
        p = (self.path / rel).resolve()
        if self.path.resolve() not in p.parents:
            raise KBError(f"{rel} is outside the build folder")
        return p.read_text(encoding="utf-8", errors="replace")

    def screenshot(self) -> Optional[Path]:
        for name in ("screenshot.png", "screenshot.jpg", "screenshot.jpeg", "screenshot.webp"):
            if (self.path / name).is_file():
                return self.path / name
        return None


@dataclass
class KB:
    root: Path
    config: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def open(cls, explicit: Optional[str] = None) -> "KB":
        root = locate(explicit)
        if root == BUNDLED.resolve() and _installed(root):
            root = working_copy(root)
        config = _merge(DEFAULTS, read_json(root / "kb.json"))
        return cls(root=root, config=config)

    # -- places -------------------------------------------------------------
    @property
    def builds_dir(self) -> Path:
        return self.root / "builds"

    @property
    def cards_dir(self) -> Path:
        return self.root / "cards"

    @property
    def eval_dir(self) -> Path:
        return self.root / "eval"

    @property
    def index_dir(self) -> Path:
        return self.root / ".index"

    @property
    def out_dir(self) -> Path:
        return self.root / ".out"

    @property
    def usage_dir(self) -> Path:
        return self.root / ".usage"

    @property
    def read_only(self) -> bool:
        """True when this is the copy a plugin manager installed (KB.open hands out
        the scientist's own copy instead, so this is only seen when one is named)."""
        return _installed(self.root)

    # -- builds -------------------------------------------------------------
    def build_ids(self) -> List[str]:
        if not self.builds_dir.is_dir():
            return []
        return sorted(p.name for p in self.builds_dir.iterdir() if (p / "build.json").is_file())

    def build(self, build_id: str) -> Build:
        path = self.builds_dir / build_id
        if not (path / "build.json").is_file():
            raise KBError(f"No build called {build_id!r} (looked in {path})")
        meta = read_json(path / "build.json")
        prompts = read_jsonl(path / "prompts.jsonl")
        return Build(id=build_id, path=path, meta=meta, prompts=prompts)

    def builds(self) -> Iterator[Build]:
        for b in self.build_ids():
            yield self.build(b)

    # -- cards --------------------------------------------------------------
    def card_path(self, build_id: str) -> Path:
        return self.cards_dir / f"{build_id}.json"

    def card_ids(self) -> List[str]:
        if not self.cards_dir.is_dir():
            return []
        return sorted(p.stem for p in self.cards_dir.glob("*.json"))

    def card(self, build_id: str) -> Dict[str, Any]:
        path = self.card_path(build_id)
        if not path.exists():
            raise KBError(f"{build_id!r} has no card yet. Write one with `astaui extract {build_id}`.")
        return read_json(path)

    def cards(self) -> List[Dict[str, Any]]:
        return [self.card(c) for c in self.card_ids()]

    # -- eval ---------------------------------------------------------------
    def queries(self) -> List[Dict[str, Any]]:
        return read_jsonl(self.eval_dir / "queries.jsonl")

    def pairs(self) -> List[Dict[str, Any]]:
        return read_jsonl(self.eval_dir / "pairs.jsonl")


def init(path: Path, name: str = "AstaUI knowledge base") -> Path:
    """Make an empty knowledge base, with the shipped ontology to start from."""
    path = path.expanduser().resolve()
    if _looks_like_kb(path):
        raise KBError(f"{path} is already a knowledge base")
    for d in ("builds", "cards", "eval"):
        (path / d).mkdir(parents=True, exist_ok=True)
    cfg = dict(DEFAULTS)
    cfg["name"] = name
    write_json(path / "kb.json", cfg)
    source = BUNDLED / "ontology.json"
    if source.exists():
        (path / "ontology.json").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        raise KBError("The shipped ontology.json is missing; copy one in by hand")
    (path / ".gitignore").write_text(".index/\n.out/\n.usage/\n", encoding="utf-8")
    return path
