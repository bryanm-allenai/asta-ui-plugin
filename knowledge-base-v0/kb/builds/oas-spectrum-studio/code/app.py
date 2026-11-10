from __future__ import annotations

import base64
import hmac
import textwrap
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from oas_web.analysis import (
    DEFAULT_MAX_REPEAT,
    DEFAULT_MIN_FIT_FRACTION,
    DEFAULT_NO_O3_DENSITY_THRESHOLD,
    DEFAULT_NO_O3_RATIO,
    DEFAULT_NO_O3_RULE,
    DEFAULT_NO_PEAK_EMPHASIS,
    DEFAULT_OD_AVG_COEFF,
    DEFAULT_OD_CLIP_THRESHOLD,
    FitConfig,
    build_continual_learning_frame_single,
    build_continual_learning_frame_timeseries,
    compute_optical_depth_from_reference,
    discover_preferred_cross_section_dir,
    load_cross_sections_from_dir,
    load_spectrum,
    prepare_download_frame,
    run_single_from_intensity_files,
    run_time_series_from_intensity_files,
)
from oas_web.ml import (
    build_continual_learning_frame_ml_single,
    build_continual_learning_frame_ml_timeseries,
    run_ml_inference,
    run_time_series_ml_from_intensity_files,
)
from oas_web.plots import (
    make_intensity_preview,
    make_overlay_figure,
    make_species_bar,
    make_timeseries_trend,
)
from oas_web.cl_submit import (
    SubmissionError,
    build_submission_payload,
    submit_to_global_model,
)


ROOT = Path(__file__).resolve().parent
ML_FALLBACK_PTH = ROOT / "machine_learning" / "exp_4_epoch_3000.pth"
ML_LATEST_POINTER = ROOT / "models" / "latest.json"
ASSETS_DIR = ROOT / "assets"

# Partner logos. Drop a real raster/vector file at either of these names to
# override the bundled placeholder:
#   assets/kaist_logo.png   (or .svg)   → links to https://www.kaist.ac.kr/kr/
#   assets/april_logo.png   (or .svg)   → links to https://april.kaist.ac.kr/
KAIST_URL = "https://www.kaist.ac.kr/kr/"
APRIL_URL = "https://april.kaist.ac.kr/"


def _resolve_active_checkpoint() -> tuple[Path, str]:
    """Return (path, release_id) for the currently active ML release.

    Reads `models/latest.json` first — that's where the fine-tune
    pipeline writes the newest promoted checkpoint. Falls back to the
    bundled baseline so the app keeps working out of the box.
    """
    import json as _json
    if ML_LATEST_POINTER.exists():
        try:
            data = _json.loads(ML_LATEST_POINTER.read_text(encoding="utf-8"))
            rel_path = str(data.get("path", "")).strip()
            release_id = str(data.get("release_id", "baseline")).strip() or "baseline"
            if rel_path:
                candidate = (ROOT / rel_path).resolve()
                if candidate.exists():
                    return candidate, release_id
        except Exception:
            pass
    return ML_FALLBACK_PTH, "baseline"


ML_DEFAULT_PTH, ML_RELEASE_ID = _resolve_active_checkpoint()

