"""The vectors in Postgres with pgvector, for a knowledge base too large to scan.

The SQLite index stays what it was: the cache of every embedding, keyed by the
hash of its text, so nothing is embedded twice. When a database is set for a
knowledge base (``astaui config database URL``, or ``$ASTAUI_DATABASE_URL``),
every vector is also kept in one Postgres table per knowledge base and embedder,
with an HNSW index per channel. A search then asks Postgres for the few hundred
builds nearest the request in each channel, and does everything it did before
(facet by facet, the far match, the steps) on those alone.

Nothing here is needed to search: without psycopg, or without a database, the
knowledge base searches from the SQLite index as before.
"""

from __future__ import annotations

import hashlib
import os
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from .kb import KB, KBError, user_config

Key = Tuple[str, str, str]  # (build id, part id or '', channel)
HNSW_MAX_DIM = 2000          # pgvector's HNSW limit for vector; halfvec goes to 4000
HALF_MAX_DIM = 4000


def database_url(kb: KB) -> Optional[str]:
    """The database set for this knowledge base on this computer, if any:
    ``$ASTAUI_DATABASE_URL`` first, then ``astaui config database``."""
    env = os.environ.get("ASTAUI_DATABASE_URL")
    if env is not None:
        return env or None
    per_kb = (user_config().get("database") or {})
    return per_kb.get(str(kb.root.resolve())) if isinstance(per_kb, dict) else None


def _channel(name: str) -> str:
    """A channel name as an SQL literal. Channel names are written into the query, not
    passed as parameters, so Postgres can use the channel's partial index."""
    if not name.replace("_", "").isalnum():
        raise KBError(f"not a channel name: {name!r}")
    return f"'{name}'"


def _vec_text(v: Sequence[float]) -> str:
    return "[" + ",".join("0" if not x else format(x, ".7g") for x in v) + "]"


def _parse(text: str) -> List[float]:
    return [float(x) for x in text.strip("[]").split(",")] if text and text != "[]" else []


