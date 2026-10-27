"""Changing the knowledge base by hand: its words, the words on each card, and the
pairs judged by eye.

The console queues changes as rows in its page, one per change, and Apply runs
``astaui manage apply --doc <page>``. Every change is checked against the
knowledge base as it will be once the changes before it are made, and then all of
them are made, or none: a rename followed by a merge into the new name is two
changes that only make sense together.

The same changes can be made from the shell:

    astaui manage do rename-term facet=data list=shapes term=table to="tabular data" because="..."

A change to the ontology raises its version, adds an entry to its change log
with the reasons given, and re-checks every card under it, so the cards say the
same thing in the new words. Words are never lost: a renamed or merged word
stays on as another word for the one that replaced it, so old cards, test
requests and a scientist's own wording still find their way to it.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from .kb import KB, KBError, read_json, write_json, write_jsonl
from .ontology import FACETS, LISTS, PART_LISTS, Ontology, norm_word

# action: (arguments fixed when the change is queued, arguments a person writes)
ACTIONS: Dict[str, Tuple[Tuple[str, ...], Tuple[str, ...]]] = {
    "add-term": (("facet", "list", "term"), ("means", "because")),
    "rename-term": (("facet", "list", "term"), ("to", "because")),
    "merge-term": (("facet", "list", "term"), ("into", "because")),
    "add-word": (("facet", "list", "term"), ("word", "because")),
    "set-meaning": (("facet", "list", "term"), ("means", "because")),
    "retire-term": (("facet", "list", "term"), ("because",)),
    "tag": (("build", "facet", "list", "term"), ()),
    "untag": (("build", "facet", "list", "term"), ()),
    "judge": (("a", "b", "judgment"), ("note",)),
    "unjudge": (("a", "b"), ()),
    "set-weight": (("facet",), ("weight", "because")),
}
OPTIONAL = {"because", "note", "means"}
JUDGMENTS = ("same", "related", "different")
JUDGED_BY = "judged in the console, with the similarity scores in view"

# What one word of each list is called in a sentence.
WORD_OF = {
    ("data", "shapes"): "data shape", ("task", "verbs"): "task", ("stage", "terms"): "stage",
    ("mechanism", "views"): "view", ("mechanism", "interactions"): "interaction",
    ("mechanism", "patterns"): "pattern", ("field", "disciplines"): "discipline",
}


class ManageError(KBError):
    pass


@dataclass
class Change:
    action: str
    args: Dict[str, str]
    row: Optional[str] = None           # the queue row it came from, if any
    problem_id: Optional[str] = None    # where that row shows a problem
    problem_now: str = ""               # the problem it shows now

    def arg(self, name: str) -> str:
        return (self.args.get(name) or "").strip()


@dataclass
class Result:
    applied: List[str] = field(default_factory=list)
    problems: List[Tuple[Change, str]] = field(default_factory=list)
    files: List[str] = field(default_factory=list)
    version: Optional[str] = None


def next_version(v: str) -> str:
    """3 -> 3.1 -> 3.2: a hand edit is a minor version of the ontology."""
    parts = str(v).split(".")
    if len(parts) == 1:
        return f"{parts[0]}.1"
    try:
        return ".".join(parts[:-1] + [str(int(parts[-1]) + 1)])
    except ValueError:
        return f"{v}.1"


class Workbench:
    """The knowledge base as it will be after the changes so far, in memory."""

    def __init__(self, kb: KB):
        self.kb = kb
        self.raw = copy.deepcopy(read_json(kb.root / "ontology.json"))
        self.cards = {cid: kb.card(cid) for cid in kb.card_ids()}
        self.pairs = kb.pairs()
        self.builds = set(kb.build_ids())
        self.ontology_changed = False
        self.cards_changed: set = set()
        self.pairs_changed = False
        self.log: List[str] = []
        self.reasons: List[str] = []

    # -- looking things up -------------------------------------------------------------
    def ont(self) -> Ontology:
        return Ontology(self.raw)

    def terms(self, facet: str, lst: str) -> Dict[str, Any]:
        if facet not in FACETS or lst not in LISTS.get(facet, ()):
            raise ManageError(f"there is no list {facet}.{lst}")
        spec = self.raw["facets"][facet].setdefault("lists", {}).setdefault(lst, {})
        return spec.setdefault("terms", {})

    def word(self, facet: str, lst: str) -> str:
        return WORD_OF.get((facet, lst), f"{facet} {lst} word")

    def find(self, facet: str, lst: str, word: str) -> Optional[str]:
        """The list's own name for a word: itself, or the term it is another word for."""
        if not word.strip():
            return None
        name, known = self.ont().canonical(facet, lst, word)
        return name if known and name in self.terms(facet, lst) else None

    def lists_of(self, card: Dict[str, Any], facet: str, lst: str) -> List[List[str]]:
        """Every list on a card that holds words of this list: the facet's own, and
        each part's when the list is one a part borrows."""
        out = []
        facet_d = card["app"].setdefault(facet, {})
        out.append(facet_d.setdefault(lst, []))
        if facet == "mechanism" and lst in PART_LISTS:
            for p in card.get("parts", []):
                out.append(p.setdefault(lst, []))
        return out

    def users(self, facet: str, lst: str, word: str) -> List[str]:
        n = norm_word(word)
        return sorted(cid for cid, c in self.cards.items()
                      if any(norm_word(w) == n for l in self.lists_of(c, facet, lst) for w in l))

    def replace_word(self, facet: str, lst: str, old: str, new: Optional[str]) -> None:
        """Put `new` wherever a card has `old` (or take `old` out, when new is None)."""
        n = norm_word(old)
        for cid, c in self.cards.items():
            changed = False
            for l in self.lists_of(c, facet, lst):
                if any(norm_word(w) == n for w in l):
                    keep = [w for w in l if norm_word(w) != n]
                    if new is not None and new not in keep:
                        at = next(i for i, w in enumerate(l) if norm_word(w) == n)
                        keep.insert(min(at, len(keep)), new)
                    l[:] = keep
                    changed = True
            if changed:
                c["proposed"] = [p for p in c.get("proposed", []) if not (p["facet"] == facet and p["list"] == lst and norm_word(p["term"]) == n)]
                self.cards_changed.add(cid)

    def pair_at(self, a: str, b: str) -> Optional[int]:
        for i, p in enumerate(self.pairs):
            if {p.get("a"), p.get("b")} == {a, b}:
                return i
        return None

    # -- one change ---------------------------------------------------------------------------
    def apply(self, ch: Change) -> str:
        """Make one change in memory. Returns what was done, in words; raises with what
        is wrong, in words that say how to put it right."""
        if ch.action not in ACTIONS:
            raise ManageError(f"there is no change called {ch.action!r}")
        fixed, written = ACTIONS[ch.action]
        for name in fixed + written:
            if name not in OPTIONAL and not ch.arg(name):
                raise ManageError(f"say {'the ' + name if name in fixed else 'what ' + name.replace('-', ' ') + ' should be'}")
        a = ch.arg
        because = a("because")
        if ch.action in ("tag", "untag", "judge", "unjudge"):
            return getattr(self, "_" + ch.action)(ch)

        if ch.action == "set-weight":
            facet = a("facet")
            try:
                w = float(a("weight"))
            except ValueError:
                raise ManageError(f"the weight must be a number between 0 and 1, not {a('weight')!r}")
            if not 0 <= w <= 1:
                raise ManageError("the weight must be between 0 and 1")
            if facet == "summary":
                old = self.raw.get("summary_weight")
                self.raw["summary_weight"] = w
            elif facet == "workflow":
                old = self.raw.setdefault("workflow", {}).get("weight")
                self.raw["workflow"]["weight"] = w
            elif facet in FACETS:
                old = self.raw["facets"][facet].get("weight")
                self.raw["facets"][facet]["weight"] = w
            else:
                raise ManageError(f"there is no facet {facet!r}; the weights are for {', '.join(FACETS)}, summary and workflow")
            return self._ontology(f"the {facet} weight went from {old} to {w}", because)

        facet, lst, term = a("facet"), a("list"), a("term")
        terms = self.terms(facet, lst)
        what = self.word(facet, lst)

        if ch.action == "add-term":
            have = self.find(facet, lst, term)
            if have:
                raise ManageError(f"“{term}” is already a {what}" + (f", as another word for “{have}”" if have != term else ""))
            terms[term] = {"means": a("means"), "also": []}
            self.replace_word(facet, lst, term, term)  # it is no longer a proposal
            return self._ontology(f"added the {what} “{term}”" + (f" ({a('means')})" if a("means") else ""), because)

        name = self.find(facet, lst, term)
        if ch.action == "merge-term" and name is None:
            # A word the cards proposed and the list lacks can be merged into one it has.
            if not self.users(facet, lst, term):
                raise ManageError(f"no card uses “{term}” and it is not a {what}")
        elif name is None:
            raise ManageError(f"“{term}” is not a {what}")

        if ch.action == "rename-term":
            to = a("to")
            if norm_word(to) == norm_word(name):
                raise ManageError(f"the new name is the same as “{name}”")
            other = self.find(facet, lst, to)
            if other and other != name:
                raise ManageError(f"“{to}” is already a {what}" + (f" (another word for “{other}”)" if other != to else "") + "; merge into it instead")
            entry = terms[name]
            also = [w for w in entry.get("also", []) if norm_word(w) != norm_word(to)]
            entry["also"] = also + [name]
            renamed = {(to if k == name else k): v for k, v in terms.items()}
            terms.clear()
            terms.update(renamed)
            self.replace_word(facet, lst, name, to)
            return self._ontology(f"renamed the {what} “{name}” to “{to}”; “{name}” stays on as another word for it", because)

        if ch.action == "merge-term":
            into = self.find(facet, lst, a("into"))
            if into is None:
                raise ManageError(f"“{a('into')}” is not a {what}; it can only merge into one the list has")
            source = name or term
            if into == source:
                if norm_word(term) != norm_word(source):
                    raise ManageError(f"“{term}” already counts as “{source}”")
                raise ManageError(f"“{source}” and “{a('into')}” are already the same {what}")
            target = terms[into]
            moved = [source] + (terms.pop(source).get("also", []) if name else [])
            target["also"] = list(dict.fromkeys(target.get("also", []) + [w for w in moved if norm_word(w) != norm_word(into)]))
            self.replace_word(facet, lst, source, into)
            return self._ontology(f"merged the {what} “{source}” into “{into}”", because)

        if ch.action == "add-word":
            word = a("word")
            other = self.find(facet, lst, word)
            if other == name:
                raise ManageError(f"“{word}” already counts as “{name}”")
            if other:
                raise ManageError(f"“{word}” already counts as “{other}”")
            terms[name].setdefault("also", []).append(word)
            return self._ontology(f"“{word}” now counts as the {what} “{name}”", because)

        if ch.action == "set-meaning":
            if not a("means"):
                raise ManageError("say what the word means")
            terms[name]["means"] = a("means")
            return self._ontology(f"the {what} “{name}” now means: {a('means')}", because)

        if ch.action == "retire-term":
            used = self.users(facet, lst, name)
            if used:
                raise ManageError(f"{len(used)} card{'s use' if len(used) > 1 else ' uses'} “{name}” ({', '.join(used[:4])}); merge it into another {what} instead")
            del terms[name]
            return self._ontology(f"retired the {what} “{name}”", because)

        raise ManageError(f"there is no change called {ch.action!r}")

    def _ontology(self, said: str, because: str) -> str:
        self.ontology_changed = True
        self.log.append(said[0].upper() + said[1:])
        if because:
            self.reasons.append(because[0].upper() + because[1:].rstrip("."))
        return said[0].upper() + said[1:]

    def _card(self, ch: Change) -> Dict[str, Any]:
        b = ch.arg("build")
        if b not in self.cards:
            raise ManageError(f"{b!r} has no card" if b in self.builds else f"there is no build {b!r}")
        return self.cards[b]

    def _tag(self, ch: Change) -> str:
        card = self._card(ch)
        facet, lst, term = ch.arg("facet"), ch.arg("list"), ch.arg("term")
        self.terms(facet, lst)
        word = self.find(facet, lst, term) or term
        l = card["app"].setdefault(facet, {}).setdefault(lst, [])
        if any(norm_word(w) == norm_word(word) for w in l):
            raise ManageError(f"{card['id']} already has the {self.word(facet, lst)} “{word}”")
        l.append(word)
        self.cards_changed.add(card["id"])
        return f"Gave {card['id']} the {self.word(facet, lst)} “{word}”"

    def _untag(self, ch: Change) -> str:
        card = self._card(ch)
        facet, lst, term = ch.arg("facet"), ch.arg("list"), ch.arg("term")
        self.terms(facet, lst)
        word = self.find(facet, lst, term) or term
        l = card["app"].setdefault(facet, {}).setdefault(lst, [])
        keep = [w for w in l if norm_word(w) != norm_word(word)]
        if len(keep) == len(l):
            raise ManageError(f"{card['id']} does not have the {self.word(facet, lst)} “{word}”")
        l[:] = keep
        self.cards_changed.add(card["id"])
        return f"Took the {self.word(facet, lst)} “{word}” off {card['id']}"

    def _judge(self, ch: Change) -> str:
        a, b, j = ch.arg("a"), ch.arg("b"), ch.arg("judgment").lower()
        for x in (a, b):
            if x not in self.builds:
                raise ManageError(f"there is no build {x!r}")
        if a == b:
            raise ManageError("a pair needs two different builds")
        if j not in JUDGMENTS:
            raise ManageError(f"a judgment is one of {', '.join(JUDGMENTS)}, not {j!r}")
        row = {"a": a, "b": b, "judgment": j, "note": ch.arg("note"), "by": JUDGED_BY, "date": date.today().isoformat()}
        at = self.pair_at(a, b)
        if at is None:
            self.pairs.append(row)
        else:
            self.pairs[at] = row
        self.pairs_changed = True
        return f"Judged {a} and {b} {j}"

    def _unjudge(self, ch: Change) -> str:
        a, b = ch.arg("a"), ch.arg("b")
        at = self.pair_at(a, b)
        if at is None:
            raise ManageError(f"{a} and {b} have not been judged")
        del self.pairs[at]
        self.pairs_changed = True
        return f"Took back the judgment on {a} and {b}"

    # -- writing ----------------------------------------------------------------------------------
    def write(self, result: Result) -> None:
        """Re-check every card that needs it under the new ontology, and only then
        write anything, so a card that no longer passes stops the whole change."""
        from .cards import check_card

        if self.ontology_changed:
            self.raw["version"] = next_version(self.raw.get("version", "0"))
            self.raw.setdefault("changes", []).append({
                "version": self.raw["version"],
                "date": date.today().isoformat(),
                "change": ". ".join(self.log) + ".",
                "because": (". ".join(self.reasons) + ".") if self.reasons else "No reason was given.",
                "by": "the console",
            })
            result.version = self.raw["version"]
        ont = Ontology(self.raw)
        recheck = sorted(self.cards) if self.ontology_changed else sorted(self.cards_changed)
        new_cards = {}
        for cid in recheck:
            card, chk = check_card(ont, self.cards[cid], self.kb.build(cid), made=self.cards[cid].get("made"))
            if chk.errors:
                raise ManageError(f"{cid} would no longer pass its check: {chk.errors[0]}")
            new_cards[cid] = card
        if self.ontology_changed:
            write_json(self.kb.root / "ontology.json", self.raw)
            result.files.append("kb/ontology.json")
        written = 0
        for cid, card in new_cards.items():
            if card != self.kb.card(cid):
                write_json(self.kb.card_path(cid), card)
                written += 1
        if written:
            result.files.append(f"{written} card{'s' if written > 1 else ''} in kb/cards")
        if self.pairs_changed:
            write_jsonl(self.kb.eval_dir / "pairs.jsonl", self.pairs)
            result.files.append("kb/eval/pairs.jsonl")


