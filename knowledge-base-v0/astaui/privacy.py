"""The strip step: what must not leave a scientist's machine.

A card describes structure, not data or people. Before a build is shared, this
looks through its prompts and code for keys, email addresses, home paths and large
blocks of embedded data, and can replace the first three with placeholders.
It cannot tell a real participant's name from an invented one; the report says so.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

from .kb import Build

KEY_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("Anthropic API key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{16,}")),
    ("OpenAI-style API key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9]{24,}")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("password in code", re.compile(r"(?i)\b(password|passwd|secret|api_key|apikey|token)\s*[:=]\s*['\"][^'\"\s]{8,}['\"]")),
]
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
HOME_PATH = re.compile(r"(/home/[^/\s'\"]+|/Users/[^/\s'\"]+|[A-Za-z]:\\\\?Users\\\\?[^\\\s'\"]+)")
DATA_URI = re.compile(r"data:[\w/+.-]+;base64,[A-Za-z0-9+/=]{20000,}")
NUMBER_RUN = re.compile(r"(?:-?\d+(?:\.\d+)?(?:e-?\d+)?\s*,\s*){400,}")
SAFE_EMAIL = re.compile(r"@(example\.(com|org|net)|users\.noreply\.github\.com|anthropic\.com)$", re.I)


@dataclass
class Finding:
    level: str  # "block": must be fixed before sharing; "check": a person should look
    what: str
    file: str
    line: int
    excerpt: str


def _excerpt(line: str, m: re.Match, mask: bool) -> str:
    s = line.strip()
    if mask:
        s = s.replace(m.group(0), m.group(0)[:6] + "…")
    return s[:120]


def scan_text(text: str, file: str) -> List[Finding]:
    found: List[Finding] = []
    for n, line in enumerate(text.splitlines(), 1):
        for what, pat in KEY_PATTERNS:
            for m in pat.finditer(line):
                found.append(Finding("block", what, file, n, _excerpt(line, m, True)))
        for m in EMAIL.finditer(line):
            if not SAFE_EMAIL.search(m.group(0)):
                found.append(Finding("block", "email address", file, n, _excerpt(line, m, True)))
        for m in HOME_PATH.finditer(line):
            found.append(Finding("check", "path that names a person's home folder", file, n, _excerpt(line, m, False)))
        if DATA_URI.search(line):
            found.append(Finding("check", "large embedded file (data: URI)", file, n, line.strip()[:80]))
        if NUMBER_RUN.search(line):
            found.append(Finding("check", "long run of numbers: make sure it is not real data", file, n, line.strip()[:80]))
    return found


def scan_build(build: Build) -> List[Finding]:
    found: List[Finding] = []
    for i, t in enumerate(build.prompts, 1):
        for f in scan_text(t.get("text", ""), f"prompts.jsonl turn {i}"):
            found.append(f)
    for p in build.code_files():
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        found.extend(scan_text(text, str(p.relative_to(build.path))))
    return found


def strip_text(text: str) -> Tuple[str, int]:
    """Replace keys, emails and home paths with placeholders. Returns the new text
    and how many things were replaced."""
    count = 0
    for _, pat in KEY_PATTERNS:
        text, n = pat.subn("<redacted>", text)
        count += n

    def email(m: re.Match) -> str:
        nonlocal count
        if SAFE_EMAIL.search(m.group(0)):
            return m.group(0)
        count += 1
        return "<email>"

    text = EMAIL.sub(email, text)
    text, n = HOME_PATH.subn("~", text)
    return text, count + n


def strip_build(build: Build) -> int:
    """Rewrite the build's prompts and text files with placeholders. Returns how many
    things were replaced."""
    total = 0
    rows = []
    for t in build.prompts:
        new, n = strip_text(t.get("text", ""))
        total += n
        rows.append({**t, "text": new})
    with (build.path / "prompts.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    for p in build.code_files():
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        new, n = strip_text(text)
        if new != text:
            Path(p).write_text(new, encoding="utf-8")
            total += n
    return total
