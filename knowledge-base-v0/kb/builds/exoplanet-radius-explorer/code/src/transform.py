from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd

from .config import AGE_GROUP_EDGES_GYR, AGE_GROUP_ORDER

REQUIRED_COLUMNS = [
    "pl_name",
    "hostname",
    "discoverymethod",
    "disc_year",
    "pl_orbper",
    "pl_rade",
    "pl_bmasse",
    "pl_insol",
    "pl_eqt",
    "sy_dist",
    "tran_flag",
    "st_age",
]


class SchemaError(Exception):
    pass


def prepare_data(raw: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in REQUIRED_COLUMNS if c not in raw.columns]
    if missing:
        raise SchemaError(f"Missing expected column(s): {', '.join(missing)}")

    df = raw.copy()

    for col in ("st_age_err", "pl_rade_err", "pl_controv_flag"):
        if col not in df.columns:
            df[col] = pd.NA

    numeric_cols = [
        "pl_rade",
        "pl_orbper",
        "st_age",
        "st_age_err",
        "pl_rade_err",
        "sy_dist",
        "pl_insol",
        "pl_eqt",
        "pl_bmasse",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["pl_controv_flag"] = pd.to_numeric(df["pl_controv_flag"], errors="coerce").fillna(0)
    df["tran_flag"] = pd.to_numeric(df["tran_flag"], errors="coerce").fillna(0)

    df = df.dropna(subset=["pl_rade"]).copy()

    df["st_age_myr"] = df["st_age"] * 1000.0

    edges = [0.0, *AGE_GROUP_EDGES_GYR, np.inf]
    df["age_group"] = pd.cut(df["st_age"], bins=edges, labels=AGE_GROUP_ORDER, right=False)

    df["radius_provenance"] = np.where(
        df["tran_flag"] > 0,
        "Published measurement",
        "Calculated from mass",
    )

    df["log_insol"] = np.log10(df["pl_insol"].where(df["pl_insol"] > 0))

    return df.reset_index(drop=True)


@dataclasses.dataclass
class FilterSpec:
    discovery_methods: tuple[str, ...]
    age_groups: tuple[str, ...]
    include_unknown_age: bool
    radius_range: tuple[float, float] | None
    radius_cap: float | None
    period_range: tuple[float, float] | None
    include_unknown_period: bool
    max_distance: float | None
    max_age_relerr: float | None
    max_radius_relerr: float | None
    published_radius_only: bool
    exclude_controversial: bool


def apply_filters(df: pd.DataFrame, spec: FilterSpec) -> pd.DataFrame:
    mask = df["discoverymethod"].isin(spec.discovery_methods)

    age_known = df["st_age"].notna()
    age_mask = df["age_group"].astype(str).isin(spec.age_groups)
    mask &= (age_known & age_mask) | (~age_known & spec.include_unknown_age)

    if spec.radius_range is not None:
        lo, hi = spec.radius_range
        mask &= df["pl_rade"].between(lo, hi)
    if spec.radius_cap is not None:
        mask &= df["pl_rade"] <= spec.radius_cap

    period_known = df["pl_orbper"].notna()
    if spec.period_range is not None:
        lo, hi = spec.period_range
        period_mask = df["pl_orbper"].between(lo, hi)
    else:
        period_mask = pd.Series(True, index=df.index)
    mask &= (period_known & period_mask) | (~period_known & spec.include_unknown_period)

    if spec.max_distance is not None:
        mask &= df["sy_dist"].isna() | (df["sy_dist"] <= spec.max_distance)

    if spec.max_age_relerr is not None:
        relerr = df["st_age_err"].abs() / df["st_age"].replace(0, np.nan)
        mask &= df["st_age"].isna() | (relerr <= spec.max_age_relerr)

    if spec.max_radius_relerr is not None:
        relerr = df["pl_rade_err"].abs() / df["pl_rade"].replace(0, np.nan)
        mask &= df["pl_rade_err"].isna() | (relerr <= spec.max_radius_relerr)

    if spec.published_radius_only:
        mask &= df["radius_provenance"] == "Published measurement"

    if spec.exclude_controversial:
        mask &= df["pl_controv_flag"].fillna(0) == 0

    return df[mask].copy()
