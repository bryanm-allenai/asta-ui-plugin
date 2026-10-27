"""A symbol index: where each function, class, element and style rule in a build is.

It is worked out by reading the code, with no model involved: functions, classes,
methods and top-level data in JavaScript, TypeScript and Python; elements with an
id (and landmark elements with a class) in HTML; rules in CSS, including the
<style> and <script> blocks inside an HTML file. Each symbol has a line range.

The extractor is shown this index, so a card can point at code by symbol rather
than by guessed line numbers. Slices use it to pull in what a span depends on:
the functions it calls, the style rules for the classes in its markup, and the
elements its script reaches for by id.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

JS_EXT = {".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx"}
HTML_EXT = {".html", ".htm", ".mrbl", ".vue", ".svelte"}
CSS_EXT = {".css", ".scss"}
PY_EXT = {".py"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
LANDMARKS = {"aside", "section", "main", "header", "nav", "footer", "form", "dialog", "table", "article", "svg", "canvas"}
KEYWORDS = {"if", "for", "while", "switch", "catch", "function", "return", "with", "else", "do", "try", "new", "typeof", "await"}

JS_PATTERNS = [
    ("function", re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)\s*\(")),
    ("function", re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s+)?(?:function\b|\([^)]*\)\s*=>|[A-Za-z_$][\w$]*\s*=>)")),
    ("class", re.compile(r"^\s*(?:export\s+)?(?:default\s+)?class\s+([A-Za-z_$][\w$]*)")),
    ("data", re.compile(r"^\s{0,4}(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*[\[{`]")),
    ("method", re.compile(r"^\s+(?:async\s+|static\s+|get\s+|set\s+)*([A-Za-z_$][\w$]*)\s*\([^()]*\)\s*\{\s*$")),
]
PY_PATTERNS = [
    ("function", re.compile(r"^(\s*)(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(")),
    ("class", re.compile(r"^(\s*)class\s+([A-Za-z_]\w*)")),
]
HTML_OPEN = re.compile(r"<([a-zA-Z][\w-]*)\b([^>]*)>")
ID_ATTR = re.compile(r"""\bid\s*=\s*["']([^"']+)["']""")
CLASS_ATTR = re.compile(r"""\bclass\s*=\s*["']([^"']+)["']""")


@dataclass
class Symbol:
    name: str
    kind: str      # function, method, class, data, element, css, block
    file: str
    start: int
    end: int

    def as_dict(self) -> Dict[str, object]:
        return asdict(self)

    def label(self) -> str:
        return f"{self.kind} {self.name} {self.start}-{self.end}"


REGEX_BEFORE = set("(,=:[!&|?{};+-*%<>~^")


def _regex_can_start(line: str, j: int) -> bool:
    """Whether a / at column j starts a regular expression rather than a division:
    true after an operator or an opening bracket, at the start of a line, or after
    a keyword like return."""
    before = line[:j].rstrip()
    if not before:
        return True
    if before[-1] in REGEX_BEFORE:
        return True
    return bool(re.search(r"\b(return|typeof|case|in|of|delete|void|throw|new)$", before))


def _regex_end(line: str, j: int) -> int:
    """The column of the / that closes a regular expression opened at column j."""
    k = j + 1
    in_class = False
    while k < len(line):
        c = line[k]
        if c == "\\":
            k += 2
            continue
        if c == "[":
            in_class = True
        elif c == "]":
            in_class = False
        elif c == "/" and not in_class:
            return k
        k += 1
    return j  # not a regex after all: treat the / as a plain character


def _brace_end(lines: List[str], start: int, open_ch: str = "{", close_ch: str = "}") -> int:
    """The line (0-based) where the block opened at or after ``start`` closes.
    Skips braces inside strings, template literals and comments."""
    depth = 0
    opened = False
    state = None  # None, "'", '"', "`", "//", "/*"
    for i in range(start, len(lines)):
        line = lines[i]
        j = 0
        if state == "//":
            state = None
        while j < len(line):
            c = line[j]
            nxt = line[j + 1] if j + 1 < len(line) else ""
            if state in ("'", '"', "`"):
                if c == "\\":
                    j += 2
                    continue
                if c == state:
                    state = None
            elif state == "/*":
                if c == "*" and nxt == "/":
                    state = None
                    j += 1
            else:
                if c == "/" and nxt == "/":
                    break
                if c == "/" and nxt == "*":
                    state = "/*"
                    j += 1
                elif c == "/" and _regex_can_start(line, j):
                    j = _regex_end(line, j)
                elif c in ("'", '"', "`"):
                    state = c
                elif c == open_ch:
                    depth += 1
                    opened = True
                elif c == close_ch:
                    depth -= 1
                    if opened and depth <= 0:
                        return i
            j += 1
        if state in ("'", '"'):
            state = None  # an unclosed quote does not span lines
        if not opened and line.rstrip().endswith(";"):
            return i  # a statement with no block
    return start if not opened else len(lines) - 1


CONST_LINE = re.compile(r"^\s{0,4}(?:export\s+)?(?:const|let|var)\s+(.*)$")
UPPER = re.compile(r"(?:^|,)\s*([A-Z][A-Z0-9_]*)\s*=")
HANDLE = re.compile(r"(?:^|,)\s*([A-Za-z_$][\w$]*)\s*=\s*(?:document\.)?(?:getElementById|querySelector(?:All)?|\$)\s*\(")


def _declared(line: str) -> List[str]:
    """Names declared on a top-level line as constants (BOARD_W = 2000, ...) or as
    handles on elements (board = $('board'), ...)."""
    m = CONST_LINE.match(line)
    if not m:
        return []
    rest = m.group(1)
    names = UPPER.findall(rest) + HANDLE.findall(rest)
    return list(dict.fromkeys(names))


def _js(lines: List[str], file: str, offset: int = 0) -> List[Symbol]:
    out: List[Symbol] = []
    for i, line in enumerate(lines):
        matched = False
        for kind, pat in JS_PATTERNS:
            m = pat.match(line)
            if not m:
                continue
            name = m.group(1)
            if kind == "method" and name in KEYWORDS:
                continue
            end = _brace_end(lines, i) if ("{" in line[m.end() - 1:] or kind in ("function", "class", "method")) else i
            if kind == "data":
                end = _brace_end(lines, i, "[", "]") if "[" in line.split("=", 1)[1][:3] else _brace_end(lines, i)
            out.append(Symbol(name, kind, file, i + 1 + offset, max(i, end) + 1 + offset))
            matched = True
            break
        if not matched:
            for name in _declared(line):
                end = _brace_end(lines, i) if line.rstrip().endswith(("{", "[", "(", ",")) else i
                out.append(Symbol(name, "data", file, i + 1 + offset, max(i, end) + 1 + offset))
    return out


def _py(lines: List[str], file: str) -> List[Symbol]:
    out: List[Symbol] = []
    for i, line in enumerate(lines):
        for kind, pat in PY_PATTERNS:
            m = pat.match(line)
            if not m:
                continue
            indent = len(m.group(1))
            end = i
            for k in range(i + 1, len(lines)):
                s = lines[k]
                if s.strip() and (len(s) - len(s.lstrip())) <= indent:
                    break
                if s.strip():
                    end = k
            out.append(Symbol(m.group(2), kind, file, i + 1, end + 1))
            break
    return out


def _css(lines: List[str], file: str, offset: int = 0) -> List[Symbol]:
    out: List[Symbol] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^\s*([^{}/;][^{};]*?)\s*\{", line)
        if m and not line.strip().startswith("//"):
            sel = " ".join(m.group(1).split())
            end = _brace_end(lines, i)
            out.append(Symbol(sel[:80], "css", file, i + 1 + offset, end + 1 + offset))
            if sel.startswith("@media") or sel.startswith("@supports") or sel.startswith("@container"):
                i += 1  # look inside for the rules it holds
                continue
            i = end + 1
            continue
        i += 1
    return out


def _html(lines: List[str], file: str) -> List[Symbol]:
    out: List[Symbol] = []
    text_lines = lines
    # Blocks of other languages inside the page.
    i = 0
    while i < len(text_lines):
        low = text_lines[i].lower()
        for tag, sub in (("script", _js), ("style", _css)):
            if re.search(rf"<{tag}\b", low) and not re.search(rf"<{tag}\b[^>]*\bsrc=", low):
                end = i
                while end < len(text_lines) and f"</{tag}>" not in text_lines[end].lower():
                    end += 1
                end = min(end, len(text_lines) - 1)
                out.append(Symbol(f"<{tag}>", "block", file, i + 1, end + 1))
                inner = text_lines[i + 1 : end]
                out.extend(sub(inner, file, offset=i + 1))
                i = end
                break
        i += 1
    # Elements with an id, and landmark elements.
    blocks = [(s.start, s.end) for s in out if s.kind == "block"]
    for i, line in enumerate(lines):
        if any(a <= i + 1 <= b for a, b in blocks):
            continue
        for m in HTML_OPEN.finditer(line):
            tag, attrs = m.group(1).lower(), m.group(2)
            idm = ID_ATTR.search(attrs)
            clm = CLASS_ATTR.search(attrs)
            if not idm and not (tag in LANDMARKS and clm):
                continue
            name = f"#{idm.group(1)}" if idm else f"{tag}.{clm.group(1).split()[0]}"
            end = _element_end(lines, i, m.start(), tag, attrs)
            out.append(Symbol(name, "element", file, i + 1, end + 1))
    # Landmarks named by tag and class can repeat: number them, section.block:2 and so on.
    counts: Dict[str, int] = {}
    for sym in out:
        if sym.kind == "element" and not sym.name.startswith("#"):
            counts[sym.name] = counts.get(sym.name, 0) + 1
    seen: Dict[str, int] = {}
    for sym in out:
        if sym.kind == "element" and counts.get(sym.name, 0) > 1:
            seen[sym.name] = seen.get(sym.name, 0) + 1
            sym.name = f"{sym.name}:{seen[sym.name]}"
    return out


def _element_end(lines: List[str], row: int, col: int, tag: str, attrs: str) -> int:
    if tag in VOID or attrs.rstrip().endswith("/"):
        return row
    depth = 0
    open_re = re.compile(rf"<{tag}\b", re.I)
    close_re = re.compile(rf"</{tag}\s*>", re.I)
    for i in range(row, len(lines)):
        seg = lines[i][col:] if i == row else lines[i]
        events = sorted([(m.start(), 1) for m in open_re.finditer(seg)] + [(m.start(), -1) for m in close_re.finditer(seg)])
        for _, d in events:
            depth += d
            if depth == 0:
                return i
    return row


def index_file(rel: str, text: str) -> List[Symbol]:
    ext = Path(rel).suffix.lower()
    lines = text.splitlines()
    if ext in JS_EXT:
        return _js(lines, rel)
    if ext in HTML_EXT:
        return _html(lines, rel)
    if ext in CSS_EXT:
        return _css(lines, rel)
    if ext in PY_EXT:
        return _py(lines, rel)
    return []


def index_build(build) -> List[Symbol]:
    out: List[Symbol] = []
    for p in build.code_files():
        rel = str(p.relative_to(build.path))
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        out.extend(index_file(rel, text))
    return out


ROLE_KINDS = {"markup": ("element",), "style": ("css",), "logic": ("function", "method", "class"), "data": ("data",)}


def find(symbols: Iterable[Symbol], name: str, file: Optional[str] = None, role: Optional[str] = None) -> Optional[Symbol]:
    """A symbol by name. ``#grid`` can be an element and a style rule; the role says
    which is meant (markup or style). Otherwise functions and elements come first."""
    order = {"function": 0, "class": 1, "element": 2, "data": 3, "method": 4, "css": 5, "block": 6}
    if role in ROLE_KINDS:
        for k in ROLE_KINDS[role]:
            order[k] = -1
    want = name.strip()
    hits = [s for s in symbols if (s.name == want or s.name == want.lstrip("#.") or s.name == f"#{want}")
            and (file is None or s.file == file)]
    return min(hits, key=lambda s: order.get(s.kind, 9)) if hits else None


def outline(symbols: List[Symbol], file: str, limit: int = 160) -> List[str]:
    """The symbols in one file, one per line, for the extractor."""
    rows = [s for s in symbols if s.file == file and s.kind != "block"]
    rows.sort(key=lambda s: s.start)
    out = [f"  {s.kind:<8} {s.name}  {s.start}-{s.end}" for s in rows[:limit]]
    if len(rows) > limit:
        out.append(f"  … and {len(rows) - limit} more")
    return out


# -- what a span depends on --------------------------------------------------------

CALL = re.compile(r"(?<![\w$.])([A-Za-z_$][\w$]*)\s*\(")
WORD = re.compile(r"(?<![\w$.])([A-Za-z_$][\w$]*)(?![\w$])")
BY_ID = re.compile(r"""(?:getElementById\(\s*["']|querySelector(?:All)?\(\s*["']#|\$\(\s*["']#?)([\w-]+)""")
CLASSES = re.compile(r"""\bclass(?:Name)?\s*=\s*["'{`]([^"'}`]+)""")
CLASS_USE = re.compile(r"""classList\.(?:add|remove|toggle|contains)\(\s*["']([\w-]+)""")


def references(text: str) -> Dict[str, List[str]]:
    """Names a span of code uses: functions it calls, words that may be data,
    ids it reaches for, and classes it writes or toggles."""
    classes: List[str] = []
    for m in CLASSES.finditer(text):
        classes.extend(c for c in re.split(r"\s+", m.group(1)) if re.match(r"^[\w-]+$", c))
    classes.extend(CLASS_USE.findall(text))
    return {
        "calls": sorted(set(CALL.findall(text)) - KEYWORDS),
        "words": sorted(set(WORD.findall(text))),
        "ids": sorted(set(BY_ID.findall(text)) | set(ID_ATTR.findall(text))),
        "classes": sorted(set(classes)),
    }


def _subjects(selector: str) -> List[str]:
    """The last compound of each selector in a list: the element the rule styles.
    `.block .record-title, #grid > li:hover` gives `.record-title` and `li:hover`."""
    out = []
    for part in selector.split(","):
        bits = re.split(r"\s*[>+~]\s*|\s+", part.strip())
        if bits and bits[-1]:
            out.append(bits[-1])
    return out


def css_for(symbols: Iterable[Symbol], ids: Iterable[str], classes: Iterable[str]) -> List[Symbol]:
    """Style rules for these ids and classes: rules whose subject (the element they
    style, the last part of the selector) carries one of them. A rule that only
    mentions a class as an ancestor styles something else, and is left out."""
    names = [rf"#{re.escape(i)}(?![\w-])" for i in ids] + [rf"\.{re.escape(c)}(?![\w-])" for c in classes]
    if not names:
        return []
    pat = re.compile("|".join(names))
    return [s for s in symbols if s.kind == "css" and not s.name.startswith("@")
            and any(pat.search(subj) for subj in _subjects(s.name))]


def as_ranges(symbols: Iterable[Symbol]) -> List[Tuple[str, int, int]]:
    return [(s.file, s.start, s.end) for s in symbols]
