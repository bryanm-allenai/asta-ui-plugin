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
from pathlib import Path
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from .cards import card_text, facet_text, here_text, part_text, specifics_text, step_text, structure_text, workflow_text
from .embed import get_embedder, text_hash
from .kb import KB, Build, KBError
from .ontology import FACETS
from .vec import Vector, VecSet, from_bytes, to_bytes

APP_CHANNELS = ("summary",) + FACETS + ("workflow", "specifics", "card", "structure", "prompt", "raw")
RAW_LIMIT = 12000
PROMPT_LIMIT = 8000


def raw_text(build: Build) -> str:
    """The prompts and the code as they are, entry file first, cut at RAW_LIMIT."""
    chunks = [build.prompt_text()]
    entry = build.meta.get("entry")
    files = build.code_files(fetch=False)
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


def _fingerprint(rows: Iterable[Tuple[Tuple[str, str, str], str]], embedder_id: str) -> str:
    """One hash over (card, part, channel) -> text hash rows, in a fixed order."""
    import hashlib

    h = hashlib.sha1(embedder_id.encode("utf-8"))
    for (c, p, ch), t in sorted(rows):
        h.update(f"{c}\x1f{p}\x1f{ch}\x1f{t}\x1e".encode("utf-8"))
    return h.hexdigest()