class PgStore:
    """One knowledge base's vectors for one embedder, in one table."""

    def __init__(self, url: str, kb: KB, embedder_id: str):
        try:
            import psycopg  # type: ignore
        except ImportError:
            raise KBError("A database is set for this knowledge base, but psycopg is not installed "
                          "(run setup/python.sh, or use .venv/bin/python)") from None
        self._psycopg = psycopg
        self.url = url
        self.embedder_id = embedder_id
        where = f"{kb.index_dir.resolve()}\x1f{embedder_id}"
        self.table = "astaui_" + hashlib.sha1(where.encode("utf-8")).hexdigest()[:16]
        self._conn = None

    # -- connection ------------------------------------------------------------------
    def conn(self):
        if self._conn is None or self._conn.closed:
            self._conn = self._psycopg.connect(self.url, autocommit=True)
        return self._conn

    @contextmanager
    def _tx(self) -> Iterator[Any]:
        with self.conn().transaction():
            with self.conn().cursor() as cur:
                yield cur

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # -- schema ----------------------------------------------------------------------
    def _kind(self, dim: int) -> str:
        if dim <= HNSW_MAX_DIM:
            return "vector"
        if dim <= HALF_MAX_DIM:
            return "halfvec"
        raise KBError(f"{self.embedder_id} gives {dim} numbers per vector; pgvector indexes at most {HALF_MAX_DIM}")

    def _ensure(self, dim: int) -> str:
        kind = self._kind(dim)
        with self._tx() as cur:
            cur.execute("CREATE TABLE IF NOT EXISTS astaui_meta (tbl text, key text, value text, PRIMARY KEY (tbl, key))")
            cur.execute(f"CREATE TABLE IF NOT EXISTS {self.table} ("
                        f"card text NOT NULL, part text NOT NULL, channel text NOT NULL, hash text NOT NULL, "
                        f"embedding {kind}({dim}) NOT NULL, PRIMARY KEY (card, part, channel))")
            cur.execute("INSERT INTO astaui_meta VALUES (%s, 'embedder', %s), (%s, 'kind', %s) "
                        "ON CONFLICT (tbl, key) DO UPDATE SET value = EXCLUDED.value",
                        (self.table, self.embedder_id, self.table, kind))
        return kind

    def kind(self) -> str:
        return self.meta("kind") or "vector"

    def _index_channels(self, channels: Iterable[str]) -> None:
        """An HNSW index for each channel, partial, so a nearest-neighbour query on one
        channel walks only that channel's vectors."""
        ops = "halfvec_cosine_ops" if self.kind() == "halfvec" else "vector_cosine_ops"
        with self._tx() as cur:
            for ch in sorted(set(channels)):
                name = f"{self.table}_{hashlib.sha1(ch.encode()).hexdigest()[:8]}"
                cur.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {self.table} USING hnsw (embedding {ops}) "
                            f"WHERE channel = {_channel(ch)}")

    def meta(self, key: str) -> Optional[str]:
        try:
            with self._tx() as cur:
                cur.execute("SELECT value FROM astaui_meta WHERE tbl = %s AND key = %s", (self.table, key))
                row = cur.fetchone()
        except self._psycopg.errors.UndefinedTable:
            return None
        return row[0] if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self._tx() as cur:
            cur.execute("INSERT INTO astaui_meta VALUES (%s, %s, %s) ON CONFLICT (tbl, key) DO UPDATE SET value = EXCLUDED.value",
                        (self.table, key, value))

    # -- keeping it in step with the SQLite index ------------------------------------------
    def sync(self, hashes: Dict[Key, str], load: Callable[[List[Key]], Dict[Key, Sequence[float]]],
             version: str, batch: int = 2000) -> Dict[str, int]:
        """Make the table hold exactly the index's vectors: hashes[(card, part, channel)] is
        each one's text hash, and load(keys) reads those vectors. Only what changed is
        read and written, a batch at a time. ``version`` is remembered, so a search knows
        the table matches the index it came from."""
        if not hashes:
            return {"added": 0, "removed": 0, "kept": 0}
        try:
            with self._tx() as cur:
                cur.execute(f"SELECT card, part, channel, hash FROM {self.table}")
                have = {(c, p, ch): h for c, p, ch, h in cur.fetchall()}
        except self._psycopg.errors.UndefinedTable:
            have = {}
        gone = [k for k in have if k not in hashes]
        todo = sorted(k for k, h in hashes.items() if have.get(k) != h)
        if gone:
            with self._tx() as cur:
                cur.executemany(f"DELETE FROM {self.table} WHERE card = %s AND part = %s AND channel = %s", gone)
        kind, dim = None, None
        for i in range(0, len(todo), batch):
            vecs = load(todo[i:i + batch])
            if not vecs:
                continue
            if kind is None:
                dim = len(next(iter(vecs.values())))
                kind = self._ensure(dim)
            with self._tx() as cur:
                cur.execute(f"CREATE TEMP TABLE IF NOT EXISTS incoming (card text, part text, channel text, hash text, "
                            f"embedding {kind}({dim})) ON COMMIT DELETE ROWS")
                with cur.copy("COPY incoming (card, part, channel, hash, embedding) FROM STDIN") as copy:
                    for k, v in vecs.items():
                        copy.write_row((k[0], k[1], k[2], hashes[k], _vec_text(v)))
                cur.execute(f"INSERT INTO {self.table} SELECT * FROM incoming "
                            "ON CONFLICT (card, part, channel) DO UPDATE SET hash = EXCLUDED.hash, embedding = EXCLUDED.embedding")
        if kind is not None or have:
            self._index_channels({k[2] for k in hashes})
            self.set_meta("version", version)
            if todo or gone:
                with self._tx() as cur:
                    cur.execute(f"ANALYZE {self.table}")
        return {"added": len(todo), "removed": len(gone), "kept": len(hashes) - len(todo)}

    def drop(self) -> None:
        with self._tx() as cur:
            cur.execute(f"DROP TABLE IF EXISTS {self.table}")
            cur.execute("DELETE FROM astaui_meta WHERE tbl = %s", (self.table,))

    # -- asking ------------------------------------------------------------------------
    def nearest(self, channel: str, q: Sequence[float], k: int, app: bool = True) -> List[Tuple[str, str, float]]:
        """The k vectors of one channel nearest q, by cosine similarity, best first:
        [(build, part, similarity)]. App-level channels have part ''."""
        cast = self.kind()
        qt = _vec_text(q)
        with self._tx() as cur:
            # Enough candidates for the index to return k after the channel filter.
            cur.execute(f"SET LOCAL hnsw.ef_search = {max(40, min(1000, int(k)))}")
            cur.execute("SET LOCAL hnsw.iterative_scan = relaxed_order")
            cur.execute(f"SELECT card, part, 1 - (embedding <=> %s::{cast}) FROM {self.table} "
                        f"WHERE channel = {_channel(channel)} ORDER BY embedding <=> %s::{cast} LIMIT %s",
                        (qt, qt, int(k)))
            rows = cur.fetchall()
        out = [(c, p, float(s)) for c, p, s in rows if (p == "") == app]
        out.sort(key=lambda r: -r[2])
        return out

    def scores(self, channel: str, q: Sequence[float], cards: Sequence[str]) -> Dict[str, float]:
        """The exact similarity of q with each named build's vector in one channel."""
        if not cards:
            return {}
        cast = self.kind()
        with self._tx() as cur:
            cur.execute(f"SELECT card, 1 - (embedding <=> %s::{cast}) FROM {self.table} "
                        f"WHERE channel = {_channel(channel)} AND part = '' AND card = ANY(%s)", (_vec_text(q), list(cards)))
            return {c: float(s) for c, s in cur.fetchall()}

    def vectors(self, channels: Sequence[str], cards: Sequence[str]) -> Dict[Key, List[float]]:
        """The stored vectors of these builds in these channels."""
        if not cards or not channels:
            return {}
        with self._tx() as cur:
            cur.execute(f"SELECT card, part, channel, embedding::text FROM {self.table} "
                        f"WHERE channel = ANY(%s) AND card = ANY(%s)", (list(channels), list(cards)))
            return {(c, p, ch): _parse(t) for c, p, ch, t in cur.fetchall()}

    def vectors_at(self, channel: str, keys: Sequence[Tuple[str, str]]) -> Dict[Tuple[str, str], List[float]]:
        """The stored vectors at these (build, part) places in one channel, in one query."""
        if not keys:
            return {}
        with self._tx() as cur:
            cur.execute(f"SELECT t.card, t.part, t.embedding::text FROM {self.table} t "
                        f"JOIN unnest(%s::text[], %s::text[]) AS k(card, part) ON t.card = k.card AND t.part = k.part "
                        f"WHERE t.channel = {_channel(channel)}", ([k[0] for k in keys], [k[1] for k in keys]))
            return {(c, p): _parse(t) for c, p, t in cur.fetchall()}

    def scores_at(self, channel: str, q: Sequence[float], keys: Sequence[Tuple[str, str]]) -> Dict[Tuple[str, str], float]:
        """q's similarity with the vectors at these (build, part) places in one channel."""
        if not keys:
            return {}
        cast = self.kind()
        with self._tx() as cur:
            cur.execute(f"SELECT t.card, t.part, 1 - (t.embedding <=> %s::{cast}) FROM {self.table} t "
                        f"JOIN unnest(%s::text[], %s::text[]) AS k(card, part) ON t.card = k.card AND t.part = k.part "
                        f"WHERE t.channel = {_channel(channel)}", (_vec_text(q), [k[0] for k in keys], [k[1] for k in keys]))
            return {(c, p): float(x) for c, p, x in cur.fetchall()}

    def count(self) -> int:
        with self._tx() as cur:
            cur.execute(f"SELECT count(*) FROM {self.table}")
            return int(cur.fetchone()[0])
