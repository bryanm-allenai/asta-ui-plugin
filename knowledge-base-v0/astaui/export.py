"""Getting the vectors out, for other tools.

- ``projector``: two TSV files for Google's Embedding Projector
  (projector.tensorflow.org): load the vectors and the metadata, colour by any
  facet, look at neighbours. Nothing to host.
- ``sql``: a script for Postgres with the pgvector extension (Cloud SQL, AlloyDB,
  or a local Docker container): one table of cards, one of vectors.
- ``jsonl``: one line per vector with its card's metadata, for a notebook.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .index import APP_CHANNELS, Index
from .kb import KB


def _meta(kb: KB) -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}
    cards = {c["id"]: c for c in kb.cards()}
    for b in kb.builds():
        app = (cards.get(b.id) or {}).get("app", {})

        def first(facet: str, lst: str) -> str:
            w = (app.get(facet) or {}).get(lst) or []
            return w[0] if w else ""

        out[b.id] = {
            "id": b.id,
            "title": app.get("title") or b.title,
            "field": (app.get("field") or {}).get("text", ""),
            "discipline": first("field", "disciplines"),
            "task": first("task", "verbs"),
            "data": first("data", "shapes"),
            "stage": first("stage", "terms"),
            "pattern": first("mechanism", "patterns"),
            "kind": b.kind,
        }
    return out


def _clean(s: str) -> str:
    return " ".join(str(s).split()).replace("\t", " ")


def projector(kb: KB, index: Index, channel: str, out_dir: Path) -> List[Path]:
    index.ensure()
    vecs = index.channel(channel)
    meta = _meta(kb)
    out_dir.mkdir(parents=True, exist_ok=True)
    vpath = out_dir / f"{channel}-vectors.tsv"
    mpath = out_dir / f"{channel}-metadata.tsv"
    cols = ["id", "title", "discipline", "field", "task", "data", "stage", "pattern", "kind"]
    ids = [i for i in meta if i in vecs]
    with vpath.open("w", encoding="utf-8") as f:
        for i in ids:
            f.write("\t".join(f"{x:.6f}" for x in vecs[i]) + "\n")
    with mpath.open("w", encoding="utf-8") as f:
        f.write("\t".join(cols) + "\n")
        for i in ids:
            f.write("\t".join(_clean(meta[i][c]) for c in cols) + "\n")
    return [vpath, mpath]


def _sql_str(s: Any) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def sql(kb: KB, index: Index) -> str:
    """A pgvector load script. Cards go in as JSON; each vector keeps its channel."""
    index.ensure()
    cards = kb.cards()
    carded = {c["id"] for c in cards}
    vectors = [(cid, "", ch, v) for ch in APP_CHANNELS for cid, v in sorted(index.channel(ch).items())]
    vectors += [(cid, pid, "part", v) for (cid, pid), v in sorted(index.parts().items())]
    vectors = [row for row in vectors if row[0] in carded]
    dim = len(vectors[0][3]) if vectors else 1
    emb = _sql_str(index.embedder.id)
    out = [
        f"-- {kb.config.get('name', 'knowledge base')}: cards and vectors from {index.embedder.id}",
        "-- Load with: psql \"$DATABASE_URL\" -f kb.sql",
        "CREATE EXTENSION IF NOT EXISTS vector;",
        "CREATE TABLE IF NOT EXISTS cards (id text PRIMARY KEY, card jsonb NOT NULL);",
        "CREATE TABLE IF NOT EXISTS vectors (card text REFERENCES cards(id) ON DELETE CASCADE, part text NOT NULL DEFAULT '', "
        f"channel text NOT NULL, embedder text NOT NULL, embedding vector({dim}) NOT NULL, PRIMARY KEY (card, part, channel, embedder));",
        "BEGIN;",
        f"DELETE FROM vectors WHERE embedder = {emb};",
    ]
    for c in cards:
        out.append(f"INSERT INTO cards VALUES ({_sql_str(c['id'])}, {_sql_str(json.dumps(c, ensure_ascii=False))}::jsonb) "
                   "ON CONFLICT (id) DO UPDATE SET card = EXCLUDED.card;")
    for cid, pid, ch, v in vectors:
        literal = "[" + ",".join(f"{x:.6f}" for x in v) + "]"
        out.append(f"INSERT INTO vectors (card, part, channel, embedder, embedding) VALUES "
                   f"({_sql_str(cid)}, {_sql_str(pid)}, {_sql_str(ch)}, {emb}, '{literal}');")
    out += [
        "COMMIT;",
        "-- Nearest cards to a vector on one channel:",
        "--   SELECT card, 1 - (embedding <=> $1) AS similarity FROM vectors",
        "--   WHERE channel = 'card' AND part = '' ORDER BY embedding <=> $1 LIMIT 5;",
        "",
    ]
    return "\n".join(out)


def jsonl(kb: KB, index: Index, out: Path) -> Path:
    index.ensure()
    meta = _meta(kb)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for ch in APP_CHANNELS:
            for cid, v in sorted(index.channel(ch).items()):
                f.write(json.dumps({**meta.get(cid, {"id": cid}), "part": "", "channel": ch, "embedder": index.embedder.id,
                                    "vector": [round(x, 6) for x in v]}, ensure_ascii=False) + "\n")
        for (cid, pid), v in sorted(index.parts().items()):
            f.write(json.dumps({**meta.get(cid, {"id": cid}), "part": pid, "channel": "part", "embedder": index.embedder.id,
                                "vector": [round(x, 6) for x in v]}, ensure_ascii=False) + "\n")
    return out
