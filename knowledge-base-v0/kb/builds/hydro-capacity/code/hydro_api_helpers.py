"""Local stand-in for the shared `hydro_api_helpers` module.

The upstream repo imports this from a private devtools monorepo
(~/Dev/devtools/lib/hydro_api_helpers.py) that isn't published with the
project. This file reproduces the small surface api.py actually uses
(cors_origins, df_to_json_safe, build_json_response) so the FastAPI app
can start standalone.
"""
from __future__ import annotations

import base64
import math

import numpy as np
import pandas as pd


def cors_origins(name: str, port: int) -> list[str]:
    return [
        f"http://127.0.0.1:{port}",
        f"http://localhost:{port}",
        "*",
    ]


def _clean_value(v):
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        f = float(v)
        return None if math.isnan(f) else f
    if isinstance(v, np.bool_):
        return bool(v)
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d")
    if v is pd.NaT:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    return v


def df_to_json_safe(df: pd.DataFrame, limit: int | None = None) -> dict:
    d = df.head(limit) if limit else df
    records = [
        {k: _clean_value(v) for k, v in row.items()}
        for row in d.to_dict(orient="records")
    ]
    return {"columns": [str(c) for c in d.columns], "rows": records}


def build_json_response(
    *, preview: dict, meta: dict, results: dict, xlsx_bytes: bytes
) -> dict:
    return {
        "preview": preview,
        "meta": meta,
        "results": results,
        "xlsx_base64": base64.b64encode(xlsx_bytes).decode("ascii"),
    }
