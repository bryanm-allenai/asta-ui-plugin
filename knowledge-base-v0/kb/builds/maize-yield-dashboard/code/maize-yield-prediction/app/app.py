import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import io
import datetime
import re
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles    import getSampleStyleSheet
from reportlab.platypus      import (SimpleDocTemplate, Paragraph,
                                      Spacer, Table, TableStyle)
from reportlab.lib           import colors

import sys
APP_DIR  = Path(__file__).resolve().parent   # .../maize-yield-prediction/app/
ROOT     = APP_DIR.parent                     # .../maize-yield-prediction/
DATA_DIR = ROOT / "outputs" / "predictions"   # explicit constant — avoids repeating path fragments
SRC_DIR  = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

CV_R2_NORM   = 0.355
TEST_R2_NORM = 0.361
N_SAMPLES    = 46_686
N_LOCATIONS  = 38
N_HYBRIDS    = 2_912
N_YEARS      = 5
MODEL_NAME   = "XGBoost"
DATASET      = "G2F 2014-2018"
YIELD_HIGH   = 170
YIELD_MEDIUM = 150

# ── THE KEY FIX: GitHub raw URL as fallback data source ──────
# If the file isn't found locally, we fetch it directly from GitHub.
# Note: GitHub has a 100MB limit on raw file serving. If your .csv.gz
# is larger, you'll need to use Git LFS or an external host like HuggingFace.
GITHUB_RAW_URL = (
    "https://raw.githubusercontent.com/manan348/maize-yield-prediction/"
    "main/maize-yield-prediction/outputs/predictions/all_predictions.csv.gz"
)

