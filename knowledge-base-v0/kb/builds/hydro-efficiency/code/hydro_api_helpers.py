"""Standalone stand-in for the private ~/Dev/devtools/lib/hydro_api_helpers module
that api.py tries to import. The real module is not part of this repository; this
file is placed on sys.path (repo root) so `from hydro_api_helpers import ...` resolves.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd


def cors_origins(name: str, port: int) -> list[str]:
    return [
        f"http://localhost:{port}",
        f"http://127.0.0.1:{port}",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


def cjk_header_safe(value: str) -> str:
    return value.encode("ascii", "backslashreplace").decode("ascii")


def _safe(v):
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, np.generic):
        item = v.item()
        if isinstance(item, float) and math.isnan(item):
            return None
        return item
    if isinstance(v, pd.Timestamp):
        return v.isoformat()
    return v


def df_to_json_safe(df: pd.DataFrame | None) -> dict:
    if df is None:
        return {"columns": [], "rows": []}
    columns = [str(c) for c in df.columns]
    rows = [[_safe(v) for v in row] for row in df.itertuples(index=False, name=None)]
    return {"columns": columns, "rows": rows}