class Index:
    def __init__(self, kb: KB, embedder: Optional[str] = None):
        self.kb = kb
        self.embedder = get_embedder(embedder or kb.config.get("embedder"))
        self.path = kb.index_dir / f"{_slug(self.embedder.id)}.sqlite"
        self._loaded: Optional[Dict[Tuple[str, str, str], Vector]] = None
        self._grouped: Optional[Dict[str, Any]] = None
        self._by_channel: Dict[str, Dict[Tuple[str, str], Vector]] = {}
        self._sets: Dict[str, Tuple[List[str], VecSet]] = {}
        self._steps_of: Dict[str, Dict[int, Tuple[Optional[Vector], Optional[Vector]]]] = {}
        self._parts_of: Dict[str, Dict[Tuple[str, str], Vector]] = {}
        self._store: Any = False  # not looked for yet

    # -- the database, when this knowledge base has one ---------------------------------
    @property
    def store(self):
        """The Postgres store set for this knowledge base on this computer, or None.
        A knowledge base with a database still searches without it when psycopg is
        missing (the system Python), from this index alone."""
        if self._store is False:
            from .store_pg import PgStore, database_url

            url = database_url(self.kb)
            self._store = None
            if url:
                try:
                    self._store = PgStore(url, self.kb, self.embedder.id)
                except KBError:
                    self._store = None
        return self._store

    def generation(self) -> str:
        """A fingerprint of every vector in the index, made when it is built: what the
        database copy and anything worked out from the vectors are checked against."""
        with closing(self._db()) as db:
            row = db.execute("SELECT value FROM meta WHERE key='generation'").fetchone()
        if row:
            return row[0]
        gen = self.signature(None)
        with closing(self._db()) as db:
            db.execute("INSERT OR REPLACE INTO meta VALUES('generation', ?)", (gen,))
            db.commit()
        return gen

    def sync_store(self) -> Optional[Dict[str, int]]:
        """Bring the database copy in line with this index, writing only what changed."""
        st = self.store
        if st is None:
            return None
        with closing(self._db()) as db:
            hashes = {(c, p, ch): h for c, p, ch, h in db.execute("SELECT card, part, channel, hash FROM vectors")}

        def load(keys: List[Tuple[str, str, str]]) -> Dict[Tuple[str, str, str], Vector]:
            wanted = sorted({hashes[k] for k in keys})
            found: Dict[str, Vector] = {}
            with closing(self._db()) as db:
                for i in range(0, len(wanted), 500):
                    chunk = wanted[i:i + 500]
                    marks = ",".join("?" * len(chunk))
                    for h, vec in db.execute(f"SELECT hash, vec FROM cache WHERE kind='document' AND hash IN ({marks})", chunk):
                        found[h] = from_bytes(vec)
            return {k: found[hashes[k]] for k in keys if hashes[k] in found}

        return st.sync(hashes, load, self.generation())

    def store_ready(self) -> bool:
        """Whether there is a database copy and it matches this index."""
        st = self.store
        if st is None:
            return False
        try:
            return st.meta("version") == self.generation()
        except Exception:
            return False

    def _db(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(str(self.path))
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS cache(hash TEXT, kind TEXT, vec BLOB, PRIMARY KEY(hash, kind));
            CREATE TABLE IF NOT EXISTS vectors(card TEXT, part TEXT, channel TEXT, hash TEXT, PRIMARY KEY(card, part, channel));
            CREATE INDEX IF NOT EXISTS vectors_channel ON vectors(channel);
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
        # Taken before reading, so a file changed while this runs makes the index stale.
        stamp = self._stamp()
        texts = channel_texts(self.kb)
        hashed = {key: text_hash(t) for key, t in texts.items()}
        with closing(self._db()) as db:
            embedded = self._embed_missing(db, {hashed[k]: texts[k] for k in texts}, "document", progress)
            db.execute("DELETE FROM vectors")
            db.executemany("INSERT INTO vectors VALUES(?, ?, ?, ?)", [(c, p, ch, h) for (c, p, ch), h in hashed.items()])
            built = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            db.execute("INSERT OR REPLACE INTO meta VALUES('built', ?)", (built,))
            db.execute("INSERT OR REPLACE INTO meta VALUES('generation', ?)", (_fingerprint(hashed.items(), self.embedder.id),))
            db.commit()
        self._loaded = self._grouped = None
        self._by_channel = {}
        self._sets = {}
        self._steps_of, self._parts_of = {}, {}
        self._remember_stamp(stamp)
        stored = self.sync_store()
        # Which steps are the same move, worked out now for the whole knowledge base
        # and kept, so no search has to.
        from .workflows import StepSpace

        StepSpace(self, {c["id"]: c for c in self.kb.cards()})
        return {
            "builds": len({c for c, _, _ in texts}),
            "cards": len({c for c, p, ch in texts if ch == "card"}),
            "parts": sum(1 for _, _, ch in texts if ch == "part"),
            "vectors": len(texts),
            "embedded": embedded,
            "reused": len(set(hashed.values())) - embedded,
            **({"database": stored} if stored is not None else {}),
        }

    def _stamp(self) -> str:
        """A fingerprint of every file the index is made from, by name, size and time,
        so an unchanged knowledge base is known fresh without reading its code."""
        import hashlib
        import os

        h = hashlib.sha1(self.embedder.id.encode("utf-8"))
        root = str(self.kb.root)
        try:
            st = os.stat(os.path.join(root, "ontology.json"))
            h.update(f"ontology.json\x1f{st.st_size}\x1f{st.st_mtime_ns}\x1e".encode())
        except OSError:
            pass
        for folder in (self.kb.cards_dir, self.kb.builds_dir):
            for dirpath, dirnames, filenames in os.walk(folder):
                dirnames.sort()
                rel = dirpath[len(root):]
                for f in sorted(filenames):
                    try:
                        st = os.stat(os.path.join(dirpath, f))
                    except OSError:
                        continue
                    h.update(f"{rel}/{f}\x1f{st.st_size}\x1f{st.st_mtime_ns}\x1e".encode("utf-8", "surrogateescape"))
        return h.hexdigest()

    def _remember_stamp(self, stamp: Optional[str] = None) -> None:
        try:
            stamp = stamp or self._stamp()
            with closing(self._db()) as db:
                db.execute("INSERT OR REPLACE INTO meta VALUES('stamp', ?)", (stamp,))
                db.commit()
        except Exception:
            pass

    def is_fresh(self) -> bool:
        if not self.path.exists():
            return False
        stamp = self._stamp()
        with closing(self._db()) as db:
            row = db.execute("SELECT value FROM meta WHERE key='stamp'").fetchone()
        if row and row[0] == stamp:
            return True
        texts = channel_texts(self.kb)
        want = {key: text_hash(t) for key, t in texts.items()}
        with closing(self._db()) as db:
            have = {(c, p, ch): h for c, p, ch, h in db.execute("SELECT card, part, channel, hash FROM vectors")}
        if want != have:
            return False
        self._remember_stamp(stamp)
        return True

    def ensure(self, progress: Optional[Callable[[int, int], None]] = None) -> None:
        if not self.is_fresh():
            self.build(progress)
        elif self.store is not None and not self.store_ready():
            # The index is current but the database copy is behind (built by a Python
            # without psycopg, say): bring it up.
            self.sync_store()

    def _load(self) -> Dict[Tuple[str, str, str], Vector]:
        if self._loaded is None:
            with closing(self._db()) as db:
                rows = db.execute(
                    "SELECT v.card, v.part, v.channel, c.vec FROM vectors v JOIN cache c ON c.hash=v.hash AND c.kind='document'"
                ).fetchall()
            self._loaded = {(c, p, ch): from_bytes(vec) for c, p, ch, vec in rows}
        return self._loaded

    def _rows(self, channel: str) -> Dict[Tuple[str, str], Vector]:
        """One channel's vectors, read from the index the first time they are asked
        for, so a search holds only the channels it uses."""
        if channel not in self._by_channel:
            if self._loaded is not None:
                self._by_channel[channel] = {(c, p): v for (c, p, ch), v in self._loaded.items() if ch == channel}
            else:
                with closing(self._db()) as db:
                    rows = db.execute(
                        "SELECT v.card, v.part, c.vec FROM vectors v JOIN cache c ON c.hash=v.hash AND c.kind='document' "
                        "WHERE v.channel=?", (channel,)).fetchall()
                self._by_channel[channel] = {(c, p): from_bytes(vec) for c, p, vec in rows}
        return self._by_channel[channel]

    def _groups(self) -> Dict[str, Any]:
        """Steps and parts sorted once by card, so each lookup is one dictionary away,
        however many cards there are."""
        if self._grouped is None:
            steps: Dict[str, Dict[int, Tuple[Optional[Vector], Optional[Vector]]]] = {}
            parts: Dict[str, Dict[Tuple[str, str], Vector]] = {}
            for (c, p), v in self._rows("part").items():
                parts.setdefault(c, {})[(c, p)] = v
            for ch in ("step", "here"):
                for (c, p), v in self._rows(ch).items():
                    if not p.startswith("step-"):
                        continue
                    n = int(p.split("-", 1)[1])
                    general, specific = steps.setdefault(c, {}).get(n, (None, None))
                    steps[c][n] = (v, specific) if ch == "step" else (general, v)
            self._grouped = {"steps": steps, "parts": parts}
        return self._grouped

    def channel(self, name: str) -> Dict[str, Vector]:
        """App-level vectors for one channel, by build id."""
        return {c: v for (c, p), v in self._rows(name).items() if p == ""}

    def vecset(self, name: str) -> Tuple[List[str], VecSet]:
        """One channel's vectors as a VecSet, with the build id of each row, for
        scoring a query against every build at once."""
        if name not in self._sets:
            vecs = self.channel(name)
            ids = sorted(vecs)
            self._sets[name] = (ids, VecSet([vecs[i] for i in ids]))
        return self._sets[name]

    def scores(self, name: str, q: Optional[Vector]) -> Dict[str, float]:
        """The similarity of q with every build's vector in one channel, by build id."""
        if q is None:
            return {}
        ids, vs = self.vecset(name)
        return dict(zip(ids, vs.scores(q)))

    def _card_rows(self, card: str, channels: Sequence[str]) -> List[Tuple[str, str, Vector]]:
        marks = ",".join("?" * len(channels))
        with closing(self._db()) as db:
            rows = db.execute(
                "SELECT v.part, v.channel, c.vec FROM vectors v JOIN cache c ON c.hash=v.hash AND c.kind='document' "
                f"WHERE v.card=? AND v.channel IN ({marks})", (card, *channels)).fetchall()
        return [(p, ch, from_bytes(vec)) for p, ch, vec in rows]

    def steps(self, card: str) -> Dict[int, Tuple[Optional[Vector], Optional[Vector]]]:
        """One card's workflow steps, by number: (general vector, specific vector). Read
        for that card alone, unless every card's steps are loaded already."""
        if self._grouped is not None:
            return dict(self._grouped["steps"].get(card, {}))
        if card not in self._steps_of:
            out: Dict[int, Tuple[Optional[Vector], Optional[Vector]]] = {}
            for p, ch, v in self._card_rows(card, ("step", "here")):
                if not p.startswith("step-"):
                    continue
                n = int(p.split("-", 1)[1])
                general, specific = out.get(n, (None, None))
                out[n] = (v, specific) if ch == "step" else (general, v)
            self._steps_of[card] = out
        return dict(self._steps_of[card])

    def parts(self, card: Optional[str] = None) -> Dict[Tuple[str, str], Vector]:
        if card is None:
            return {k: v for per in self._groups()["parts"].values() for k, v in per.items()}
        if self._grouped is not None:
            return dict(self._grouped["parts"].get(card, {}))
        if card not in self._parts_of:
            self._parts_of[card] = {(card, p): v for p, _, v in self._card_rows(card, ("part",))}
        return dict(self._parts_of[card])

    def signature(self, channels: Optional[Iterable[str]]) -> str:
        """A fingerprint of every vector in these channels (all of them for None), so a
        result worked out from them can be kept and trusted until one of them changes."""
        want = set(channels) if channels is not None else None
        with closing(self._db()) as db:
            rows = [((c, p, ch), h) for c, p, ch, h in db.execute("SELECT card, part, channel, hash FROM vectors")
                    if want is None or ch in want]
        return _fingerprint(rows, self.embedder.id)

    def derived(self, key: str, sig: str) -> Optional[str]:
        """A result kept by ``keep``, if it was worked out from the same vectors."""
        with closing(self._db()) as db:
            db.execute("CREATE TABLE IF NOT EXISTS derived(key TEXT PRIMARY KEY, sig TEXT, value TEXT)")
            row = db.execute("SELECT sig, value FROM derived WHERE key=?", (key,)).fetchone()
        return row[1] if row and row[0] == sig else None

    def keep(self, key: str, sig: str, value: str) -> None:
        with closing(self._db()) as db:
            db.execute("CREATE TABLE IF NOT EXISTS derived(key TEXT PRIMARY KEY, sig TEXT, value TEXT)")
            db.execute("INSERT OR REPLACE INTO derived VALUES(?, ?, ?)", (key, sig, value))
            db.commit()

    def keep_steps(self, sig: str, summary: str, rows: Iterable[Tuple[str, int, int, int]]) -> None:
        """Keep the step types: a summary (thresholds, steps per build) and one row per
        step, (build, step, type, how many other builds share it), written together."""
        with closing(self._db()) as db:
            db.execute("CREATE TABLE IF NOT EXISTS derived(key TEXT PRIMARY KEY, sig TEXT, value TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS step_types(card TEXT, step INTEGER, type INTEGER, df INTEGER, "
                       "PRIMARY KEY(card, step))")
            db.execute("DELETE FROM step_types")
            db.executemany("INSERT INTO step_types VALUES(?, ?, ?, ?)", rows)
            db.execute("INSERT OR REPLACE INTO derived VALUES('steps', ?, ?)", (sig, summary))
            db.commit()

    def step_facts(self, card: Optional[str] = None) -> List[Tuple[str, int, int, int]]:
        """The kept step types, for one build or all: (build, step, type, shared by)."""
        with closing(self._db()) as db:
            db.execute("CREATE TABLE IF NOT EXISTS step_types(card TEXT, step INTEGER, type INTEGER, df INTEGER, "
                       "PRIMARY KEY(card, step))")
            if card is None:
                return db.execute("SELECT card, step, type, df FROM step_types").fetchall()
            return db.execute("SELECT card, step, type, df FROM step_types WHERE card=?", (card,)).fetchall()

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
        out = {"embedder": self.embedder.id, "path": str(self.path), "built": meta.get("built", "never"), "vectors": str(n)}
        if self.store is not None:
            out["database"] = f"{self.store.url} ({'up to date' if self.store_ready() else 'behind; `astaui index` brings it up'})"
        return out