st.set_page_config(
    page_title="OAS Spectrum Studio",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────


def html(body: str) -> None:
    """Inject raw HTML through st.markdown after stripping common indent.

    Streamlit's markdown parser treats 4+ space indents as code blocks, so any
    HTML pasted from indented Python source needs to be dedented first.
    """
    st.markdown(textwrap.dedent(body), unsafe_allow_html=True)


def _encode_image_b64(path: Path) -> str:
    if not path.exists():
        return ""
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _resolve_logo_data_uri(stem: str) -> str:
    """Return a data: URI for assets/<stem>.png|.svg, or '' if neither exists.

    Prefers a raster .png (real institutional logo) over a bundled .svg so
    dropping in an official file just works.
    """
    for ext, mime in ((".png", "image/png"), (".svg", "image/svg+xml")):
        candidate = ASSETS_DIR / f"{stem}{ext}"
        b64 = _encode_image_b64(candidate)
        if b64:
            return f"data:{mime};base64,{b64}"
    return ""


KAIST_LOGO_URI = _resolve_logo_data_uri("kaist_logo")
APRIL_LOGO_URI = _resolve_logo_data_uri("april_logo")


# ────────────────────────────────────────────────────────────────────────────
# Styles
# ────────────────────────────────────────────────────────────────────────────


def inject_styles() -> None:
    html("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500&display=swap');

    :root {
        --primary: #6366f1;
        --primary-dark: #4f46e5;
        --accent: #f97316;
        --ink: #0f172a;
        --muted: #64748b;
        --soft: #f1f5f9;
        --border: rgba(15, 23, 42, 0.08);
        --border-strong: rgba(15, 23, 42, 0.14);
        --shadow: 0 1px 2px rgba(15,23,42,.04), 0 8px 24px rgba(15,23,42,.06);
        --shadow-lg: 0 4px 12px rgba(15,23,42,.06), 0 24px 48px rgba(15,23,42,.08);
    }

    /* Body-level font — do NOT cover icon spans */
    html, body, .stApp { font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif; }

    .stApp {
        background:
            radial-gradient(1200px 600px at 8% -10%, rgba(99,102,241,.10), transparent 60%),
            radial-gradient(900px 500px at 100% 0%, rgba(249,115,22,.08), transparent 60%),
            linear-gradient(180deg, #fafafa 0%, #f5f7fb 100%);
    }
    header[data-testid="stHeader"] { background: transparent; }
    [data-testid="stToolbar"] { display: none; }

    .block-container {
        padding-top: 1.4rem;
        padding-bottom: 2rem;
        padding-left: 1.6rem;
        padding-right: 1.6rem;
        max-width: 1480px;
    }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
        border-right: 1px solid var(--border);
    }

    /* Hero */
    /* Hero — refined deep-indigo gradient (less candy, more "lab report") */
    .hero {
        background:
            radial-gradient(900px 400px at 20% 20%, rgba(255,255,255,.10), transparent 60%),
            linear-gradient(135deg, #1e1b4b 0%, #3b2596 38%, #6d28d9 72%, #a21caf 100%);
        border-radius: 22px;
        padding: 1.55rem 1.85rem;
        margin-bottom: 1.05rem;
        box-shadow:
            0 1px 2px rgba(30,27,75,.18),
            0 14px 40px rgba(76, 29, 149, 0.28),
            inset 0 1px 0 rgba(255,255,255,.08);
        position: relative;
        overflow: hidden;
        display: flex;
        align-items: center;
        gap: 1.5rem;
    }
    .hero::before {
        content: "";
        position: absolute; right: -100px; top: -100px;
        width: 320px; height: 320px;
        background: radial-gradient(circle, rgba(255,255,255,.22), transparent 70%);
        filter: blur(10px);
        pointer-events: none;
    }
    .hero::after {
        /* subtle dot pattern for "scientific" texture */
        content: "";
        position: absolute; inset: 0;
        background-image: radial-gradient(rgba(255,255,255,0.08) 1px, transparent 1px);
        background-size: 16px 16px;
        opacity: 0.4;
        pointer-events: none;
    }
    .hero-text { flex: 1.2; min-width: 280px; position: relative; z-index: 1; }
    .hero-pill {
        display: inline-flex;
        align-items: center;
        gap: .4rem;
        background: rgba(255,255,255,0.12);
        border: 1px solid rgba(255,255,255,0.28);
        border-radius: 999px;
        padding: 4px 12px;
        font-family: 'JetBrains Mono', ui-monospace, monospace;
        font-size: 0.7rem;
        font-weight: 600;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: rgba(255,255,255,0.92);
        margin-bottom: 0.55rem;
        backdrop-filter: blur(6px);
    }
    .hero-pill::before {
        content: "";
        width: 6px; height: 6px; border-radius: 50%;
        background: #34d399;
        box-shadow: 0 0 8px rgba(52,211,153,0.7);
        flex-shrink: 0;
    }
    .hero-text h1 {
        font-size: 1.72rem !important;
        font-weight: 800 !important;
        margin: 0 0 0.3rem 0 !important;
        color: white !important;
        letter-spacing: -0.018em;
        line-height: 1.15;
        text-shadow: 0 1px 0 rgba(0,0,0,.08);
    }
    .hero-text p {
        margin: 0 !important;
        opacity: 0.94;
        font-size: 0.95rem;
        font-weight: 500;
        color: rgba(255,255,255,0.92) !important;
        max-width: 58ch;
        line-height: 1.55;
    }
    .hero-image {
        flex: 1;
        max-width: 400px;
        position: relative;
        z-index: 1;
    }
    .hero-image img {
        width: 100%;
        height: auto;
        border-radius: 14px;
        background: rgba(255,255,255,0.98);
        padding: 8px;
        box-shadow:
            0 6px 20px rgba(15,23,42,.22),
            0 0 0 1px rgba(255,255,255,.4);
    }
    @media (max-width: 880px) {
        .hero { flex-direction: column; align-items: stretch; }
        .hero-image { max-width: 100%; }
    }

    /* Cards — native container as a paper-grade card with top gradient accent */
    [data-testid="stVerticalBlockBorderWrapper"] {
        background: white;
        border: 1px solid var(--border) !important;
        border-radius: 16px !important;
        padding: 1.2rem 1.35rem !important;
        box-shadow: var(--shadow);
        margin-bottom: 0.9rem;
        position: relative;
        transition: transform .15s ease, box-shadow .25s ease;
        overflow: hidden;
    }
    [data-testid="stVerticalBlockBorderWrapper"]::before {
        content: "";
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 3px;
        background: linear-gradient(90deg, #6366f1 0%, #8b5cf6 50%, #ec4899 100%);
        opacity: 0;
        transition: opacity .25s ease;
    }
    [data-testid="stVerticalBlockBorderWrapper"]:hover::before {
        opacity: 0.85;
    }
    [data-testid="stVerticalBlockBorderWrapper"]:hover {
        box-shadow: var(--shadow-lg);
    }

    /* Step header inside cards */
    .step-head { display: flex; align-items: center; gap: .65rem; margin: 0 0 1rem 0; }
    .step-num {
        width: 30px; height: 30px; border-radius: 9px;
        background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
        color: white;
        display: inline-flex; align-items: center; justify-content: center;
        font-weight: 800; font-size: .9rem;
        box-shadow: 0 1px 3px rgba(79,70,229,.30), 0 4px 10px rgba(79,70,229,.18);
    }
    .step-title {
        font-weight: 700; font-size: 1.05rem;
        color: var(--ink);
        letter-spacing: -0.008em;
    }

    /* Metric cards — premium look, larger numbers, accent stripe */
    [data-testid="stMetric"] {
        background: white;
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: .85rem 1rem;
        box-shadow: var(--shadow);
        position: relative;
        overflow: hidden;
    }
    [data-testid="stMetric"]::before {
        content: "";
        position: absolute; top: 0; left: 0; bottom: 0;
        width: 3px;
        background: linear-gradient(180deg, #6366f1 0%, #a855f7 100%);
        opacity: 0.7;
    }
    [data-testid="stMetricLabel"] {
        font-family: 'JetBrains Mono', ui-monospace, monospace !important;
        font-weight: 600 !important;
        font-size: .72rem !important;
        color: var(--muted) !important;
        text-transform: uppercase;
        letter-spacing: 0.06em;
    }
    [data-testid="stMetricValue"] {
        font-family: 'JetBrains Mono', ui-monospace, monospace !important;
        font-weight: 700 !important;
        font-size: 1.32rem !important;
        color: var(--ink) !important;
        letter-spacing: -0.01em;
    }

    /* Tabs — sophisticated selected state */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
        background: white;
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 5px;
        margin-bottom: .85rem;
        box-shadow: var(--shadow);
    }
    .stTabs [data-baseweb="tab"] {
        background: transparent;
        border-radius: 8px !important;
        padding: 0.55rem 1rem !important;
        font-weight: 600 !important;
        color: var(--muted) !important;
        border: none !important;
        transition: background .15s ease, color .15s ease;
    }
    .stTabs [data-baseweb="tab"]:hover {
        background: rgba(99,102,241,.06);
        color: var(--ink) !important;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%) !important;
        box-shadow: 0 1px 2px rgba(15,23,42,.18), 0 4px 10px rgba(15,23,42,.12);
    }
    .stTabs [aria-selected="true"] * { color: white !important; }

    /* Primary button — premium gradient with glow on hover */
    .stButton > button,
    .stButton > button > div,
    .stButton > button p {
        color: white !important;
    }
    .stButton > button {
        background: linear-gradient(135deg, #1e1b4b 0%, #4f46e5 60%, #7c3aed 100%) !important;
        border: none !important;
        border-radius: 11px !important;
        font-weight: 700 !important;
        padding: 0.62rem 1.1rem !important;
        letter-spacing: 0.005em;
        transition: transform .12s ease, box-shadow .2s ease, filter .15s ease;
        box-shadow:
            0 1px 2px rgba(30,27,75,.20),
            0 4px 14px rgba(79,70,229,.22);
    }
    .stButton > button:hover {
        transform: translateY(-1px);
        filter: brightness(1.06);
        box-shadow:
            0 2px 6px rgba(30,27,75,.24),
            0 14px 32px rgba(79,70,229,.30);
    }
    .stButton > button[kind="secondary"],
    .stButton > button[kind="secondary"] > div,
    .stButton > button[kind="secondary"] p {
        background: white !important;
        color: var(--ink) !important;
        border: 1px solid var(--border-strong) !important;
        box-shadow: var(--shadow) !important;
    }
    .stDownloadButton > button,
    .stDownloadButton > button > div,
    .stDownloadButton > button p {
        background: white !important;
        color: var(--ink) !important;
        border: 1px solid var(--border-strong) !important;
        border-radius: 11px !important;
        font-weight: 600 !important;
        padding: 0.55rem 1rem !important;
        transition: border-color .15s ease, box-shadow .15s ease, transform .12s ease;
    }
    .stDownloadButton > button:hover {
        border-color: var(--primary) !important;
        box-shadow: 0 4px 14px rgba(99,102,241,.18);
        transform: translateY(-1px);
    }

    /* File uploader — premium dropzone */
    [data-testid="stFileUploader"] section {
        background: linear-gradient(180deg, #fbfaff 0%, #f5f3ff 100%);
        border: 1.5px dashed rgba(99,102,241,.30) !important;
        border-radius: 14px;
        transition: background .2s ease, border-color .2s ease, box-shadow .2s ease;
    }
    [data-testid="stFileUploader"] section:hover {
        background: linear-gradient(180deg, #f5f3ff 0%, #ede9fe 100%);
        border-color: rgba(99,102,241,.60) !important;
        box-shadow: inset 0 0 0 1px rgba(99,102,241,.12);
    }

    /* Number input */
    [data-testid="stNumberInput"] input {
        border-radius: 10px !important;
        border: 1px solid var(--border-strong) !important;
        font-family: 'JetBrains Mono', monospace !important;
        font-weight: 600;
    }

    /* Dataframe */
    [data-testid="stDataFrame"] {
        border-radius: 12px;
        overflow: hidden;
        border: 1px solid var(--border);
        box-shadow: var(--shadow);
    }

    /* Section chip */
    .chip-row { display: flex; gap: .4rem; flex-wrap: wrap; margin-top: .35rem; }
    .chip {
        font-size: 0.72rem; font-weight: 600;
        background: var(--soft); color: var(--muted);
        border: 1px solid var(--border);
        border-radius: 999px; padding: 3px 10px;
    }
    .chip-accent { background: rgba(99,102,241,.10); color: var(--primary-dark); border-color: rgba(99,102,241,.25); }

    /* ML-only consent card (banner that sits above the Run button) */
    .consent-card {
        background: linear-gradient(135deg, #f5f3ff 0%, #fdf4ff 60%, #fef3c7 100%);
        border: 1px solid rgba(168, 85, 247, 0.22);
        border-radius: 14px;
        padding: 0.85rem 1rem;
        margin: .55rem 0 .65rem 0;
        box-shadow: 0 1px 2px rgba(168,85,247,.05), 0 8px 20px rgba(168,85,247,.07);
    }
    .consent-card-title {
        display: flex; align-items: center; gap: .5rem;
        font-weight: 700; font-size: .98rem; color: #4c1d95;
        margin-bottom: .25rem;
    }
    .consent-icon { font-size: 1.05rem; line-height: 1; }
    .consent-card-body {
        font-size: 0.85rem; line-height: 1.5;
        color: #4c1d95; opacity: 0.88;
    }

    .consent-note {
        background: linear-gradient(180deg, #f5f3ff 0%, #fdf4ff 100%);
        border: 1px solid rgba(168,85,247,.18);
        color: #4c1d95;
        border-radius: 12px;
        padding: .65rem .85rem;
        font-size: 0.85rem;
        margin-top: .55rem;
        line-height: 1.45;
    }
    .consent-note strong { color: #312e81; }

    /* Sidebar brand + status panel */
    .sidebar-brand { margin: 0 0 0.3rem 0; }
    .brand-mark {
        display: flex; align-items: center; gap: .55rem;
        font-weight: 800; font-size: 1.22rem; color: var(--ink);
        letter-spacing: -0.018em;
    }
    .brand-logo {
        display: inline-flex; align-items: center; justify-content: center;
        width: 30px; height: 30px; border-radius: 9px;
        background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
        color: white; font-size: 1.05rem;
        box-shadow: 0 1px 3px rgba(79,70,229,.30), 0 4px 10px rgba(79,70,229,.18);
        flex-shrink: 0;
    }
    .brand-name {
        background: linear-gradient(90deg, #1e1b4b 0%, #6d28d9 100%);
        -webkit-background-clip: text; background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .brand-tagline {
        color: var(--muted); font-size: .78rem; font-weight: 500;
        margin: .25rem 0 0 0;
    }
    .brand-version {
        display: inline-block;
        font-family: 'JetBrains Mono', ui-monospace, monospace;
        font-size: 0.62rem;
        color: var(--primary-dark);
        background: rgba(99,102,241,.10);
        border: 1px solid rgba(99,102,241,.22);
        border-radius: 999px;
        padding: 1px 7px;
        letter-spacing: 0.04em;
        margin-left: auto;        /* push to the right within .brand-mark */
        align-self: center;
        line-height: 1.5;
    }

    .sidebar-status {
        margin: .25rem 0 .75rem 0;
        padding: .55rem .65rem;
        border: 1px solid var(--border);
        border-radius: 11px;
        background: rgba(248, 250, 252, 0.65);
    }
    .status-row {
        display: flex; align-items: flex-start; gap: .5rem;
        padding: .25rem 0;
    }
    .status-dot {
        width: 8px; height: 8px; border-radius: 50%;
        margin-top: 5px; flex-shrink: 0;
    }
    .status-dot.ok {
        background: #22c55e;
        box-shadow: 0 0 6px rgba(34,197,94,.55);
    }
    .status-dot.warn {
        background: #f97316;
        box-shadow: 0 0 6px rgba(249,115,22,.55);
    }
    .status-text { flex: 1; min-width: 0; }
    .status-label {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.66rem;
        color: var(--muted);
        text-transform: uppercase;
        letter-spacing: 0.06em;
        font-weight: 600;
    }
    .status-value {
        font-size: 0.78rem;
        color: var(--ink);
        font-weight: 600;
        word-break: break-all;
    }

    .sidebar-footer {
        margin-top: 1rem;
        padding-top: .1rem;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.78rem;
        color: var(--muted);
        opacity: 0.85;
        text-align: center;
    }
    .sidebar-footer a {
        color: var(--primary-dark);
        text-decoration: none;
        font-weight: 600;
    }
    .sidebar-footer a:hover { text-decoration: underline; }

    /* Partner logos (KAIST · APRIL Lab) — small, linked, neutral chips */
    .partner-logos {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 0.9rem;
        flex-wrap: wrap;
        margin: 0.2rem 0 0.4rem 0;
    }
    .partner-logos a {
        display: inline-flex;
        align-items: center;
        opacity: 0.92;
        transition: opacity .15s ease, transform .15s ease;
    }
    .partner-logos a:hover { opacity: 1; transform: translateY(-1px); }
    .partner-logos img {
        height: 34px;
        width: auto;
        display: block;
    }
    /* Text fallback when no logo file is present */
    .partner-logo-text {
        font-family: 'Inter', system-ui, sans-serif;
        font-weight: 800;
        font-size: 0.72rem;
        letter-spacing: 0.04em;
        color: var(--ink);
        background: white;
        border: 1px solid var(--border-strong);
        border-radius: 8px;
        padding: 5px 10px;
        line-height: 1.1;
        text-decoration: none;
    }
    .partner-logo-text small {
        display: block;
        font-size: 0.58rem;
        font-weight: 600;
        color: var(--muted);
        letter-spacing: 0.08em;
    }

    /* Plotly chart card */
    [data-testid="stPlotlyChart"] {
        background: white;
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 0.5rem;
        box-shadow: var(--shadow);
    }

    /* ── Sidebar layout + bottom-pin + screencast polish (modern) ─── */

    /* Sidebar becomes the positioning context for the absolutely-pinned
       footer below. No internal scroll — the widget stack lives in the
       reserved region above the footer (see padding-bottom). */
    section[data-testid="stSidebar"] {
        position: relative !important;
    }
    section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
        height: 100vh !important;
        max-height: 100vh !important;
        overflow: hidden !important;
        padding-top: 0 !important;
        padding-bottom: 0 !important;
    }
    /* Collapse the «« header band entirely — we never collapse the
       sidebar during the demo, and removing it frees ~30 px for the
       widget stack below. */
    section[data-testid="stSidebar"] [data-testid="stSidebarHeader"] {
        padding: 0 !important;
        min-height: 0 !important;
        height: 0 !important;
        overflow: hidden !important;
    }
    /* The padding-bottom here reserves space for the absolutely-positioned
       footer (≈ 120 px covers OAS Studio · APRIL Lab · PI · Dev block).
       padding-top pushes the brand/mode/expander stack downward. */
    section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
        height: 100% !important;
        max-height: 100% !important;
        overflow: hidden !important;
        padding-top: 1.5rem !important;
        padding-bottom: 120px !important;
    }
    section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] [data-testid="stVerticalBlock"] {
        display: flex !important;
        flex-direction: column !important;
        height: 100% !important;
        max-height: 100% !important;
        min-height: 0 !important;
        overflow: hidden !important;
        gap: 1.3rem !important;
    }
    /* Footer wrapper — ONLY the outer stElementContainer becomes absolute.
       The inner wrappers stay in normal flow so the text-align:center on
       .sidebar-footer actually centers the credits inside the full
       sidebar width. */
    section[data-testid="stSidebar"] [data-testid="stElementContainer"]:has(.sidebar-footer) {
        position: absolute !important;
        bottom: 2.75rem !important;
        left: 0 !important;
        right: 0 !important;
        width: 100% !important;
        margin: 0 !important;
        padding: 0 0.75rem !important;
        z-index: 5 !important;
    }
    section[data-testid="stSidebar"] [data-testid="stElementContainer"]:has(.sidebar-footer) [data-testid="stMarkdownContainer"] {
        width: 100% !important;
    }
    .sidebar-footer {
        display: block !important;
        width: 100% !important;
    }

    /* Soft, modern separator — fades out at both edges, replaces the
       solid hr line that read as harsh against the surrounding widgets. */
    section[data-testid="stSidebar"] hr {
        border: none !important;
        height: 1px !important;
        background: linear-gradient(90deg,
            transparent 0%,
            rgba(15,23,42,0.10) 18%,
            rgba(15,23,42,0.10) 82%,
            transparent 100%) !important;
        margin: 1.2rem 0 !important;
        opacity: 1 !important;
    }

    /* Strip the default 1px border around the Advanced expander card so
       it reads as part of the sidebar flow rather than a separate panel. */
    section[data-testid="stSidebar"] [data-testid="stExpander"],
    section[data-testid="stSidebar"] [data-testid="stExpander"] details,
    section[data-testid="stSidebar"] [data-testid="stExpander"] summary,
    section[data-testid="stSidebar"] [data-testid="stExpander"] [data-testid="stExpanderToggle"] {
        border: none !important;
        box-shadow: none !important;
        background: transparent !important;
    }
    /* Slightly tighter rhythm between the four sliders inside the
       expander — keeps Streamlit's native slider look but recovers
       enough vertical space that everything still fits. */
    section[data-testid="stSidebar"] [data-testid="stExpander"] [data-testid="stSlider"] {
        margin-bottom: 0.3rem !important;
    }
    section[data-testid="stSidebar"] [data-testid="stExpander"] [data-testid="stCaptionContainer"] {
        margin-bottom: 0.45rem !important;
    }
    /* Fallback: if a user's display is short enough that the expander
       still won't fit, scroll inside the expander only — the rest of
       the sidebar stays untouched (no scrollbar on the sidebar itself). */
    section[data-testid="stSidebar"] [data-testid="stExpander"] [data-testid="stExpanderDetails"],
    section[data-testid="stSidebar"] [data-testid="stExpander"] [data-testid="stExpanderContent"],
    section[data-testid="stSidebar"] [data-testid="stExpander"] [role="region"] {
        max-height: calc(100vh - 380px) !important;
        overflow-y: auto !important;
        overflow-x: hidden !important;
    }

    /* ML / cross-sections status box — modern spacing */
    .sidebar-status {
        margin: 0.35rem 0 !important;
        padding: 0.55rem 0.7rem !important;
    }
    .status-row { padding: 0.18rem 0 !important; }

    /* Method-picker radio — taller hit zones for clearer 1080p screencasts */
    .stRadio > div[role="radiogroup"] {
        gap: 0.4rem;
        flex-wrap: wrap;
    }
    .stRadio > div[role="radiogroup"] > label {
        padding: 0.3rem 0.7rem;
        border-radius: 9px;
        transition: background .15s ease;
    }
    .stRadio > div[role="radiogroup"] > label:hover {
        background: rgba(99,102,241,.06);
    }

    /* Consent banner — slightly stronger shadow so the click target reads
       at video distance during the Scene-5 pause */
    .consent-card {
        border-width: 1.5px;
        box-shadow:
            0 1px 2px rgba(168,85,247,.08),
            0 10px 24px rgba(168,85,247,.10);
    }
    .consent-card-title { font-size: 1.0rem; }

    /* Alert (success / info / warning) — premium padding + shadow */
    [data-testid="stAlert"] {
        border-radius: 12px !important;
        padding: 0.85rem 1rem !important;
        box-shadow:
            0 1px 2px rgba(15,23,42,.04),
            0 8px 24px rgba(15,23,42,.06) !important;
    }
    </style>
    """)


# ────────────────────────────────────────────────────────────────────────────
# Continual-learning submission config
# ────────────────────────────────────────────────────────────────────────────


def _get_cl_endpoint() -> tuple[str, str]:
    """Return (endpoint_url, anon_key) from Streamlit secrets, or ('','')."""
    try:
        cl = st.secrets.get("cl", {})
    except StreamlitSecretNotFoundError:
        cl = {}
    return (str(cl.get("endpoint", "")).strip(), str(cl.get("anon_key", "")).strip())


def _current_username() -> str:
    """Best-effort identifier: authenticated username if login is on, else 'anonymous'."""
    return str(st.session_state.get("username") or "anonymous")


def _fit_config_dict(config: FitConfig) -> dict:
    """FitConfig → plain dict stored alongside each submission (schema v2)."""
    return {
        "od_clip_threshold": float(config.od_clip_threshold),
        "od_avg_coeff": float(config.od_avg_coeff),
        "min_fit_fraction": float(config.min_fit_fraction),
        "max_repeat": int(config.max_repeat),
        "no_o3_rule": str(config.no_o3_rule),
        "no_o3_ratio": float(config.no_o3_ratio),
        "no_o3_density_threshold": float(config.no_o3_density_threshold),
        "align_no_bands": bool(config.align_no_bands),
        "no_fwhm_mode": str(config.no_fwhm_mode),
        "no_fwhm_delta": float(config.no_fwhm_delta),
        "no_peak_emphasis": float(config.no_peak_emphasis),
        "no_hot_band": bool(config.no_hot_band),
        "o3_tail_fit": bool(config.o3_tail_fit),
    }


def auto_save_submission(
    *,
    path_length_cm: float,
    reference_file: str,
    measured_file: str,
    wavelengths,
    measured,
    reconstructed,
    species,
    number_densities,
    metrics: dict,
    fit_config: dict,
    raw_reference: tuple,   # (wavelengths, intensities)
    raw_measured: tuple,    # (wavelengths, intensities)
    per_species_od=None,    # (n_points, n_species) aligned to wavelengths
) -> tuple[bool, str]:
    """Best-effort auto-save of one analysis (raw inputs + results) to the
    continual-learning corpus.

    Consent is mandatory to run (see render_consent_block), so every completed
    analysis is contributed automatically. Returns (ok, message). Never raises —
    a failed upload must not invalidate the analysis the user just ran.
    """
    endpoint, anon_key = _get_cl_endpoint()
    if not endpoint or not anon_key:
        return (False, "endpoint not configured for this deployment")
    try:
        payload = build_submission_payload(
            method="linear_regression",
            path_length_cm=float(path_length_cm),
            user_id=_current_username(),
            reference_file=str(reference_file),
            measured_file=str(measured_file),
            wavelengths=wavelengths,
            measured=measured,
            reconstructed=reconstructed,
            species=species,
            number_densities=number_densities,
            metrics=metrics,
            fit_config=fit_config,
            selected_method="linear_regression",
            raw_reference=raw_reference,
            raw_measured=raw_measured,
            per_species_od=per_species_od,
        )
        submission_id = submit_to_global_model(payload, endpoint=endpoint, anon_key=anon_key)
        return (True, str(submission_id))
    except Exception as exc:                                     # noqa: BLE001
        return (False, str(exc))


def _auto_save_timeseries(
    *,
    ts_payload: dict,
    file_items: list[tuple[str, bytes]],
    path_length_cm: float,
    config: FitConfig,
) -> tuple:
    """Auto-save every frame of a time-series run (raw + results), best-effort.

    Returns a status tuple:
      ("unconfigured",)                — no submission endpoint on this deploy
      ("done", n_ok, n_fail, n_total)  — after attempting all frames
    """
    endpoint, anon_key = _get_cl_endpoint()
    if not endpoint or not anon_key:
        return ("unconfigured",)

    # Linear regression is the sole engine; only linear frames carry a
    # `.regression`. Guard defensively in case that ever changes.
    if ts_payload.get("kind") != "linear":
        return ("unconfigured",)

    from oas_web.analysis import sort_time_series_files_by_name

    bytes_by_name = {name: data for name, data in file_items}
    ref_name, ref_bytes = sort_time_series_files_by_name(file_items)[0]
    raw_ref = load_spectrum(ref_bytes)
    raw_ref_xy = (raw_ref.wavelengths, raw_ref.values)

    labels = ts_payload["labels"]
    singles = ts_payload["single_results"]
    fit_cfg = _fit_config_dict(config)

    n_ok = 0
    n_fail = 0
    total = len(labels)
    save_prog = st.progress(0.0, text="Auto-saving frames to the corpus…")
    for i, (label, s) in enumerate(zip(labels, singles), start=1):
        try:
            raw_meas = load_spectrum(bytes_by_name[label])
            ok, _ = auto_save_submission(
                path_length_cm=path_length_cm,
                reference_file=ref_name,
                measured_file=label,
                wavelengths=s.wavelengths,
                measured=s.measured_od,
                reconstructed=s.regression.reconstructed,
                species=list(s.regression.species),
                number_densities=s.regression.number_densities,
                metrics=dict(s.regression.metrics),
                fit_config=fit_cfg,
                raw_reference=raw_ref_xy,
                raw_measured=(raw_meas.wavelengths, raw_meas.values),
                per_species_od=s.regression.per_species_od,
            )
            n_ok += int(ok)
            n_fail += int(not ok)
        except Exception:                                        # noqa: BLE001
            n_fail += 1
        save_prog.progress(i / max(total, 1),
                           text=f"Auto-saving frames to the corpus… {i}/{total}")
    save_prog.empty()
    return ("done", n_ok, n_fail, total)


def render_submit_to_global_model(
    *,
    method: str,                                    # "linear_regression" | "machine_learning"
    path_length_cm: float,
    reference_file: str,
    measured_file: str,
    wavelengths,
    measured,
    reconstructed,
    species,
    number_densities,
    ml_metrics: dict | None,
    button_key: str,
) -> None:
    """Render the Submit-to-global-model button + handle the POST.

    Only call this when the user has already checked the consent box.
    """
    endpoint, anon_key = _get_cl_endpoint()
    sent_key = f"_cl_sent_{button_key}"
    if not endpoint or not anon_key:
        st.caption(
            "🌐 *Submission portal not configured for this deployment.* Use the "
            "CSV download below as a local backup; the operator will collect "
            "submissions manually until the cloud endpoint is wired up."
        )
        return

    if st.session_state.get(sent_key):
        sub_id = st.session_state[sent_key]
        st.success(
            f"✓ Submitted to the global model corpus. Reference id: "
            f"`{sub_id}`. Thank you for contributing!"
        )
        return

    if st.button("📡  Submit this analysis to the global model",
                 type="primary", key=button_key, width="stretch"):
        try:
            payload = build_submission_payload(
                method=method,
                path_length_cm=float(path_length_cm),
                user_id=_current_username(),
                reference_file=reference_file,
                measured_file=measured_file,
                wavelengths=wavelengths,
                measured=measured,
                reconstructed=reconstructed,
                species=species,
                number_densities=number_densities,
                ml_metrics=ml_metrics,
            )
            with st.spinner("Uploading…"):
                submission_id = submit_to_global_model(
                    payload, endpoint=endpoint, anon_key=anon_key
                )
        except SubmissionError as exc:
            st.error(f"Submission failed: {exc}")
            return
        except Exception as exc:                          # noqa: BLE001
            st.error(f"Submission failed unexpectedly: {exc}")
            return

        st.session_state[sent_key] = submission_id
        st.rerun()


# ────────────────────────────────────────────────────────────────────────────
# UI primitives
# ────────────────────────────────────────────────────────────────────────────


def _partner_logos_html() -> str:
    """Two small linked institutional logos (KAIST · APRIL Lab).

    Uses the bundled logo file when present; otherwise renders a text badge
    so the layout never breaks on a fresh checkout.
    """
    def _one(uri: str, url: str, label: str, sub: str) -> str:
        if uri:
            inner = f'<img src="{uri}" alt="{label}" />'
        else:
            inner = f'<span class="partner-logo-text">{label}<small>{sub}</small></span>'
        return (
            f'<a href="{url}" target="_blank" rel="noopener" title="{label}">'
            f'{inner}</a>'
        )

    return (
        '<div class="partner-logos">'
        + _one(KAIST_LOGO_URI, KAIST_URL, "KAIST", "kaist.ac.kr")
        + _one(APRIL_LOGO_URI, APRIL_URL, "APRIL", "LAB · KAIST")
        + "</div>"
    )


def render_partner_logos() -> None:
    html(_partner_logos_html())


def render_hero(title: str, subtitle: str, badge: str) -> None:
    html(f"""
    <div class="hero">
        <div class="hero-text">
            <span class="hero-pill">{badge}</span>
            <h1>{title}</h1>
            <p>{subtitle}</p>
        </div>
    </div>
    """)


def render_step(num: int, title: str) -> None:
    html(f"""
    <div class="step-head">
        <span class="step-num">{num}</span>
        <span class="step-title">{title}</span>
    </div>
    """)


def render_metric_row(metrics: dict[str, float]) -> None:
    cols = st.columns(4)
    cols[0].metric("R²", f"{metrics.get('r2', float('nan')):.4f}")
    cols[1].metric("RMSE", f"{metrics.get('rmse', float('nan')):.3e}")
    cols[2].metric("MAE", f"{metrics.get('mae', float('nan')):.3e}")
    cols[3].metric("MAPE", f"{metrics.get('mape', float('nan')):.2f}%")


def render_chemical_table(species: list[str], values: np.ndarray) -> None:
    detected = [bool(v > 0) for v in values]
    # Number densities routinely exceed JavaScript's Number.MAX_SAFE_INTEGER
    # (~9.007e15 — e.g. NO/NO2 at ~1e16+), and st.column_config.NumberColumn's
    # client-side "%.3e" formatter falls back to the raw integer for those.
    # Pre-format every value in Python and render as text so all rows show a
    # consistent scientific notation regardless of magnitude.
    frame = pd.DataFrame({
        "Species": species,
        "Detected": ["Yes" if d else "No" for d in detected],
        "Number density": [f"{float(v):.3e}" for v in values],
        "Unit": ["molec/cm³"] * len(species),
    })
    st.dataframe(
        frame,
        width="stretch",
        hide_index=True,
        column_config={
            "Species": st.column_config.TextColumn("Species", width="small"),
            "Detected": st.column_config.TextColumn("Detected", width="small"),
            "Number density": st.column_config.TextColumn(
                "Number density (molec/cm³)",
            ),
            "Unit": st.column_config.TextColumn("Unit", width="small"),
        },
    )


def render_diagnostics(
    repeat_count: int | None = None,
    clip_applied: bool | None = None,
    hono_exceed: bool | None = None,
    excluded_species: list[str] | None = None,
    no_align_shifts: dict | None = None,
    no_fwhm_delta: float | None = None,
    no_band_scales: dict | None = None,
    no_hot_ratio: float | None = None,
    o3_wing_scale: float | None = None,
    o3_baseline_level: float | None = None,
) -> None:
    chips = []
    if repeat_count is not None:
        chips.append(f"<span class='chip'>Refit iterations: {repeat_count}</span>")
    if no_align_shifts:
        shift_text = " / ".join(
            f"{band} nm {shift:+.2f}" for band, shift in no_align_shifts.items()
        )
        if no_fwhm_delta is not None:
            shift_text += f" · ΔFWHM {no_fwhm_delta:+.2f} nm"
        chips.append(f"<span class='chip chip-accent'>NO align: {shift_text}</span>")
    if no_band_scales:
        scale_text = " / ".join(
            f"{band} nm ×{scale:.2f}" for band, scale in no_band_scales.items()
        )
        chips.append(f"<span class='chip chip-accent'>NO band scale: {scale_text}</span>")
    if no_hot_ratio is not None:
        chips.append(
            f"<span class='chip chip-accent'>NO hot band (v″=1): "
            f"{no_hot_ratio:.2f}× cold</span>"
        )
    if o3_wing_scale is not None or o3_baseline_level is not None:
        parts = []
        if o3_wing_scale is not None:
            parts.append(f"wing ×{o3_wing_scale:.2f}")
        if o3_baseline_level is not None:
            parts.append(f"baseline {o3_baseline_level:.1e}")
        chips.append(
            f"<span class='chip chip-accent'>O3 tail: {' · '.join(parts)}</span>"
        )
    if clip_applied is not None:
        chips.append(
            f"<span class='chip {'chip-accent' if clip_applied else ''}'>"
            f"Positive clip: {'on' if clip_applied else 'off'}</span>"
        )
    if hono_exceed is not None:
        chips.append(
            f"<span class='chip {'chip-accent' if hono_exceed else ''}'>"
            f"HONO exceed: {'yes' if hono_exceed else 'no'}</span>"
        )
    if excluded_species:
        chips.append(
            f"<span class='chip chip-accent'>Suppressed: {', '.join(excluded_species)}</span>"
        )
    if chips:
        html(f"<div class='chip-row'>{''.join(chips)}</div>")


# ────────────────────────────────────────────────────────────────────────────
# Sidebar
# ────────────────────────────────────────────────────────────────────────────


# The "Result variant" buttons map to an internal O3-mode suppression rule.
# "standard" = original 20x NO/O3 pair (recommended); "off" = keep everything.
_O3_MODE_LABEL: dict[str, str] = {
    "standard": "Auto-clean",
    "off": "Keep all species",
}


def _set_o3_mode(mode: str) -> None:
    """on_click callback for the Result-variant buttons."""
    st.session_state["o3_mode"] = mode


# Factory defaults for the four advanced sliders, keyed by their session_state
# key. The sliders are created WITHOUT a `value=` argument and read straight
# from session_state, so the reset callback only has to write these back —
# which reliably re-syncs both the value AND the slider thumb on rerun.
_FIT_CONFIG_DEFAULTS: dict[str, float | int | bool | str] = {
    "cfg_min_fit_fraction": float(DEFAULT_MIN_FIT_FRACTION),
    "cfg_od_avg_coeff": float(DEFAULT_OD_AVG_COEFF),
    "cfg_od_clip_threshold": float(DEFAULT_OD_CLIP_THRESHOLD),
    "cfg_max_repeat": int(DEFAULT_MAX_REPEAT),
    "cfg_align_no_bands": True,
    "cfg_no_fwhm_mode": "Auto",
    "cfg_no_fwhm_delta": 0.0,
    "cfg_no_peak_emphasis": float(DEFAULT_NO_PEAK_EMPHASIS),
    "cfg_no_hot_band": True,
    "cfg_o3_tail_fit": True,
}


def _seed_fit_config_defaults() -> None:
    """Seed each slider's session_state key once, before the widgets render."""
    for key, value in _FIT_CONFIG_DEFAULTS.items():
        st.session_state.setdefault(key, value)


def _reset_fit_config_defaults() -> None:
    """on_click callback: write the factory defaults back into session_state.

    Runs before the rerun that re-renders the sliders, so the widgets pick up
    the default straight away — and because the value lives in session_state
    (not a `value=` arg) the thumb position updates too.
    """
    for key, value in _FIT_CONFIG_DEFAULTS.items():
        st.session_state[key] = value
    st.session_state["o3_mode"] = "off"


def render_sidebar() -> tuple[str, FitConfig]:
    ml_ready = ML_DEFAULT_PTH.exists()
    with st.sidebar:
        html(f"""
        <div class="sidebar-brand">
            <div class="brand-mark">
                <span class="brand-logo">⚛</span>
                <span class="brand-name">OAS Studio</span>
                <span class="brand-version">v1.3</span>
            </div>
            <div class="brand-tagline">Optical Absorption Spectroscopy</div>
        </div>
        """)

        analysis_type = st.radio(
            "Analysis mode",
            options=["Single OAS analysis", "Time-series OAS analysis"],
            index=0,
            key="sidebar_analysis_type",
        )

        st.markdown("---")
        _seed_fit_config_defaults()
        with st.expander("Advanced fit configuration", expanded=False):
            st.caption(
                "Tune the heuristics that drive O₃ clipping and the iterative refit. "
                "These apply to the linear regression path."
            )
            min_fit_fraction = st.slider(
                "Min fit fraction", 0.0, 0.5, step=0.01,
                key="cfg_min_fit_fraction",
                help="Minimum ratio of fit points to total points. Below this, the fit returns zeros.",
            )
            od_avg_coeff = st.slider(
                "False-positive suppression coefficient", 0.5, 4.0, step=0.05,
                key="cfg_od_avg_coeff",
                help=("In the 350–370 nm window, drop a species column whose reconstructed average "
                      "exceeds this multiple of the total OD average."),
            )
            od_clip_threshold = st.slider(
                "OD clipping threshold", 0.05, 0.6, step=0.01,
                key="cfg_od_clip_threshold",
                help="Noise threshold for O₃ peak based positive clipping.",
            )
            max_repeat = st.slider(
                "Max refit iterations", 0, 10, step=1,
                key="cfg_max_repeat",
            )
            align_no_bands = st.checkbox(
                "NO γ-band auto-alignment",
                key="cfg_align_no_bands",
                help=("Cross-correlate the sharp NO γ(1,0)/γ(0,0) bands (≈215/226 nm) "
                      "against the measured OD and re-align the NO cross section by up "
                      "to ±0.5 nm before fitting. Only engages when a clear NO band is "
                      "present; other species are unaffected."),
            )
            no_fwhm_mode_label = st.selectbox(
                "NO resolution (ΔFWHM) matching",
                options=["Auto", "Manual", "Off"],
                key="cfg_no_fwhm_mode",
                disabled=not align_no_bands,
                help=("Match the NO cross-section resolution to your spectrometer. "
                      "ΔFWHM is relative to the built-in cross section: positive "
                      "broadens (lower-resolution instrument), negative sharpens "
                      "(higher-resolution instrument, regularised deconvolution). "
                      "Auto scans ΔFWHM and keeps 0 when the built-in resolution "
                      "already matches. Runs after the wavelength shift is fixed; "
                      "band area — and the NO density — is preserved."),
            )
            no_fwhm_delta = st.number_input(
                "Manual ΔFWHM vs. built-in σ (nm)",
                min_value=-0.35, max_value=1.5, step=0.05, format="%.2f",
                key="cfg_no_fwhm_delta",
                disabled=(not align_no_bands) or no_fwhm_mode_label != "Manual",
                help=("Used only in Manual mode. Example: your spectrometer resolves "
                      "0.3 nm worse than the built-in σ → enter +0.30."),
            )
            no_peak_emphasis = st.slider(
                "NO peak emphasis", 0.0, 1.0, step=0.1,
                key="cfg_no_peak_emphasis",
                disabled=not align_no_bands,
                help=("After the global fit, re-scale each NO γ band to its own "
                      "amplitude: 0 keeps the global least-squares fit (band tops "
                      "may sit low), 1 matches the measured peak tops exactly "
                      "(band wings may overshoot). The reported NO density follows "
                      "the γ(0,0) 226 nm band."),
            )
            no_hot_band = st.checkbox(
                "NO hot-band (v″=1) component",
                key="cfg_no_hot_band",
                disabled=not align_no_bands,
                help=("In hot plasmas vibrationally excited NO absorbs one X-state "
                      "quantum (≈1876 cm⁻¹) to the red of each cold γ band — "
                      "γ(1,1)≈224 nm, γ(0,1)≈236 nm — which the room-temperature "
                      "cross section misses. When the residual shows these bands, "
                      "fit them with a wavenumber-shifted, broadened copy of the "
                      "NO cross section. Engages only when a clear correlation is "
                      "present; the hot/cold amplitude ratio is shown as a chip."),
            )

            o3_tail_fit = st.checkbox(
                "O3 tail refinement (wing + baseline)",
                key="cfg_o3_tail_fit",
                help=("For O3-dominated spectra (Hartley OD > 1): exclude "
                      "stray-light-saturated points (OD > 2.5) so the flanks "
                      "anchor O3, give the temperature-sensitive Hartley red "
                      "wing (~290-330 nm) its own amplitude, and fit a smooth "
                      "broadband baseline (aerosol scattering / lamp drift) "
                      "above ~300 nm so it no longer masquerades as HONO/NO2. "
                      "Inactive for NOx-mode spectra."),
            )

            o3_mode = st.session_state.setdefault("o3_mode", "off")
            bcols = st.columns(2)
            bcols[0].button(
                "Auto-clean",
                key="o3_btn_standard", width="stretch",
                type=("primary" if o3_mode == "standard" else "secondary"),
                on_click=_set_o3_mode, args=("standard",),
                help="In an O₃-dominated spectrum, automatically drops NO (or O₃) "
                     "when one is a false positive, then re-fits the rest.",
            )
            bcols[1].button(
                "Keep all species",
                key="o3_btn_off", width="stretch",
                type=("primary" if o3_mode == "off" else "secondary"),
                on_click=_set_o3_mode, args=("off",),
                help="Default. Keep every species as fitted — no O₃-mode NO/O₃ removal.",
            )

            # Reset writes the factory defaults back into session_state; the
            # widgets read from session_state, so values + thumbs revert on rerun.
            st.button(
                "↺  Reset to defaults",
                key="cfg_reset_btn",
                type="secondary",
                width="stretch",
                on_click=_reset_fit_config_defaults,
                help="Restore every advanced setting above to its factory default.",
            )

        config = FitConfig(
            od_clip_threshold=float(od_clip_threshold),
            od_avg_coeff=float(od_avg_coeff),
            min_fit_fraction=float(min_fit_fraction),
            max_repeat=int(max_repeat),
            no_o3_rule=("ratio" if o3_mode == "standard" else "off"),
            no_o3_ratio=float(DEFAULT_NO_O3_RATIO),
            no_o3_density_threshold=float(DEFAULT_NO_O3_DENSITY_THRESHOLD),
            align_no_bands=bool(align_no_bands),
            no_fwhm_mode=str(no_fwhm_mode_label).lower(),
            no_fwhm_delta=float(no_fwhm_delta),
            no_peak_emphasis=float(no_peak_emphasis),
            no_hot_band=bool(no_hot_band),
            o3_tail_fit=bool(o3_tail_fit),
        )

        st.markdown("---")
        html(f"""
        <div class="sidebar-status">
            <div class="status-row">
                <span class="status-dot {'ok' if ml_ready else 'warn'}"></span>
                <div class="status-text">
                    <div class="status-label">ML release</div>
                    <div class="status-value">{ML_RELEASE_ID} · <code>{ML_DEFAULT_PTH.name}</code></div>
                </div>
            </div>
            <div class="status-row">
                <span class="status-dot ok"></span>
                <div class="status-text">
                    <div class="status-label">Cross-sections</div>
                    <div class="status-value">Cross_sections_modified · auto-detected</div>
                </div>
            </div>
        </div>
        """)

        # Institutional logos — sit in normal sidebar flow, just above the
        # bottom-pinned credits.
        render_partner_logos()

        # Footer is rendered in its own html() call so it gets a dedicated
        # stElementContainer wrapper. CSS gives that wrapper margin-top:auto
        # inside the flex-column stVerticalBlock, pinning the credits to
        # the viewport bottom.
        html("""
        <div class="sidebar-footer">
            <div><b>OAS Studio · 2026</b></div>
            <div style="margin-top:2px;">
                <a href="https://sites.google.com/view/plasmalab/" target="_blank" rel="noopener">APRIL Lab · KAIST</a>
                &nbsp;·&nbsp;
                <a href="https://github.com/jongchan1999/oas-spectrum-studio" target="_blank" rel="noopener">github ↗</a>
            </div>
            <div style="margin-top:3px; font-size:0.73rem; line-height:1.3;">
                PI <a href="mailto:[email removed]">Sanghoo Park</a><br/>
                Dev <a href="mailto:[email removed]">Jongchan Kim</a>
            </div>
        </div>
        """)

    return analysis_type, config


# ────────────────────────────────────────────────────────────────────────────
# Consent (shared)
# ────────────────────────────────────────────────────────────────────────────


def render_consent_block(key: str) -> bool:
    """Continual-learning consent banner — always shown, and required to run.

    Consent is now mandatory: the analysis raw spectra and the extracted
    results are contributed to the continual-learning corpus so the global
    model keeps improving. The Run button stays disabled until the user
    agrees here.
    """
    html("""
    <div class="consent-card">
        <div class="consent-card-title">
            <span class="consent-icon">🌐</span>
            <span>Help improve the global model</span>
        </div>
        <div class="consent-card-body">
            To run an analysis you agree to contribute it to the
            continual-learning corpus: the raw spectra you upload (reference I₀
            and measured Iₜ) together with the extracted results are stored to
            train the next model release. This consent is required before the
            analysis can run.
        </div>
    </div>
    """)
    return st.checkbox(
        "I agree to contribute this analysis (raw data + results) to the global model",
        value=False,
        key=key,
        help="Required to run. Enables the continual-learning contribution and sample download.",
    )


# ────────────────────────────────────────────────────────────────────────────
# Run helpers (method-agnostic adapters)
# ────────────────────────────────────────────────────────────────────────────


def run_single_analysis(
    method: str,
    ref_bytes: bytes,
    meas_bytes: bytes,
    cross_dir: str,
    path_length_cm: float,
    config: FitConfig,
) -> dict:
    """Return a dict with the canonical result shape, regardless of method."""
    if method == "Linear regression":
        result = run_single_from_intensity_files(
            reference_file=ref_bytes,
            measured_file=meas_bytes,
            cross_section_dir=cross_dir,
            path_length_cm=path_length_cm,
            config=config,
        )
        return {
            "kind": "linear",
            "species": list(result.regression.species),
            "number_densities": np.asarray(result.regression.number_densities, dtype=float),
            "wavelengths": np.asarray(result.wavelengths, dtype=float),
            "measured": np.asarray(result.measured_od, dtype=float),
            "reconstructed": np.asarray(result.regression.reconstructed, dtype=float),
            "per_species_od": np.asarray(result.regression.per_species_od, dtype=float),
            "metrics": dict(result.regression.metrics),
            "diagnostics": {
                "repeat_count": int(result.regression.repeat_count),
                "clip_applied": bool(result.regression.clip_applied),
                "hono_exceed": bool(result.regression.hono_exceed),
                "excluded_species": list(result.regression.excluded_species),
                "no_align_shifts": dict(result.regression.no_align_shifts or {}),
                "no_fwhm_delta": result.regression.no_fwhm_delta,
                "no_band_scales": dict(result.regression.no_band_scales or {}),
                "no_hot_ratio": result.regression.no_hot_ratio,
                "o3_wing_scale": result.regression.o3_wing_scale,
                "o3_baseline_level": result.regression.o3_baseline_level,
            },
            "baseline_od": result.regression.baseline_od,
            "_native": result,
        }

    if not ML_DEFAULT_PTH.exists():
        raise FileNotFoundError("Default ML checkpoint missing at machine_learning/exp_4_epoch_3000.pth")

    ref_spectrum = load_spectrum(ref_bytes)
    meas_spectrum = load_spectrum(meas_bytes)
    optical_depth = compute_optical_depth_from_reference(
        reference_spectrum=ref_spectrum,
        measured_spectrum=meas_spectrum,
        wave_low=210.0,
        wave_high=400.0,
    )
    cross_data = load_cross_sections_from_dir(cross_dir)
    ml_result = run_ml_inference(
        absorbance=optical_depth,
        cross_sections=cross_data,
        model_file=ML_DEFAULT_PTH,
        exp_id=4,
        path_length_cm=path_length_cm,
    )
    return {
        "kind": "ml",
        "species": list(ml_result.species),
        "number_densities": np.asarray(ml_result.number_densities, dtype=float),
        "wavelengths": np.asarray(ml_result.wavelengths, dtype=float),
        "measured": np.asarray(ml_result.measured_absorbance, dtype=float),
        "reconstructed": np.asarray(ml_result.reconstructed, dtype=float),
        "per_species_od": np.asarray(ml_result.per_species_od, dtype=float),
        "metrics": dict(ml_result.metrics),
        "diagnostics": None,
        "_native": ml_result,
    }


def run_timeseries_analysis(
    method: str,
    file_items: list[tuple[str, bytes]],
    cross_dir: str,
    path_length_cm: float,
    config: FitConfig,
    progress_callback=None,
) -> dict:
    if method == "Linear regression":
        result = run_time_series_from_intensity_files(
            files=file_items,
            cross_section_dir=cross_dir,
            path_length_cm=path_length_cm,
            config=config,
            progress_callback=progress_callback,
        )
        return {
            "kind": "linear",
            "summary_table": result.summary_table,
            "labels": list(result.labels),
            "single_results": result.single_results,
            "_native": result,
        }

    if not ML_DEFAULT_PTH.exists():
        raise FileNotFoundError("Default ML checkpoint missing at machine_learning/exp_4_epoch_3000.pth")

    ts_ml = run_time_series_ml_from_intensity_files(
        files=file_items,
        cross_section_dir=cross_dir,
        model_file=ML_DEFAULT_PTH,
        exp_id=4,
        path_length_cm=path_length_cm,
        progress_callback=progress_callback,
    )
    return {
        "kind": "ml",
        "summary_table": ts_ml.summary_table,
        "labels": list(ts_ml.labels),
        "single_results": ts_ml.single_results,
        "_native": ts_ml,
    }


# ────────────────────────────────────────────────────────────────────────────
# Single page
# ────────────────────────────────────────────────────────────────────────────


def _run_single_from_ctx(ctx: dict, cross_dir: str, config: FitConfig,
                         o3_mode: str, method: str, *, do_save: bool) -> None:
    """Run a single analysis from stored input bytes and store the result.

    Used both by the Run button (do_save=True → auto-saves) and by the instant
    Result-variant switch (do_save=False → preview only, not saved).
    """
    try:
        result_payload = run_single_analysis(
            method=method,
            ref_bytes=ctx["ref_bytes"],
            meas_bytes=ctx["meas_bytes"],
            cross_dir=cross_dir,
            path_length_cm=ctx["path_length"],
            config=config,
        )
    except Exception as exc:                                    # noqa: BLE001
        st.error(f"Analysis failed: {exc}")
        st.session_state.pop("single_result", None)
        return

    st.session_state["single_result"] = result_payload
    st.session_state["single_result_mode"] = o3_mode
    st.session_state["single_inputs"] = {
        "ref": ctx["ref_name"], "meas": ctx["meas_name"],
        "path_length": ctx["path_length"], "method": method, "cl_consent": True,
    }
    if do_save:
        st.session_state["single_preview"] = False
        raw_ref = load_spectrum(ctx["ref_bytes"])
        raw_meas = load_spectrum(ctx["meas_bytes"])
        st.session_state["single_save"] = auto_save_submission(
            path_length_cm=ctx["path_length"],
            reference_file=ctx["ref_name"],
            measured_file=ctx["meas_name"],
            wavelengths=result_payload["wavelengths"],
            measured=result_payload["measured"],
            reconstructed=result_payload["reconstructed"],
            species=result_payload["species"],
            number_densities=result_payload["number_densities"],
            metrics=result_payload["metrics"],
            fit_config=_fit_config_dict(config),
            raw_reference=(raw_ref.wavelengths, raw_ref.values),
            raw_measured=(raw_meas.wavelengths, raw_meas.values),
            per_species_od=result_payload["per_species_od"],
        )
    else:
        st.session_state["single_preview"] = True


def render_single_page(selected_cross: str, config: FitConfig) -> None:
    # Linear regression is the sole analysis engine (higher accuracy); the
    # method picker was removed.
    method = "Linear regression"

    render_hero(
        title="Single OAS analysis",
        subtitle=("Upload a single measured spectrum together with the reference I₀. "
                  "The app computes optical depth, estimates concentrations for 8 chemical "
                  "species, and validates the reconstruction."),
        badge="Single OAS",
    )

    # ── Input card ─────────────────────────────────────────────
    with st.container(border=True):
        render_step(1, "Spectrum inputs")

        col_a, col_b = st.columns(2)
        with col_a:
            ref_file = st.file_uploader(
                "Reference spectrum I₀  (lowest-suffix file)",
                type=["txt", "csv", "dat"],
                key="single_ref",
            )
        with col_b:
            meas_file = st.file_uploader(
                "Measured spectrum Iₜ  (target time file)",
                type=["txt", "csv", "dat"],
                key="single_meas",
            )

        path_length_cm = st.number_input(
            "Absorption path length (cm)",
            min_value=0.1, max_value=10000.0, value=15.0, step=0.1, format="%.2f",
            key="single_path_length",
        )

        cl_enabled = render_consent_block(key="single_cl_consent")

        run_clicked = st.button(
            "Run analysis", type="primary", key="single_run_btn",
            width="stretch", disabled=not cl_enabled,
        )
        if not cl_enabled:
            st.caption("☑️  Check the agreement above to enable the analysis.")

        # Always show preview if both files are uploaded — same UI for LR and ML.
        if ref_file and meas_file:
            try:
                ref_spectrum = load_spectrum(ref_file.getvalue())
                meas_spectrum = load_spectrum(meas_file.getvalue())
                ref_on_meas = np.interp(
                    meas_spectrum.wavelengths,
                    ref_spectrum.wavelengths,
                    ref_spectrum.values,
                    left=np.nan, right=np.nan,
                )
                mask = np.isfinite(ref_on_meas) & np.isfinite(meas_spectrum.values)
                st.plotly_chart(
                    make_intensity_preview(
                        wavelengths=meas_spectrum.wavelengths[mask],
                        reference=ref_on_meas[mask],
                        measured=meas_spectrum.values[mask],
                        title="Uploaded spectra preview",
                    ),
                    width="stretch",
                )
            except Exception as exc:
                st.warning(f"Could not preview the spectra: {exc}")

    # ── Run handler ────────────────────────────────────────────
    o3_mode = st.session_state.get("o3_mode", "standard")
    if run_clicked:
        if ref_file is None or meas_file is None:
            st.error("Both I₀ and Iₜ files are required before running.")
        else:
            # Store the raw input bytes so the Result-variant buttons can
            # re-run instantly without a re-upload.
            st.session_state["single_ctx"] = {
                "ref_bytes": ref_file.getvalue(),
                "meas_bytes": meas_file.getvalue(),
                "ref_name": ref_file.name,
                "meas_name": meas_file.name,
                "path_length": float(path_length_cm),
            }
            _run_single_from_ctx(
                st.session_state["single_ctx"], selected_cross, config,
                o3_mode, method, do_save=True,
            )
    else:
        # Instant Result-variant switch: when the user clicked a variant button
        # after a completed analysis, re-run (preview only) with the new mode.
        ctx = st.session_state.get("single_ctx")
        if (ctx is not None and st.session_state.get("single_result") is not None
                and st.session_state.get("single_result_mode") != o3_mode):
            _run_single_from_ctx(ctx, selected_cross, config, o3_mode, method, do_save=False)

    # ── Result card ────────────────────────────────────────────
    result = st.session_state.get("single_result")
    inputs = st.session_state.get("single_inputs", {})
    with st.container(border=True):
        render_step(2, "Results")
        if result is None:
            st.info("📊  Results appear here once an analysis run completes.")
            return

        variant_label = _O3_MODE_LABEL.get(st.session_state.get("single_result_mode", "standard"))
        if st.session_state.get("single_preview"):
            st.info(
                f"👁 Previewing the **{variant_label}** variant (not saved). Press "
                "**Run analysis** to save this result to the corpus."
            )
        elif (save := st.session_state.get("single_save")) is not None:
            ok, msg = save
            if ok:
                st.success(
                    f"💾 Auto-saved the **{variant_label}** result to the global corpus "
                    f"· reference id `{msg}`"
                )
            elif "not configured" in msg:
                st.caption(
                    "💾 Auto-save skipped — submission endpoint not configured for this "
                    "deployment. Results are still downloadable below."
                )
            else:
                st.warning(f"⚠️ Auto-save could not upload (analysis is still valid): {msg}")

        render_metric_row(result["metrics"])

        tab_extract, tab_validate, tab_downloads = st.tabs(
            ["Chemical extraction", "Validation overlay", "Downloads"]
        )

        with tab_extract:
            c1, c2 = st.columns([1.05, 1.0])
            with c1:
                render_chemical_table(result["species"], result["number_densities"])
                if result["diagnostics"]:
                    render_diagnostics(**result["diagnostics"])
            with c2:
                st.plotly_chart(
                    make_species_bar(result["species"], result["number_densities"]),
                    width="stretch",
                )

        with tab_validate:
            per_species_frame = pd.DataFrame({"wavelength": result["wavelengths"]})
            for idx, name in enumerate(result["species"]):
                per_species_frame[name] = result["per_species_od"][:, idx]
            if result.get("baseline_od") is not None:
                per_species_frame["Baseline"] = result["baseline_od"]
            st.plotly_chart(
                make_overlay_figure(
                    wavelengths=result["wavelengths"],
                    measured=result["measured"],
                    reconstructed=result["reconstructed"],
                    species_frame=per_species_frame,
                    title="Measured vs reconstructed OD",
                ),
                width="stretch",
            )
            st.caption(
                "Solid traces: measured vs full reconstruction. "
                "Dashed traces: per-species contribution. Click a legend entry to toggle."
            )

        with tab_downloads:
            recon_frame = prepare_download_frame(
                wavelengths=result["wavelengths"],
                measured=result["measured"],
                reconstructed=result["reconstructed"],
                species=result["species"],
                per_species_od=result["per_species_od"],
            )
            st.download_button(
                "Download reconstruction (CSV)",
                data=recon_frame.to_csv(index=False).encode("utf-8"),
                file_name="oas_reconstruction.csv",
                mime="text/csv",
                width="stretch",
            )
            st.caption(
                "Per-wavelength measured vs reconstructed optical depth plus each "
                "species' contribution. Corpus save status is shown in the banner "
                "above the metrics."
            )


# ────────────────────────────────────────────────────────────────────────────
# Time-series page
# ────────────────────────────────────────────────────────────────────────────


def render_timeseries_page(selected_cross: str, config: FitConfig) -> None:
    # Linear regression is the sole analysis engine (higher accuracy); the
    # method picker was removed.
    method = "Linear regression"

    render_hero(
        title="Time-series OAS analysis",
        subtitle=("Upload a sequence of measured spectra. The file with the lowest numeric "
                  "suffix is treated as I₀, and the rest are processed in order. Observe the "
                  "species trends in real time and download the final summary."),
        badge="Time-series OAS",
    )

    with st.container(border=True):
        render_step(1, "Time-series inputs")

        uploads = st.file_uploader(
            "Upload spectra (I₀ and subsequent timepoints)",
            type=["csv", "txt", "dat"],
            accept_multiple_files=True,
            key="ts_uploads",
        )

        path_length_cm = st.number_input(
            "Absorption path length (cm)",
            min_value=0.1, max_value=10000.0, value=15.0, step=0.1, format="%.2f",
            key="ts_path_length",
        )

        cl_enabled = render_consent_block(key="ts_cl_consent")

        run_clicked = st.button(
            "Run analysis", type="primary", key="ts_run_btn",
            width="stretch", disabled=not cl_enabled,
        )
        if not cl_enabled:
            st.caption("☑️  Check the agreement above to enable the analysis.")

        if uploads:
            st.caption(f"📁 {len(uploads)} files loaded.")

    if run_clicked:
        if not uploads or len(uploads) < 2:
            st.error("Upload at least two files (I₀ + one measurement).")
        else:
            file_items = [(u.name, u.getvalue()) for u in uploads]
            progress = st.progress(0.0, text="Processing time-series…")

            def _on_step(done: int, total: int) -> None:
                ratio = done / max(total, 1)
                progress.progress(ratio, text=f"Processing time-series… {done}/{total}")

            ts_payload_new = None
            try:
                with st.spinner(f"Running {method.lower()} on {len(file_items)} frames…"):
                    ts_payload_new = run_timeseries_analysis(
                        method=method,
                        file_items=file_items,
                        cross_dir=selected_cross,
                        path_length_cm=float(path_length_cm),
                        config=config,
                        progress_callback=_on_step,
                    )
                progress.empty()
                st.session_state["ts_result"] = ts_payload_new
                st.session_state["ts_inputs"] = {
                    "path_length": float(path_length_cm),
                    "method": method,
                    "cl_consent": bool(cl_enabled),
                }
            except Exception as exc:
                progress.empty()
                st.error(f"Time-series analysis failed: {exc}")
                st.session_state.pop("ts_result", None)

            # Auto-save every frame (raw inputs + results) to the corpus.
            # Best-effort and decoupled from the analysis: a failed upload never
            # invalidates the run. Skipped entirely when no endpoint is set.
            if ts_payload_new is not None:
                st.session_state["ts_save"] = _auto_save_timeseries(
                    ts_payload=ts_payload_new,
                    file_items=file_items,
                    path_length_cm=float(path_length_cm),
                    config=config,
                )

    ts_payload = st.session_state.get("ts_result")
    ts_inputs = st.session_state.get("ts_inputs", {})
    with st.container(border=True):
        render_step(2, "Results")
        if ts_payload is None:
            st.info("📈  Run the analysis to see the trend, summary, and per-frame validation.")
            return
        if ts_inputs.get("method") and ts_inputs["method"] != method:
            st.info(f"The current result was produced by *{ts_inputs['method']}*. Re-run to refresh.")

        ts_save = st.session_state.get("ts_save")
        if ts_save is not None:
            if ts_save[0] == "unconfigured":
                st.caption(
                    "💾 Auto-save skipped — submission endpoint not configured for this "
                    "deployment. The summary is still downloadable below."
                )
            elif ts_save[0] == "done":
                _, n_ok, n_fail, total = ts_save
                if n_fail == 0:
                    st.success(f"💾 Auto-saved all {n_ok}/{total} frames (raw + results) to the global corpus.")
                else:
                    st.warning(
                        f"💾 Auto-saved {n_ok}/{total} frames; {n_fail} failed to upload "
                        "(analysis is still valid)."
                    )

        summary_table = ts_payload["summary_table"]
        labels = ts_payload["labels"]
        species_cols = [c for c in summary_table.columns if c != "Time (s)"]
        detected = [sp for sp in species_cols if summary_table[sp].astype(float).abs().sum() > 0]

        if "Time (s)" in summary_table.columns and len(summary_table) > 0:
            time_axis = summary_table["Time (s)"].astype(float)
            duration_s = float(time_axis.max() - time_axis.min())
        else:
            duration_s = 0.0

        mcols = st.columns(4)
        mcols[0].metric("Timepoints", len(summary_table))
        mcols[1].metric("Detected species", f"{len(detected)} / {len(species_cols)}")
        mcols[2].metric("Duration", f"{duration_s:.0f} s")
        mcols[3].metric("Method", method.split()[0])

        tab_trend, tab_summary, tab_validate, tab_downloads = st.tabs(
            ["Trend", "Summary table", "Per-frame validation", "Downloads"]
        )

        with tab_trend:
            st.plotly_chart(make_timeseries_trend(summary_table), width="stretch")
            st.caption("Y-axis is log-scaled. Zero values are hidden by Plotly; this is expected.")

        with tab_summary:
            display_table = summary_table.copy()
            for col in species_cols:
                display_table[col] = display_table[col].map(lambda v: f"{v:.3e}")
            st.dataframe(display_table, width="stretch", hide_index=True, height=380)

        with tab_validate:
            if not labels:
                st.info("No timepoints to validate.")
            else:
                sel = st.selectbox(
                    "Pick a timepoint",
                    options=list(range(len(labels))),
                    format_func=lambda i: labels[i],
                    key=f"ts_validation_sel_{method}",
                )
                if ts_payload["kind"] == "linear":
                    s = ts_payload["single_results"][sel]
                    wavelengths = s.wavelengths
                    measured = s.measured_od
                    reconstructed = s.regression.reconstructed
                    metrics = s.regression.metrics
                    per_species_od = s.regression.per_species_od
                    species = s.regression.species
                    baseline_od = s.regression.baseline_od
                    diag = {
                        "repeat_count": s.regression.repeat_count,
                        "clip_applied": s.regression.clip_applied,
                        "hono_exceed": s.regression.hono_exceed,
                        "excluded_species": s.regression.excluded_species,
                        "no_align_shifts": dict(s.regression.no_align_shifts or {}),
                        "no_fwhm_delta": s.regression.no_fwhm_delta,
                        "no_band_scales": dict(s.regression.no_band_scales or {}),
                        "no_hot_ratio": s.regression.no_hot_ratio,
                        "o3_wing_scale": s.regression.o3_wing_scale,
                        "o3_baseline_level": s.regression.o3_baseline_level,
                    }
                else:
                    m = ts_payload["single_results"][sel]
                    wavelengths = m.wavelengths
                    measured = m.measured_absorbance
                    reconstructed = m.reconstructed
                    metrics = m.metrics
                    per_species_od = m.per_species_od
                    species = m.species
                    baseline_od = None
                    diag = None

                render_metric_row(metrics)
                per_species_frame = pd.DataFrame({"wavelength": wavelengths})
                for idx, name in enumerate(species):
                    per_species_frame[name] = per_species_od[:, idx]
                if baseline_od is not None:
                    per_species_frame["Baseline"] = baseline_od
                st.plotly_chart(
                    make_overlay_figure(
                        wavelengths=wavelengths,
                        measured=measured,
                        reconstructed=reconstructed,
                        species_frame=per_species_frame,
                        title=f"Validation · {labels[sel]}",
                    ),
                    width="stretch",
                )
                if diag:
                    render_diagnostics(**diag)

        with tab_downloads:
            st.download_button(
                "Download summary (CSV)",
                data=summary_table.to_csv(index=False).encode("utf-8"),
                file_name="time_series_oas_summary.csv",
                mime="text/csv",
                width="stretch",
            )
            st.caption(
                "Per-timepoint number densities for every species. All frames "
                "(raw inputs + results) were auto-saved to the global corpus — "
                "see the banner above."
            )


# ────────────────────────────────────────────────────────────────────────────
# Auth
# ────────────────────────────────────────────────────────────────────────────


def require_login_if_enabled() -> None:
    try:
        auth = st.secrets.get("auth", {})
    except StreamlitSecretNotFoundError:
        auth = {}
    if not bool(auth.get("enabled", False)):
        return

    if st.session_state.get("authenticated", False):
        # Sign-out button intentionally hidden — kept off the sidebar so
        # the demo screencast doesn't expose the auth control. To sign
        # out, close the browser tab or clear the session.
        return

    render_hero(
        title="Sign in to OAS Studio",
        subtitle="This deployment is access-controlled. Enter your credentials to continue.",
        badge="Protected access",
    )

    users = auth.get("users", None)
    single_username = str(auth.get("username", "")).strip()
    single_password = str(auth.get("password", ""))

    allowed_users: dict[str, str] = {}
    if users is not None:
        from collections.abc import Mapping
        try:
            if isinstance(users, Mapping):
                allowed_users = {str(u).strip(): str(p) for u, p in users.items()}
            else:
                try:
                    allowed_users = {str(u).strip(): str(p) for u, p in users.items()}  # type: ignore[attr-defined]
                except Exception:
                    allowed_users = {}
        except Exception:
            allowed_users = {}
    if not allowed_users and single_username and single_password:
        allowed_users = {single_username: single_password}
    if not allowed_users:
        st.error("Authentication is enabled, but no credentials are configured in `secrets.toml`.")
        st.stop()

    with st.form("login_form", clear_on_submit=False):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in", type="primary", width="stretch")

    if submitted:
        ok = any(
            hmac.compare_digest(str(username).strip(), au)
            and hmac.compare_digest(str(password), ap)
            for au, ap in allowed_users.items()
        )
        if ok:
            st.session_state["authenticated"] = True
            st.session_state["username"] = str(username).strip()
            st.rerun()
        else:
            st.error("Invalid username or password.")
    st.stop()


# ────────────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────────────


def main() -> None:
    inject_styles()
    require_login_if_enabled()

    analysis_type, config = render_sidebar()

    selected_cross = discover_preferred_cross_section_dir(str(ROOT))
    if selected_cross is None:
        render_hero(
            title="Cross-section data missing",
            subtitle="The expected `Cross_sections_modified` folder with 8 species was not found.",
            badge="Configuration error",
        )
        st.error(
            "Place the following files under `Cross_sections_modified/` and reload:\n\n"
            "- HONO_ordered_cross_section.txt\n"
            "- HONO2_ordered_cross_section.txt\n"
            "- N2O4_ordered_cross_section.txt\n"
            "- N2O5_ordered_cross_section.txt\n"
            "- NO_ordered_cross_section.txt\n"
            "- NO2_ordered_cross_section.txt\n"
            "- NO3_ordered_cross_section.txt\n"
            "- O3_ordered_cross_section.txt"
        )
        return

    if analysis_type == "Single OAS analysis":
        render_single_page(selected_cross=str(selected_cross), config=config)
    else:
        render_timeseries_page(selected_cross=str(selected_cross), config=config)


if __name__ == "__main__":
    main()
