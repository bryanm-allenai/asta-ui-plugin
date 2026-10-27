"""A record of what was searched for, what came back and what helped.

The prototype is a probe for studying how scientists reuse each other's
interfaces, so every search is logged locally (``kb/.usage/usage.jsonl``, never
committed), and ``astaui feedback`` records whether a match was used and helped:
the Architecture board's open question, "what makes a match good: same
structure, or a scientist saying it helped?". Set ASTAUI_NO_LOG=1 to turn it off.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .kb import KB, read_jsonl


def _path(kb: KB):
    return kb.usage_dir / "usage.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def log_search(kb: KB, res: Dict[str, Any]) -> Optional[str]:
    if os.environ.get("ASTAUI_NO_LOG"):
        return None
    sid = uuid.uuid4().hex[:10]
    q = res.get("query", {})
    row = {
        "event": "search",
        "id": sid,
        "at": _now(),
        "request": q.get("request", ""),
        "described": [k for k in ("summary", "task", "data", "stage", "mechanism", "field") if q.get(k)],
        "embedder": res.get("embedder"),
        "results": [[r["id"], r["score"]] for r in res.get("results", [])],
        "far": res["far"]["id"] if res.get("far") else None,
    }
    try:
        kb.usage_dir.mkdir(parents=True, exist_ok=True)
        with _path(kb).open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        return None
    return sid


def log_feedback(kb: KB, search_id: str, build: str, used: Optional[bool], helped: Optional[bool], note: str = "") -> Dict[str, Any]:
    row = {"event": "feedback", "search": search_id, "at": _now(), "build": build, "used": used, "helped": helped, "note": note}
    kb.usage_dir.mkdir(parents=True, exist_ok=True)
    with _path(kb).open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def history(kb: KB) -> List[Dict[str, Any]]:
    return read_jsonl(_path(kb))
