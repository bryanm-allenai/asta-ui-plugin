"""The console: a local page that shows how the knowledge base is working.

``astaui console`` starts a small web server on this machine (127.0.0.1 only) and
opens a page with the knowledge base's health, every build and its card, a search
playground that shows the workflow comparison and the code for each step, the
workflow families, the evaluation, what scientists searched for and whether it
helped, and the ontology. It reads the files live, so a change to a card shows up
on the next refresh. It changes nothing except the vector cache, when asked to
rebuild it.
"""

from __future__ import annotations

import json
import mimetypes
import statistics
import threading
import traceback
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlparse

from .cards import check_card, part_spans
from .index import Index
from .kb import KB, KBError, read_json, write_json
from .ontology import FACETS, LISTS, Ontology
from .privacy import scan_build


class Console:
    """The data behind the page. Searchers are kept per embedder, and rebuilt when
    the knowledge base's files change."""

    def __init__(self, kb_path: Optional[str] = None):
        self.kb_path = kb_path
        self.lock = threading.Lock()
        self._searchers: Dict[str, Tuple[float, Any]] = {}

    # -- plumbing -----------------------------------------------------------------
    def kb(self) -> KB:
        return KB.open(self.kb_path)

    def _stamp(self, kb: KB) -> float:
        newest = 0.0
        for d in (kb.builds_dir, kb.cards_dir, kb.eval_dir):
            if d.exists():
                for p in d.rglob("*"):
                    if p.is_file():
                        newest = max(newest, p.stat().st_mtime)
        for f in ("ontology.json", "kb.json"):
            if (kb.root / f).exists():
                newest = max(newest, (kb.root / f).stat().st_mtime)
        return newest

    def searcher(self, embedder: Optional[str]):
        from .search import Searcher

        kb = self.kb()
        name = embedder or kb.config.get("embedder", "lexical")
        stamp = self._stamp(kb)
        with self.lock:
            cached = self._searchers.get(name)
            if cached and cached[0] == stamp:
                return cached[1]
            s = Searcher(kb, name)
            self._searchers[name] = (stamp, s)
            return s

    def space(self, embedder: Optional[str]):
        from .workflows import StepSpace

        s = self.searcher(embedder)
        return s._space_ready()

    def embedders(self, kb: KB) -> List[Dict[str, Any]]:
        """The configured embedder, and every embedder with a cache on disk."""
        import sqlite3
        from contextlib import closing

        names = [kb.config.get("embedder", "lexical")]
        if kb.index_dir.exists():
            for p in sorted(kb.index_dir.glob("*.sqlite")):
                try:
                    with closing(sqlite3.connect(str(p))) as db:
                        row = db.execute("SELECT value FROM meta WHERE key='embedder'").fetchone()
                    if row:
                        names.append("lexical" if row[0] == "lexical/1" else row[0])
                except sqlite3.Error:
                    continue
        out = []
        for n in dict.fromkeys(names):
            out.append({"name": n, "default": n == names[0]})
        return out

    # -- views --------------------------------------------------------------------------
    def overview(self, embedder: Optional[str]) -> Dict[str, Any]:
        from .cli import run_checks
        from .usage import history

        kb = self.kb()
        ont = Ontology.load(kb.root / "ontology.json")
        cards = {c["id"]: c for c in kb.cards()}
        kinds: Dict[str, int] = {}
        lint_block = lint_look = 0
        for b in kb.builds():
            kinds[b.kind or "unknown"] = kinds.get(b.kind or "unknown", 0) + 1
            for f in scan_build(b):
                if f.level == "block":
                    lint_block += 1
                else:
                    lint_look += 1
        parts = sum(len(c.get("parts", [])) for c in cards.values())
        spans = sum(len(part_spans(p)) for c in cards.values() for p in c.get("parts", []))
        steps = sum(len((c["app"].get("workflow") or {}).get("steps", [])) for c in cards.values())
        proposals = {(p["facet"], p["list"], p["term"]) for c in cards.values() for p in c.get("proposed", [])}
        idx = Index(kb, embedder)
        info = idx.info()
        fresh = idx.is_fresh() if info.get("built") != "never" else False
        events = history(kb)
        searches = [e for e in events if e.get("event") == "search"]
        feedback = [e for e in events if e.get("event") == "feedback"]
        last_eval = self._load_eval(kb, idx.embedder.id)
        fams = None
        try:
            if cards and fresh:
                from .workflows import families

                res = families(self.space(embedder))
                fams = {"families": sum(1 for f in res["families"] if len(f["members"]) > 1),
                        "alone": sum(1 for f in res["families"] if len(f["members"]) == 1)}
        except KBError:
            fams = None
        return {
            "name": kb.config.get("name"),
            "root": str(kb.root),
            "read_only": kb.read_only,
            "ontology": ont.version,
            "embedder": idx.embedder.id,
            "embedders": self.embedders(kb),
            "counts": {"builds": len(kb.build_ids()), "cards": len(cards), "parts": parts, "spans": spans,
                       "steps": steps, "queries": len(kb.queries()), "pairs": len(kb.pairs())},
            "kinds": kinds,
            "problems": run_checks(kb),
            "without_card": [b for b in kb.build_ids() if b not in cards],
            "privacy": {"must_go": lint_block, "to_look_at": lint_look},
            "proposals": len(proposals),
            "index": {**info, "fresh": fresh},
            "activity": {"searches": len(searches), "feedback": len(feedback),
                         "helped": sum(1 for f in feedback if f.get("helped") is True),
                         "not_helped": sum(1 for f in feedback if f.get("helped") is False),
                         "last": (searches[-1]["at"] if searches else None)},
            "eval": last_eval and {"at": last_eval.get("at"), "modes": (last_eval.get("queries") or {}).get("modes"),
                                   "far": (last_eval.get("queries") or {}).get("far"),
                                   "steps": (last_eval.get("queries") or {}).get("steps")},
            "families": fams,
        }

    def builds(self, embedder: Optional[str]) -> List[Dict[str, Any]]:
        from .slices import slice_part
        from .symbols import index_build

        kb = self.kb()
        ont = Ontology.load(kb.root / "ontology.json")
        cards = {c["id"]: c for c in kb.cards()}
        family = self._family_map(embedder) if cards else {}
        rows = []
        for b in kb.builds():
            card = cards.get(b.id)
            row: Dict[str, Any] = {
                "id": b.id, "title": b.title, "kind": b.kind, "author": (b.meta.get("author") or {}).get("name", ""),
                "prompts": len(b.prompts), "files": len(b.code_files()), "card": bool(card),
            }
            entry = b.path / b.meta.get("entry", "") if b.meta.get("entry") else None
            if entry and entry.is_file():
                row["lines"] = entry.read_text(encoding="utf-8", errors="replace").count("\n") + 1
            if card:
                app = card["app"]
                _, chk = check_card(ont, card, b, made=card.get("made"))
                syms = index_build(b)
                sizes = [slice_part(kb, b.id, p, symbols=syms)["lines"] for p in card.get("parts", [])]
                row.update({
                    "field": (app.get("field") or {}).get("text", ""),
                    "discipline": ((app.get("field") or {}).get("disciplines") or [""])[0],
                    "workflow": (app.get("workflow") or {}).get("name", ""),
                    "family": family.get(b.id, ""),
                    "parts": len(card.get("parts", [])),
                    "spans": sum(len(part_spans(p)) for p in card.get("parts", [])),
                    "slice_median": int(statistics.median(sizes)) if sizes else 0,
                    "problems": len(chk.errors), "notes": len(chk.warnings),
                })
            rows.append(row)
        return rows

    def build(self, build_id: str, embedder: Optional[str]) -> Dict[str, Any]:
        kb = self.kb()
        ont = Ontology.load(kb.root / "ontology.json")
        b = kb.build(build_id)
        out: Dict[str, Any] = {"id": b.id, "meta": b.meta, "prompts": b.prompts,
                               "files": [str(p.relative_to(b.path)) for p in b.code_files()],
                               "privacy": [f.__dict__ for f in scan_build(b)]}
        if build_id in kb.card_ids():
            card = kb.card(build_id)
            _, chk = check_card(ont, card, b, made=card.get("made"))
            out.update(card=card, problems=chk.errors, notes=chk.warnings)
            try:
                from .workflows import compare_cards

                space = self.space(embedder)
                others = []
                for oid in space.vecs:
                    if oid != build_id and build_id in space.vecs:
                        others.append((space.overlap(build_id, oid), oid))
                others.sort(reverse=True)
                out["neighbours"] = [{"id": oid, "title": kb.card(oid)["app"].get("title", oid), "overlap": round(o, 3)}
                                     for o, oid in others[:4]]
            except KBError:
                pass
        return out

    def slice(self, build_id: str, part_id: str, deps: bool) -> Dict[str, Any]:
        from .slices import find_part, slice_part

        kb = self.kb()
        return slice_part(kb, build_id, find_part(kb, build_id, part_id), deps=deps)

    def search(self, body: Dict[str, Any]) -> Dict[str, Any]:
        s = self.searcher(body.get("embedder"))
        card = body.get("card") or None
        if isinstance(card, str) and card.strip():
            card = json.loads(card)
        res = s.search(body.get("request", ""), card if isinstance(card, dict) else None, k=int(body.get("k") or 5),
                       parts=int(body.get("parts") or 2))
        return res

    def examples(self) -> List[Dict[str, Any]]:
        kb = self.kb()
        return [{"id": q.get("id"), "request": q.get("request", ""), "card": q.get("card"), "wanted": q.get("wanted", [])}
                for q in kb.queries()]

    def workflows(self, embedder: Optional[str]) -> Dict[str, Any]:
        from .workflows import families

        return families(self.space(embedder))

    def compare(self, a: str, b: str, embedder: Optional[str]) -> Dict[str, Any]:
        from .workflows import compare_cards

        kb = self.kb()
        d = compare_cards(self.space(embedder), kb.card(a), kb.card(b))
        d["a_title"] = kb.card(a)["app"].get("title", a)
        d["b_title"] = kb.card(b)["app"].get("title", b)
        return d

    def _eval_path(self, kb: KB, embedder_id: str) -> Path:
        safe = "".join(ch if ch.isalnum() else "-" for ch in embedder_id).strip("-")
        return kb.out_dir / f"eval-{safe}.json"

    def _load_eval(self, kb: KB, embedder_id: str) -> Optional[Dict[str, Any]]:
        p = self._eval_path(kb, embedder_id)
        return read_json(p) if p.exists() else None

    def evaluation(self, embedder: Optional[str], run: bool) -> Dict[str, Any]:
        from .evaluate import MODES, run_pairs, run_queries

        kb = self.kb()
        s = self.searcher(embedder)
        if not run:
            return self._load_eval(kb, s.index.embedder.id) or {"never": True, "modes": MODES}
        qres = run_queries(s, kb.queries()) if kb.queries() else None
        pres = run_pairs(s, kb.pairs()) if kb.pairs() else None
        out = {"at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
               "embedder": s.index.embedder.id, "modes": MODES, "queries": qres, "pairs": pres}
        write_json(self._eval_path(kb, s.index.embedder.id), out)
        return out

    def activity(self) -> List[Dict[str, Any]]:
        from .usage import history

        kb = self.kb()
        events = history(kb)
        searches = {e["id"]: {**e, "feedback": []} for e in events if e.get("event") == "search" and e.get("id")}
        loose = []
        for e in events:
            if e.get("event") == "feedback":
                if e.get("search") in searches:
                    searches[e["search"]]["feedback"].append(e)
                else:
                    loose.append(e)
        rows = sorted(searches.values(), key=lambda e: e.get("at", ""), reverse=True)
        return rows + [{"event": "feedback", **e} for e in loose]

    def ontology(self) -> Dict[str, Any]:
        kb = self.kb()
        ont = Ontology.load(kb.root / "ontology.json")
        counts: Dict[Tuple[str, str, str], List[str]] = {}
        used: Dict[Tuple[str, str], Dict[str, int]] = {}
        for c in kb.cards():
            for p in c.get("proposed", []):
                counts.setdefault((p["facet"], p["list"], p["term"]), []).append(c["id"])
            for f in FACETS:
                for lst in LISTS[f]:
                    for w in (c["app"].get(f) or {}).get(lst) or []:
                        used.setdefault((f, lst), {})
                        used[(f, lst)][w] = used[(f, lst)].get(w, 0) + 1
        lists = []
        for f in FACETS:
            for lst in LISTS[f]:
                terms = ont.terms(f, lst)
                u = used.get((f, lst), {})
                lists.append({"facet": f, "list": lst, "terms": len(terms), "open": ont.is_open(f, lst),
                              "used": len(u), "unused": [t.name for t in terms if t.name not in u],
                              "top": sorted(u.items(), key=lambda kv: -kv[1])[:8]})
        return {
            "version": ont.version,
            "lists": lists,
            "moves": len(ont.moves()),
            "proposals": [{"facet": f, "list": l, "term": t, "cards": ids} for (f, l, t), ids in sorted(counts.items(), key=lambda kv: -len(kv[1]))],
            "changes": ont.data.get("changes", []),
        }

    def rebuild_index(self, embedder: Optional[str]) -> Dict[str, Any]:
        kb = self.kb()
        stats = Index(kb, embedder).build()
        with self.lock:
            self._searchers.clear()
        return stats

    def map_page(self, embedder: Optional[str]) -> str:
        from .mapview import map_data, render

        kb = self.kb()
        data = map_data(kb, Index(kb, embedder))
        for it in data["items"]:
            if it.get("entry"):
                rel = Path(it["entry"]).resolve().relative_to(kb.builds_dir.resolve())
                it["entry"] = "/builds/" + "/".join(rel.parts)
        return render(data)

    def _family_map(self, embedder: Optional[str]) -> Dict[str, str]:
        try:
            res = self.workflows(embedder)
        except KBError:
            return {}
        out = {}
        for f in res["families"]:
            for m in f["members"]:
                out[m["id"]] = f["name"] if len(f["members"]) > 1 else ""
        return out


