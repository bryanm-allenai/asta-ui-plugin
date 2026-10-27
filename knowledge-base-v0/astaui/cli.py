"""The ``astaui`` command. Run ``astaui -h`` for the list, ``astaui <command> -h`` for one."""

from __future__ import annotations

import argparse
import json
import os
import sys
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import __version__
from .builds import KINDS, CONSENT, SOURCES, add_build, check_build, list_sessions, read_prompt_file, session_prompts, this_session
from .cards import check_card, check_query
from .evaluate import MODES, report, run_pairs, run_queries
from .extract import EXTRACT_VERSION, QUERY_VERSION, call_claude, card_schema, describe_prompt, extract_prompt, query_schema
from .index import Index
from .kb import KB, KBError, check_id, init as kb_init, read_json, set_user_config, user_config, write_json, write_jsonl
from .ontology import Ontology
from .privacy import scan_build, strip_build


def _print_json(data: Any) -> None:
    json.dump(data, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


def _say(msg: str = "") -> None:
    sys.stdout.write(msg + "\n")


def _warn(msg: str) -> None:
    sys.stderr.write(msg + "\n")


def _read_json_arg(value: str) -> Any:
    if value == "-":
        return json.loads(sys.stdin.read())
    p = Path(value)
    if p.exists():
        return read_json(p)
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        raise KBError(f"{value!r} is neither a file nor JSON") from None


def _kb(args) -> KB:
    return KB.open(getattr(args, "kb", None))


def _ont(kb: KB) -> Ontology:
    return Ontology.load(kb.root / "ontology.json")


def _writable(kb: KB) -> None:
    if kb.read_only:
        raise KBError(
            f"{kb.root} is the copy a plugin manager installed, so it is read-only. To add to the knowledge base, "
            "clone the repository and point astaui at it: `astaui config kb <clone>/knowledge-base-v0/kb`."
        )


# -- commands ---------------------------------------------------------------------

def cmd_init(args) -> int:
    path = kb_init(Path(args.path), args.name)
    _say(f"Made a knowledge base at {path}. Point astaui at it with `astaui config kb {path}`.")
    return 0


def cmd_config(args) -> int:
    if args.key == "show" or args.key is None:
        cfg = user_config()
        _print_json(cfg or {"kb": None})
        return 0
    if args.key == "inbox-link":
        return _config_inbox(args)
    if args.unset:
        set_user_config("kb", None)
        _say("astaui will look for a knowledge base above the working folder, then use the one it shipped with.")
        return 0
    if not args.value:
        raise KBError("astaui config kb PATH")
    path = Path(args.value).expanduser().resolve()
    KB.open(str(path))  # checks it is one
    where = set_user_config("kb", str(path))
    _say(f"astaui now uses {path} (saved in {where}).")
    return 0


def _config_inbox(args) -> int:
    """The Add only link the line sends builds through. It is checked from
    outside first: it has to open a page in the drive this knowledge base is in.
    The line carries it to scientists; it is never written into the plugin."""
    from .sources import drive_root, open_link, public_link
    if args.unset:
        set_user_config("inbox-link", None)
        set_user_config("inbox", None)
        _say("The line no longer sends builds to the drive; scientists push them to the repository as add-<id> branches.")
        return 0
    if not args.value:
        raise KBError("astaui config inbox-link LINK [--public ADDRESS]")
    link = public_link(args.value, args.public)
    door = open_link(link)
    kb = _kb(args)
    root = drive_root(kb.root)
    page = (root / f"{door['page']}.mrbl") if root else None
    if page is None or not page.is_file():
        raise KBError(f"The link opens {door['page']}, which is not a page in the drive {kb.root} is in")
    set_user_config("inbox-link", link)
    if args.public:
        set_user_config("drive-url", args.public.rstrip("/"))
    where = set_user_config("inbox", str(page))
    _say(f"The line now sends builds to {door['page']} through {link} (saved in {where}).")
    return 0


def cmd_send(args) -> int:
    from .sources import send
    kb = _kb(args)
    res = send(kb, args.id, args.to)
    if args.json:
        _print_json(res)
        return 0
    _say(f"Sent {res['id']} ({max(1, round(res['bytes'] / 1024))} KB) to {res['page']} on {res['drive']}. "
         "The knowledge base's owner's drive checks it and adds it by itself within the hour; sending it again replaces it.")
    return 0


def cmd_filed(args) -> int:
    from .sources import filed_as
    bid = filed_as(Path(args.folder) if args.folder else None)
    if args.json:
        _print_json({"id": bid})
    elif bid:
        _say(f"This folder was filed as {bid}. File it again as {bid}, with --replace, and send it: the newer copy replaces the one sent before.")
    else:
        _say("This folder has not been filed yet.")
    return 0


def cmd_intake(args) -> int:
    from .sources import intake
    kb = _kb(args)
    _writable(kb)
    res = intake(kb, index=not args.no_index)
    if args.json:
        _print_json({"taken": [{k: w.get(k) for k in ("id", "as", "title", "replaced", "stripped")} for w in res["taken"]],
                     "held": [{"id": w["id"], "title": w["title"], "why": w["held"]} for w in res["held"]]})
        return 0
    for w in res["taken"]:
        how = "Replaced" if w.get("replaced") else "Took in"
        also = f" (sent as {w['as']}, which another build has)" if w.get("as") and w["as"] != w["id"] else ""
        _say(f"{how} {w['id']}, {w['title']}{also}" + (f"; swapped {w['stripped']} key(s), email(s) or path(s) for placeholders" if w.get("stripped") else ""))
    for w in res["held"]:
        _say(f"Held {w['id']}, {w['title']}: " + "; ".join(w["held"]))
    if not res["taken"] and not res["held"]:
        _say("Nothing new has been sent.")
    elif res["taken"] and not args.no_index:
        _say("The index is up to date.")
    return 0


def cmd_status(args) -> int:
    kb = _kb(args)
    builds = kb.build_ids()
    cards = set(kb.card_ids())
    missing = [b for b in builds if b not in cards]
    orphan = sorted(cards - set(builds))
    idx = Index(kb, args.embedder)
    info = idx.info()
    fresh = idx.is_fresh() if info.get("built") != "never" else False
    kinds: Dict[str, int] = {}
    for b in kb.builds():
        kinds[b.kind or "unknown"] = kinds.get(b.kind or "unknown", 0) + 1
    data = {"kb": str(kb.root), "read_only": kb.read_only, "builds": len(builds), "cards": len(cards & set(builds)),
            "without_card": missing, "cards_without_build": orphan, "kinds": kinds,
            "queries": len(kb.queries()), "pairs": len(kb.pairs()), "index": {**info, "fresh": fresh}}
    if args.json:
        _print_json(data)
        return 0
    _say(f"{kb.config.get('name')} at {kb.root}{' (read-only)' if kb.read_only else ''}")
    _say(f"{len(builds)} builds ({', '.join(f'{n} {k}' for k, n in sorted(kinds.items()))}), {data['cards']} with cards")
    if missing:
        _say(f"Without a card: {', '.join(missing)}. Write them with `astaui extract <id>`.")
    if orphan:
        _say(f"Cards with no build: {', '.join(orphan)}")
    _say(f"Evaluation: {data['queries']} queries, {data['pairs']} judged pairs")
    _say(f"Index: {info['embedder']}, built {info.get('built')}, {'up to date' if fresh else 'needs `astaui index`'}")
    return 0


def _gather_prompts(args) -> List[Dict[str, Any]]:
    prompts: List[Dict[str, Any]] = []
    if args.session:
        if args.session == "latest":
            found = list_sessions(Path.cwd(), limit=1)
            if not found:
                raise KBError("No Claude Code session found for this folder; pass the session file with --session PATH")
            path = Path(found[0]["path"])
        elif args.session == "this":
            path = this_session()
            if path is None:
                raise KBError("This is not running in a Claude Code session whose log can be found; pass the session file with --session PATH")
        else:
            path = Path(args.session).expanduser()
        prompts += session_prompts(path)
    for f in args.prompts or []:
        prompts += read_prompt_file(Path(f).expanduser())
    for t in args.prompt or []:
        prompts.append({"text": t})
    return prompts


def cmd_add(args) -> int:
    kb = _kb(args)
    _writable(kb)
    author = {k: v for k, v in (("name", args.author), ("role", args.role), ("field", args.field)) if v}
    res = add_build(
        kb, check_id(args.id, "build id"), args.title, _gather_prompts(args), [Path(c) for c in args.code],
        screenshot=Path(args.screenshot) if args.screenshot else None, author=author or None,
        sources=args.source or None, kind=args.kind, consent=args.consent, origin=args.origin or "",
        forked_from=args.forked_from, entry=args.entry, notes=args.notes or "", replace=args.replace,
        source={k: v for k, v in (("repo", args.repo), ("commit", args.commit), ("path", args.subdir)) if v} or None,
    )
    if args.json:
        _print_json(res)
        return 0
    _say(f"Filed {res['id']}: {res['prompts']} prompts, {len(res['files'])} files.")
    for s in res["skipped"][:12]:
        _say(f"  skipped {s}")
    findings = scan_build(kb.build(res["id"]))
    blocks = [f for f in findings if f.level == "block"]
    if findings:
        _say(f"The privacy check found {len(blocks)} thing(s) that must go and {len(findings) - len(blocks)} to look at: run `astaui lint {res['id']}`.")
    _say(f"Next: `astaui extract {res['id']}` to write its card.")
    return 0


def cmd_sessions(args) -> int:
    rows = list_sessions(None if args.all else Path(args.cwd or ".").resolve(), limit=args.limit)
    if args.json:
        _print_json(rows)
        return 0
    if not rows:
        _say("No Claude Code sessions found" + ("" if args.all else " for this folder (try --all)") + ".")
        return 0
    for r in rows:
        _say(f"{r['modified']}  {r['prompts']:>3} prompts  {r['path']}")
        _say(f"            {r['first']}")
    return 0


def cmd_lint(args) -> int:
    kb = _kb(args)
    ids = kb.build_ids() if args.all else [args.id]
    if not ids or ids == [None]:
        raise KBError("astaui lint <build id> (or --all)")
    total_block = 0
    out = []
    for bid in ids:
        b = kb.build(bid)
        if args.strip:
            _writable(kb)
            n = strip_build(b)
            _say(f"{bid}: replaced {n} thing(s) with placeholders")
            b = kb.build(bid)
        for f in scan_build(b):
            out.append({"build": bid, **f.__dict__})
            total_block += f.level == "block"
    if args.json:
        _print_json(out)
    else:
        if not out:
            _say("Nothing found: no keys, email addresses, home paths or large embedded data. Names of people cannot be checked by a program; read the prompts once.")
        for f in out:
            mark = "MUST GO" if f["level"] == "block" else "look   "
            _say(f"{mark}  {f['build']}  {f['file']}:{f['line']}  {f['what']}: {f['excerpt']}")
        if total_block:
            _say(f"\n{total_block} thing(s) must go before this is shared. `astaui lint {args.id or '--all'} --strip` replaces keys, emails and home paths.")
    return 1 if total_block else 0


def cmd_extract(args) -> int:
    kb = _kb(args)
    ont = _ont(kb)
    if args.missing:
        missing = [b for b in kb.build_ids() if b not in set(kb.card_ids())]
        if args.json:
            _print_json(missing)
        else:
            _say("\n".join(missing) if missing else "Every build has a card.")
        return 0
    if not args.id:
        raise KBError("astaui extract <build id>")
    build = kb.build(args.id)
    if args.schema:
        _print_json(card_schema())
        return 0
    if not args.api:
        sys.stdout.write(extract_prompt(ont, build, args.out))
        return 0
    _writable(kb)
    provider = args.provider or kb.config["extract"].get("provider", "anthropic")
    model = args.model or kb.config["extract"].get("model", "claude-opus-5")
    raw = call_claude(extract_prompt(ont, build), card_schema(), provider=provider, model=model)
    card, chk = check_card(ont, raw, build, made={"by": f"api:{provider}", "model": model, "prompt": EXTRACT_VERSION})
    if args.out:
        write_json(Path(args.out), raw)
    return _finish_put(kb, args.id, card, chk, args.json, dry=args.dry_run)


def _finish_put(kb: KB, build_id: str, card: Dict[str, Any], chk, as_json: bool, dry: bool = False) -> int:
    if as_json:
        _print_json({"ok": chk.ok, "errors": chk.errors, "warnings": chk.warnings, "proposed": card.get("proposed", []),
                     "saved": (not dry and chk.ok)})
    else:
        for e in chk.errors:
            _say(f"problem: {e}")
        for w in chk.warnings:
            _say(f"note: {w}")
        for p in card.get("proposed", []):
            _say(f"new word: {p['facet']}.{p['list']} \"{p['term']}\" (kept; listed in `astaui ontology proposals`)")
    if not chk.ok:
        if not as_json:
            _say("Not saved. Fix the problems above and put it again.")
        return 1
    if not dry:
        write_json(kb.card_path(build_id), card)
        if not as_json:
            _say(f"Saved the card for {build_id}: {len(card['parts'])} parts. `astaui index` brings the vectors up to date (search does it too).")
    return 0


def cmd_card(args) -> int:
    kb = _kb(args)
    ont = _ont(kb)
    if args.action == "schema":
        _print_json(card_schema())
        return 0
    if args.action == "put":
        _writable(kb)
        if not args.id or not args.file:
            raise KBError("astaui card put <build id> <file or ->")
        build = kb.build(args.id)
        raw = _read_json_arg(args.file)
        made = {"by": args.by or "agent", "prompt": EXTRACT_VERSION}
        if args.model:
            made["model"] = args.model
        card, chk = check_card(ont, raw, build, made=made)
        return _finish_put(kb, args.id, card, chk, args.json, dry=args.dry_run)
    if args.action == "refresh":
        # Re-check cards under the current ontology and save them: new synonyms map
        # old words, inferred fields fill in, and the card records the new version.
        _writable(kb)
        ids = kb.card_ids() if (args.all or not args.id) else [args.id]
        bad = 0
        for cid in ids:
            old = kb.card(cid)
            card, chk = check_card(ont, old, kb.build(cid), made=old.get("made"))
            if chk.errors:
                bad += 1
                for e in chk.errors:
                    _say(f"{cid}: problem: {e}")
                continue
            if card != old:
                write_json(kb.card_path(cid), card)
                _say(f"{cid}: refreshed for ontology {ont.version}")
        _say(f"{len(ids) - bad} of {len(ids)} cards are on ontology {ont.version}.")
        return 1 if bad else 0
    if args.action == "check":
        ids = kb.card_ids() if (args.id in (None, "--all") or args.all) else [args.id]
        bad = 0
        for cid in ids:
            card = kb.card(cid)
            build = kb.build(cid) if cid in kb.build_ids() else None
            _, chk = check_card(ont, card, build, made=card.get("made"))
            if chk.errors:
                bad += 1
            for e in chk.errors:
                _say(f"{cid}: problem: {e}")
            for w in chk.warnings:
                _say(f"{cid}: note: {w}")
        _say(f"{len(ids) - bad} of {len(ids)} cards are sound.")
        return 1 if bad else 0
    if args.action == "show":
        card = kb.card(args.id)
        if args.json:
            _print_json(card)
        else:
            _print_card(card)
        return 0
    raise KBError(f"unknown card action {args.action!r}")


def _print_card(card: Dict[str, Any]) -> None:
    app = card["app"]
    _say(f"{app.get('title')}  [{card['id']}]")
    _say(app.get("summary", ""))
    for f in ("task", "data", "stage", "mechanism", "field"):
        facet = app.get(f) or {}
        words = [w for k, v in facet.items() if isinstance(v, list) for w in v]
        _say(f"  {f:<10} {facet.get('text', '')}" + (f"  [{', '.join(words)}]" if words else ""))
    wf = app.get("workflow") or {}
    if wf:
        _say(f"  workflow   {wf.get('name', '')}")
        for i, st in enumerate(wf.get("steps", []), 1):
            _say(f"    {i}. {st.get('step', '')}" + (f"  [{', '.join(st['parts'])}]" if st.get("parts") else ""))
            if st.get("here"):
                _say(f"       here: {st['here']}")
        for d in wf.get("distinctive", []):
            _say(f"    particular: {d}")
    from .cards import part_spans

    for p in card.get("parts", []):
        spans = part_spans(p)
        where = ("  " + "; ".join(f"{sp['file']}:{sp['start']}-{sp['end']} {sp.get('role', '')}"
                                 + (f" ({sp['symbol']})" if sp.get("symbol") else "") for sp in spans)) if spans else ""
        indent = "    " if p.get("parent") else "  "
        _say(f"{indent}- {p['title']} ({p['level']}){where}")


def cmd_describe(args) -> int:
    kb = _kb(args)
    ont = _ont(kb)
    context = Path(args.context).read_text(encoding="utf-8") if args.context else ""
    if not args.api:
        sys.stdout.write(describe_prompt(ont, args.request, context))
        return 0
    provider = args.provider or kb.config["extract"].get("provider", "anthropic")
    model = args.model or kb.config["extract"].get("model", "claude-opus-5")
    raw = call_claude(describe_prompt(ont, args.request, context), query_schema(), provider=provider, model=model)
    raw["request"] = raw.get("request") or args.request
    q, chk = check_query(ont, raw)
    q["made"] = {"by": f"api:{provider}", "model": model, "prompt": QUERY_VERSION}
    if args.out:
        write_json(Path(args.out), q)
    if args.json or not args.out:
        _print_json(q)
    for w in chk.warnings:
        _warn(f"note: {w}")
    return 0 if chk.ok else 1


def cmd_index(args) -> int:
    kb = _kb(args)
    idx = Index(kb, args.embedder)
    if args.rebuild and idx.path.exists():
        idx.path.unlink()

    def progress(done: int, total: int) -> None:
        if total > 64:
            _warn(f"  embedded {done} of {total}")

    stats = idx.build(progress)
    if args.json:
        _print_json({**stats, **idx.info()})
    else:
        _say(f"Index for {idx.embedder.id}: {stats['builds']} builds, {stats['cards']} cards, {stats['parts']} parts; "
             f"embedded {stats['embedded']} new texts, reused {stats['reused']}.")
    return 0


def cmd_search(args) -> int:
    from .search import Searcher, format_results
    from .usage import log_search

    kb = _kb(args)
    card = _read_json_arg(args.card) if args.card else None
    if not args.request and not card:
        raise KBError("astaui search \"what you want to build\" (and optionally --card query.json)")
    s = Searcher(kb, args.embedder)
    res = s.search(args.request or "", card, k=args.k, where=args.where or (), exclude=args.exclude or (),
                   parts=args.parts, far=False if args.no_far else None, pieces=args.pieces)
    sid = log_search(kb, res)
    if sid:
        res["search_id"] = sid
    if args.json:
        _print_json(res)
    else:
        sys.stdout.write(format_results(res, show_code=not args.no_code))
        if sid:
            _say(f"\n(Logged as search {sid}. Afterwards: `astaui feedback {sid} <build id> --used yes --helped yes`.)")
    return 0


def cmd_show(args) -> int:
    from .slices import find_part, format_slice, slice_part

    kb = _kb(args)
    b = kb.build(args.id)
    data: Dict[str, Any] = {"id": b.id, "meta": b.meta, "prompts": b.prompts,
                            "files": [str(p.relative_to(b.path)) for p in b.code_files()]}
    card = kb.card(b.id) if b.id in kb.card_ids() else None
    data["card"] = card
    if card and args.part:
        sl = slice_part(kb, b.id, find_part(kb, b.id, args.part))
        if args.json:
            _print_json(sl)
        else:
            sys.stdout.write(format_slice(sl))
        return 0
    if args.json:
        _print_json(data)
        return 0
    _say(f"{b.title}  [{b.id}]  {b.kind} build by {(b.meta.get('author') or {}).get('name', '?')}")
    _say(f"Files: {', '.join(data['files'])}")
    _say("\nPrompts:")
    for i, t in enumerate(b.prompts, 1):
        _say(f"  {i}. {t.get('text', '')}")
    if card:
        _say("\nCard:")
        _print_card(card)
    else:
        _say(f"\nNo card yet: `astaui extract {b.id}`.")
    return 0


def cmd_slice(args) -> int:
    from .slices import find_part, format_slice, slice_part

    kb = _kb(args)
    sl = slice_part(kb, args.build, find_part(kb, args.build, args.part), deps=not args.no_deps, max_lines=args.max_lines)
    if args.json:
        _print_json(sl)
    else:
        sys.stdout.write(format_slice(sl, numbers=not args.plain))
    return 0


def cmd_symbols(args) -> int:
    from .symbols import index_build, outline

    kb = _kb(args)
    b = kb.build(args.build)
    syms = index_build(b)
    if args.file:
        syms = [s for s in syms if s.file in (args.file, f"code/{args.file}")]
    if args.json:
        _print_json([s.as_dict() for s in syms])
        return 0
    for f in sorted({s.file for s in syms}):
        _say(f)
        for line in outline(syms, f, limit=10**6):
            _say(line)
    return 0


def cmd_slim(args) -> int:
    from .builds import slim_build

    kb = _kb(args)
    _writable(kb)
    res = slim_build(kb, args.id, force=args.force, dry_run=args.dry_run)
    if args.json:
        _print_json(res)
        return 0
    verb = "Would keep" if args.dry_run else "Kept"
    _say(f"{verb} {len(res['kept'])} file(s) the card points at; {'would drop' if args.dry_run else 'dropped'} {len(res['dropped'])} "
         f"({res['dropped_bytes'] // 1000} KB). The full code stays at {res['source']}.")
    return 0


def cmd_console(args) -> int:
    from .console import serve

    serve(getattr(args, "kb", None), port=args.port, open_browser=not args.no_open)
    return 0


def _page(path: str) -> str:
    """A Marble page's source, from its path in the drive (or anywhere)."""
    p = Path(path)
    if not p.is_file():
        raise KBError(f"No page at {path}; run this from the drive's folder, or give the page's full path")
    return p.read_text(encoding="utf-8")


def cmd_marble_ops(args) -> int:
    """The edits that bring the console page up to date, as batch files an agent lands."""
    from .console import Console
    from .marble import eval_ops, refresh_ops, search_ops, write_batches
    from .mdiff import PageError

    console = Console(getattr(args, "kb", None))
    source = _page(args.doc)
    try:
        if args.what == "refresh":
            ops, note = refresh_ops(console, source, args.embedder), "Refresh the console from the knowledge base"
        elif args.what == "search":
            if not (args.request or args.card):
                raise KBError("marble-ops search needs --request, --card or both")
            card = _read_json_arg(args.card) if args.card else None
            ops, note = search_ops(console, source, args.request or "", card, args.embedder), "Show what the search found"
        else:
            ops, note = eval_ops(console, source, args.run, args.embedder), "Show the evaluation"
    except PageError as e:
        raise KBError(f"{e}. Rebuild the page with `astaui marble-doc --out <page> --replace` when nobody has it open.")
    _print_json(write_batches(ops, note, args.out))
    return 0


def cmd_manage(args) -> int:
    """Change the knowledge base's words, tags and judged pairs, by hand or from the console's queue."""
    from .manage import ACTIONS, ManageError, apply_ops, parse_args, run

    kb = _kb(args)
    if args.action == "actions":
        for name, (fixed, written) in ACTIONS.items():
            _say(f"{name:12} {' '.join(f'{a}=…' for a in fixed + written)}")
        return 0
    if args.action == "do":
        if not args.rest:
            raise KBError("astaui manage do <action> name=value …; `astaui manage actions` lists them")
        _writable(kb)
        res = run(kb, [parse_args(args.rest[0], args.rest[1:])], dry=args.dry_run)
        for ch, msg in res.problems:
            _warn(f"astaui: {msg}")
        for line in res.applied:
            _say(("Would do: " if args.dry_run else "") + line)
        if res.files:
            _say("Changed " + ", ".join(res.files) + ".")
        return 1 if res.problems else 0
    if args.action == "apply":
        from .console import Console
        from .marble import refresh_ops, write_batches
        from .mdiff import PageError

        if not args.doc:
            raise KBError("astaui manage apply --doc <the console page>")
        _writable(kb)
        source = _page(args.doc)
        try:
            res, ops = apply_ops(kb, source, dry=args.dry_run)
        except ManageError as e:
            raise KBError(str(e))
        note = "Apply the changes waiting in the queue"
        if res.applied and not res.problems and not args.dry_run:
            try:
                ops += refresh_ops(Console(getattr(args, "kb", None)), source, args.embedder)
            except PageError as e:
                raise KBError(f"The changes were made, but the page could not be brought up to date: {e}")
            note = "Apply the changes waiting in the queue, and refresh the console"
        out = write_batches(ops, note, args.out)
        out["applied"] = res.applied
        out["problems"] = [msg for _, msg in res.problems]
        out["files"] = res.files
        _print_json(out)
        return 0
    raise KBError(f"unknown manage action {args.action!r}")


def cmd_marble_doc(args) -> int:
    from .console import Console
    from .marble import document

    out = Path(args.out)
    if out.exists() and not args.replace:
        raise KBError(f"{out} exists; refresh it with its own Refresh button, or pass --replace to write it over")
    keep = Path(args.keep).read_text(encoding="utf-8") if args.keep else None
    out.write_text(document(Console(getattr(args, "kb", None)), args.embedder, keep=keep), encoding="utf-8")
    _say(f"Wrote {out}. Open it in Marble Drive; its Refresh button keeps it current.")
    return 0


def cmd_map(args) -> int:
    from .mapview import map_data, render

    kb = _kb(args)
    idx = Index(kb, args.embedder)
    data = map_data(kb, idx, method=args.method, queries=args.query or [])
    out = Path(args.out) if args.out else kb.out_dir / "map.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    # Each point links to its interface, relative to where the map is written.
    for it in data["items"]:
        if it.get("entry"):
            it["entry"] = os.path.relpath(it["entry"], out.resolve().parent).replace(os.sep, "/")
    out.write_text(render(data), encoding="utf-8")
    _say(f"Wrote the map to {out} ({len(data['items'])} builds, placed by {data['method']}).")
    if args.open:
        webbrowser.open(out.resolve().as_uri())
    return 0


def cmd_export(args) -> int:
    from .export import jsonl, projector, sql

    kb = _kb(args)
    idx = Index(kb, args.embedder)
    if args.what == "projector":
        out = Path(args.out) if args.out else kb.out_dir / "projector"
        paths = projector(kb, idx, args.channel, out)
        _say("Wrote " + " and ".join(str(p) for p in paths) + ". Load both at https://projector.tensorflow.org (Load → choose the two files).")
    elif args.what == "sql":
        text = sql(kb, idx)
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
            _say(f"Wrote {args.out}. Load it with psql \"$DATABASE_URL\" -f {args.out}")
        else:
            sys.stdout.write(text)
    elif args.what == "jsonl":
        out = jsonl(kb, idx, Path(args.out) if args.out else kb.out_dir / "vectors.jsonl")
        _say(f"Wrote {out}.")
    return 0


def cmd_eval(args) -> int:
    from .search import Searcher

    kb = _kb(args)
    s = Searcher(kb, args.embedder)
    modes = args.modes.split(",") if args.modes else list(MODES)
    for m in modes:
        if m not in MODES:
            raise KBError(f"unknown mode {m!r}; use {', '.join(MODES)}")
    qres = run_queries(s, kb.queries(), modes) if kb.queries() else None
    pres = run_pairs(s, kb.pairs()) if kb.pairs() else None
    if not qres and not pres:
        raise KBError("Nothing to evaluate: add requests to eval/queries.jsonl or judged pairs with `astaui pairs add`.")
    text = report(qres, pres, s.index.embedder.id, len(s.cards))
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    if args.json:
        _print_json({"queries": qres, "pairs": pres})
    else:
        sys.stdout.write(text)
    return 0


def cmd_pairs(args) -> int:
    kb = _kb(args)
    path = kb.eval_dir / "pairs.jsonl"
    pairs = kb.pairs()
    if args.action == "list":
        for p in pairs:
            _say(f"{p['a']} ~ {p['b']}: {p['judgment']}" + (f"  ({p['note']})" if p.get("note") else ""))
        return 0
    _writable(kb)
    if not (args.a and args.b and args.judgment):
        raise KBError("astaui pairs add <build> <build> same|related|different [--note TEXT]")
    if args.judgment not in ("same", "related", "different"):
        raise KBError("the judgement is same, related or different")
    known = set(kb.build_ids())
    for x in (args.a, args.b):
        if x not in known:
            raise KBError(f"no build called {x!r}")
    pairs = [p for p in pairs if {p["a"], p["b"]} != {args.a, args.b}]
    pairs.append({"a": args.a, "b": args.b, "judgment": args.judgment, **({"note": args.note} if args.note else {})})
    write_jsonl(path, pairs)
    _say(f"Judged {args.a} ~ {args.b}: {args.judgment}. {len(pairs)} pairs in all.")
    return 0


def cmd_ontology(args) -> int:
    kb = _kb(args)
    ont = _ont(kb)
    if args.action == "show":
        sys.stdout.write(ont.vocabulary_text())
        return 0
    if args.action == "schema":
        _print_json(card_schema())
        return 0
    counts: Dict[tuple, List[str]] = {}
    for c in kb.cards():
        for p in c.get("proposed", []):
            counts.setdefault((p["facet"], p["list"], p["term"]), []).append(c["id"])
    if args.json:
        _print_json([{"facet": f, "list": l, "term": t, "cards": ids} for (f, l, t), ids in sorted(counts.items())])
        return 0
    if not counts:
        _say("No proposals: every word on every card is in the ontology.")
        return 0
    _say("Words cards used that the ontology does not have yet (add the ones that recur to ontology.json, and log why):")
    for (f, l, t), ids in sorted(counts.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        _say(f"  {f}.{l}: \"{t}\" on {len(ids)} card(s): {', '.join(ids)}")
    return 0


def cmd_workflows(args) -> int:
    from .workflows import StepSpace, families, format_families

    kb = _kb(args)
    idx = Index(kb, args.embedder)
    idx.ensure()
    fams = families(StepSpace(idx, {c["id"]: c for c in kb.cards()}))
    if args.json:
        _print_json(fams)
    else:
        sys.stdout.write(format_families(fams))
    return 0


def cmd_compare(args) -> int:
    from .workflows import StepSpace, compare_cards, format_diff

    kb = _kb(args)
    idx = Index(kb, args.embedder)
    idx.ensure()
    a, b = kb.card(args.a), kb.card(args.b)
    d = compare_cards(StepSpace(idx, {c["id"]: c for c in kb.cards()}), a, b)
    if args.json:
        _print_json(d)
        return 0
    _say(f"{a['app'].get('title')}  [{args.a}]")
    _say(f"   workflow: {d['a_name']}")
    _say(f"{b['app'].get('title')}  [{args.b}]")
    _say(f"   workflow: {d['b_name']}")
    _say(f"\nShared workflow: {d['overlap']:.2f} (0 is no steps in common, 1 is the same steps; rare steps count more)")
    lines = format_diff({**d, "b_name": ""}, you=args.a, them=args.b, indent="")
    for line in lines:
        _say(line)
    back = [n for n in d.get("b_needs", []) if n["covered"]]
    if back:
        _say(f"{args.b} needs {args.a} likely meets: " + "; ".join(n["need"] for n in back))
    return 0


def cmd_feedback(args) -> int:
    from .usage import log_feedback

    kb = _kb(args)
    yn = {"yes": True, "no": False, None: None}
    row = log_feedback(kb, args.search, args.build, yn[args.used], yn[args.helped], args.note or "")
    _say(f"Recorded: {row['build']} used={args.used or '?'} helped={args.helped or '?'}.")
    return 0


def _card_problems(kb: KB, ont: Ontology, cid: str) -> List[str]:
    card = kb.card(cid)
    _, chk = check_card(ont, card, kb.build(cid), made=card.get("made"))
    problems = [f"card {cid}: {e}" for e in chk.errors]
    if card.get("ontology") != ont.version:
        problems.append(f"card {cid}: written for ontology {card.get('ontology')}, the ontology is {ont.version} (re-extract it)")
    return problems


def build_problems(kb: KB, build_id: str) -> List[str]:
    """What a pull request checks about one build and its card, in words."""
    problems = [f"build {build_id}: {p}" for p in check_build(kb, build_id)]
    if problems and not (kb.builds_dir / build_id / "build.json").is_file():
        return problems
    for f in scan_build(kb.build(build_id)):
        if f.level == "block":
            problems.append(f"build {build_id}: {f.what} in {f.file}:{f.line}")
    if kb.card_path(build_id).is_file():
        problems += _card_problems(kb, _ont(kb), build_id)
    else:
        problems.append(f"card {build_id}: there is none")
    return problems


def run_checks(kb: KB) -> List[str]:
    """Everything a pull request should pass, as a list of problems in words."""
    ont = _ont(kb)
    problems: List[str] = []
    builds = kb.build_ids()
    for bid in builds:
        problems += [f"build {bid}: {p}" for p in check_build(kb, bid)]
        for f in scan_build(kb.build(bid)):
            if f.level == "block":
                problems.append(f"build {bid}: {f.what} in {f.file}:{f.line}")
    for cid in kb.card_ids():
        if cid not in builds:
            problems.append(f"card {cid}: there is no build with this id")
            continue
        problems += _card_problems(kb, ont, cid)
    known = set(builds)
    for q in kb.queries():
        for b in (q.get("wanted") or []) + (q.get("far") or []):
            if b not in known:
                problems.append(f"query {q.get('id')}: names {b!r}, which is not a build")
        if q.get("card"):
            _, chk = check_query(ont, {**q["card"], "request": q.get("request", "")})
            problems += [f"query {q.get('id')}: {e}" for e in chk.errors]
    for p in kb.pairs():
        for b in (p.get("a"), p.get("b")):
            if b not in known:
                problems.append(f"pair {p.get('a')} ~ {p.get('b')}: {b!r} is not a build")
        if p.get("judgment") not in ("same", "related", "different"):
            problems.append(f"pair {p.get('a')} ~ {p.get('b')}: judgement must be same, related or different")
    return problems


def cmd_check(args) -> int:
    """Everything a pull request should pass: builds, cards, evaluation references, privacy."""
    kb = _kb(args)
    problems = run_checks(kb)
    builds = kb.build_ids()
    if args.json:
        _print_json({"ok": not problems, "problems": problems})
    else:
        for p in problems:
            _say(p)
        _say(f"{len(builds)} builds, {len(kb.card_ids())} cards checked: " + ("all sound." if not problems else f"{len(problems)} problem(s)."))
    return 1 if problems else 0


def cmd_incoming(args) -> int:
    from .sources import incoming, review, take
    kb = _kb(args)
    if args.review:
        path = review(kb, args.review)
        if args.json:
            _print_json({"kb": str(path)})
            return 0
        _say(f"A copy of the knowledge base with {args.review} in it: {path}")
        _say(f"Check it there, without touching this one: `astaui --kb \"{path}\" check`, then `lint {args.review}` and `card show {args.review}` the same way.")
        return 0
    if args.take:
        _writable(kb)
        res = take(kb, args.take)
        if args.json:
            _print_json(res)
            return 0
        _say(f"{'Replaced' if res.get('replaced') else 'Brought'} {res['id']} in from {res['branch'] or res['page']}: {len(res['files'])} files" + ("" if res["card"] else ", and no card yet") + ". Nothing is committed.")
        _say("Next: `astaui index`, then refresh the console.")
        return 0
    res = incoming(kb, fetch=args.fetch)
    if args.json:
        _print_json({**res, "looked": res["looked"].isoformat() if res["looked"] else None})
        return 0
    if res["repo"] is None and res["inbox"] is None:
        _say("This knowledge base is in no git repository and no drive page takes builds, so nothing can be sent to it.")
        return 0
    if not res["waiting"]:
        _say("Nothing is waiting." + ("" if args.fetch else " `--fetch` looks on the remote first."))
        return 0
    for w in res["waiting"]:
        a = w["author"]
        who = " · ".join(x for x in (a.get("name"), ", ".join(y for y in (a.get("role"), a.get("field")) if y)) if x)
        on = f"to {w['page']}" if w.get("via") == "drive" else f"on {w['branch']}"
        _say(f"{w['id']}  {w['title']}  ({who or 'no name'}; sent {w['sent']} {on}{'' if w['card'] else '; no card yet'})")
    return 0


# -- the parser -------------------------------------------------------------------------

def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="astaui", description="A knowledge base of the interfaces scientists build: file them, describe them, find them.")
    p.add_argument("--version", action="version", version=f"astaui {__version__}")
    p.add_argument("--kb", help="the knowledge base folder (default: $ASTAUI_KB, `astaui config kb`, a kb above here, or the bundled one)")
    sub = p.add_subparsers(dest="command", metavar="command")

    def cmd(name: str, help: str, fn, json_flag: bool = True, embedder: bool = False):
        sp = sub.add_parser(name, help=help, description=help)
        sp.set_defaults(fn=fn)
        if json_flag:
            sp.add_argument("--json", action="store_true", help="answer in JSON")
        if embedder:
            sp.add_argument("--embedder", help="lexical, st:<model>, voyage:<model>, gemini:<model> or vertex:<model> (default: kb.json)")
        return sp

    sp = cmd("init", "make an empty knowledge base", cmd_init, json_flag=False)
    sp.add_argument("path")
    sp.add_argument("--name", default="AstaUI knowledge base")

    sp = cmd("config", "set which knowledge base astaui uses (config kb PATH), or the drive link builds are sent through "
             "(config inbox-link LINK)", cmd_config, json_flag=False)
    sp.add_argument("key", nargs="?", choices=["kb", "inbox-link", "show"])
    sp.add_argument("value", nargs="?")
    sp.add_argument("--unset", action="store_true")
    sp.add_argument("--public", metavar="ADDRESS", help="the address the drive answers at from outside, for a link made on this computer")

    cmd("status", "what is in the knowledge base and what is missing", cmd_status, embedder=True)

    sp = cmd("add", "file a build: its prompts, its code, a screenshot", cmd_add)
    sp.add_argument("id", help="lowercase-with-hyphens")
    sp.add_argument("--title", required=True)
    sp.add_argument("--prompts", action="append", help="a file of prompts: .jsonl, or text with a blank line between prompts (repeatable)")
    sp.add_argument("--prompt", action="append", help="one prompt (repeatable)")
    sp.add_argument("--session", help="a Claude Code session log, `latest` for this folder's newest before this one, or `this` for the one running this command")
    sp.add_argument("--code", action="append", required=True, help="a file or folder of the interface's code (repeatable)")
    sp.add_argument("--screenshot")
    sp.add_argument("--entry", help="the file that opens the interface (default: the first .html)")
    sp.add_argument("--author", help="a pseudonym such as P07, unless the person asked to be named")
    sp.add_argument("--role")
    sp.add_argument("--field")
    sp.add_argument("--source", action="append", choices=SOURCES)
    sp.add_argument("--kind", default="contributed", choices=KINDS)
    sp.add_argument("--consent", default="team", choices=CONSENT)
    sp.add_argument("--origin")
    sp.add_argument("--forked-from")
    sp.add_argument("--notes")
    sp.add_argument("--replace", action="store_true")
    sp.add_argument("--repo", help="where the full code lives (a git URL), so the build can later keep only what its card uses")
    sp.add_argument("--commit", help="the commit the code was taken from")
    sp.add_argument("--subdir", help="the folder inside the repo the interface lives in")

    sp = cmd("sessions", "list Claude Code sessions to file prompts from", cmd_sessions)
    sp.add_argument("--cwd", help="the project folder (default: here)")
    sp.add_argument("--all", action="store_true", help="every project")
    sp.add_argument("--limit", type=int, default=15)

    sp = cmd("lint", "the strip step: keys, emails, home paths, embedded data", cmd_lint)
    sp.add_argument("id", nargs="?")
    sp.add_argument("--all", action="store_true")
    sp.add_argument("--strip", action="store_true", help="replace keys, emails and home paths with placeholders")

    sp = cmd("extract", "write a build's card: prints the instructions for your agent, or --api", cmd_extract)
    sp.add_argument("id", nargs="?")
    sp.add_argument("--api", action="store_true", help="ask Claude through the API instead of printing the instructions")
    sp.add_argument("--provider", choices=["anthropic", "vertex"])
    sp.add_argument("--model")
    sp.add_argument("--out", help="where the card JSON goes (named in the instructions; with --api, the raw answer)")
    sp.add_argument("--missing", action="store_true", help="list builds that have no card")
    sp.add_argument("--schema", action="store_true", help="print the card's JSON Schema")
    sp.add_argument("--dry-run", action="store_true")

    sp = cmd("card", "put, show or check cards", cmd_card)
    sp.add_argument("action", choices=["put", "show", "check", "refresh", "schema"])
    sp.add_argument("id", nargs="?")
    sp.add_argument("file", nargs="?", help="card JSON: a file, - for stdin, or inline JSON")
    sp.add_argument("--by", help="who wrote it (default: agent)")
    sp.add_argument("--model")
    sp.add_argument("--all", action="store_true")
    sp.add_argument("--dry-run", action="store_true")

    sp = cmd("describe", "describe a request as a query card: prints the instructions, or --api", cmd_describe)
    sp.add_argument("request")
    sp.add_argument("--context", help="a file with more about the person's data and situation")
    sp.add_argument("--api", action="store_true")
    sp.add_argument("--provider", choices=["anthropic", "vertex"])
    sp.add_argument("--model")
    sp.add_argument("--out")

    sp = cmd("index", "bring the vectors up to date with the cards", cmd_index, embedder=True)
    sp.add_argument("--rebuild", action="store_true", help="start the cache over")

    sp = cmd("search", "find builds worth adapting for a request", cmd_search, embedder=True)
    sp.add_argument("request", nargs="?", default="")
    sp.add_argument("--card", help="a query card (file, - or JSON) from `astaui describe`")
    sp.add_argument("--k", type=int)
    sp.add_argument("--where", action="append", help="exact filter, e.g. shape=table, verb=annotate, field=hci, kind=study (repeatable)")
    sp.add_argument("--exclude", action="append")
    sp.add_argument("--parts", type=int, help="views and components to show per build")
    sp.add_argument("--pieces", type=int, default=4, help="pieces from other builds to show")
    sp.add_argument("--no-far", action="store_true", help="do not look for a match from another field")
    sp.add_argument("--no-code", action="store_true")

    sp = cmd("show", "a build: its prompts, files and card; --part for one part's code", cmd_show)
    sp.add_argument("id")
    sp.add_argument("--part")

    sp = cmd("map", "write the embedding-space map as one HTML file", cmd_map, json_flag=False, embedder=True)
    sp.add_argument("--out")
    sp.add_argument("--query", action="append", help="a request to place on the map (repeatable)")
    sp.add_argument("--method", choices=["pca", "umap"], default="pca")
    sp.add_argument("--open", action="store_true")

    sp = cmd("export", "vectors out: projector TSVs, pgvector SQL, or JSONL", cmd_export, json_flag=False, embedder=True)
    sp.add_argument("what", choices=["projector", "sql", "jsonl"])
    sp.add_argument("--channel", default="card", help="for projector: card, structure, raw, data, task, mechanism, stage, summary, prompt, field")
    sp.add_argument("--out")

    sp = cmd("eval", "how well each representation finds what you wanted", cmd_eval, embedder=True)
    sp.add_argument("--modes", help=f"comma-separated: {', '.join(MODES)}")
    sp.add_argument("--out", help="also write the report to this Markdown file")

    sp = cmd("pairs", "judge pairs of builds by eye", cmd_pairs, json_flag=False)
    sp.add_argument("action", choices=["add", "list"])
    sp.add_argument("a", nargs="?")
    sp.add_argument("b", nargs="?")
    sp.add_argument("judgment", nargs="?", help="same, related or different")
    sp.add_argument("--note")

    sp = cmd("ontology", "show the vocabulary, the schema, or the new words cards proposed", cmd_ontology)
    sp.add_argument("action", choices=["show", "proposals", "schema"])

    sp = cmd("feedback", "record whether a match was used and helped", cmd_feedback, json_flag=False)
    sp.add_argument("search", help="the id a search printed")
    sp.add_argument("build")
    sp.add_argument("--used", choices=["yes", "no"])
    sp.add_argument("--helped", choices=["yes", "no"])
    sp.add_argument("--note")

    sp = cmd("slice", "the code for one part: its spans and what they use from elsewhere in the build", cmd_slice)
    sp.add_argument("build")
    sp.add_argument("part")
    sp.add_argument("--no-deps", action="store_true", help="only the spans the card names")
    sp.add_argument("--max-lines", type=int, default=300)
    sp.add_argument("--plain", action="store_true", help="no line numbers, ready to paste")

    sp = cmd("symbols", "the functions, elements and style rules in a build, with their lines", cmd_symbols)
    sp.add_argument("build")
    sp.add_argument("--file")

    sp = cmd("slim", "for a build from a big repo: keep only the files its card points at, and where the rest lives", cmd_slim)
    sp.add_argument("id")
    sp.add_argument("--force", action="store_true", help="slim even without a recorded source repository")
    sp.add_argument("--dry-run", action="store_true")

    cmd("workflows", "group builds into workflow families, and say what is each one's own", cmd_workflows, embedder=True)

    sp = cmd("compare", "line up two builds' workflows: shared steps, how each does them, what is each one's own", cmd_compare, embedder=True)
    sp.add_argument("a")
    sp.add_argument("b")

    sp = cmd("console", "a local page showing how the knowledge base is working: health, builds, search, workflows, evaluation, activity", cmd_console, json_flag=False)
    sp.add_argument("--port", type=int, default=8770)
    sp.add_argument("--no-open", action="store_true", help="do not open a browser")

    sp = cmd("marble-ops", "the edits that bring the console page in the drive up to date, as batch files for apply_ops", cmd_marble_ops, json_flag=False, embedder=True)
    sp.add_argument("what", choices=["refresh", "search", "eval"])
    sp.add_argument("--doc", required=True, help="the console page, e.g. 'Ai2/AstaUI/AstaUI Console.mrbl'")
    sp.add_argument("--out", help="the folder for the batch files (default: a new one under the system's temp folder)")
    sp.add_argument("--request", help="for search: the request")
    sp.add_argument("--card", help="for search: a query card (file, - or JSON)")
    sp.add_argument("--run", action="store_true", help="for eval: run the evaluation first")

    sp = cmd("manage", "change the ontology's words, a card's words and the judged pairs: `manage actions`, `manage do <action> name=value …`, `manage apply --doc <page>`", cmd_manage, json_flag=False, embedder=True)
    sp.add_argument("action", choices=["actions", "do", "apply"])
    sp.add_argument("rest", nargs="*", help="for do: the action, then name=value arguments")
    sp.add_argument("--doc", help="for apply: the console page whose queue to run")
    sp.add_argument("--out", help="for apply: the folder for the batch files")
    sp.add_argument("--dry-run", action="store_true", help="check every change and make none")

    sp = cmd("marble-doc", "write the console as a Marble page, whole (its buttons keep it current through marble-ops and manage)", cmd_marble_doc, json_flag=False, embedder=True)
    sp.add_argument("--out", required=True, help="where the .mrbl goes, e.g. 'Ai2/AstaUI/AstaUI Console.mrbl'")
    sp.add_argument("--replace", action="store_true")
    sp.add_argument("--keep", help="an older console page whose looks, waiting changes and search request the new page keeps")

    cmd("check", "everything a pull request should pass", cmd_check)
    sp = cmd("send", "send a filed build to the knowledge base's owner, through the Add only link the plugin carries", cmd_send)
    sp.add_argument("id")
    sp.add_argument("--to", metavar="LINK", help="another link: https://<their drive>/s/<code>")

    sp = cmd("filed", "the build this folder was filed as before, if it was", cmd_filed)
    sp.add_argument("folder", nargs="?", help="the app's folder (default: this one)")

    sp = cmd("intake", "on the owner's computer: take in every build sent to the drive that passes the checks, and index it", cmd_intake)
    sp.add_argument("--no-index", action="store_true", help="leave the index as it is")

    sp = cmd("incoming", "builds scientists sent, to the owner's drive or as add-* branches: list them, check one apart, or bring it in", cmd_incoming)
    sp.add_argument("--fetch", action="store_true", help="look on the remote first")
    sp.add_argument("--review", metavar="ID", help="copy the knowledge base with that build in it, to check it there")
    sp.add_argument("--take", metavar="ID", help="bring that build and its card into this knowledge base")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    p = parser()
    args = p.parse_args(argv)
    if not getattr(args, "fn", None):
        p.print_help()
        return 0
    try:
        return int(args.fn(args) or 0)
    except KBError as e:
        _warn(f"astaui: {e}")
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
