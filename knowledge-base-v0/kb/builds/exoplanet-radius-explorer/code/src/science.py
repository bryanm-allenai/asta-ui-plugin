from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
from scipy import stats

try:
    import diptest
except ImportError:
    diptest = None


@dataclasses.dataclass
class CorrelationResult:
    rho: float
    p: float
    n: int

    def describe(self) -> str:
        if self.n < 3 or np.isnan(self.rho):
            return f"n = {self.n:,}, too few points"
        return f"rho = {self.rho:+.3f}, p = {self.p:.2g}, n = {self.n:,}"


def spearman(df, x, y) -> CorrelationResult:
    sub = df[[x, y]].dropna()
    if len(sub) < 3:
        return CorrelationResult(float("nan"), float("nan"), len(sub))
    rho, p = stats.spearmanr(sub[x], sub[y])
    return CorrelationResult(float(rho), float(p), len(sub))


def partial_spearman(df, x, y, control) -> CorrelationResult:
    sub = df[[x, y, control]].dropna()
    if len(sub) < 4:
        return CorrelationResult(float("nan"), float("nan"), len(sub))
    rx, ry, rc = sub[x].rank(), sub[y].rank(), sub[control].rank()

    def resid(a, b):
        slope, intercept, *_ = stats.linregress(b, a)
        return a - (slope * b + intercept)

    rho, p = stats.pearsonr(resid(rx, rc), resid(ry, rc))
    return CorrelationResult(float(rho), float(p), len(sub))


def correlation_by_group(df, x, y, group_col) -> pd.DataFrame:
    rows = []
    for label, sub in df.groupby(group_col, observed=True):
        result = spearman(sub, x, y)
        rows.append({group_col: label, "rho": result.rho, "p": result.p, "n": result.n})
    return pd.DataFrame(rows)


def binned_percentiles(df, x, y, n_bins: int = 12, min_count: int = 20) -> pd.DataFrame:
    sub = df[[x, y]].dropna()
    sub = sub[sub[x] > 0]
    if sub.empty:
        return pd.DataFrame(columns=["x", "median", "p16", "p84", "n"])
    edges = np.logspace(np.log10(sub[x].min()), np.log10(sub[x].max()), n_bins + 1)
    rows = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        chunk = sub[(sub[x] >= lo) & (sub[x] < hi)]
        if len(chunk) < min_count:
            continue
        rows.append(
            {
                "x": float(np.sqrt(lo * hi)),
                "median": float(chunk[y].median()),
                "p16": float(chunk[y].quantile(0.16)),
                "p84": float(chunk[y].quantile(0.84)),
                "n": len(chunk),
            }
        )
    return pd.DataFrame(rows)


@dataclasses.dataclass
class BootstrapResult:
    ratio: float
    ci_low: float
    ci_high: float
    n_young: int
    n_old: int
    n_young_clusters: int
    n_old_clusters: int
    resampling_unit: str


def bootstrap_median_ratio(
    young,
    old,
    cluster_col: str = "hostname",
    n_boot: int = 2000,
    random_state: int = 42,
) -> BootstrapResult:
    rng = np.random.default_rng(random_state)
    young = young.dropna(subset=["pl_rade"])
    old = old.dropna(subset=["pl_rade"])
    n_young, n_old = len(young), len(old)
    if n_young == 0 or n_old == 0:
        return BootstrapResult(float("nan"), float("nan"), float("nan"), n_young, n_old, 0, 0, "host")

    def cluster_draw(frame: pd.DataFrame) -> pd.DataFrame:
        hosts = frame[cluster_col].dropna().unique()
        if len(hosts) == 0:
            return frame.sample(n=len(frame), replace=True, random_state=int(rng.integers(1_000_000)))
        picked = rng.choice(hosts, size=len(hosts), replace=True)
        return pd.concat([frame[frame[cluster_col] == h] for h in picked], ignore_index=True)

    ratios = []
    for _ in range(n_boot):
        y, o = cluster_draw(young), cluster_draw(old)
        if y.empty or o.empty or o["pl_rade"].median() == 0:
            continue
        ratios.append(y["pl_rade"].median() / o["pl_rade"].median())
    ratios = np.array(ratios)
    point = float(young["pl_rade"].median() / old["pl_rade"].median())
    ci_low, ci_high = np.percentile(ratios, [2.5, 97.5]) if len(ratios) else (float("nan"), float("nan"))

    return BootstrapResult(
        ratio=point,
        ci_low=float(ci_low),
        ci_high=float(ci_high),
        n_young=n_young,
        n_old=n_old,
        n_young_clusters=int(young[cluster_col].nunique()),
        n_old_clusters=int(old[cluster_col].nunique()),
        resampling_unit="host",
    )


def completeness_note(df: pd.DataFrame) -> dict:
    return {
        "planets": len(df),
        "with_age": int(df["st_age"].notna().sum()),
        "with_period": int(df["pl_orbper"].notna().sum()),
        "published_radius": int((df["radius_provenance"] == "Published measurement").sum()),
        "host_stars": int(df["hostname"].nunique()),
    }


def detrended_radius(df: pd.DataFrame) -> pd.Series:
    return df["pl_rade"] * (df["pl_orbper"] / 10.0) ** 0.09


@dataclasses.dataclass
class BimodalityResult:
    n: int
    dip_p: float
    delta_bic: float


def bimodality(series: pd.Series) -> BimodalityResult:
    values = series.dropna().to_numpy()
    n = len(values)
    if n < 10:
        return BimodalityResult(n, float("nan"), float("nan"))

    dip_p = float("nan")
    if diptest is not None:
        _, dip_p = diptest.diptest(values)

    from sklearn.mixture import GaussianMixture

    x = values.reshape(-1, 1)
    gm1 = GaussianMixture(n_components=1, random_state=0).fit(x)
    gm2 = GaussianMixture(n_components=2, random_state=0).fit(x)
    delta_bic = float(gm1.bic(x) - gm2.bic(x))

    return BimodalityResult(n, float(dip_p), delta_bic)


@dataclasses.dataclass
class ValleyDepth:
    lower_peak: float
    upper_peak: float
    depth: float


def valley_depth(series: pd.Series) -> ValleyDepth:
    values = series.dropna().to_numpy()
    if len(values) < 10:
        return ValleyDepth(float("nan"), float("nan"), float("nan"))
    kde = stats.gaussian_kde(values)
    grid = np.linspace(values.min(), values.max(), 400)
    density = kde(grid)
    mid = len(grid) // 2
    lower_idx = int(np.argmax(density[:mid])) if mid > 0 else 0
    upper_idx = mid + int(np.argmax(density[mid:]))
    trough_idx = (
        lower_idx + int(np.argmin(density[lower_idx : upper_idx + 1])) if upper_idx > lower_idx else lower_idx
    )
    shallow_peak = min(density[lower_idx], density[upper_idx])
    depth = 1.0 - (density[trough_idx] / shallow_peak) if shallow_peak > 0 else float("nan")
    return ValleyDepth(float(grid[lower_idx]), float(grid[upper_idx]), float(depth))
