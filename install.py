#!/usr/bin/env python3
"""Install AstaUI for any coding agent.

    curl -fsSL https://raw.githubusercontent.com/bryanm-allenai/asta-ui-plugin/main/install.py | python3 - --link <link>

It downloads the plugin into ~/.astaui/plugin (replacing an older copy), then
runs `astaui setup`, which puts the skills where Claude Code, Codex, Cursor,
Gemini CLI and other agents find them and keeps the link builds are sent to.
Running it again brings everything up to date. It needs Python 3.9 or later
and nothing else.
"""

import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

REPO = "bryanm-allenai/asta-ui-plugin"
URL = os.environ.get("ASTAUI_PLUGIN_URL", f"https://codeload.github.com/{REPO}/tar.gz/refs/heads/main")
HOME = Path(os.environ.get("ASTAUI_HOME", Path.home() / ".astaui"))


def main() -> int:
    if sys.version_info < (3, 9):
        print("AstaUI needs Python 3.9 or later.", file=sys.stderr)
        return 1
    try:
        data = urllib.request.urlopen(URL, timeout=120).read()
    except OSError as e:
        print(f"Could not download AstaUI from {URL}: {e}", file=sys.stderr)
        return 1
    HOME.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=".download-", dir=HOME))
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as t:
            for m in t.getmembers():
                if m.name.startswith(("/", "\\")) or ".." in Path(m.name).parts or not (m.isfile() or m.isdir()):
                    print(f"The download holds something unexpected ({m.name}); nothing was installed.", file=sys.stderr)
                    return 1
            if hasattr(tarfile, "data_filter"):
                t.extractall(tmp, filter="data")
            else:
                t.extractall(tmp)
        top = next(p for p in tmp.iterdir() if p.is_dir())
        dest = HOME / "plugin"
        if dest.exists():
            shutil.rmtree(dest)
        top.rename(dest)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    cli = dest / "knowledge-base-v0" / "astaui_cli.py"
    print(f"Downloaded AstaUI into {dest}.")
    return subprocess.call([sys.executable, str(cli), "setup", *sys.argv[1:]])


if __name__ == "__main__":
    sys.exit(main())
