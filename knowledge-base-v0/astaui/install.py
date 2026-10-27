"""Putting the skills where coding agents find them.

The skills are folders with a SKILL.md, the format Claude Code, Codex, Cursor,
Gemini CLI, GitHub Copilot, OpenCode and other agents read. Most of them read
the shared folder ~/.agents/skills; Claude Code reads ~/.claude/skills, so a
link there points at the shared copy. Each installed SKILL.md names this
computer's astaui by its full path, since a skill folder on its own has no
tool beside it.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent
SKILLS = PLUGIN / "skills"
CLI = PLUGIN / "astaui_cli.py"
# How a skill names the tool when it sits inside the plugin.
RELATIVE = "python3 <this skill's folder>/../../astaui_cli.py"
# Written into a skill so a later setup knows it as its own and may replace it.
MARK = "<!-- installed by astaui setup -->"


def _home() -> Path:
    return Path(os.environ.get("ASTAUI_SKILLS_HOME", Path.home()))


def _claude_plugin_installed(home: Path) -> bool:
    """Whether Claude Code already has these skills as the asta-ui plugin, so a
    second copy would show every skill twice."""
    path = Path(os.environ.get("CLAUDE_CONFIG_DIR", home / ".claude")) / "plugins" / "installed_plugins.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return any(k.split("@")[0] == "asta-ui" for k in (data.get("plugins") or data))


def _write_skill(src: Path, dest: Path, command: str) -> None:
    if dest.is_symlink() or dest.is_file():
        dest.unlink()
    elif dest.is_dir():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    md = dest / "SKILL.md"
    text = md.read_text(encoding="utf-8").replace(RELATIVE, command)
    md.write_text(text.rstrip("\n") + "\n\n" + MARK + "\n", encoding="utf-8")


def _ours(dest: Path) -> bool:
    """A folder this setup may replace: one it wrote, or none at all."""
    if not dest.exists() and not dest.is_symlink():
        return True
    if dest.is_symlink():
        return True
    md = dest / "SKILL.md"
    try:
        return MARK in md.read_text(encoding="utf-8")
    except OSError:
        return False


def install_skills(home: Optional[Path] = None) -> Dict[str, Any]:
    """Install every skill into ~/.agents/skills, and link Claude Code's folder to
    it (unless Claude Code has them as the plugin). A skill folder of the same
    name that this setup did not write is left alone and reported."""
    home = home or _home()
    command = f'"{sys.executable}" "{CLI}"'
    shared = home / ".agents" / "skills"
    shared.mkdir(parents=True, exist_ok=True)
    claude = None if _claude_plugin_installed(home) else home / ".claude" / "skills"
    put: List[str] = []
    skipped: List[str] = []
    for src in sorted(p for p in SKILLS.iterdir() if (p / "SKILL.md").is_file()):
        dest = shared / src.name
        if not _ours(dest):
            skipped.append(str(dest))
            continue
        _write_skill(src, dest, command)
        put.append(str(dest))
        if claude is None:
            continue
        link = claude / src.name
        if not _ours(link):
            skipped.append(str(link))
            continue
        claude.mkdir(parents=True, exist_ok=True)
        if link.is_symlink() or link.is_file():
            link.unlink()
        elif link.is_dir():
            shutil.rmtree(link)
        try:
            link.symlink_to(dest, target_is_directory=True)
        except OSError:  # Windows without the right to make links: a copy
            _write_skill(src, link, command)
        put.append(str(link))
    return {"installed": put, "skipped": skipped, "command": command, "claude_plugin": claude is None}