def run(kb: KB, changes: List[Change], dry: bool = False) -> Result:
    """Make every change, in order, or none of them."""
    if kb.read_only:
        raise KBError("This knowledge base is the copy the plugin installed; change a clone of the repository instead")
    bench = Workbench(kb)
    result = Result()
    for ch in changes:
        try:
            result.applied.append(bench.apply(ch))
        except ManageError as e:
            result.problems.append((ch, str(e)))
    if result.problems or dry or not changes:
        return result
    try:
        bench.write(result)
    except ManageError as e:
        result.problems.append((changes[-1], str(e)))
        result.applied = []
    return result


def parse_args(action: str, pairs: List[str]) -> Change:
    """`key=value` words from the shell, as one change."""
    args = {}
    for p in pairs:
        if "=" not in p:
            raise ManageError(f"write each argument as name=value, not {p!r}")
        k, v = p.split("=", 1)
        args[k.strip()] = v
    return Change(action=action, args=args)


# -- the console's queue ---------------------------------------------------------------------------

QUEUE = "kb-queue"
NOTE = "kb-apply-note"


class _Row:
    """What a person wrote in one queue row: each `data-arg` element's text, and the
    element that shows the row's problem."""

    VOID = {"br", "hr", "img", "input", "wbr"}

    def __init__(self, inner: str):
        from html.parser import HTMLParser

        self.args: Dict[str, str] = {}
        self.problem_id: Optional[str] = None
        self.problem = ""
        stack: List[Tuple[str, Optional[str], str]] = []
        row = self

        class P(HTMLParser):
            def handle_starttag(self, tag, attrs):
                if tag in _Row.VOID:
                    return
                a = dict(attrs)
                kind = "arg" if a.get("data-arg") else "problem" if "problem" in (a.get("class") or "").split() else ""
                if kind == "arg":
                    row.args[a["data-arg"]] = ""
                elif kind == "problem":
                    row.problem_id = a.get("data-marble-id")
                stack.append((tag, a.get("data-arg"), kind))

            def handle_endtag(self, tag):
                while stack:
                    if stack.pop()[0] == tag:
                        break

            def handle_data(self, data):
                for _, name, kind in reversed(stack):
                    if kind == "arg":
                        row.args[name] += data
                        return
                    if kind == "problem":
                        row.problem += data
                        return

        P(convert_charrefs=True).feed(inner)


