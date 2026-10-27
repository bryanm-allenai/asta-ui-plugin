"""Bringing a Marble page in line with what it should hold, with as few edits as possible.

The console page is made of a fixed skeleton and, inside it, slots: containers
whose children are blocks with stable ids (a point on the map, a row of the
matrix, a word in the Types view). The renderer says what every slot should hold;
this module reads the page file, finds what each slot does hold, and works out
the ops that turn one into the other:

- a block that is the same is left alone, so an unchanged knowledge base costs
  no edits at all;
- a block whose attributes changed gets setAttr, one per attribute;
- a block whose contents changed gets setInner;
- a new block is inserted where it belongs, and a block that should no longer
  be there is removed; blocks out of order are moved.

Marble's agent tools only let an agent change an element it has read in full,
and only read in full what fits in one read. So every block stays small, and the
ops are cut into batches, each with the list of elements it edits (`reads`) to
read first, within one read's budget.

Two pieces of markup are "the same" when they parse to the same tags, the same
attributes (in any order, however quoted) and the same text.
"""

from __future__ import annotations

import html as _html
import re
import zlib
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Sequence, Tuple

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
ID = "data-marble-id"
INNER_LIMIT = 11500      # setInner's own cap is 12K
READ_BUDGET = 18000      # one read_document call shows about 24K
BATCH_OPS = 20         # apply_ops takes 24
BATCH_CHARS = 20000      # a batch file an agent can print whole


@dataclass
class Node:
    id: str
    tag: str
    attrs: Dict[str, str]
    start: int
    inner_start: int
    inner_end: int = -1
    end: int = -1
    parent: Optional[str] = None
    children: List[str] = field(default_factory=list)
    direct: bool = True     # its parent in the page is its addressed parent, with no tag between


class _Indexer(HTMLParser):
    def __init__(self, source: str):
        super().__init__(convert_charrefs=True)
        self.source = source
        self.lines = [0]
        for m in re.finditer("\n", source):
            self.lines.append(m.end())
        self.stack: List[Tuple[str, Optional[Node]]] = []
        self.nodes: Dict[str, Node] = {}
        self.order: List[str] = []

    def _offset(self) -> int:
        line, col = self.getpos()
        return self.lines[line - 1] + col

    def _parent_id(self) -> Optional[str]:
        for _, node in reversed(self.stack):
            if node is not None:
                return node.id
        return None

    def handle_starttag(self, tag, attrs):
        start = self._offset()
        raw = self.get_starttag_text() or ""
        a = {k: (v if v is not None else "") for k, v in attrs}
        node = None
        if ID in a:
            node = Node(id=a[ID], tag=tag, attrs=a, start=start, inner_start=start + len(raw), parent=self._parent_id(),
                        direct=not self.stack or self.stack[-1][1] is not None)
            if node.parent:
                self.nodes[node.parent].children.append(node.id)
            self.nodes[node.id] = node
            self.order.append(node.id)
        if tag in VOID:
            if node:
                node.inner_end = node.inner_start
                node.end = node.inner_start
            return
        self.stack.append((tag, node))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID and self.stack and self.stack[-1][0] == tag:
            _, node = self.stack.pop()
            if node:
                node.inner_end = node.inner_start
                node.end = node.inner_start

    def handle_endtag(self, tag):
        pos = self._offset()
        close = self.source.find(">", pos)
        end = close + 1 if close >= 0 else pos
        # Pop to the matching open tag; anything left open inside it closes here too.
        for k in range(len(self.stack) - 1, -1, -1):
            if self.stack[k][0] == tag:
                for depth, (t, node) in enumerate(self.stack[k:]):
                    if node is not None:
                        node.inner_end = pos
                        node.end = end if depth == 0 else pos
                del self.stack[k:]
                return


def index(source: str) -> Dict[str, Node]:
    """Every addressed element in a page: its tag, attributes, where it starts and
    ends in the file, its addressed parent and children."""
    p = _Indexer(source)
    p.feed(source)
    p.close()
    return p.nodes


def outer(source: str, node: Node) -> str:
    return source[node.start:node.end]


