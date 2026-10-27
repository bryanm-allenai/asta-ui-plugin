"""The vector index: a cache of embeddings, rebuilt from the cards whenever they change.

Each card is embedded several times, once per channel:

- one vector per facet (``task``, ``data``, ``stage``, ``mechanism``, ``field``)
  and one for the ``summary``, so a search can weight data shape and task
  above field;
- ``workflow``: the general workflow, its name and steps in general words;
- ``specifics``: how this build does each step, and what is distinctive about it;
- ``card``: the whole card as one text, the "describe first, then embed" side;
- ``structure``: only the ontology's words for task, data, stage and mechanism,
  with nothing from the field, for the far match;
- ``prompt``: the prompts alone, so a new prompt can find similar prompts;
- ``raw``: the prompts and the code as they are, the baseline the cards are
  compared against.

Every view and component on a card gets a ``part`` vector, for snippets, and every
workflow step gets two: ``step`` (the general move) and ``here`` (how it is done
in this case), so two workflows can be lined up step by step.

The cache is a SQLite file per embedder under ``kb/.index/``, keyed by a hash of
the text, so rebuilding only embeds what changed.
"""

from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from .cards import card_text, facet_text, here_text, part_text, specifics_text, step_text, structure_text, workflow_text
from .embed import get_embedder, text_hash
from .kb import KB, Build, KBError
from .ontology import FACETS
from .vec import Vector, from_bytes, to_bytes

APP_CHANNELS = ("summary",) + FACETS + ("workflow", "specifics", "card", "structure", "prompt", "raw")
RAW_LIMIT = 12000
PROMPT_LIMIT = 8000


