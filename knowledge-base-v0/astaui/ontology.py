"""The ontology: the facets a card has, and the words each facet may use.

Words are matched loosely. ``Coding``, ``code`` and ``tag`` all become ``annotate``
because ``ontology.json`` lists them as other words for it. A word with no match is
kept as it was written and reported as a proposal, so the vocabulary can grow
from what real cards turned out to need.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .kb import KBError, read_json

FACETS = ("task", "data", "stage", "mechanism", "field")

# Which list on which facet, and the key it is stored under in a card.
LISTS: Dict[str, Tuple[str, ...]] = {
    "task": ("verbs",),
    "data": ("shapes",),
    "stage": ("terms",),
    "mechanism": ("views", "interactions", "patterns"),
    "field": ("disciplines", "terms"),
}

# A part (a view or component) borrows the mechanism vocabulary.
PART_LISTS = ("views", "interactions", "patterns")


def norm_word(s: str) -> str:
    s = s.strip().lower().replace("_", " ")
    s = re.sub(r"[\s\-/]+", " ", s)
    s = re.sub(r"[^\w +&']", "", s)
    return s.strip()


@dataclass
class Term:
    name: str
    means: str
    also: List[str]


class Ontology:
    def __init__(self, data: Dict[str, Any]):
        self.data = data
        self.version = str(data.get("version", "0"))
        facets = data.get("facets") or {}
        missing = [f for f in FACETS if f not in facets]
        if missing:
            raise KBError(f"ontology.json has no facet {', '.join(missing)}")
        self.facets = facets
        self._lookup: Dict[Tuple[str, str], Dict[str, str]] = {}
        self._terms: Dict[Tuple[str, str], List[Term]] = {}
        self._open: Dict[Tuple[str, str], bool] = {}
        for facet, lists in LISTS.items():
            for lst in lists:
                spec = ((facets[facet].get("lists") or {}).get(lst)) or {}
                terms = spec.get("terms") or {}
                self._open[(facet, lst)] = bool(spec.get("open"))
                table: Dict[str, str] = {}
                out: List[Term] = []
                for name, info in terms.items():
                    info = info or {}
                    t = Term(name=name, means=info.get("means", ""), also=list(info.get("also") or []))
                    out.append(t)
                    table[norm_word(name)] = name
                    for a in t.also:
                        table.setdefault(norm_word(a), name)
                self._lookup[(facet, lst)] = table
                self._terms[(facet, lst)] = out

    @classmethod
    def load(cls, path: Path) -> "Ontology":
        return cls(read_json(path))

    # -- weights ------------------------------------------------------------
    def weight(self, facet: str) -> float:
        if facet == "summary":
            return float(self.data.get("summary_weight", 0.10))
        if facet == "workflow":
            return float((self.data.get("workflow") or {}).get("weight", 0.25))
        return float(self.facets[facet].get("weight", 0.2))

    def weights(self) -> Dict[str, float]:
        w = {f: self.weight(f) for f in FACETS}
        w["summary"] = self.weight("summary")
        w["workflow"] = self.weight("workflow")
        return w

    # -- words --------------------------------------------------------------
    def terms(self, facet: str, lst: str) -> List[Term]:
        return self._terms.get((facet, lst), [])

    def is_open(self, facet: str, lst: str) -> bool:
        return self._open.get((facet, lst), False)

    def canonical(self, facet: str, lst: str, word: str) -> Tuple[str, bool]:
        """The ontology's word for ``word``, and whether the ontology knew it."""
        n = norm_word(word)
        table = self._lookup.get((facet, lst), {})
        if n in table:
            return table[n], True
        # A plural, -ing or -ed form is the same word: codes, coding, coded -> code.
        variants = [n + "s"]
        for suffix, repl in (("ies", "y"), ("es", ""), ("s", ""), ("ing", ""), ("ing", "e"), ("ed", ""), ("ed", "e")):
            if n.endswith(suffix) and len(n) > len(suffix) + 2:
                variants.append(n[: -len(suffix)] + repl)
        for variant in variants:
            if variant in table:
                return table[variant], True
        return n, self.is_open(facet, lst)

    def normalize(self, facet: str, lst: str, words: Any) -> Tuple[List[str], List[str]]:
        """Clean a list of words: canonical names, no repeats. Returns (words, proposed)."""
        if words is None:
            return [], []
        if isinstance(words, str):
            words = [w for w in re.split(r"[;,]", words)]
        out: List[str] = []
        proposed: List[str] = []
        for w in words:
            if not isinstance(w, str) or not w.strip():
                continue
            name, known = self.canonical(facet, lst, w)
            if name and name not in out:
                out.append(name)
                if not known:
                    proposed.append(name)
        return out, proposed

    def moves(self) -> Dict[str, str]:
        """Common general workflow steps, worded once so cards word them alike."""
        return dict((self.data.get("workflow") or {}).get("moves") or {})

    # -- for prompts ----------------------------------------------------------
    def vocabulary_text(self, include_means: bool = True) -> str:
        """The vocabulary as plain text, for the extractor's instructions."""
        lines: List[str] = []
        for facet in FACETS:
            spec = self.facets[facet]
            lines.append(f"### {facet}: {spec.get('says', '')}")
            for lst in LISTS[facet]:
                terms = self.terms(facet, lst)
                if self.is_open(facet, lst) and not terms:
                    lines.append(f"- {lst}: free words, lowercase, in the builder's own terms")
                    continue
                lines.append(f"- {lst}:")
                for t in terms:
                    lines.append(f"  - {t.name}" + (f": {t.means}" if include_means and t.means else ""))
            lines.append("")
        if self.moves():
            lines.append("### workflow moves: general steps worded once, so steps that are the same read the same. Use one when it fits; otherwise write your own general step.")
            for move, means in self.moves().items():
                lines.append(f"- {move}" + (f": {means}" if include_means and means else ""))
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"