def inner(source: str, node: Node) -> str:
    return source[node.inner_start:node.inner_end]


# Attributes the page sets for itself and never files, and ids Marble mints as
# a block lands: neither says anything about what a block shows.
PAGE_ONLY = {"aria-pressed", "tabindex", "contenteditable", "spellcheck", ID}


def clean_attrs(attrs) -> Dict[str, str]:
    """A block's attributes as the renderer would write them: without what the page
    keeps to itself, and without the classes it derives (marble-…)."""
    out = {}
    for k, v in (attrs.items() if isinstance(attrs, dict) else attrs):
        if k in PAGE_ONLY:
            continue
        v = v or ""
        if k == "class":
            v = " ".join(c for c in v.split() if not c.startswith("marble-"))
            if not v:
                continue
        out[k] = v
    return out


class _Canon(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: List[str] = []

    def handle_starttag(self, tag, attrs):
        self.out.append("<" + tag + "".join(f" {k}={v!r}" for k, v in sorted(clean_attrs(attrs).items())) + ">")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.out.append(f"</{tag}>")

    def handle_endtag(self, tag):
        if tag not in VOID:
            self.out.append(f"</{tag}>")

    def handle_data(self, data):
        # Marble indents an element it inserts into another: a line break and spaces
        # between two tags say nothing about what a block shows.
        if "\n" in data and not data.strip():
            return
        self.out.append(data)


def canon(markup: str) -> str:
    """The markup as tags, sorted attributes and text, so the same page written two
    ways compares equal, however Marble indents what it inserts."""
    p = _Canon()
    p.feed(markup)
    p.close()
    return "".join(p.out)


def _bounds(markup: str) -> Tuple[str, Dict[str, str], int, int]:
    """An element's tag and attributes, and where its inner markup starts and ends."""
    m = re.match(r"\s*<([a-zA-Z][\w-]*)\b", markup)
    if not m:
        raise ValueError("a block must start with its element")
    tag = m.group(1).lower()

    class _First(HTMLParser):
        attrs: Dict[str, str] = {}
        raw = ""

        def handle_starttag(self, t, a):
            if not self.raw:
                self.attrs = {k: (v if v is not None else "") for k, v in a}
                self.raw = self.get_starttag_text() or ""

    f = _First()
    f.feed(markup)
    start = markup.index(f.raw) + len(f.raw)
    end = markup.rstrip().rfind("</")
    if end < start or tag in VOID:
        end = start
    return tag, f.attrs, start, end


def split_block(markup: str) -> Tuple[str, Dict[str, str], str]:
    """A block's tag, attributes and inner markup."""
    tag, attrs, start, end = _bounds(markup)
    return tag, attrs, markup[start:end]


@dataclass
class Op:
    op: Dict[str, Any]
    reads: List[str]
    read_size: int
    # Starts a batch of its own: an insert into an element an earlier setInner
    # brought, which Marble only knows by id once that setInner has landed.
    after: bool = False

    @property
    def size(self) -> int:
        return len(str(self.op.get("html", ""))) + len(str(self.op.get("value", "") or "")) + len(str(self.op.get("text", ""))) + 80


class PageError(Exception):
    """The page cannot be brought in line by edits; it says why and what to do."""


# What Marble adds to every element that lands without an id, before it measures
# a setInner against its cap: ` data-marble-id="` + eight letters + `"`.
MINTED = len(f' {ID}=""') + 8


def minted_len(markup: str) -> int:
    """How long markup is once Marble has given each element without an id one."""
    tags = re.findall(r"<[a-zA-Z][^>]*>", markup)
    return len(markup) + MINTED * sum(1 for t in tags if f"{ID}=" not in t)


def _pieces(markup: str) -> List[str]:
    """Markup cut into its top-level elements and the text between them, as written."""
    lines = [0] + [m.end() for m in re.finditer("\n", markup)]
    cuts = {0, len(markup)}

    class _Cut(HTMLParser):
        depth = 0

        def _at(self) -> int:
            line, col = self.getpos()
            return lines[line - 1] + col

        def handle_starttag(self, tag, attrs):
            if self.depth == 0:
                cuts.add(self._at())
                if tag in VOID:
                    cuts.add(self._at() + len(self.get_starttag_text() or ""))
            if tag not in VOID:
                self.depth += 1

        def handle_startendtag(self, tag, attrs):
            if self.depth == 0:
                cuts.add(self._at())
                cuts.add(self._at() + len(self.get_starttag_text() or ""))

        def handle_endtag(self, tag):
            if tag in VOID:
                return
            self.depth -= 1
            if self.depth == 0:
                cuts.add(markup.find(">", self._at()) + 1)

    p = _Cut(convert_charrefs=False)
    p.feed(markup)
    p.close()
    at = sorted(cuts)
    return [markup[a:b] for a, b in zip(at, at[1:]) if b > a]


def fit(pid: str, body: str, limit: int, salt: str = "") -> Tuple[str, List[Dict[str, Any]]]:
    """`body` as what one setInner of `pid` can carry once Marble has minted its ids,
    and the inserts that add the rest, in order. Where an element has to be cut, it
    gets an id of its own so the rest can be inserted into it. Those ids are new for
    every body, because a setInner may not bring back an id the page still holds."""
    salt = salt or format(zlib.crc32(body.encode()), "08x")
    count = iter(range(10**6))

    def name() -> str:
        return f"{pid}-{salt}-{next(count)}"

    def opened(piece: str) -> Tuple[str, str, str]:
        _, _, start, end = _bounds(piece)
        open_tag, inside, close = piece[:start], piece[start:end], piece[end:]
        if f"{ID}=" not in open_tag:
            open_tag = re.sub(r"^(\s*<[a-zA-Z][\w-]*)", lambda m: f'{m.group(1)} {ID}="{name()}"', open_tag, count=1)
        return open_tag, inside, close

    def own_id(open_tag: str) -> str:
        return re.search(f'{ID}="([^"]+)"', open_tag).group(1)

    def split(parent: str, inside: str, room: int) -> Tuple[str, List[Dict[str, Any]]]:
        if minted_len(inside) <= room:
            return inside, []
        pieces = _pieces(inside)
        head, used = "", 0
        for k, piece in enumerate(pieces):
            size = minted_len(piece)
            if used + size <= room:
                head, used = head + piece, used + size
                continue
            later: List[Dict[str, Any]] = []
            if piece.lstrip().startswith("<"):
                open_tag, sub, close = opened(piece)
                left = room - used - minted_len(open_tag + close)
                if sub and left > 0:
                    sub_head, sub_later = split(own_id(open_tag), sub, left)
                    head += open_tag + sub_head + close
                    later += sub_later
                else:
                    later += place(parent, piece)
            else:
                later += place(parent, piece)
            for p in pieces[k + 1:]:
                later += place(parent, p)
            return head, later
        return head, []

    def place(parent: str, piece: str) -> List[Dict[str, Any]]:
        if not piece.lstrip().startswith("<"):
            # Marble indents what it inserts anyway; any other text cannot be inserted alone.
            if "\n" in piece and not piece.strip():
                return []
            raise PageError(f"{pid!r} is too big for one edit and has text between its parts; wrap that text in an element")
        if minted_len(piece) <= limit:
            return [{"type": "insert", "parentId": parent, "beforeId": None, "html": piece}]
        open_tag, sub, close = opened(piece)
        sub_head, sub_later = split(own_id(open_tag), sub, limit - minted_len(open_tag + close))
        return [{"type": "insert", "parentId": parent, "beforeId": None, "html": open_tag + sub_head + close}] + sub_later

    return split(pid, body, limit)


def diff_slot(source: str, nodes: Dict[str, Node], slot: str, blocks: Sequence[Tuple[str, str]]) -> List[Op]:
    """The ops that make slot `slot` hold exactly `blocks` (id, markup), in order."""
    if slot not in nodes:
        raise PageError(f"the page has no {slot!r}; it is older than this version of astaui")
    have = [c for c in nodes[slot].children]
    want_ids = [b for b, _ in blocks]
    if len(set(want_ids)) != len(want_ids):
        raise PageError(f"two blocks in {slot!r} share an id")
    ops: List[Op] = []
    # Remove what should no longer be there.
    for cid in have:
        if cid not in want_ids:
            n = nodes[cid]
            ops.append(Op({"type": "remove", "id": cid}, [cid], n.end - n.start))
    kept = [c for c in have if c in want_ids]
    # Change what changed.
    for bid, markup in blocks:
        if bid not in nodes:
            continue
        if bid not in kept:
            raise PageError(f"{bid!r} is in the page but not inside {slot!r}")
        n = nodes[bid]
        tag, attrs, body = split_block(markup)
        if tag != n.tag:
            raise PageError(f"{bid!r} changed from <{n.tag}> to <{tag}>; rebuild the page")
        size = n.end - n.start
        want_a, have_a = clean_attrs(attrs), clean_attrs(n.attrs)
        for name in sorted(set(want_a) | set(have_a)):
            new, old = want_a.get(name), have_a.get(name)
            if new != old:
                ops.append(Op({"type": "setAttr", "id": bid, "name": name, "value": new}, [bid], size))
        # What a person typed into a field is theirs: a refresh brings the
        # field's attributes up to date and leaves its words alone.
        if n.attrs.get("data-marble-editable") == "write":
            continue
        if canon(body) != canon(inner(source, n)):
            head, rest = fit(bid, body, INNER_LIMIT)
            ops.append(Op({"type": "setInner", "id": bid, "html": head}, [bid], size))
            ops.extend(Op(o, [], 0, after=k == 0) for k, o in enumerate(rest))
    # Put the kept ones in order, then insert the new ones where they belong.
    order_now = [c for c in kept]
    order_want = [b for b in want_ids if b in kept]
    if order_now != order_want:
        for k in range(len(order_want) - 1, -1, -1):
            bid = order_want[k]
            before = order_want[k + 1] if k + 1 < len(order_want) else None
            ops.append(Op({"type": "move", "id": bid, "parentId": slot, "beforeId": before}, [bid], nodes[bid].end - nodes[bid].start))
    present = set(kept)
    for k, (bid, markup) in enumerate(blocks):
        if bid in present:
            continue
        if len(markup) > INNER_LIMIT + 400:
            raise PageError(f"{bid!r} is {len(markup)} characters, more than one edit can carry")
        before = next((b for b, _ in blocks[k + 1:] if b in present), None)
        ops.append(Op({"type": "insert", "parentId": slot, "beforeId": before, "html": markup}, [], 0))
    return ops


def batches(ops: Sequence[Op], note: str) -> List[Dict[str, Any]]:
    """Ops cut into batches an agent can carry: each batch's reads fit one read, its
    ops fit one call."""
    out: List[Dict[str, Any]] = []
    cur: List[Op] = []
    reads: List[str] = []
    read_size = 0
    chars = 0

    def flush():
        nonlocal cur, reads, read_size, chars
        if cur:
            out.append({"reads": list(dict.fromkeys(reads)), "ops": [o.op for o in cur]})
        cur, reads, read_size, chars = [], [], 0, 0

    for o in ops:
        new_reads = [r for r in o.reads if r not in reads]
        add_read = o.read_size if new_reads else 0
        if cur and (o.after or len(cur) >= BATCH_OPS or chars + o.size > BATCH_CHARS or read_size + add_read > READ_BUDGET):
            flush()
            new_reads = list(o.reads)
            add_read = o.read_size if new_reads else 0
        cur.append(o)
        reads.extend(new_reads)
        read_size += add_read
        chars += o.size
    flush()
    n = len(out)
    for k, b in enumerate(out, 1):
        b["note"] = note + (f" ({k} of {n})" if n > 1 else "")
    return [{"note": b["note"], "reads": b["reads"], "ops": b["ops"]} for b in out]


def text_of(source: str, node: Node) -> str:
    """An element's text, tags stripped, entities read."""
    return _html.unescape(re.sub(r"<[^>]+>", "", inner(source, node))).strip()