def raw_text(build: Build) -> str:
    """The prompts and the code as they are, entry file first, cut at RAW_LIMIT."""
    chunks = [build.prompt_text()]
    entry = build.meta.get("entry")
    files = build.code_files()
    if entry:
        files.sort(key=lambda p: 0 if str(p.relative_to(build.path)) == entry else 1)
    for p in files:
        try:
            chunks.append(p.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            continue
        if sum(len(c) for c in chunks) > RAW_LIMIT:
            break
    return "\n\n".join(chunks)[:RAW_LIMIT]


def channel_texts(kb: KB) -> Dict[Tuple[str, str, str], str]:
    """Every text the index holds, keyed by (build id, part id or '', channel)."""
    texts: Dict[Tuple[str, str, str], str] = {}
    cards = set(kb.card_ids())
    for b in kb.builds():
        texts[(b.id, "", "prompt")] = b.prompt_text(PROMPT_LIMIT) or b.title
        texts[(b.id, "", "raw")] = raw_text(b)
        if b.id not in cards:
            continue
        card = kb.card(b.id)
        app = card.get("app", {})
        for ch in ("summary",) + FACETS:
            t = facet_text(app, ch)
            if t:
                texts[(b.id, "", ch)] = t
        texts[(b.id, "", "card")] = card_text(app)
        if workflow_text(app):
            texts[(b.id, "", "workflow")] = workflow_text(app)
        if specifics_text(app):
            texts[(b.id, "", "specifics")] = specifics_text(app)
        for i, st in enumerate((app.get("workflow") or {}).get("steps") or [], 1):
            if step_text(st):
                texts[(b.id, f"step-{i}", "step")] = step_text(st)
                texts[(b.id, f"step-{i}", "here")] = here_text(st)
        if structure_text(app):
            texts[(b.id, "", "structure")] = structure_text(app)
        for part in card.get("parts", []):
            texts[(b.id, part["id"], "part")] = part_text(part)
    return texts


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()


class Index:
    def __init__(self, kb: KB, embedder: Optional[str] = None):
        self.kb = kb
        self.embedder = get_embedder(embedder or kb.config.get("embedder"))
        self.path = kb.index_dir / f"{_slug(self.embedder.id)}.sqlite"
        self._loaded: Optional[Dict[Tuple[str, str, str], Vector]] = None

    def _db(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(str(self.path))
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS cache(hash TEXT, kind TEXT, vec BLOB, PRIMARY KEY(hash, kind));
            CREATE TABLE IF NOT EXISTS vectors(card TEXT, part TEXT, channel TEXT, hash TEXT, PRIMARY KEY(card, part, channel));
            """
        )
        row = db.execute("SELECT value FROM meta WHERE key='embedder'").fetchone()
        if row and row[0] != self.embedder.id:
            db.close()
            raise KBError(f"{self.path} holds vectors from {row[0]}, not {self.embedder.id}; delete it to rebuild")
        db.execute("INSERT OR REPLACE INTO meta VALUES('embedder', ?)", (self.embedder.id,))
        return db

    def _embed_missing(self, db: sqlite3.Connection, texts: Dict[str, str], kind: str,
                       progress: Optional[Callable[[int, int], None]] = None) -> int:
        have = {h for (h,) in db.execute("SELECT hash FROM cache WHERE kind=?", (kind,))}
        todo = [(h, t) for h, t in texts.items() if h not in have]
        done = 0
        for i in range(0, len(todo), 64):
            batch = todo[i : i + 64]
            vecs = self.embedder.embed([t for _, t in batch], kind=kind)
            if len(vecs) != len(batch):
                raise KBError(f"{self.embedder.id} returned {len(vecs)} vectors for {len(batch)} texts")
            db.executemany("INSERT OR REPLACE INTO cache VALUES(?, ?, ?)",
                           [(h, kind, to_bytes(v)) for (h, _), v in zip(batch, vecs)])
            db.commit()
            done += len(batch)
            if progress:
                progress(done, len(todo))
        return len(todo)

    def build(self, progress: Optional[Callable[[int, int], None]] = None) -> Dict[str, int]:
        """Bring the index up to date with the cards. Embeds only texts it has not seen."""
        texts = channel_texts(self.kb)
        hashed = {key: text_hash(t) for key, t in texts.items()}
        with closing(self._db()) as db:
            embedded = self._embed_missing(db, {hashed[k]: texts[k] for k in texts}, "document", progress)
            db.execute("DELETE FROM vectors")
            db.executemany("INSERT INTO vectors VALUES(?, ?, ?, ?)", [(c, p, ch, h) for (c, p, ch), h in hashed.items()])
            stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            db.execute("INSERT OR REPLACE INTO meta VALUES('built', ?)", (stamp,))
            db.commit()
        self._loaded = None
        return {
            "builds": len({c for c, _, _ in texts}),
            "cards": len({c for c, p, ch in texts if ch == "card"}),
            "parts": sum(1 for _, _, ch in texts if ch == "part"),
            "vectors": len(texts),
            "embedded": embedded,
            "reused": len(set(hashed.values())) - embedded,
        }

    def is_fresh(self) -> bool:
        if not self.path.exists():
            return False
        texts = channel_texts(self.kb)
        want = {key: text_hash(t) for key, t in texts.items()}
        with closing(self._db()) as db:
            have = {(c, p, ch): h for c, p, ch, h in db.execute("SELECT card, part, channel, hash FROM vectors")}
        return want == have

    def ensure(self, progress: Optional[Callable[[int, int], None]] = None) -> None:
        if not self.is_fresh():
            self.build(progress)

    def _load(self) -> Dict[Tuple[str, str, str], Vector]:
        if self._loaded is None:
            with closing(self._db()) as db:
                rows = db.execute(
                    "SELECT v.card, v.part, v.channel, c.vec FROM vectors v JOIN cache c ON c.hash=v.hash AND c.kind='document'"
                ).fetchall()
            self._loaded = {(c, p, ch): from_bytes(vec) for c, p, ch, vec in rows}
        return self._loaded

    def channel(self, name: str) -> Dict[str, Vector]:
        """App-level vectors for one channel, by build id."""
        return {c: v for (c, p, ch), v in self._load().items() if ch == name and p == ""}

    def steps(self, card: str) -> Dict[int, Tuple[Optional[Vector], Optional[Vector]]]:
        """One card's workflow steps, by number: (general vector, specific vector)."""
        out: Dict[int, Tuple[Optional[Vector], Optional[Vector]]] = {}
        for (c, p, ch), v in self._load().items():
            if c == card and p.startswith("step-") and ch in ("step", "here"):
                n = int(p.split("-", 1)[1])
                general, specific = out.get(n, (None, None))
                out[n] = (v, specific) if ch == "step" else (general, v)
        return out

    def parts(self, card: Optional[str] = None) -> Dict[Tuple[str, str], Vector]:
        return {(c, p): v for (c, p, ch), v in self._load().items() if ch == "part" and (card is None or c == card)}

    def embed_queries(self, texts: Iterable[str]) -> List[Vector]:
        """Embed query texts, through the same cache (queries repeat in evaluation)."""
        texts = list(texts)
        hashes = [text_hash(t) for t in texts]
        with closing(self._db()) as db:
            self._embed_missing(db, dict(zip(hashes, texts)), "query")
            found = {}
            for h in set(hashes):
                row = db.execute("SELECT vec FROM cache WHERE hash=? AND kind='query'", (h,)).fetchone()
                found[h] = from_bytes(row[0])
        return [found[h] for h in hashes]

    def info(self) -> Dict[str, str]:
        if not self.path.exists():
            return {"embedder": self.embedder.id, "path": str(self.path), "built": "never"}
        with closing(self._db()) as db:
            meta = dict(db.execute("SELECT key, value FROM meta").fetchall())
            n = db.execute("SELECT COUNT(*) FROM vectors").fetchone()[0]
        return {"embedder": self.embedder.id, "path": str(self.path), "built": meta.get("built", "never"), "vectors": str(n)}