st.set_page_config(
    page_title="NeuroCrop - Maize Yield Predictor",
    page_icon="🌽",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:wght@300;600;800&family=Instrument+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
  html, body, [class*="css"] { font-family: 'Instrument Sans', sans-serif; }
  h1, h2, h3 { font-family: 'Fraunces', serif; }
  .kpi { background: #0d2218; border: 1.5px solid #1a4d2e; border-radius: 14px; padding: 18px 16px; text-align: center; transition: all 0.25s ease; cursor: default; }
  .kpi:hover { background: #112b1e; border-color: #22c55e; box-shadow: 0 6px 22px rgba(34,197,94,0.2); transform: translateY(-3px); }
  .kpi .v { font-size: 1.9rem; font-weight: 700; color: #4ade80; font-family: 'Fraunces', serif; }
  .kpi .l { font-size: 0.72rem; color: #86efac; text-transform: uppercase; letter-spacing: 0.07em; margin-top: 4px; font-weight: 500; }
  .info-pill { background: #0a1f12; border-left: 4px solid #22c55e; border-radius: 0 10px 10px 0; padding: 14px 18px; margin: 10px 0; font-size: 0.89rem; color: #d1fae5; line-height: 1.7; }
  .info-pill strong { color: #4ade80; }
  .warn-pill { background: #1a1200; border-left: 4px solid #f59e0b; border-radius: 0 10px 10px 0; padding: 14px 18px; margin: 10px 0; font-size: 0.89rem; color: #fde68a; line-height: 1.7; }
  .compare-card { background: #0d2218; border: 1.5px solid #1a4d2e; border-radius: 14px; padding: 20px; text-align: center; transition: all 0.25s ease; }
  .compare-card:hover { background: #112b1e; border-color: #22c55e; box-shadow: 0 6px 24px rgba(34,197,94,0.2); transform: translateY(-3px); }
  .compare-card .hn { font-family: 'Fraunces', serif; font-size: 1.1rem; color: #a7f3c0; font-weight: 700; }
  .compare-card .yb { font-size: 2.4rem; font-weight: 700; font-family: 'Fraunces', serif; color: #4ade80; }
  .compare-card .yu { font-size: 0.85rem; color: #86efac; font-weight: 500; }
  .about-section { background: #0d2218; border: 1.5px solid #1a4d2e; border-radius: 14px; padding: 24px 28px; margin: 12px 0; transition: all 0.25s ease; }
  .about-section:hover { background: #112b1e; border-color: #22c55e; }
  .about-section h4 { font-family: 'Fraunces', serif; color: #4ade80; margin-bottom: 10px; font-size: 1.05rem; font-weight: 700; }
  .about-section, .about-section p { color: #d1fae5; line-height: 1.75; }
  .about-section strong { color: #a7f3c0; }
  .about-section a { color: #4ade80; font-weight: 600; text-decoration: none; }
  .about-section a:hover { text-decoration: underline; color: #86efac; }
  .stTabs [data-baseweb="tab-list"] { gap: 4px; background: #f0fdf4; border-radius: 10px; padding: 5px; border: 1.5px solid #bbf7d0; }
  .stTabs [data-baseweb="tab"] { border-radius: 8px; padding: 7px 16px; font-weight: 500; font-size: 0.85rem; color: #166534 !important; transition: all 0.2s; }
  .stTabs [data-baseweb="tab"]:hover { background: #dcfce7 !important; }
  .stTabs [aria-selected="true"] { background: #16a34a !important; color: #ffffff !important; box-shadow: 0 2px 8px rgba(22,163,74,0.3); }
</style>
""", unsafe_allow_html=True)


# ── Data loading: local → GitHub raw → demo ──────────────────
@st.cache_data(show_spinner="Loading prediction database…", ttl=3600)
def load_data():
    # DATA_DIR = ROOT/outputs/predictions — defined at module level
    parquet_path = DATA_DIR / "all_predictions.parquet"
    gz_path      = DATA_DIR / "all_predictions.csv.gz"
    csv_path     = DATA_DIR / "all_predictions.csv"

    # 1. Local parquet (fastest on repeat runs)
    if parquet_path.exists():
        return pd.read_parquet(parquet_path)

    # 2. Local .csv.gz
    if gz_path.exists():
        df = pd.read_csv(gz_path)
        try:
            df.to_parquet(parquet_path, index=False)
        except Exception:
            pass
        return df

    # 3. Local plain .csv
    if csv_path.exists():
        return pd.read_csv(csv_path)

    # 4. Fetch directly from GitHub raw URL
    try:
        st.info(
            "📡 **Downloading predictions from GitHub** — takes ~20-40 seconds on first load. "
            "Subsequent loads are instant thanks to caching."
        )
        df = pd.read_csv(GITHUB_RAW_URL, compression="gzip")
        # Try to save locally so next restart is instant
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            df.to_csv(gz_path, index=False, compression="gzip")
        except Exception:
            pass
        return df
    except Exception as e:
        st.warning(
            f"⚠️ **Could not load real predictions** (local or GitHub). Error: `{e}`\n\n"
            "Running in **demo mode** with 500 synthetic rows. "
            "To fix: ensure `outputs/predictions/all_predictions.csv.gz` is in your repo "
            "and accessible via GitHub raw URL, or use Git LFS for large files."
        )

    # 5. Demo fallback — synthetic data so UI still works
    _rng = np.random.default_rng(42)
    _n   = 500
    return pd.DataFrame({
        "Female":   [f"B73-{i%20:03d}" for i in _rng.integers(0, 20, _n)],
        "Male":     [f"Mo17-{i%20:03d}" for i in _rng.integers(0, 20, _n)],
        "Location": [f"Iowa-{i%10}" for i in _rng.integers(0, 10, _n)],
        "Yield":    _rng.normal(160, 20, _n).round(2),
    })


df        = load_data()
females   = sorted(df["Female"].unique().tolist())
males     = sorted(df["Male"].unique().tolist())
locations = sorted(df["Location"].unique().tolist())


# ── Memory-efficient lookup: indexed DataFrame instead of a giant dict ──
# The old dict held ~5.8M entries and consumed ~700MB RAM, crashing Streamlit Cloud.
# A sorted MultiIndex DataFrame uses ~60% less memory and is equally fast via .loc[].
df.columns = [c.strip() for c in df.columns]   # defensive: strip whitespace from headers
_required = {"Female", "Male", "Location", "Yield"}
_missing  = _required - set(df.columns)
if _missing:
    st.error(f"❌ Data file is missing columns: {_missing}. Check your CSV headers.")
    st.stop()

df_indexed = df.set_index(["Female", "Male", "Location"]).sort_index()


def lookup(p1: str, p2: str, loc: str):
    for f, m in [(p1, p2), (p2, p1)]:
        try:
            v = df_indexed.loc[(f, m, loc), "Yield"]
            if hasattr(v, "iloc"):   # handles duplicate entries — take first
                v = v.iloc[0]
            return round(float(v), 2)
        except KeyError:
            continue
    return None


@st.cache_data(show_spinner=False)
def overall_stats():
    return {"mean": df["Yield"].mean(), "std": df["Yield"].std(),
            "min": df["Yield"].min(), "max": df["Yield"].max(), "n": len(df)}


OV = overall_stats()


@st.cache_data(show_spinner=False, ttl=3600)
def build_loc_yields():
    return {loc: df[df["Location"] == loc]["Yield"].values for loc in locations}


LOC_YIELDS = build_loc_yields()


def pct_rank(y: float, loc: str) -> float:
    arr = LOC_YIELDS.get(loc)
    return round(float((arr < y).mean()) * 100, 1) if arr is not None and len(arr) else 0.0


def cat(y: float) -> str:
    if y >= YIELD_HIGH:   return "🟢 High"
    if y >= YIELD_MEDIUM: return "🟡 Medium"
    return "🔴 Low"


def strip_emoji(text: str) -> str:
    """Remove emoji/symbol characters while preserving accented Latin letters."""
    import unicodedata
    return "".join(
        ch for ch in text
        if unicodedata.category(ch) not in {"So", "Sm", "Sk", "Sc", "Cs", "Co", "Cn"}
    ).strip()


@st.cache_data(show_spinner=False, ttl=3600)
def cross_locations(p1: str, p2: str) -> list:
    rows = []
    for loc in locations:
        v = lookup(p1, p2, loc)
        if v is not None:
            rows.append({"Location": loc, "Yield": v})
    return sorted(rows, key=lambda x: x["Yield"], reverse=True)


@st.cache_data(show_spinner=False, ttl=3600)
def location_stats():
    return df.groupby("Location")["Yield"].agg(
        Mean="mean", Std="std", N="count"
    ).reset_index().sort_values("Mean", ascending=False)


@st.cache_data(show_spinner=False, ttl=3600)
def parent_stats(col_name: str):
    ps = df.groupby(col_name)["Yield"].mean()\
           .sort_values(ascending=False).head(20).reset_index()
    ps.columns = [col_name, "Mean Yield"]
    return ps


@st.cache_data(show_spinner="Computing stability metrics…", ttl=3600)
def stability_df():
    g = df.groupby(["Female", "Male"])["Yield"]
    t = g.agg(Mean_Yield="mean", Std_Yield="std", N_Locs="count").reset_index()
    t["CV_pct"]    = (t["Std_Yield"] / t["Mean_Yield"] * 100).round(1)
    t["Hybrid"]    = t["Female"] + " × " + t["Male"]
    t["Stability"] = t["CV_pct"].apply(
        lambda v: "🟢 Stable" if v < 5 else ("🟡 Moderate" if v < 10 else "🔴 Unstable"))
    return t.sort_values("Mean_Yield", ascending=False).reset_index(drop=True)


# ── PDF builder ───────────────────────────────────────────────
def make_pdf(p1, p2, loc, pred, loc_rows, percentile):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter)
    sty = getSampleStyleSheet(); s = []
    s.append(Paragraph("NeuroCrop - Maize Yield Prediction Report", sty["Title"]))
    s.append(Spacer(1, 10))
    s.append(Paragraph(
        f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}  |  "
        f"Model: {MODEL_NAME}  |  Dataset: {DATASET}", sty["Normal"]))
    s.append(Spacer(1, 14))
    s.append(Paragraph("Model Performance", sty["Heading2"]))
    s.append(Paragraph(
        f"CV R2 (honest) = {CV_R2_NORM:.3f}  |  Test R2 = {TEST_R2_NORM:.3f}  |  "
        f"Samples = {N_SAMPLES:,}  |  Locations = {N_LOCATIONS}  |  Years = {N_YEARS}", sty["Normal"]))
    s.append(Spacer(1, 14))
    s.append(Paragraph("Prediction Summary", sty["Heading2"]))
    cs = strip_emoji(cat(pred))
    data = [["Parameter", "Value"], ["Female Parent", p1], ["Male Parent", p2],
            ["Location", loc], ["Predicted Yield", f"{pred} bu/A"],
            ["Percentile", f"Top {100 - percentile:.0f}%"], ["Category", cs]]
    tbl = Table(data, colWidths=[200, 300])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#14532d")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID",       (0, 0), (-1, -1), 1, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0fdf4")]),
    ]))
    s.append(tbl); s.append(Spacer(1, 20))
    if loc_rows:
        s.append(Paragraph("Top Locations", sty["Heading2"]))
        ld = [["Rank", "Location", "Yield (bu/A)", "Category"]]
        for i, r in enumerate(loc_rows[:10], 1):
            ld.append([str(i), r["Location"], str(r["Yield"]), strip_emoji(cat(r["Yield"]))])
        lt = Table(ld, colWidths=[50, 150, 150, 150])
        lt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#14532d")),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID",       (0, 0), (-1, -1), 1, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0fdf4")]),
        ]))
        s.append(lt)
    s.append(Spacer(1, 30))
    s.append(Paragraph(
        f"NeuroCrop - Generative Breeding Platform  |  Abdul Manan  |  {DATASET}", sty["Normal"]))
    doc.build(s); buf.seek(0); return buf


# ══════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════
components.html("""<!DOCTYPE html><html><head>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background:transparent; font-family:'Instrument Sans',sans-serif; }
  @keyframes logoFadeIn { from{opacity:0;transform:translateY(-10px)} to{opacity:1;transform:translateY(0)} }
  @keyframes pulseGlow  { 0%,100%{filter:drop-shadow(0 0 6px rgba(74,222,128,0.5))} 50%{filter:drop-shadow(0 0 18px rgba(74,222,128,0.9))} }
  @keyframes spinDNA    { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
  @keyframes leafSway   { 0%,100%{transform:rotate(-8deg)} 50%{transform:rotate(8deg)} }
  @keyframes counterLS  { 0%,100%{transform:rotate(6deg)} 50%{transform:rotate(-6deg)} }
  @keyframes neuralP    { 0%,100%{stroke-opacity:.2} 50%{stroke-opacity:.9} }
  @keyframes fadeText   { from{opacity:0;transform:translateY(6px)} to{opacity:1;transform:translateY(0)} }
  .hero { background:linear-gradient(135deg,#020f07 0%,#071a0e 35%,#0d3320 70%,#14532d 100%); border-radius:20px; padding:32px 44px 28px; position:relative; overflow:hidden; border:1px solid rgba(74,222,128,0.18); }
  .hero::before { content:""; position:absolute; top:0; right:0; bottom:0; width:50%; background:radial-gradient(ellipse at 85% 50%,rgba(74,222,128,0.10) 0%,transparent 65%); }
  .hero-inner { display:flex; align-items:center; gap:28px; position:relative; z-index:1; }
  .logo-wrap { flex-shrink:0; width:92px; height:92px; animation:logoFadeIn .7s ease both; }
  .logo-glow { animation:pulseGlow 3s ease-in-out infinite; }
  .dna-ring { transform-origin:44px 44px; animation:spinDNA 12s linear infinite; }
  .leaf-r { transform-origin:50px 60px; animation:leafSway 3s ease-in-out infinite; }
  .leaf-l { transform-origin:44px 50px; animation:counterLS 3.4s ease-in-out infinite; }
  .n-line { animation:neuralP 2.5s ease-in-out infinite; }
  .hero-text { flex:1; }
  .hero-title { font-family:'Fraunces',serif; color:#f0fdf4; font-size:2.5rem; font-weight:800; letter-spacing:-0.025em; line-height:1.1; animation:fadeText .7s ease .15s both; }
  .hero-title span { color:#4ade80; }
  .hero-sub { color:#a7f3c0; font-size:0.82rem; font-weight:500; letter-spacing:.09em; margin:6px 0 14px; animation:fadeText .7s ease .3s both; text-transform:uppercase; }
  .tags { animation:fadeText .7s ease .45s both; }
  .tag { display:inline-block; background:rgba(74,222,128,.12); border:1px solid rgba(74,222,128,.38); color:#6ee7a0; font-size:.7rem; font-weight:600; letter-spacing:.08em; padding:4px 11px; border-radius:20px; margin-right:6px; margin-top:6px; text-transform:uppercase; }
</style></head><body>
<div class="hero"><div class="hero-inner">
  <div class="logo-wrap">
    <svg viewBox="0 0 88 88" xmlns="http://www.w3.org/2000/svg" class="logo-glow" width="92" height="92">
      <defs>
        <radialGradient id="bgG" cx="50%" cy="50%" r="50%"><stop offset="0%" stop-color="#0d3320"/><stop offset="100%" stop-color="#020f07"/></radialGradient>
        <radialGradient id="kG" cx="40%" cy="35%" r="60%"><stop offset="0%" stop-color="#86efac"/><stop offset="100%" stop-color="#15803d"/></radialGradient>
        <linearGradient id="sG" x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stop-color="#166534"/><stop offset="100%" stop-color="#4ade80"/></linearGradient>
      </defs>
      <circle cx="44" cy="44" r="43" fill="url(#bgG)" stroke="rgba(74,222,128,0.35)" stroke-width="1.5"/>
      <g class="dna-ring">
        <circle cx="44" cy="44" r="36" fill="none" stroke="rgba(74,222,128,0.18)" stroke-width="1" stroke-dasharray="4 6"/>
        <circle cx="44" cy="8" r="2.5" fill="#4ade80" opacity=".75"/>
        <circle cx="80" cy="44" r="2.5" fill="#4ade80" opacity=".75"/>
        <circle cx="44" cy="80" r="2.5" fill="#4ade80" opacity=".75"/>
        <circle cx="8" cy="44" r="2.5" fill="#4ade80" opacity=".75"/>
      </g>
      <path d="M 44 78 Q 42 62 44 48 Q 46 34 44 18" stroke="url(#sG)" stroke-width="3.5" fill="none" stroke-linecap="round"/>
      <g class="leaf-r"><path d="M 46 58 Q 64 50 68 38 Q 58 48 46 52 Z" fill="#16a34a" opacity=".9"/></g>
      <g class="leaf-l"><path d="M 42 50 Q 24 44 20 30 Q 30 42 42 46 Z" fill="#15803d" opacity=".85"/></g>
      <rect x="38" y="32" width="12" height="22" rx="6" fill="url(#kG)" opacity=".95"/>
      <line x1="44" y1="33" x2="44" y2="53" stroke="rgba(22,101,52,.6)" stroke-width="1"/>
      <line x1="40" y1="35" x2="40" y2="51" stroke="rgba(22,101,52,.5)" stroke-width=".8"/>
      <line x1="48" y1="35" x2="48" y2="51" stroke="rgba(22,101,52,.5)" stroke-width=".8"/>
      <circle cx="28" cy="28" r="3" fill="#4ade80" opacity=".5"/>
      <circle cx="60" cy="28" r="3" fill="#4ade80" opacity=".5"/>
      <circle cx="26" cy="60" r="3" fill="#4ade80" opacity=".4"/>
      <circle cx="62" cy="60" r="3" fill="#4ade80" opacity=".4"/>
      <line x1="28" y1="28" x2="40" y2="38" stroke="#4ade80" stroke-width=".8" class="n-line"/>
      <line x1="60" y1="28" x2="48" y2="38" stroke="#4ade80" stroke-width=".8" class="n-line"/>
      <line x1="26" y1="60" x2="40" y2="50" stroke="#4ade80" stroke-width=".8" class="n-line"/>
      <line x1="62" y1="60" x2="48" y2="50" stroke="#4ade80" stroke-width=".8" class="n-line"/>
      <text x="11" y="78" font-family="Fraunces,serif" font-size="9" font-weight="800" fill="#4ade80" opacity=".65">NC</text>
    </svg>
  </div>
  <div class="hero-text">
    <div class="hero-title">Neuro<span>Crop</span></div>
    <div class="hero-sub">Generative Breeding Platform &nbsp;·&nbsp; Maize Hybrid Yield Prediction</div>
    <div class="tags">
      <span class="tag">XGBoost</span>
      <span class="tag">Genomics + Environment</span>
      <span class="tag">5-Year Multi-Location</span>
      <span class="tag">G×E Modelling</span>
    </div>
  </div>
</div></div>
</body></html>""", height=175, scrolling=False)

cols = st.columns(7)
for col, val, lbl in [
    (cols[0], f"{CV_R2_NORM:.3f}", "CV R² (honest)"),
    (cols[1], f"{TEST_R2_NORM:.3f}", "Test R²"),
    (cols[2], f"{N_SAMPLES:,}", "Samples"),
    (cols[3], f"{N_LOCATIONS}", "Locations"),
    (cols[4], f"{N_HYBRIDS:,}", "Hybrids"),
    (cols[5], f"{N_YEARS} yrs", "G2F Years"),
    (cols[6], f"{OV['n']:,}", "Predictions"),
]:
    col.markdown(f'<div class="kpi"><div class="v">{val}</div><div class="l">{lbl}</div></div>',
                 unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────
st.markdown("""
<style>
  [data-testid="stSidebar"] { background:linear-gradient(180deg,#020f07 0%,#071a0e 60%,#0d2218 100%) !important; border-right:1px solid rgba(74,222,128,0.12) !important; }
  [data-testid="stSidebar"] * { color:#d1fae5 !important; }
  [data-testid="stSidebar"] .stSelectbox label { font-size:.72rem !important; text-transform:uppercase; letter-spacing:.07em; color:#6ee7a0 !important; font-weight:600 !important; }
  [data-testid="stSidebar"] [data-baseweb="select"] > div { background:#0a1f12 !important; border:1.5px solid #1a4d2e !important; border-radius:10px !important; }
  [data-testid="stSidebar"] [data-baseweb="select"] > div:hover { border-color:#22c55e !important; }
  .sb-stat { display:flex; justify-content:space-between; align-items:center; padding:8px 12px; border-radius:10px; margin:5px 0; background:rgba(74,222,128,0.05); border:1px solid rgba(74,222,128,0.1); }
  .sb-stat .sk { font-size:.72rem; text-transform:uppercase; letter-spacing:.06em; color:#6b7280 !important; }
  .sb-stat .sv { font-size:.9rem; font-weight:700; color:#4ade80 !important; font-family:'Fraunces',serif; }
  .sb-brand { text-align:center; padding:14px 8px 6px; border-top:1px solid rgba(74,222,128,0.12); margin-top:8px; }
  .sb-brand .logo-txt { font-family:'Fraunces',serif; font-size:1.1rem; font-weight:800; color:#f0fdf4 !important; }
  .sb-brand .logo-txt span { color:#4ade80 !important; }
  .sb-brand .author { font-size:.72rem; color:#6b7280 !important; letter-spacing:.05em; margin-top:3px; }
  .sb-brand .links a { color:#4ade80 !important; font-size:.75rem; text-decoration:none; margin:0 6px; }
  .sb-preview { background:linear-gradient(135deg,#0a1f12,#0d2a18); border:1.5px solid rgba(74,222,128,0.25); border-radius:12px; padding:12px 14px; margin:10px 0; text-align:center; }
  .sb-preview .sp-cross { font-size:.75rem; color:#6b7280 !important; margin-bottom:4px; }
  .sb-preview .sp-yield { font-family:'Fraunces',serif; font-size:1.6rem; font-weight:800; line-height:1; }
  .sb-preview .sp-unit { font-size:.78rem; color:#86efac !important; }
</style>
""", unsafe_allow_html=True)

st.sidebar.markdown("""
<div style="padding:18px 4px 10px;">
  <div style="font-family:'Fraunces',serif;font-size:1.05rem;font-weight:800;color:#f0fdf4;">
    🔬 Select <span style="color:#4ade80;">Hybrid</span>
  </div>
  <div style="font-size:.72rem;color:#6b7280;letter-spacing:.05em;margin-top:2px;">CHOOSE PARENTS + LOCATION</div>
</div>
""", unsafe_allow_html=True)

default_f = females.index("B73")  if "B73"  in females else 0
default_m = males.index("Mo17")   if "Mo17" in males   else 0
female   = st.sidebar.selectbox("♀ Female Parent", females, index=default_f)
male     = st.sidebar.selectbox("♂ Male Parent",   males,   index=default_m)
location = st.sidebar.selectbox("📍 Location",      locations)

_prev = lookup(female, male, location)
if _prev is not None:
    _pc  = cat(_prev)
    _clr = "#4ade80" if "High" in _pc else ("#fbbf24" if "Medium" in _pc else "#f87171")
    _p   = pct_rank(_prev, location)
    st.sidebar.markdown(f"""
    <div class="sb-preview">
      <div class="sp-cross">{female} × {male} @ {location}</div>
      <div class="sp-yield" style="color:{_clr};">{_prev}</div>
      <div class="sp-unit">bu / Acre &nbsp;·&nbsp; {_pc}</div>
      <div style="margin-top:8px;">
        <div style="font-size:.68rem;color:#6b7280;margin-bottom:3px;">Top {100-_p:.0f}% at location</div>
        <div style="background:#0a1a10;border-radius:99px;height:5px;overflow:hidden;">
          <div style="width:{_p}%;height:100%;background:{_clr};border-radius:99px;"></div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)
else:
    st.sidebar.markdown('<div class="sb-preview" style="border-color:rgba(220,38,38,.3);"><div style="color:#f87171;font-size:.8rem;">❌ Not in database</div></div>', unsafe_allow_html=True)

st.sidebar.markdown("<div style='margin:6px 0 2px;'>", unsafe_allow_html=True)
for k, v in [("Model", MODEL_NAME), ("CV R²", f"{CV_R2_NORM:.3f}"), ("Test R²", f"{TEST_R2_NORM:.3f}"),
             ("Samples", f"{N_SAMPLES:,}"), ("Hybrids", f"{N_HYBRIDS:,}"),
             ("Locations", f"{N_LOCATIONS}"), ("Years", f"{N_YEARS}")]:
    st.sidebar.markdown(f'<div class="sb-stat"><span class="sk">{k}</span><span class="sv">{v}</span></div>', unsafe_allow_html=True)

st.sidebar.markdown("""
<div class="sb-brand">
  <div class="logo-txt">Neuro<span>Crop</span></div>
  <div class="author">Abdul Manan · Plant Breeder + ML</div>
  <div class="links" style="margin-top:6px;">
    <a href="https://github.com/manan348" target="_blank">GitHub</a>
    <a href="https://www.linkedin.com/in/abdul-manan-0aa546332/" target="_blank">LinkedIn</a>
  </div>
</div>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════
(tab1, tab2, tab3, tab4, tab5,
 tab6, tab7, tab8, tab9, tab10) = st.tabs([
    "🔮 Predict", "📍 Best Location", "🏆 Best Cross", "⚖️ Compare Hybrids",
    "🔄 G×E Analysis", "📊 Stability", "📈 Yield Explorer",
    "📦 Batch Predict", "🧠 Model Insights", "ℹ️ About",
])

st.markdown("""
<style>
  @keyframes cardPop { from{opacity:0;transform:scale(.94) translateY(8px)} to{opacity:1;transform:scale(1) translateY(0)} }
  @keyframes barGrow  { from{width:0%} to{width:var(--w)} }
  .result-card { background:linear-gradient(135deg,#0a1f12,#0d2a18); border:1.5px solid #1a4d2e; border-radius:16px; padding:24px 28px; animation:cardPop .45s cubic-bezier(.22,1,.36,1) both; transition:border-color .2s,box-shadow .2s; }
  .result-card:hover { border-color:#22c55e; box-shadow:0 8px 28px rgba(34,197,94,.18); }
  .result-card .big  { font-size:3rem; font-weight:800; color:#4ade80; font-family:'Fraunces',serif; line-height:1; }
  .result-card .unit { font-size:.9rem; color:#86efac; margin-left:4px; }
  .result-card .label{ font-size:.72rem; text-transform:uppercase; letter-spacing:.08em; color:#6b7280; margin-top:4px; }
  .pbar-wrap { background:#0a1a10; border-radius:99px; height:10px; overflow:hidden; margin:6px 0; }
  .pbar-fill  { height:100%; border-radius:99px; background:linear-gradient(90deg,#16a34a,#4ade80); width:var(--w); animation:barGrow .8s cubic-bezier(.22,1,.36,1) .2s both; }
  .rank-badge { display:inline-block; padding:5px 14px; border-radius:99px; font-size:.78rem; font-weight:700; letter-spacing:.05em; margin:4px 2px; }
  .rank-high  { background:rgba(22,163,74,.2);  border:1px solid #16a34a; color:#4ade80; }
  .rank-med   { background:rgba(234,179,8,.15); border:1px solid #ca8a04; color:#fbbf24; }
  .rank-low   { background:rgba(220,38,38,.15); border:1px solid #dc2626; color:#f87171; }
  .fancy-row { display:flex; align-items:center; gap:12px; padding:10px 14px; border-radius:10px; margin:4px 0; transition:background .15s; cursor:default; }
  .fancy-row:hover { background:rgba(74,222,128,.07); }
  .fancy-row .rank-num { font-size:.78rem; color:#6b7280; width:22px; flex-shrink:0; }
  .fancy-row .loc-name { font-weight:600; color:#d1fae5; flex:1; font-size:.88rem; }
  .fancy-row .yield-val { font-family:'Fraunces',serif; font-size:1.1rem; color:#4ade80; }
  @keyframes pulse { 0%,100%{transform:scale(1);opacity:1} 50%{transform:scale(1.5);opacity:.6} }
  .pulse-dot { display:inline-block; width:8px; height:8px; border-radius:50%; background:#4ade80; animation:pulse 2s ease-in-out infinite; margin-right:6px; }
</style>
""", unsafe_allow_html=True)

# TAB 1 — Predict ─────────────────────────────────────────────
with tab1:
    pred = lookup(female, male, location)
    if pred is not None:
        p    = pct_rank(pred, location)
        c    = cat(pred)
        diff = pred - OV["mean"]
        clr  = "#4ade80" if "High" in c else ("#fbbf24" if "Medium" in c else "#f87171")
        pct_fill = round((pred - OV["min"]) / (OV["max"] - OV["min"]) * 100, 1)
        rank_cls = "rank-high" if "High" in c else ("rank-med" if "Medium" in c else "rank-low")
        st.markdown(f"""
        <div class="result-card" style="margin-bottom:18px;">
          <div style="display:flex;align-items:flex-end;gap:6px;flex-wrap:wrap;">
            <span class="big" style="color:{clr}">{pred}</span>
            <span class="unit">bu / Acre</span>
            <span class="rank-badge {rank_cls}" style="margin-left:12px;margin-bottom:6px;">{c}</span>
          </div>
          <div class="label">{female} × {male} &nbsp;·&nbsp; {location}</div>
          <div style="margin-top:14px;">
            <div style="display:flex;justify-content:space-between;font-size:.75rem;color:#6b7280;margin-bottom:4px;">
              <span>Yield percentile at this location</span>
              <span style="color:#4ade80;font-weight:700;">Top {100-p:.0f}%</span>
            </div>
            <div class="pbar-wrap"><div class="pbar-fill" style="--w:{p}%;background:linear-gradient(90deg,{clr}88,{clr});"></div></div>
            <div style="display:flex;justify-content:space-between;font-size:.75rem;color:#6b7280;margin-top:10px;">
              <span>vs overall avg ({OV['mean']:.1f})</span>
              <span style="color:{'#4ade80' if diff>=0 else '#f87171'};font-weight:700;">{diff:+.1f} bu/A</span>
            </div>
            <div class="pbar-wrap"><div class="pbar-fill" style="--w:{pct_fill}%;"></div></div>
          </div>
        </div>
        """, unsafe_allow_html=True)
        ga, gb = st.columns([3, 2])
        with ga:
            fig = go.Figure(go.Indicator(
                mode="gauge+number+delta", value=pred,
                title={"text": "Predicted Yield (bu/A)", "font": {"size": 14, "color": "#a7f3c0"}},
                delta={"reference": OV["mean"], "suffix": " vs avg",
                       "increasing": {"color": "#4ade80"}, "decreasing": {"color": "#f87171"}},
                number={"font": {"color": clr, "size": 52}, "suffix": " bu/A"},
                gauge={
                    "axis": {"range": [OV["min"], OV["max"]], "tickfont": {"color": "#86efac"}},
                    "bar": {"color": clr, "thickness": 0.25},
                    "bgcolor": "#0d1f13", "bordercolor": "#1a4d2e",
                    "steps": [{"range": [OV["min"], 150], "color": "#1a0a0a"},
                              {"range": [150, 170], "color": "#1a1400"},
                              {"range": [170, OV["max"]], "color": "#0a1f0a"}],
                    "threshold": {"line": {"color": "#4ade80", "width": 2},
                                  "thickness": 0.75, "value": OV["mean"]},
                }
            ))
            fig.update_layout(height=300, margin=dict(t=30, b=0, l=20, r=20),
                              paper_bgcolor="#0d1f13", font=dict(color="#e2f5e9", size=13))
            st.plotly_chart(fig, use_container_width=True)
        with gb:
            st.markdown("**Feature Contribution**")
            for name, val, col_ in [("🧬 Genetics (SNPs)", 41.1, "#4ade80"),
                                     ("🌿 Plant Traits", 23.7, "#86efac"),
                                     ("🌦 Season Weather", 18.9, "#fbbf24"),
                                     ("⚡ Critical Weather", 16.3, "#fb923c")]:
                st.markdown(f'<div style="margin:8px 0;"><div style="display:flex;justify-content:space-between;font-size:.8rem;margin-bottom:3px;"><span style="color:#d1fae5;">{name}</span><span style="color:{col_};font-weight:700;">{val}%</span></div><div class="pbar-wrap"><div class="pbar-fill" style="--w:{val}%;background:{col_};opacity:.85;"></div></div></div>', unsafe_allow_html=True)
        st.markdown("---")
        _cross = cross_locations(female, male)   # call once, reuse below
        with st.expander("🗺️ Quick Location Scout — where else does this cross perform?", expanded=False):
            if _cross:
                s_df = pd.DataFrame(_cross)
                fig_s = px.bar(s_df, x="Location", y="Yield", color="Yield",
                               color_continuous_scale="RdYlGn", template="plotly_dark",
                               text="Yield", title=f"{female} × {male} across all locations")
                fig_s.add_hline(y=pred, line_dash="dot", line_color="#4ade80",
                                annotation_text=f"Current ({location})",
                                annotation_font_color="#4ade80")
                fig_s.update_traces(texttemplate="%{text:.1f}", textposition="outside",
                                    textfont=dict(size=10, color="#e2f5e9"))
                fig_s.update_layout(height=380, showlegend=False, xaxis_tickangle=-45,
                                    plot_bgcolor="#0d1f13", paper_bgcolor="#0d1f13",
                                    font=dict(color="#e2f5e9", size=12))
                st.plotly_chart(fig_s, use_container_width=True)
        pdf = make_pdf(female, male, location, pred, _cross, p)
        st.download_button("📄 Download PDF Report", pdf,
                           f"neurocrop_{female}_{male}_{location}.pdf",
                           "application/pdf", use_container_width=True)
    else:
        st.markdown(f'<div class="result-card" style="border-color:#dc2626;text-align:center;padding:32px;"><div style="font-size:2rem;margin-bottom:8px;">❌</div><div style="color:#f87171;font-weight:700;font-size:1rem;">Combination not found in database</div><div style="color:#6b7280;font-size:.82rem;margin-top:6px;">{female} × {male} @ {location}</div></div>', unsafe_allow_html=True)

# TAB 2 — Best Location ───────────────────────────────────────
with tab2:
    st.subheader(f"📍 Best Locations for {female} × {male}")

    @st.cache_data(show_spinner=False)
    def _best_locs(p1: str, p2: str) -> pd.DataFrame:
        rows = [{"Location": item["Location"], "Yield": item["Yield"],
                 "Percentile": pct_rank(item["Yield"], item["Location"]),
                 "Category": cat(item["Yield"])} for item in cross_locations(p1, p2)]
        if not rows:
            return pd.DataFrame(columns=["Location", "Yield", "Percentile", "Category"])
        return pd.DataFrame(rows).sort_values("Yield", ascending=False).reset_index(drop=True)

    res = _best_locs(female, male)
    if len(res):
        pc = st.columns(3)
        medals = [
            '<svg width="28" height="28" viewBox="0 0 28 28"><circle cx="14" cy="14" r="13" fill="#ca8a04"/><text x="14" y="19" text-anchor="middle" font-size="13" font-weight="800" fill="#fff" font-family="sans-serif">1</text></svg>',
            '<svg width="28" height="28" viewBox="0 0 28 28"><circle cx="14" cy="14" r="13" fill="#6b7280"/><text x="14" y="19" text-anchor="middle" font-size="13" font-weight="800" fill="#fff" font-family="sans-serif">2</text></svg>',
            '<svg width="28" height="28" viewBox="0 0 28 28"><circle cx="14" cy="14" r="13" fill="#b45309"/><text x="14" y="19" text-anchor="middle" font-size="13" font-weight="800" fill="#fff" font-family="sans-serif">3</text></svg>',
        ]
        for i in range(min(3, len(res))):
            row = res.iloc[i]
            clr = "#4ade80" if "High" in row["Category"] else ("#fbbf24" if "Medium" in row["Category"] else "#f87171")
            pc[i].markdown(f'<div class="result-card" style="text-align:center;padding:20px 14px;"><div>{medals[i]}</div><div style="font-weight:700;color:#d1fae5;font-size:.9rem;margin:6px 0;">{row["Location"]}</div><div class="big" style="font-size:2rem;color:{clr};">{row["Yield"]}</div><div class="unit">bu/A</div><div style="margin-top:8px;"><div class="pbar-wrap"><div class="pbar-fill" style="--w:{row["Percentile"]}%;background:{clr};"></div></div><div style="font-size:.72rem;color:#6b7280;margin-top:3px;">Top {100-row["Percentile"]:.0f}% at location</div></div></div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        view_mode = st.radio("Chart view", ["Bar", "Scatter (Yield vs Percentile)", "Sorted Table"], horizontal=True)
        if view_mode == "Bar":
            fig = px.bar(res, x="Location", y="Yield", color="Yield", color_continuous_scale="RdYlGn",
                         title=f"{female} × {male} — Yield by Location", text="Yield", template="plotly_dark")
            fig.update_traces(texttemplate="%{text:.1f}", textposition="outside",
                              textfont=dict(size=10, color="#e2f5e9"))
            fig.update_layout(height=460, showlegend=False, xaxis_tickangle=-45,
                              plot_bgcolor="#0d1f13", paper_bgcolor="#0d1f13",
                              font=dict(color="#e2f5e9", size=12))
            st.plotly_chart(fig, use_container_width=True)
        elif view_mode == "Scatter (Yield vs Percentile)":
            fig = px.scatter(res, x="Percentile", y="Yield", text="Location", color="Yield",
                             color_continuous_scale="RdYlGn", template="plotly_dark",
                             title="Yield vs Local Percentile Rank")
            fig.update_traces(textposition="top center",
                              textfont=dict(size=10, color="#e2f5e9"), marker_size=10)
            fig.update_layout(height=460, plot_bgcolor="#0d1f13",
                              paper_bgcolor="#0d1f13", font=dict(color="#e2f5e9", size=12))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.markdown("#### Ranked Locations")
            min_y = st.slider("Filter: min yield", int(res["Yield"].min()),
                              int(res["Yield"].max()), int(res["Yield"].min()), key="t2_filter")
            for i, row in res[res["Yield"] >= min_y].iterrows():
                clr = "#4ade80" if "High" in row["Category"] else ("#fbbf24" if "Medium" in row["Category"] else "#f87171")
                bar_w = round((row["Yield"] - res["Yield"].min()) / (res["Yield"].max() - res["Yield"].min()) * 100, 1)
                st.markdown(f'<div class="fancy-row"><span class="rank-num">{i+1}</span><span class="loc-name">{row["Location"]}</span><div style="flex:2;"><div class="pbar-wrap" style="height:6px;"><div class="pbar-fill" style="--w:{bar_w}%;background:{clr};"></div></div></div><span class="yield-val" style="color:{clr};">{row["Yield"]}</span><span style="font-size:.72rem;color:#6b7280;margin-left:4px;">bu/A</span></div>', unsafe_allow_html=True)
        st.download_button("📥 Download CSV", res.to_csv(index=False), f"best_locs_{female}_{male}.csv")

# TAB 3 — Best Cross ──────────────────────────────────────────
with tab3:
    st.subheader(f"🏆 Top Crosses at {location}")
    col_a, col_b = st.columns([3, 1])
    top_n   = col_a.slider("Show top N", 5, 50, 20, key="t3_topn")
    sort_by = col_b.selectbox("Sort by", ["Yield ↓", "Yield ↑"], key="t3_sort")
    cross_df = df[df["Location"] == location].copy()
    cross_df["Cross"] = cross_df["Female"] + " × " + cross_df["Male"]
    cross_df = cross_df.sort_values("Yield", ascending=(sort_by == "Yield ↑")).head(top_n).reset_index(drop=True)
    search = st.text_input("🔍 Filter by parent name", placeholder="e.g. B73 or Mo17", key="t3_search")
    if search:
        cross_df = cross_df[cross_df["Cross"].str.contains(search, case=False, na=False)]
    if len(cross_df):
        max_y = cross_df["Yield"].max(); min_y = cross_df["Yield"].min()
        def rank_badge(i):
            colors_map = {0: "#ca8a04", 1: "#6b7280", 2: "#b45309"}
            if i in colors_map:
                return f'<svg width="22" height="22" viewBox="0 0 22 22"><circle cx="11" cy="11" r="10" fill="{colors_map[i]}" opacity=".9"/><text x="11" y="15.5" text-anchor="middle" font-size="11" font-weight="800" fill="#fff" font-family="sans-serif">{i+1}</text></svg>'
            return f'<span style="font-size:.75rem;color:#6b7280;font-weight:600;">#{i+1}</span>'
        for i, (_, row) in enumerate(cross_df.iterrows()):
            clr   = "#4ade80" if row["Yield"] >= YIELD_HIGH else ("#fbbf24" if row["Yield"] >= YIELD_MEDIUM else "#f87171")
            bar_w = round((row["Yield"] - min_y) / (max_y - min_y + 0.01) * 100, 1) if max_y > min_y else 80
            st.markdown(f'<div class="fancy-row"><span style="width:28px;flex-shrink:0;display:flex;align-items:center;">{rank_badge(i)}</span><span class="loc-name">{row["Cross"]}</span><div style="flex:3;"><div class="pbar-wrap" style="height:7px;"><div class="pbar-fill" style="--w:{bar_w}%;background:{clr};"></div></div></div><span style="font-family:\'Fraunces\',serif;font-size:1.05rem;color:{clr};font-weight:700;">{row["Yield"]:.1f}</span><span style="font-size:.72rem;color:#6b7280;margin-left:3px;">bu/A</span></div>', unsafe_allow_html=True)
        fig = px.bar(cross_df, x="Yield", y="Cross", orientation="h", color="Yield",
                     color_continuous_scale="RdYlGn",
                     title=f"Top {len(cross_df)} Crosses at {location}",
                     text="Yield", template="plotly_dark")
        fig.update_traces(texttemplate="%{text:.1f}", textposition="outside")
        fig.update_layout(height=max(380, len(cross_df) * 22), showlegend=False,
                          yaxis={"categoryorder": "total ascending"},
                          plot_bgcolor="#0d1f13", paper_bgcolor="#0d1f13",
                          font=dict(color="#e2f5e9", size=12))
        st.plotly_chart(fig, use_container_width=True)
        st.download_button("📥 Download CSV", cross_df.to_csv(index=False), f"top_crosses_{location}.csv")
    else:
        st.info("No crosses match the search filter.")

# TAB 4 — Compare Hybrids ─────────────────────────────────────
with tab4:
    st.subheader("⚖️ Side-by-Side Hybrid Comparison")
    st.markdown('<div class="info-pill">Compare up to 4 hybrids — yields, location rankings, and stability metrics.</div>', unsafe_allow_html=True)
    n_comp = st.radio("Number of hybrids to compare", [2, 3, 4], horizontal=True)
    hybs   = []; cols_c = st.columns(n_comp)
    for i, col in enumerate(cols_c):
        with col:
            st.markdown(f"**Hybrid {i+1}**")
            fi = col.selectbox(f"Female {i+1}", females, key=f"cf{i}", index=min(i * 3, len(females) - 1))
            mi = col.selectbox(f"Male {i+1}",   males,   key=f"cm{i}", index=min(i * 2, len(males) - 1))
            li = col.selectbox(f"Location {i+1}", locations, key=f"cl{i}")
            hybs.append((fi, mi, li))
    st.markdown("---")
    card_cols = st.columns(n_comp); comp_rows = []
    for i, (fi, mi, li) in enumerate(hybs):
        v = lookup(fi, mi, li)
        with card_cols[i]:
            if v is not None:
                p_ = pct_rank(v, li); c_ = cat(v)
                color = "#16a34a" if "High" in c_ else ("#f59e0b" if "Medium" in c_ else "#dc2626")
                st.markdown(f'<div class="compare-card"><div class="hn">{fi} x {mi}</div><div style="font-size:0.75rem;color:#6b7280;margin-bottom:8px">{li}</div><div class="yb" style="color:{color}">{v}</div><div class="yu">bu/A</div><div style="margin-top:8px;font-size:0.8rem;color:#4b7a5e">Top {100-p_:.0f}% at location</div><div style="font-size:0.85rem;margin-top:4px">{c_}</div></div>', unsafe_allow_html=True)
                comp_rows.append({"Hybrid": f"{fi} x {mi}", "Location": li, "Yield": v, "Percentile": 100 - p_, "Category": c_})
            else:
                st.warning(f"No data for {fi} x {mi} @ {li}")
    if len(comp_rows) > 1:
        comp_df = pd.DataFrame(comp_rows)
        comp_df["Label"] = comp_df["Hybrid"] + "\n@" + comp_df["Location"]
        fig = px.bar(comp_df, x="Label", y="Yield", color="Yield", color_continuous_scale="RdYlGn",
                     text="Yield", title="Yield Comparison", template="plotly_dark")
        fig.update_traces(texttemplate="%{text:.1f}", textposition="outside")
        fig.update_layout(height=360, showlegend=False, plot_bgcolor="#0d1f13",
                          paper_bgcolor="#0d1f13", font=dict(color="#e2f5e9", size=13),
                          xaxis_title="", yaxis_title="Predicted Yield (bu/A)")
        st.plotly_chart(fig, use_container_width=True)
        st.markdown("**Performance across ALL locations:**")
        prof = []
        for fi, mi, _ in hybs:
            for item in cross_locations(fi, mi):
                prof.append({"Hybrid": f"{fi} x {mi}", "Location": item["Location"], "Yield": item["Yield"]})
        if prof:
            fig2 = px.line(pd.DataFrame(prof), x="Location", y="Yield", color="Hybrid",
                           markers=True, title="Yield Profile Across All Locations", template="plotly_dark")
            fig2.update_layout(height=400, xaxis_tickangle=-45, plot_bgcolor="#0d1f13",
                               paper_bgcolor="#0d1f13", font=dict(color="#e2f5e9", size=13))
            st.plotly_chart(fig2, use_container_width=True)
        stab = stability_df(); summ = []
        for fi, mi, li in hybs:
            v = lookup(fi, mi, li)
            row = stab[(stab["Female"] == fi) & (stab["Male"] == mi)]
            summ.append({"Hybrid": f"{fi} x {mi}", "Location": li,
                         "Predicted": v if v is not None else "—",
                         "Mean (all locs)": f"{row['Mean_Yield'].values[0]:.1f}" if len(row) else "—",
                         "CV%": f"{row['CV_pct'].values[0]:.1f}" if len(row) else "—",
                         "Stability": row["Stability"].values[0] if len(row) else "—"})
        st.dataframe(pd.DataFrame(summ), use_container_width=True, hide_index=True)
        st.download_button("📥 Download CSV", comp_df.to_csv(index=False), "comparison.csv")

# TAB 5 — G×E Analysis ────────────────────────────────────────
with tab5:
    st.subheader("🔄 G×E Interaction Analysis")
    st.markdown('<div class="info-pill"><span class="pulse-dot"></span><strong>Crossing lines = strong G×E</strong>. Parallel lines = stable, wide-adapted hybrid.</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    sel_f  = c1.multiselect("Female Parents", females, default=females[:4], key="ge_f")
    fix_m  = c2.selectbox("Fixed Male Parent", males, index=males.index("Mo17") if "Mo17" in males else 0, key="ge_male")
    if sel_f:
        ge = df[df["Female"].isin(sel_f) & (df["Male"] == fix_m)].copy()
        ge["Hybrid"] = ge["Female"] + " × " + ge["Male"]
        if len(ge):
            grand_mean = ge["Yield"].mean()
            fig = px.line(ge, x="Location", y="Yield", color="Hybrid", markers=True,
                          title=f"G×E Interaction Profile (Male={fix_m})", template="plotly_dark",
                          color_discrete_sequence=px.colors.qualitative.Safe)
            fig.add_hline(y=grand_mean, line_dash="dash", line_color="#4ade80",
                          annotation_text=f"Grand Mean ({grand_mean:.1f})",
                          annotation_font_color="#4ade80")
            fig.update_traces(line_width=2, marker_size=7)
            fig.update_layout(height=440, xaxis_tickangle=-45, plot_bgcolor="#0d1f13",
                              paper_bgcolor="#0d1f13", font=dict(color="#e2f5e9", size=12),
                              legend=dict(bgcolor="#0d1f13", bordercolor="#1a4d2e"))
            st.plotly_chart(fig, use_container_width=True)
            pivot = ge.pivot_table(index="Hybrid", columns="Location", values="Yield", aggfunc="mean")
            dev   = pivot.subtract(pivot.mean(axis=1), axis=0)
            view  = st.radio("Heatmap view", ["Absolute Yield (bu/A)", "Deviation from Hybrid Mean"],
                             horizontal=True, key="ge_hm")
            data_hm = pivot if view.startswith("Absolute") else dev
            fig2 = px.imshow(data_hm.round(1),
                             color_continuous_scale="RdYlGn" if view.startswith("Absolute") else "RdBu",
                             title="G×E Heatmap", text_auto=".0f", template="plotly_dark", aspect="auto")
            fig2.update_layout(height=max(280, len(sel_f) * 70 + 120),
                               paper_bgcolor="#0d1f13", plot_bgcolor="#0d1f13",
                               font=dict(color="#e2f5e9", size=12))
            st.plotly_chart(fig2, use_container_width=True)
            with st.expander("🏆 Which hybrid wins at each location?"):
                for loc_ in pivot.columns:
                    col_vals = pivot[loc_].dropna()
                    if len(col_vals):
                        st.markdown(f'<div class="fancy-row"><span class="loc-name">{loc_}</span><span style="color:#a7f3c0;font-size:.85rem;">{col_vals.idxmax()}</span><span style="color:#4ade80;font-family:\'Fraunces\',serif;font-size:1rem;margin-left:auto;">{round(col_vals.max(),1)} bu/A</span></div>', unsafe_allow_html=True)
        else:
            st.info("No data for this combination.")

# TAB 6 — Stability ───────────────────────────────────────────
with tab6:
    st.subheader("📊 G×E Stability Ranking")
    st.markdown('<div class="info-pill"><strong>CV%</strong> = coefficient of variation across locations. Lower = more stable.</div>', unsafe_allow_html=True)
    stab = stability_df()
    c1, c2, c3 = st.columns(3)
    min_m = c1.slider("Min mean yield (bu/A)", int(stab["Mean_Yield"].min()),
                      int(stab["Mean_Yield"].max()), 150, key="stab_miny")
    max_c = c2.slider("Max CV%", 1, 30, 12, key="stab_maxcv")
    min_n = c3.slider("Min locations tested", 1, int(stab["N_Locs"].max()), 3, key="stab_minn")
    filt = stab[(stab["Mean_Yield"] >= min_m) & (stab["CV_pct"] <= max_c) & (stab["N_Locs"] >= min_n)].head(80)
    if len(filt):
        st.markdown(f'<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px;"><div class="rank-badge rank-high">✅ {(filt["Stability"]=="🟢 Stable").sum()} Stable</div><div class="rank-badge rank-med">{(filt["Stability"]=="🟡 Moderate").sum()} Moderate</div><div class="rank-badge rank-low">{(filt["Stability"]=="🔴 Unstable").sum()} Unstable</div><div style="color:#6b7280;font-size:.8rem;padding:5px 0;">of {len(filt)} hybrids shown</div></div>', unsafe_allow_html=True)
        chart_type = st.radio("Chart", ["Scatter", "Top 20 Bubble", "Histogram"], horizontal=True, key="stab_chart")
        if chart_type == "Scatter":
            fig = px.scatter(filt, x="CV_pct", y="Mean_Yield", color="Stability", size="N_Locs",
                             hover_name="Hybrid",
                             color_discrete_map={"🟢 Stable": "#16a34a", "🟡 Moderate": "#ca8a04", "🔴 Unstable": "#dc2626"},
                             title="Yield vs Stability", template="plotly_dark")
            fig.update_layout(height=480, plot_bgcolor="#0d1f13", paper_bgcolor="#0d1f13",
                              font=dict(color="#e2f5e9", size=12))
            st.plotly_chart(fig, use_container_width=True)
        elif chart_type == "Top 20 Bubble":
            fig = px.scatter(filt.head(20), x="CV_pct", y="Mean_Yield", size="Mean_Yield",
                             color="CV_pct", color_continuous_scale="RdYlGn_r",
                             text="Hybrid", template="plotly_dark",
                             title="Top 20 Hybrids — Yield vs Stability")
            fig.update_traces(textposition="top center", textfont=dict(size=9, color="#d1fae5"))
            fig.update_layout(height=500, plot_bgcolor="#0d1f13", paper_bgcolor="#0d1f13",
                              font=dict(color="#e2f5e9", size=12))
            st.plotly_chart(fig, use_container_width=True)
        else:
            col_h1, col_h2 = st.columns(2)
            with col_h1:
                fig = px.histogram(filt, x="Mean_Yield", nbins=25,
                                   color_discrete_sequence=["#4ade80"],
                                   title="Mean Yield Distribution", template="plotly_dark")
                fig.update_layout(height=300, plot_bgcolor="#0d1f13",
                                  paper_bgcolor="#0d1f13", font=dict(color="#e2f5e9", size=12))
                st.plotly_chart(fig, use_container_width=True)
            with col_h2:
                fig2 = px.histogram(filt, x="CV_pct", nbins=25,
                                    color_discrete_sequence=["#fbbf24"],
                                    title="CV% Distribution", template="plotly_dark")
                fig2.update_layout(height=300, plot_bgcolor="#0d1f13",
                                   paper_bgcolor="#0d1f13", font=dict(color="#e2f5e9", size=12))
                st.plotly_chart(fig2, use_container_width=True)
        show = ["Hybrid", "Mean_Yield", "Std_Yield", "CV_pct", "N_Locs", "Stability"]
        st.dataframe(filt[show].reset_index(drop=True), use_container_width=True)
        st.download_button("📥 Download Table", filt[show].to_csv(index=False), "stability.csv")
    else:
        st.warning("No hybrids match. Try relaxing the filters.")

# TAB 7 — Yield Explorer ──────────────────────────────────────
with tab7:
    st.subheader("📈 Yield Explorer — Database Analytics")
    et1, et2, et3 = st.tabs(["Distribution", "By Location", "Parent Effects"])
    with et1:
        fig = px.histogram(df, x="Yield", nbins=60,
                           title=f"Global Yield Distribution ({OV['n']:,} predictions)",
                           color_discrete_sequence=["#16a34a"], template="plotly_dark")
        fig.add_vline(x=OV["mean"], line_dash="dash", line_color="#14532d",
                      annotation_text=f"Mean: {OV['mean']:.1f}")
        fig.add_vline(x=150, line_dash="dot", line_color="orange",
                      annotation_text="Medium threshold")
        fig.add_vline(x=170, line_dash="dot", line_color="#16a34a",
                      annotation_text="High threshold")
        fig.update_layout(height=380, plot_bgcolor="#0d1f13",
                          paper_bgcolor="#0d1f13", font=dict(color="#e2f5e9", size=13))
        st.plotly_chart(fig, use_container_width=True)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Mean", f"{OV['mean']:.1f} bu/A"); c2.metric("Std", f"{OV['std']:.1f} bu/A")
        c3.metric("Min", f"{OV['min']:.1f} bu/A"); c4.metric("Max", f"{OV['max']:.1f} bu/A")
        ph = (df["Yield"] >= YIELD_HIGH).mean() * 100
        pm = ((df["Yield"] >= YIELD_MEDIUM) & (df["Yield"] < YIELD_HIGH)).mean() * 100
        pl = (df["Yield"] < YIELD_MEDIUM).mean() * 100
        fig2 = px.pie(values=[ph, pm, pl], names=["High (>=170)", "Medium (150-170)", "Low (<150)"],
                      color_discrete_sequence=["#16a34a", "#ca8a04", "#dc2626"],
                      title="Category Distribution", hole=0.45, template="plotly_dark")
        fig2.update_layout(height=320, paper_bgcolor="#0d1f13", font=dict(color="#e2f5e9", size=13))
        st.plotly_chart(fig2, use_container_width=True)
    with et2:
        ls = location_stats()
        fig = px.bar(ls, x="Location", y="Mean", error_y="Std", color="Mean",
                     color_continuous_scale="RdYlGn",
                     title="Mean Predicted Yield by Location", template="plotly_dark")
        fig.update_layout(height=460, xaxis_tickangle=-45, plot_bgcolor="#0d1f13",
                          paper_bgcolor="#0d1f13", font=dict(color="#e2f5e9", size=13), showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(ls.reset_index(drop=True), use_container_width=True)
        st.download_button("📥 Location Stats CSV", ls.to_csv(index=False), "location_stats.csv")
    with et3:
        for label, col_name, palette in [("Female", "Female", "Greens"), ("Male", "Male", "Blues")]:
            st.markdown(f"**Top 20 {label} Parents by Mean Yield**")
            ps = parent_stats(col_name)
            fig = px.bar(ps, x=col_name, y="Mean Yield", color="Mean Yield",
                         color_continuous_scale=palette,
                         title=f"Top 20 {label} Parents", template="plotly_dark")
            fig.update_layout(height=360, xaxis_tickangle=-45, plot_bgcolor="#0d1f13",
                              paper_bgcolor="#0d1f13", font=dict(color="#e2f5e9", size=13), showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

# TAB 8 — Batch Predict ───────────────────────────────────────
with tab8:
    st.subheader("📦 Batch Yield Prediction")
    st.markdown("Upload a CSV with columns: **Female, Male, Location**")
    sample = pd.DataFrame({"Female": ["B73", "A632", "Oh43"],
                            "Male":   ["Mo17", "Mo17", "Mo17"],
                            "Location": ["ILH1", "WIH1", "IAH4"]})
    st.dataframe(sample, use_container_width=True)
    st.download_button("📥 Download Template", sample.to_csv(index=False), "template.csv", "text/csv")
    st.markdown("---")
    uploaded = st.file_uploader("Upload CSV", type=["csv"])
    if uploaded:
        inp = pd.read_csv(uploaded)
        st.markdown(f"**{len(inp)} rows**"); st.dataframe(inp.head(), use_container_width=True)
        miss = [c for c in ["Female", "Male", "Location"] if c not in inp.columns]
        if miss:
            st.error(f"Missing columns: {miss}")
        elif st.button("🔮 Run All Predictions", type="primary", use_container_width=True):
            results, errors = [], []
            prog = st.progress(0); stat = st.empty()
            for i, (_, row) in enumerate(inp.iterrows()):
                p1, p2, loc = str(row["Female"]).strip(), str(row["Male"]).strip(), str(row["Location"]).strip()
                v = lookup(p1, p2, loc)
                if v is not None:
                    results.append({"Female": p1, "Male": p2, "Location": loc,
                                    "Predicted Yield": v, "Percentile": pct_rank(v, loc), "Category": cat(v)})
                else:
                    errors.append({"Female": p1, "Male": p2, "Location": loc, "Error": "Not found"})
                prog.progress((i + 1) / len(inp)); stat.text(f"Processing {i+1}/{len(inp)}…")
            prog.empty(); stat.empty()
            if results:
                res = pd.DataFrame(results).sort_values("Predicted Yield", ascending=False).reset_index(drop=True)
                res.index += 1
                st.success(f"✅ {len(results)} predictions")
                if errors: st.warning(f"⚠️ {len(errors)} not found")
                m1, m2, m3 = st.columns(3)
                m1.metric("Best", f"{res['Predicted Yield'].max():.1f} bu/A")
                m2.metric("Average", f"{res['Predicted Yield'].mean():.1f} bu/A")
                m3.metric("Worst", f"{res['Predicted Yield'].min():.1f} bu/A")
                st.dataframe(res, use_container_width=True)
                fig = px.histogram(res, x="Predicted Yield", nbins=20, title="Batch Distribution",
                                   color_discrete_sequence=["#16a34a"], template="plotly_dark")
                fig.update_layout(paper_bgcolor="#0d1f13", plot_bgcolor="#0d1f13",
                                  font=dict(color="#e2f5e9", size=13))
                st.plotly_chart(fig, use_container_width=True)
                c1, c2 = st.columns(2)
                c1.download_button("📥 CSV", res.to_csv(index=False), "batch.csv",
                                   "text/csv", use_container_width=True)
                try:
                    import openpyxl  # noqa: F401
                    xb = io.BytesIO()
                    with pd.ExcelWriter(xb, engine="openpyxl") as w:
                        res.to_excel(w, index=False, sheet_name="Predictions")
                    xb.seek(0)
                    c2.download_button("📊 Excel", xb, "batch.xlsx",
                                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                       use_container_width=True)
                except ImportError:
                    c2.warning("Install `openpyxl` for Excel export.")
                if errors:
                    with st.expander(f"❌ {len(errors)} failed"):
                        st.dataframe(pd.DataFrame(errors), use_container_width=True)
            else:
                st.error("No predictions found. Check Female/Male/Location values match the database.")

# TAB 9 — Model Insights ──────────────────────────────────────
with tab9:
    st.subheader("🧠 Model Insights")
    st.markdown('<div class="info-pill"><span class="pulse-dot"></span>Live model performance breakdown. NeuroCrop vs industry GBLUP benchmarks.</div>', unsafe_allow_html=True)
    cl, cr = st.columns(2)
    with cl:
        st.markdown("#### Feature Importance")
        for feat, imp in [("Genetics (SNP PCA)", 41.1), ("Plant Traits", 23.7),
                          ("Season Weather", 18.9), ("Critical-Period Weather", 16.3), ("Soil", 0.0)]:
            clr = "#4ade80" if imp > 30 else ("#86efac" if imp > 15 else "#fbbf24")
            st.markdown(f'<div style="margin:10px 0;"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;"><span style="color:#d1fae5;font-size:.85rem;font-weight:500;">{feat}</span><span style="color:{clr};font-family:\'Fraunces\',serif;font-size:1.05rem;font-weight:700;">{imp}%</span></div><div class="pbar-wrap" style="height:12px;"><div class="pbar-fill" style="--w:{imp}%;background:linear-gradient(90deg,{clr}88,{clr});border-radius:99px;"></div></div></div>', unsafe_allow_html=True)
        st.markdown("<br>"); st.markdown("#### NeuroCrop vs GBLUP — Capability Radar")
        cats = ["Genomics", "Env. Data", "Multi-Year", "Multi-Location", "Speed", "Coverage"]
        fig_r = go.Figure()
        fig_r.add_trace(go.Scatterpolar(r=[85,90,95,95,80,90,85], theta=cats+[cats[0]],
                                        fill='toself', name='NeuroCrop',
                                        line_color='#4ade80', fillcolor='rgba(74,222,128,0.15)'))
        fig_r.add_trace(go.Scatterpolar(r=[90,20,40,60,70,50,90], theta=cats+[cats[0]],
                                        fill='toself', name='Standard GBLUP',
                                        line_color='#fbbf24', fillcolor='rgba(251,191,36,0.1)'))
        fig_r.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 100], gridcolor="#1a4d2e"),
                       angularaxis=dict(tickfont=dict(color="#d1fae5", size=11)),
                       bgcolor="#0d1f13"),
            showlegend=True, legend=dict(font=dict(color="#e2f5e9"), bgcolor="#0d1f13"),
            paper_bgcolor="#0d1f13", height=360, margin=dict(t=20, b=20, l=40, r=40),
        )
        st.plotly_chart(fig_r, use_container_width=True)
    with cr:
        st.markdown("#### Model Version Comparison")
        perf = pd.DataFrame({
            "Version":   ["2017 (RF)", "2014-2018 (XGBoost)"],
            "CV R2":     [0.572, 0.355], "Test R2": [0.635, 0.361],
            "Samples":   [2867, 46686],  "Locations": [23, 38],
        })
        fig2 = go.Figure()
        fig2.add_trace(go.Bar(name="CV R²", x=perf["Version"], y=perf["CV R2"],
                              marker_color="#16a34a",
                              text=[f"{v:.3f}" for v in perf["CV R2"]],
                              textposition="outside", textfont=dict(size=13, color="#e2f5e9")))
        fig2.add_trace(go.Bar(name="Test R²", x=perf["Version"], y=perf["Test R2"],
                              marker_color="#4ade80",
                              text=[f"{v:.3f}" for v in perf["Test R2"]],
                              textposition="outside", textfont=dict(size=13, color="#e2f5e9")))
        fig2.update_layout(barmode="group", template="plotly_dark", height=300,
                           plot_bgcolor="#0d1f13", paper_bgcolor="#0d1f13",
                           font=dict(color="#e2f5e9", size=13),
                           yaxis=dict(range=[0, .8], gridcolor="#1e3a28"),
                           legend=dict(bgcolor="#0d1f13", bordercolor="#1a4d2e"),
                           margin=dict(t=20, b=10))
        st.plotly_chart(fig2, use_container_width=True)
        chg = [("Samples","2,867","46,686","16x more"), ("Years","1","5","Multi-year G×E"),
               ("Locations","23","38","+15 envs"), ("Hybrids","654","2,912","4.5x diversity"),
               ("Algorithm","RF","XGBoost","Better G×E"), ("SNP strategy","Concat","Mid-parent","Half RAM"),
               ("CV (honest)","0.572*","0.355","*had leakage"),
               ("Predictions","~100k","2,994,894","Full coverage")]
        st.dataframe(pd.DataFrame(chg, columns=["Metric","2017","2014-2018","Why"]),
                     use_container_width=True, hide_index=True)
        st.markdown('<div class="warn-pill">CV R² dropped 0.572→0.355 because the old 2017 CV had data leakage. Current 0.355 is the honest cross-validated number. Published GBLUP benchmarks on G2F: R² = 0.35–0.55.</div>', unsafe_allow_html=True)

# TAB 10 — About ──────────────────────────────────────────────
with tab10:
    st.subheader("ℹ️ About NeuroCrop")
    ca, cb = st.columns([2, 1])
    with ca:
        st.markdown("""
        <div class="about-section"><h4>What is NeuroCrop?</h4>A generative breeding platform predicting maize hybrid grain yield before field trials, using genomic SNPs, weather, soil, and plant traits. Trained on the public G2F dataset: 5 years (2014-2018), 38 US locations, 2,912 hybrids, 2,994,894 pre-computed predictions.</div>
        <div class="about-section"><h4>Technical Architecture</h4><strong>Genomics:</strong> Top 10k SNPs (variance filter from 437k-SNP VCF). Mid-parent average compressed to 20 PCA components via TruncatedSVD.<br><br><strong>Environment:</strong> Season weather (May-Sep) + critical-period weather (Jun-Aug) + soil = 27 features.<br><br><strong>Model:</strong> XGBoost (400 trees, lr=0.03). Per-location z-score normalisation. Honest 3-fold CV.<br><br><strong>Inference:</strong> 2,994,894 pre-computed predictions stored in a 30 MB .csv.gz. No model inference at runtime.</div>
        <div class="about-section"><h4>Dataset</h4>Public G2F (Genomes to Fields) initiative. DOI: 10.25739/ragt-7213<br>VCF: inbreds_G2F_2014-2023_437k.vcf — 2,193 inbreds, 437,214 SNPs</div>
        """, unsafe_allow_html=True)
    with cb:
        st.markdown("""
        <div class="about-section"><h4>Author</h4><strong>Abdul Manan</strong><br>Plant Breeder · ML Researcher<br>Generative Breeding Startup<br><br>📧 [email removed]<br>🔗 <a href="https://www.linkedin.com/in/abdul-manan-0aa546332/">LinkedIn</a><br>💻 <a href="https://github.com/manan348">GitHub</a></div>
        <div class="about-section"><h4>Metrics</h4>CV R² = 0.355 (honest)<br>Test R² = 0.361<br>Samples = 46,686<br>Locations = 38<br>Hybrids = 2,912<br>Years = 5</div>
        """, unsafe_allow_html=True)

# ── Footer ────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    f"**NeuroCrop** · Generative Breeding · {DATASET} · {MODEL_NAME} · "
    f"CV R² = {CV_R2_NORM:.3f} · Test R² = {TEST_R2_NORM:.3f} · "
    f"{N_SAMPLES:,} samples · {N_LOCATIONS} locations · "
    "**Abdul Manan** · [GitHub](https://github.com/manan348) · "
    "[LinkedIn](https://www.linkedin.com/in/abdul-manan-0aa546332/)"
)