def queued(source: str) -> Tuple[List[Change], List[str]]:
    """The changes waiting in the console's queue, in order, and the rows a person
    dropped."""
    from .mdiff import index

    nodes = index(source)
    if QUEUE not in nodes:
        raise ManageError("this page has no queue of changes; rebuild it with `astaui marble-doc`")
    changes: List[Change] = []
    dropped: List[str] = []
    for rid in nodes[QUEUE].children:
        node = nodes[rid]
        if "data-dropped" in node.attrs:
            dropped.append(rid)
            continue
        args = {k[5:]: v for k, v in node.attrs.items() if k.startswith("data-") and k not in ("data-action", "data-marble-id")}
        row = _Row(source[node.inner_start:node.inner_end])
        args.update(row.args)
        changes.append(Change(action=node.attrs.get("data-action", ""), args={k: v.strip() for k, v in args.items()},
                              row=rid, problem_id=row.problem_id, problem_now=row.problem.strip()))
    return changes, dropped


def apply_ops(kb: KB, source: str, dry: bool = False):
    """Run the page's queue, and say what the page should do about it: take the
    changes made out of the queue, mark the ones with a problem, and say beside the
    Apply button what happened. Returns the result and the ops (as mdiff.Op); the
    refresh that follows a change is the caller's."""
    from datetime import datetime

    from .mdiff import Op, index

    changes, dropped = queued(source)
    result = run(kb, changes, dry=dry)
    nodes = index(source)

    def op(o: Dict[str, Any], target: str) -> Op:
        n = nodes.get(target)
        return Op(o, [target], (n.end - n.start) if n else 0)

    ops: List[Op] = []
    bad = {id(ch): msg for ch, msg in result.problems}
    stamp = datetime.now().astimezone().strftime("%b %-d at %H:%M")
    n = len(changes)
    if not changes:
        note = "There were no changes waiting." + (" The dropped ones are cleared." if dropped else "")
    elif result.problems:
        k = len(result.problems)
        note = (f"Nothing was applied: {k} change{'s have' if k > 1 else ' has'} a problem, said beside it. "
                "Fix it or drop it, then press Apply again.")
    elif dry:
        note = f"All {n} change{'s' if n > 1 else ''} would apply."
    else:
        note = f"Applied {n} change{'s' if n > 1 else ''} on {stamp}: " + "; ".join(result.applied) + "."
        if result.files:
            note += " Changed " + ", ".join(result.files) + "; commit them to share."
        if result.version:
            note += f" The ontology is now version {result.version}."
    keep_rows = bool(result.problems) or dry
    for ch in changes:
        msg = bad.get(id(ch), "")
        if keep_rows and ch.problem_id and msg != ch.problem_now:
            ops.append(op({"type": "setText", "id": ch.problem_id, "text": msg}, ch.problem_id))
    if not keep_rows:
        ops += [op({"type": "remove", "id": ch.row}, ch.row) for ch in changes]
    if not result.problems:
        ops += [op({"type": "remove", "id": rid}, rid) for rid in dropped]
    ops.append(op({"type": "setText", "id": NOTE, "text": note}, NOTE))
    return result, ops