class Handler(BaseHTTPRequestHandler):
    console: Console = None  # set by serve()

    def log_message(self, fmt: str, *args: Any) -> None:  # keep the terminal quiet
        return

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data: Any, code: int = 200) -> None:
        self._send(code, json.dumps(data, ensure_ascii=False, default=str).encode("utf-8"), "application/json; charset=utf-8")

    def _route(self, method: str) -> None:
        url = urlparse(self.path)
        q = {k: v[-1] for k, v in parse_qs(url.query).items()}
        emb = q.get("embedder") or None
        parts = [unquote(p) for p in url.path.strip("/").split("/") if p]
        c = self.console
        try:
            if method == "GET" and not parts:
                return self._send(200, page().encode("utf-8"), "text/html; charset=utf-8")
            if method == "GET" and parts == ["map"]:
                return self._send(200, c.map_page(emb).encode("utf-8"), "text/html; charset=utf-8")
            if method == "GET" and parts and parts[0] == "builds" and len(parts) >= 3:
                return self._file(parts[1], parts[2:])
            if parts[:1] != ["api"]:
                return self._json({"error": "not found"}, 404)
            name = parts[1] if len(parts) > 1 else ""
            body: Dict[str, Any] = {}
            if method == "POST":
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n).decode("utf-8") or "{}") if n else {}
                emb = body.get("embedder") or emb
            if method == "GET" and name == "overview":
                return self._json(c.overview(emb))
            if method == "GET" and name == "builds":
                return self._json(c.builds(emb))
            if method == "GET" and name == "build" and len(parts) == 3:
                return self._json(c.build(parts[2], emb))
            if method == "GET" and name == "slice" and len(parts) == 4:
                return self._json(c.slice(parts[2], parts[3], q.get("deps", "1") != "0"))
            if method == "POST" and name == "search":
                return self._json(c.search({**body, "embedder": emb}))
            if method == "GET" and name == "examples":
                return self._json(c.examples())
            if method == "GET" and name == "workflows":
                return self._json(c.workflows(emb))
            if method == "GET" and name == "compare":
                return self._json(c.compare(q["a"], q["b"], emb))
            if name == "eval":
                return self._json(c.evaluation(emb, run=(method == "POST")))
            if method == "GET" and name == "activity":
                return self._json(c.activity())
            if method == "GET" and name == "ontology":
                return self._json(c.ontology())
            if method == "POST" and name == "index":
                return self._json(c.rebuild_index(emb))
            return self._json({"error": f"no such page: {url.path}"}, 404)
        except KBError as e:
            return self._json({"error": str(e)}, 400)
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            return self._json({"error": f"bad request: {e}"}, 400)
        except Exception as e:  # pragma: no cover - shown on the page, not hidden
            traceback.print_exc()
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    def _file(self, build_id: str, rel: List[str]) -> None:
        """A build's own files, so 'Open the interface' works from the console."""
        kb = self.console.kb()
        root = (kb.builds_dir / build_id).resolve()
        path = (root / "/".join(rel)).resolve()
        if root not in path.parents or not path.is_file():
            return self._json({"error": "not found"}, 404)
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        self._send(200, path.read_bytes(), ctype)

    def do_GET(self) -> None:
        self._route("GET")

    def do_POST(self) -> None:
        self._route("POST")


def serve(kb_path: Optional[str] = None, port: int = 8770, open_browser: bool = True) -> None:
    console = Console(kb_path)
    console.kb()  # fail early, in words, if there is no knowledge base
    Handler.console = console
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"The console is at {url} (this machine only). Ctrl+C stops it.")
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        server.server_close()


def page() -> str:
    """The page, read on every request so edits to it show on a reload, with Asta's
    stylesheet (tokens, fonts, parts) in front of its own."""
    here = Path(__file__).parent
    return (here / "console.html").read_text(encoding="utf-8").replace("__ASTA__", (here / "asta.css").read_text(encoding="utf-8"))
