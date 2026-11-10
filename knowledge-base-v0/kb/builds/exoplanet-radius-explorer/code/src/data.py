from __future__ import annotations

import dataclasses
import datetime as dt
import os
from io import StringIO

import pandas as pd
import requests
import streamlit as st

from .transform import prepare_data

_HERE = os.path.dirname(__file__)
SNAPSHOT_PATH = os.path.join(_HERE, "..", "data", "pscomppars_snapshot.csv")
DEMO_PATH = os.path.join(_HERE, "..", "data", "demo_synthetic.csv")

TAP_URL = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
TAP_QUERY = (
    "select pl_name,hostname,discoverymethod,disc_year,pl_orbper,pl_rade,pl_rade_err,"
    "pl_bmasse,pl_insol,pl_eqt,pl_controv_flag,tran_flag,st_age,st_age_err,sy_dist "
    "from pscomppars"
)


class DataLoadError(Exception):
    pass


@dataclasses.dataclass
class LoadResult:
    frame: pd.DataFrame
    source: str
    retrieved_at: str
    detail: str | None = None


def _fetch_live() -> pd.DataFrame:
    response = requests.get(TAP_URL, params={"query": TAP_QUERY, "format": "csv"}, timeout=5)
    response.raise_for_status()
    return pd.read_csv(StringIO(response.text))


def _load_uncached(prefer_live: bool, force_refresh: bool) -> LoadResult:
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    if prefer_live or force_refresh:
        try:
            return LoadResult(_fetch_live(), "live", now)
        except Exception:
            pass
    if os.path.exists(SNAPSHOT_PATH):
        mtime = dt.datetime.fromtimestamp(os.path.getmtime(SNAPSHOT_PATH)).strftime("%Y-%m-%d")
        return LoadResult(pd.read_csv(SNAPSHOT_PATH), "snapshot", mtime)
    if os.path.exists(DEMO_PATH):
        return LoadResult(pd.read_csv(DEMO_PATH), "demo", "n/a")
    raise DataLoadError(
        "No archive connection, no local snapshot and no cache were found."
    )


@st.cache_data(show_spinner="Loading the catalogue...")
def cached_load(prefer_live: bool, force_refresh: bool) -> LoadResult:
    return _load_uncached(prefer_live, force_refresh)


@st.cache_data(show_spinner="Cleaning the catalogue...")
def cached_prepare(raw: pd.DataFrame) -> pd.DataFrame:
    return prepare_data(raw)
