#!/usr/bin/env python3
"""Run the astaui command without installing anything: python3 astaui_cli.py <command>.

The skills call it this way, from wherever the plugin was installed.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# On the computer that holds the whole knowledge base, setup/python.sh makes .venv
# beside this file, with numpy and psycopg. Run in it, so every caller (the skills,
# the hourly intake) gets fast similarity and the database. Nothing changes where
# there is no .venv, as in the plugin scientists install.
_venv = os.path.join(HERE, ".venv", "bin", "python")
if (os.path.exists(_venv) and not os.environ.get("ASTAUI_NO_VENV")
        and os.path.realpath(sys.prefix) != os.path.realpath(os.path.join(HERE, ".venv"))):
    os.environ["ASTAUI_NO_VENV"] = "1"  # never loop
    os.execv(_venv, [_venv, os.path.abspath(__file__), *sys.argv[1:]])

sys.path.insert(0, HERE)

from astaui.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
