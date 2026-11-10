from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def scatter(df, x, y, color_column=None, title="", log_x=False, log_y=False, show_error_bars=False):
    error_y = "pl_rade_err" if show_error_bars and "pl_rade_err" in df.columns else None
    fig = px.scatter(
        df,
        x=x,
        y=y,
        color=color_column,
        error_y=error_y,
        title=title,
        template="plotly_dark",
        hover_data=[c for c in ("pl_name", "hostname") if c in df.columns],
        log_x=log_x,
        log_y=log_y,
        height=560,
    )
    fig.update_traces(marker=dict(size=6, opacity=0.75))
    return fig


def density(df, x, y, title=""):
    return px.density_heatmap(
        df,
        x=x,
        y=y,
        title=title,
        template="plotly_dark",
        log_x=True,
        log_y=True,
        nbinsx=40,
        nbinsy=40,
        height=560,
    )


def add_binned_median(fig, binned: pd.DataFrame, label="Median"):
    if binned.empty:
        return fig
    fig.add_trace(go.Scatter(x=binned["x"], y=binned["p84"], mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(
        go.Scatter(
            x=binned["x"],
            y=binned["p16"],
            mode="lines",
            line=dict(width=0),
            fill="tonexty",
            fillcolor="rgba(255,255,255,0.15)",
            showlegend=False,
            hoverinfo="skip",
        )
    )
    fig.add_trace(go.Scatter(x=binned["x"], y=binned["median"], mode="lines+markers", name=label, line=dict(color="white", width=2)))
    return fig


def add_age_bin_boundaries(fig, unit="Gyr"):
    factor = 1000.0 if unit == "Myr" else 1.0
    for edge in (0.1, 0.5, 2.0):
        fig.add_vline(x=edge * factor, line=dict(color="gray", dash="dot", width=1))
    return fig


def add_reference_radii(fig):
    for name, radius in {"Earth": 1.0, "Neptune": 3.88, "Jupiter": 11.2}.items():
        fig.add_hline(
            y=radius,
            line=dict(color="rgba(200,200,200,0.4)", dash="dash", width=1),
            annotation_text=name,
            annotation_position="right",
        )
    return fig


def add_radius_valley(fig, period_range):
    lo, hi = period_range
    lo = max(lo, 0.3)
    periods = np.logspace(np.log10(lo), np.log10(max(hi, lo * 1.01)), 50)
    radii = 10 ** (-0.09 * np.log10(periods) + 0.37)
    fig.add_trace(go.Scatter(x=periods, y=radii, mode="lines", name="Radius valley (Van Eylen+ 2018)", line=dict(color="#F0F0F0", dash="longdash")))
    return fig


def add_solar_system(fig):
    planets = {
        "Mercury": (88.0, 0.383),
        "Venus": (224.7, 0.949),
        "Earth": (365.25, 1.0),
        "Mars": (687.0, 0.532),
        "Neptune": (60190.0, 3.88),
    }
    fig.add_trace(
        go.Scatter(
            x=[p[0] for p in planets.values()],
            y=[p[1] for p in planets.values()],
            mode="markers+text",
            text=list(planets.keys()),
            textposition="top center",
            marker=dict(color="gold", size=10, symbol="star"),
            name="Solar System",
        )
    )
    return fig
