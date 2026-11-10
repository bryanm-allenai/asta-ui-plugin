"""Fetching a public build's code from its repository when it is first read.

The copy of the knowledge base the plugin ships does not hold the code of builds
found in public repositories: it holds their cards, trees, prompts and
screenshots, and, in ``build.json``, a ``fetch`` record naming where the code is
and the fingerprint of every file the card points at::

    "fetch": {"from": "https://raw.githubusercontent.com/<owner>/<repo>/<commit>/",
              "files": {"code/app.js": {"sha256": "…", "bytes": 1234, "lines": 56}}}

The first time a skill reads one of those files (a search with code, a slice,
``astaui show``), the files are downloaded at that commit, checked against their
fingerprints and kept in the build's folder, so each build is fetched once.
"""

from __future__ import annotations

import hashlib
import os
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Tuple

from .kb import KBError

TIMEOUT = 60


def file_url(base: str, rel: str) -> str:
    """The address of a build file in its repository: the build keeps the
    repository's files under ``code/``."""
    path = rel[len("code/"):] if rel.startswith("code/") else rel
    return base.rstrip("/") + "/" + urllib.parse.quote(path)


def _get(url: str) -> Tuple[Optional[bytes], str]:
    last = ""
    for _ in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "astaui"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return r.read(), ""
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None, "not found"
            last = f"HTTP {e.code}"
        except (urllib.error.URLError, OSError) as e:
            last = str(getattr(e, "reason", e))
    return None, last


def fetch_build_code(build, rels: List[str]) -> List[str]:
    if os.environ.get("ASTAUI_NO_FETCH"):
        raise KBError(f"{build.id}'s code is not on this computer and fetching is off (ASTAUI_NO_FETCH)")
    info = build.remote_code()
    base = (build.meta.get("fetch") or {}).get("from") or ""
    if not (base.startswith("https://") or base.startswith(("http://127.0.0.1:", "http://localhost:"))):
        raise KBError(f"{build.id} points at its code but says no https address to fetch it from")
    urls = {rel: file_url(base, rel) for rel in rels}
    with ThreadPoolExecutor(min(8, len(rels))) as ex:
        got = dict(zip(rels, ex.map(_get, (urls[r] for r in rels))))
    problems, done = [], []
    for rel in rels:
        data, why = got[rel]
        if data is None:
            problems.append(f"{rel}: {why}")
            continue
        want = (info.get(rel) or {}).get("sha256")
        if want and hashlib.sha256(data).hexdigest() != want:
            problems.append(f"{rel}: the repository's copy differs from the one the card was written from")
            continue
        out = build.path / rel
        if build.path.resolve() not in out.resolve().parents:
            problems.append(f"{rel}: outside the build folder")
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_name(out.name + ".part")
        tmp.write_bytes(data)
        tmp.replace(out)
        done.append(rel)
    if problems:
        repo = (build.meta.get("source") or {}).get("repo", base)
        raise KBError(f"Could not fetch {build.id}'s code from {repo}: " + "; ".join(problems[:3])
                      + (f" (and {len(problems) - 3} more)" if len(problems) > 3 else ""))
    return done
