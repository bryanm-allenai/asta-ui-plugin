#!/usr/bin/env python3
"""Run the astaui command without installing anything: python3 astaui_cli.py <command>.

The skills call it this way, from wherever the plugin was installed.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from astaui.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
