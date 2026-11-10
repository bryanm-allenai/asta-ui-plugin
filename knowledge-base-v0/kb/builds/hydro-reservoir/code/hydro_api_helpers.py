"""Minimal local stand-in for the monorepo's ~/Dev/devtools/lib/hydro_api_helpers.

The upstream hydro-reservoir repo was migrated into a private monorepo
(see MIGRATED.md) and api.py now imports shared helpers from a path that
only exists on the author's machine. This file reproduces the small
surface area api.py actually uses so the FastAPI service can run standalone.
"""
from __future__ import annotations

import urllib.parse

import pandas as pd
from fastapi.responses import JSONResponse


def cors_origins(name: str, port: int) -> list[str]:
    return [f"http://127.0.0.1:{port}", f"http://localhost:{port}"]


def cjk_header_safe(value: str) -> str:
    return urllib.parse.quote(str(value))


def _to_native(value):
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def df_to_json_safe(df: pd.DataFrame, limit: int | None = None) -> dict:
    data = df.head(limit) if limit else df
    rows = [
        {str(col): _to_native(val) for col, val in row.items()}
        for _, row in data.iterrows()
    ]
    return {"columns": [str(c) for c in df.columns], "rows": rows, "total": len(df)}


def build_json_response(payload) -> JSONResponse:
    return JSONResponse(content=payload)
