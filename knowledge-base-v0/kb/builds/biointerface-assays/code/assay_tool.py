"""
BioInterface — Streamlit app v1.0
Streamlit app for browsing, searching, filtering, comparing, and visualizing assays.

v2.1 changes:
  - Fixed hardcoded path (now uses relative path — works on any machine)
  - Added Export Protocol button in Assay Detail > Robot Steps tab
  - Added AI Intelligence section (natural language search, RCA, batch correlation)
  - AI section degrades gracefully if api_layer.py or API key is not present
"""
import importlib
import os
import sys

# ── Path fix: resolve relative to this file's location ──────────────────
# Removes the hardcoded c:\Users\vivek\ path that broke on any other machine.
# Works on Windows, Mac, and any deployment environment.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from field_01_biopharma_v2 import BIOPHARMA_ASSAYS
from rail_protocol_generator import generate_protocol, classify_step
import deck_designer
import pipeline_visualizer
import time as _time
from datetime import datetime as _datetime

# ── AI layer import (graceful fallback if not set up yet) ────────────────
AI_AVAILABLE = False
try:
    from ai_layer import (
        search_protocols, analyze_run_failure, correlate_batch_quality,
        assign_instrument_steps, check_volume_compatibility,
    )
    from dotenv import load_dotenv
    load_dotenv()
    if os.environ.get("ANTHROPIC_API_KEY"):
        AI_AVAILABLE = True
except ImportError:
    pass

# ── Page config ──────────────────────────────────────────────────────────
st.set_page_config(
    page_title="BioInterface",
    page_icon="\U0001f9ea",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── BioInterface Theme ───────────────────────────────────────────────────
st.markdown('''
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Mono:wght@400;500&family=Outfit:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Outfit', -apple-system, BlinkMacSystemFont, sans-serif !important;
    color: #0f1117 !important;
}

h1 {
    font-family: 'DM Serif Display', Georgia, serif !important;
    color: #1a3a5c !important;
    font-size: 38px !important;
    font-weight: 400 !important;
    line-height: 1.1 !important;
    letter-spacing: -0.01em !important;
    margin-bottom: 8px !important;
}

h2 {
    font-family: 'DM Serif Display', Georgia, serif !important;
    color: #1a3a5c !important;
    font-weight: 400 !important;
    font-size: 26px !important;
    letter-spacing: -0.01em !important;
}

h3 {
    font-family: 'DM Serif Display', Georgia, serif !important;
    color: #1a3a5c !important;
    font-weight: 400 !important;
    font-size: 22px !important;
}

.stCaption, [data-testid="stCaptionContainer"] {
    color: #6b6560 !important;
    font-size: 12.5px !important;
    line-height: 1.6 !important;
}

.stButton > button {
    background: #1a3a5c !important;
    color: white !important;
    border: none !important;
    border-radius: 6px !important;
    font-weight: 500 !important;
    font-size: 13px !important;
    padding: 9px 18px !important;
    letter-spacing: 0.01em !important;
    transition: all 0.15s ease !important;
    box-shadow: 0 1px 2px rgba(26,58,92,0.1) !important;
}

.stButton > button:hover {
    background: #2d6a9f !important;
    box-shadow: 0 2px 6px rgba(26,58,92,0.15) !important;
    transform: translateY(-1px) !important;
}

.stButton > button[kind="primary"] {
    background: #c84b1f !important;
    box-shadow: 0 1px 2px rgba(200,75,31,0.15) !important;
}

.stButton > button[kind="primary"]:hover {
    background: #e56333 !important;
    box-shadow: 0 2px 6px rgba(200,75,31,0.25) !important;
}

.stDownloadButton > button {
    background: #1a6b4a !important;
    color: white !important;
    border: none !important;
    border-radius: 6px !important;
    font-weight: 500 !important;
}

.stDownloadButton > button:hover {
    background: #258558 !important;
}

.stTabs [data-baseweb="tab-list"] {
    gap: 2px;
    border-bottom: 2px solid #d4cfc4;
    margin-bottom: 16px;
}

.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    border-radius: 6px 6px 0 0 !important;
    padding: 10px 20px !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    color: #6b6560 !important;
    border: none !important;
}

.stTabs [aria-selected="true"] {
    background: #1a3a5c !important;
    color: white !important;
}

.stSuccess {
    background: #e8f5ee !important;
    border: 1px solid #b3dac3 !important;
    border-left: 4px solid #1a6b4a !important;
    border-radius: 0 8px 8px 0 !important;
    padding: 14px 18px !important;
}

.stWarning {
    background: #fdf3e8 !important;
    border: 1px solid #f0d5a8 !important;
    border-left: 4px solid #b85c00 !important;
    border-radius: 0 8px 8px 0 !important;
    padding: 14px 18px !important;
}

.stError {
    background: #fce8e8 !important;
    border: 1px solid #f0bdbd !important;
    border-left: 4px solid #c84b1f !important;
    border-radius: 0 8px 8px 0 !important;
    padding: 14px 18px !important;
}

.stInfo {
    background: #e8f0f8 !important;
    border: 1px solid #b8d0e8 !important;
    border-left: 4px solid #2d6a9f !important;
    border-radius: 0 8px 8px 0 !important;
    padding: 14px 18px !important;
}

.streamlit-expanderHeader, [data-testid="stExpander"] summary {
    background: #f7f6f1 !important;
    border-radius: 6px !important;
    font-weight: 500 !important;
    color: #1a3a5c !important;
    padding: 10px 14px !important;
}

.streamlit-expanderHeader:hover {
    background: #efece4 !important;
}

[data-testid="stMain"] [data-testid="stMetric"],
[data-testid="stMain"] [data-testid="metric-container"] {
    background: white !important;
    border: 1px solid #d4cfc4 !important;
    border-left: 3px solid #1a3a5c !important;
    border-radius: 8px !important;
    padding: 14px 18px !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.04) !important;
}

[data-testid="stMain"] [data-testid="stMetricValue"] {
    color: #1a3a5c !important;
    font-family: 'DM Serif Display', Georgia, serif !important;
    font-size: 30px !important;
    font-weight: 400 !important;
    letter-spacing: -0.01em !important;
}

[data-testid="stMain"] [data-testid="stMetricLabel"] {
    color: #6b6560 !important;
    font-size: 11px !important;
    font-weight: 500 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
}

[data-testid="stMain"] [data-testid="stMetricDelta"] {
    font-size: 12px !important;
    font-weight: 500 !important;
}

.stSelectbox label,
.stTextArea label,
.stTextInput label,
.stMultiSelect label,
.stRadio label,
.stCheckbox label,
.stSlider label,
.stNumberInput label {
    color: #1a3a5c !important;
    font-weight: 500 !important;
    font-size: 13px !important;
    margin-bottom: 4px !important;
}

.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stSelectbox > div > div > div {
    border: 1px solid #d4cfc4 !important;
    border-radius: 6px !important;
    padding: 10px 12px !important;
}

.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {
    border-color: #1a3a5c !important;
    box-shadow: 0 0 0 3px rgba(26,58,92,0.1) !important;
}

hr {
    border: none !important;
    border-top: 1px solid #d4cfc4 !important;
    margin: 24px 0 !important;
}

code {
    font-family: 'DM Mono', Monaco, monospace !important;
    background: #f0e8f8 !important;
    color: #5c1a6b !important;
    padding: 2px 6px !important;
    border-radius: 4px !important;
    font-size: 12px !important;
}

pre code {
    background: #1a1f2e !important;
    color: #e8e8e8 !important;
    padding: 14px !important;
    display: block !important;
    border-radius: 8px !important;
}

.stSpinner > div {
    border-top-color: #1a3a5c !important;
}

.stDataFrame {
    border: 1px solid #d4cfc4 !important;
    border-radius: 8px !important;
    overflow: hidden !important;
}
</style>
''', unsafe_allow_html=True)

# ── BioInterface header banner ───────────────────────────────────────────
st.markdown('''
<div style="
    background: linear-gradient(135deg, #0d1117 0%, #1a3a5c 60%, #5c1a6b 100%);
    color: white;
    padding: 16px 24px;
    margin: -1rem -1rem 24px -1rem;
    border-radius: 0 0 12px 12px;
">
    <div style="
        font-family: 'DM Mono', monospace;
        font-size: 10px;
        letter-spacing: 0.16em;
        color: rgba(255,255,255,0.55);
        margin-bottom: 4px;
        text-transform: uppercase;
    ">AI Interface for Biopharma Lab Automation</div>
    <div style="
        font-family: 'DM Serif Display', serif;
        font-size: 24px;
        line-height: 1.1;
    ">BioInterface</div>
</div>
''', unsafe_allow_html=True)

# ── Custom styling ───────────────────────────────────────────────────────
st.markdown("""
<style>
.block-container {padding-top: 1.5rem;}
.stTabs [data-baseweb="tab-list"] {gap: 8px;}
.stTabs [data-baseweb="tab"] {padding: 8px 16px; font-weight: 500;}
div[data-testid="stMetric"] {
    background: #f8f9fb;
    border-radius: 8px;
    padding: 12px;
    border-left: 4px solid #4e79a7;
}
/* ── SIDEBAR BACKGROUND ── */
[data-testid="stSidebar"] {
    background-color: #1a2332 !important;
}

/* ── METRIC CARDS ── */
[data-testid="stSidebar"] [data-testid="stMetric"] {
    background-color: #243447 !important;
    border: 1px solid #3d5a7a !important;
    border-radius: 8px !important;
    padding: 10px 14px !important;
}

/* ── METRIC NUMBERS ── */
[data-testid="stSidebar"] [data-testid="stMetricValue"] {
    color: #ffffff !important;
    font-size: 32px !important;
    font-weight: 700 !important;
}

/* ── METRIC LABELS ── */
[data-testid="stSidebar"] [data-testid="stMetricLabel"] {
    color: #a8c4e0 !important;
    font-size: 11px !important;
    font-weight: 500 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
}

/* ── ALL SIDEBAR TEXT ── */
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stRadio label,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span {
    color: #e2eaf4 !important;
}

/* ── NAVIGATION RADIO SELECTED ── */
[data-testid="stSidebar"] [aria-checked="true"] + div,
[data-testid="stSidebar"] [aria-checked="true"] {
    color: #58a6ff !important;
    font-weight: 600 !important;
}

/* ── STATUS LINE AND FIELD LABEL ── */
[data-testid="stSidebar"] .stMarkdown p {
    color: #7eb8e8 !important;
    font-weight: 500 !important;
}

/* ── SELECTBOX LABEL ── ("FIELD" caption above the trigger) */
[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] [data-testid="stSelectbox"] label,
[data-testid="stSidebar"] [data-testid="stSelectbox"] label p {
    color: #a8c4e0 !important;
    font-size: 11px !important;
    font-weight: 500 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
}

/* ── SELECTBOX TRIGGER ── (closed-state box showing the chosen field) */
[data-testid="stSidebar"] div[data-baseweb="select"] > div {
    background-color: #243447 !important;
    border: 1px solid #3d5a7a !important;
    border-radius: 6px !important;
}
[data-testid="stSidebar"] div[data-baseweb="select"] > div > div,
[data-testid="stSidebar"] div[data-baseweb="select"] input,
[data-testid="stSidebar"] div[data-baseweb="select"] [data-baseweb="tag"],
[data-testid="stSidebar"] div[data-baseweb="select"] span {
    color: #ffffff !important;
    font-weight: 600 !important;
}
[data-testid="stSidebar"] div[data-baseweb="select"] svg {
    fill: #a8c4e0 !important;
}

/* ── Compact sidebar nav buttons ── */
[data-testid="stSidebar"] .stButton > button {
    padding: 6px 12px !important;
    font-size: 12px !important;
    text-align: left !important;
    margin: 0 !important;
    box-shadow: none !important;
    transform: none !important;
    border-radius: 4px !important;
    font-weight: 500 !important;
    background: transparent !important;
    color: #e2eaf4 !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: #243447 !important;
    color: #ffffff !important;
    transform: none !important;
    box-shadow: none !important;
}
[data-testid="stSidebar"] .stButton > button[kind="primary"] {
    background: #c84b1f !important;
    color: white !important;
    font-weight: 600 !important;
}
[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {
    background: #e56333 !important;
    color: white !important;
}

/* Dropdown menu options (portal — renders at body root, not inside sidebar) */
div[data-baseweb="popover"] ul[role="listbox"],
div[data-baseweb="menu"] ul,
ul[data-testid="stSelectboxVirtualDropdown"] {
    background-color: #243447 !important;
    border: 1px solid #3d5a7a !important;
}
div[data-baseweb="popover"] li[role="option"],
div[data-baseweb="menu"] li[role="option"],
ul[data-testid="stSelectboxVirtualDropdown"] li {
    color: #e2eaf4 !important;
    background-color: #243447 !important;
}
div[data-baseweb="popover"] li[role="option"]:hover,
div[data-baseweb="menu"] li[role="option"]:hover,
ul[data-testid="stSelectboxVirtualDropdown"] li:hover,
div[data-baseweb="popover"] li[aria-selected="true"],
ul[data-testid="stSelectboxVirtualDropdown"] li[aria-selected="true"] {
    background-color: #3d5a7a !important;
    color: #ffffff !important;
}
.badge-green  {background:#d4edda; color:#155724; border-radius:12px; padding:2px 10px; font-size:11px; font-weight:600;}
.badge-amber  {background:#fff3cd; color:#856404; border-radius:12px; padding:2px 10px; font-size:11px; font-weight:600;}
.badge-red    {background:#f8d7da; color:#721c24; border-radius:12px; padding:2px 10px; font-size:11px; font-weight:600;}
.badge-blue   {background:#cce5ff; color:#004085; border-radius:12px; padding:2px 10px; font-size:11px; font-weight:600;}
.badge-purple {background:#e8daef; color:#6c3483; border-radius:12px; padding:2px 10px; font-size:11px; font-weight:600;}
.analyst-step {background:#fff3cd; border-left:3px solid #f39c12; padding:8px 12px; margin:4px 0; border-radius:4px; font-size:13px;}
.ai-result {background:#f0f7ff; border-left:3px solid #3498db; padding:10px 14px; margin:6px 0; border-radius:4px; font-size:13px;}
.ai-badge {background:#cce5ff; color:#004085; border-radius:12px; padding:2px 10px; font-size:11px; font-weight:600;}
</style>
""", unsafe_allow_html=True)

# ── Data prep ────────────────────────────────────────────────────────────
FIELD_MAP = {
    "Biopharma / CDMO": "field_01_biopharma_v2",
    "Genomics / NGS": "field_03_genomics_ngs",
    "Drug Discovery / HTS": "field_04_drug_discovery_hts_v2",
    "Core Lab Methods": "field_05_core_lab_methods",
}

if "selected_field" not in st.session_state:
    st.session_state.selected_field = "Biopharma / CDMO"

def load_field(field_name):
    module_name = FIELD_MAP[field_name]
    if module_name in sys.modules:
        mod = importlib.reload(sys.modules[module_name])
    else:
        mod = importlib.import_module(module_name)
    for attr in ["BIOPHARMA_ASSAYS", "HTS_ASSAYS", "GENOMICS_ASSAYS",
                 "CORE_LAB_METHODS_ASSAYS"]:
        if hasattr(mod, attr):
            return getattr(mod, attr)
    return []

ASSAYS = load_field(st.session_state.selected_field)
ALL_IDS = [a["assay_id"] for a in ASSAYS]

# Cross-field combined library — used by Instrument Coverage views
def _load_all_assays():
    libs = list(BIOPHARMA_ASSAYS)
    try:
        from field_03_genomics_ngs import GENOMICS_ASSAYS as _ngs
        libs.extend(_ngs)
    except ImportError:
        pass
    try:
        from field_04_drug_discovery_hts_v2 import HTS_ASSAYS as _hts
        libs.extend(_hts)
    except ImportError:
        pass
    try:
        from field_05_core_lab_methods import CORE_LAB_METHODS_ASSAYS as _core
        libs.extend(_core)
    except ImportError:
        pass
    return libs

ALL_ASSAYS_LIBRARY = _load_all_assays()


@st.cache_data(show_spinner=False)
def get_instrument_usage_across_library(_unused_cache_key: str = "v1"):
    """Aggregate instrument usage across the entire assay library.
    Returns a dict keyed by instrument type with counts and metadata.
    """
    from rail_protocol_generator import generate_execution_plan

    usage = {}
    for assay in ALL_ASSAYS_LIBRARY:
        try:
            # inject_transport=False so the coverage view shows
            # only the assay's analytical instruments, independent
            # of which deployment context is chosen elsewhere.
            plan = generate_execution_plan(assay, inject_transport=False)
        except Exception:
            continue

        for phase in plan.get("execution_phases", []):
            inst = phase["instrument"]
            if inst == "analyst":
                continue

            if inst not in usage:
                usage[inst] = {
                    "instrument": inst,
                    "_assays_using": set(),
                    "total_steps": 0,
                    "total_duration_seconds": 0,
                    "_step_types": set(),
                }

            usage[inst]["_assays_using"].add(assay["assay_id"])
            usage[inst]["total_steps"] += len(phase["steps"])
            for step in phase["steps"]:
                usage[inst]["total_duration_seconds"] += step.get("duration_seconds", 0)
                usage[inst]["_step_types"].add(step["step_type"])

    # Convert sets to sorted lists (cache-friendly: must be JSON-serialisable)
    out = {}
    for inst, data in usage.items():
        out[inst] = {
            "instrument": data["instrument"],
            "assays_using": sorted(data["_assays_using"]),
            "assay_count": len(data["_assays_using"]),
            "total_steps": data["total_steps"],
            "total_duration_seconds": data["total_duration_seconds"],
            "step_types": sorted(data["_step_types"]),
        }
    return out


ALL_PRODUCTS = sorted(set(p for a in ASSAYS for p in a.get("product_types", [])))
ALL_DIFFS = ["easy", "medium", "complex"]
ALL_WORKBENCHES = sorted(set(a.get("workbench_id", "N/A") for a in ASSAYS))
DIFF_COLORS = {"easy": "#2ecc71", "medium": "#f39c12", "complex": "#e74c3c"}
DIFF_BADGE = {"easy": "badge-green", "medium": "badge-amber", "complex": "badge-red"}


def search_assays(query):
    q = query.lower()
    return [a for a in ASSAYS
            if q in a.get("name", "").lower()
            or q in a.get("assay_id", "").lower()
            or q in a.get("purpose", "").lower()
            or q in a.get("detection", "").lower()
            or q in a.get("environment_requirement", "").lower()
            or any(q in r.lower() for r in a.get("reagents", []))
            or any(q in i.lower() for i in a.get("instruments_needed", []))
            or any(q in p.lower() for p in a.get("product_types", []))]


def count_analyst_steps(assay):
    return len([s for s in assay.get("robot_steps", []) if "[ANALYST STEP" in s])


def assay_df():
    rows = []
    for a in ASSAYS:
        rows.append({
            "ID": a["assay_id"],
            "Name": a["name"],
            "Difficulty": a["automation_difficulty"].capitalize(),
            "Robot (min)": a.get("robot_active_minutes", 0),
            "Total (hr)": a.get("total_assay_duration_hours", 0),
            "Samples/Run": a.get("throughput_samples_per_run", 0),
            "Sample (uL)": a.get("sample_volume_uL", 0),
            "WB": a.get("workbench_id", "N/A"),
            "Detection": a.get("detection", ""),
            "Analyst Steps": count_analyst_steps(a),
            "Environment": a.get("environment_requirement", ""),
        })
    return pd.DataFrame(rows)


def build_export_text(assay):
    """
    Build a plain-text protocol file formatted for Rail System loading.
    Robot steps and analyst steps are clearly separated.
    This is the file Chase Olle's system loads directly.
    """
    lines = []
    lines.append("=" * 70)
    lines.append("RAIL SYSTEM — PROTOCOL EXPORT")
    lines.append("=" * 70)
    lines.append(f"Assay ID    : {assay['assay_id']}")
    lines.append(f"Assay name  : {assay['name']}")
    lines.append(f"Field       : {assay['field']}")
    lines.append(f"Workbench   : {assay.get('workbench_id', 'N/A')}")
    lines.append(f"Difficulty  : {assay['automation_difficulty'].upper()}")
    lines.append(f"Robot time  : {assay.get('robot_active_minutes', 0)} minutes")
    lines.append(f"Throughput  : {assay.get('throughput_notes', str(assay.get('throughput_samples_per_run', 'N/A')) + ' samples/run')}")
    lines.append(f"Detection   : {assay.get('detection', 'N/A')}")
    lines.append(f"Environment : {assay.get('environment_requirement', 'N/A')}")
    lines.append(f"Regulatory  : {', '.join(assay.get('regulatory', []))}")
    lines.append("")
    lines.append("PURPOSE")
    lines.append("-" * 70)
    lines.append(assay.get("purpose", ""))
    lines.append("")
    lines.append("ROBOT STEP INSTRUCTIONS")
    lines.append("-" * 70)

    robot_step_num = 1
    analyst_step_num = 1
    for step in assay.get("robot_steps", []):
        if "[ANALYST STEP" in step:
            lines.append(f"  [ANALYST {analyst_step_num:02d}] {step}")
            analyst_step_num += 1
        else:
            lines.append(f"  Step {robot_step_num:02d}: {step}")
            robot_step_num += 1

    lines.append("")
    lines.append("DECK LAYOUT")
    lines.append("-" * 70)
    deck = assay.get("robot_deck_layout", {})
    if deck:
        for pos, desc in deck.items():
            lines.append(f"  {pos:<12} {desc}")
    else:
        lines.append("  No deck layout defined.")

    lines.append("")
    lines.append("ACCEPTANCE CRITERIA")
    lines.append("-" * 70)
    ac = assay.get("acceptance_criteria", {})
    if ac:
        for k, v in ac.items():
            lines.append(f"  {k.replace('_', ' ').upper():<45} {v}")
    else:
        lines.append("  No acceptance criteria defined.")

    lines.append("")
    lines.append("INSTRUMENTS REQUIRED")
    lines.append("-" * 70)
    for inst in assay.get("instruments_needed", []):
        lines.append(f"  - {inst}")

    lines.append("")
    lines.append("REAGENTS REQUIRED")
    lines.append("-" * 70)
    for r in assay.get("reagents", []):
        lines.append(f"  - {r}")

    lines.append("")
    lines.append("NOTES")
    lines.append("-" * 70)
    lines.append(assay.get("notes", "None."))
    lines.append("")
    lines.append("=" * 70)
    lines.append("END OF PROTOCOL — BioInterface v1.0")
    lines.append("=" * 70)

    return "\n".join(lines)


def build_automate_export(assay):
    lines = []
    lines.append("ACCURIS AUTOMATE 96 — PROTOCOL INSTRUCTIONS")
    lines.append(f"Assay     : {assay['name']} ({assay['assay_id']})")
    lines.append(f"Field     : {assay['field']}")
    lines.append(f"Head      : {assay.get('automate_96_head', 'not applicable')}")
    lines.append(f"Head note : {assay.get('automate_96_head_note', '')}")
    lines.append("=" * 60)

    steps = assay.get("robot_steps", [])
    tagged = assay.get("automate_96_steps", [])

    if not tagged:
        lines.append("No AutoMATE 96 steps for this assay.")
        lines.append("This assay uses HPLC, meters, gels, or")
        lines.append("other instruments not served by the AutoMATE 96.")
        return "\n".join(lines)

    lines.append(f"AutoMATE 96 executes {len(tagged)} of "
                 f"{len(steps)} total steps")
    lines.append("")

    for i, step in enumerate(steps, 1):
        if i in tagged:
            lines.append(f"Step {i:02d} [AUTOMATE 96]: {step}")

    lines.append("")
    lines.append("─" * 60)
    lines.append("DECK POSITIONS SERVICED BY AUTOMATE 96")
    lines.append("─" * 60)
    assignment = assay.get("instrument_assignment", {})
    for pos in assignment.get("automate_96", []):
        deck = assay.get("robot_deck_layout", {})
        desc = deck.get(pos, "")
        lines.append(f"  {pos}: {desc}")

    lines.append("")
    lines.append("Generated by BioInterface v1.0")
    return "\n".join(lines)


# ── Sidebar ──────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### \U0001f9ea Assay Library")
    st.caption(f"BioInterface v1.0 \u2022 {st.session_state.selected_field}")
    st.divider()

    # ── Phase 1 restructure: three top-level modes ─────────────────
    _MODE_HEADER_STYLE = (
        "font-family: DM Mono, monospace; font-size: 10px; "
        "letter-spacing: 0.16em; text-transform: uppercase; "
        "color: rgba(255,255,255,0.55); margin: 12px 0 6px 0;"
    )

    st.markdown(
        f'<div style="{_MODE_HEADER_STYLE}">Choose a mode</div>',
        unsafe_allow_html=True,
    )

    # Consume any pending nav_request BEFORE the mode/section radios are
    # instantiated. Writing to a widget's session_state key after the widget
    # renders raises StreamlitAPIException; writing before is allowed.
    _RUN_SECTIONS = {
        "Custom Protocol Builder",
        "Pipeline Runner",
        "Upload Run Data",
        "Experiment Wizard",
        "System Run Planner",
    }
    _nav_request = st.session_state.pop("nav_request", None)
    if _nav_request in _RUN_SECTIONS:
        st.session_state["bi_mode"] = "🧪 Run an Experiment"
        st.session_state["bi_run_section"] = _nav_request

    mode = st.radio(
        "Mode",
        [
            "🧪 Run an Experiment",
            "📚 Explore the Library",
            "⚙ Configure",
        ],
        label_visibility="collapsed",
        key="bi_mode",
    )

    st.markdown("---")

    if mode == "🧪 Run an Experiment":
        # Wizard is the default landing page — sub-nav lists alternative tools.
        # The header is dimmer than the explore mini-headers to signal optional.
        st.markdown(
            '<div style="font-family: DM Mono, monospace; '
            'font-size: 10px; letter-spacing: 0.16em; '
            'text-transform: uppercase; '
            'color: rgba(255,255,255,0.4); '
            'margin: 14px 0 4px 0;">'
            'Or jump to a tool</div>',
            unsafe_allow_html=True,
        )
        _run_options = [
            "Pipeline Runner",
            "Upload Run Data",
            "Custom Protocol Builder",
            "Experiment Wizard",
            "System Run Planner",
        ]
        # Clear stale stored selection (e.g. "New Run" from a prior version)
        # so it doesn't error against the trimmed options list.
        if st.session_state.get("bi_run_section") not in _run_options:
            st.session_state.pop("bi_run_section", None)
        section = st.radio(
            "Run section",
            _run_options,
            index=None,
            label_visibility="collapsed",
            key="bi_run_section",
        )
    elif mode == "📚 Explore the Library":
        if "bi_explore_section" not in st.session_state:
            st.session_state.bi_explore_section = "Browse Assays"

        # ── Group 1: Search & Discover ─────────────────────────────
        st.markdown(
            '<div style="font-family: DM Mono, monospace; '
            'font-size: 10px; letter-spacing: 0.16em; '
            'text-transform: uppercase; '
            'color: rgba(255,255,255,0.55); '
            'margin: 8px 0 4px 0;">'
            '🔍 Search & Discover</div>',
            unsafe_allow_html=True,
        )
        search_options = ["Ask BioInterface", "Search"]
        search_choice = st.radio(
            "Search & discover",
            search_options,
            index=(
                search_options.index(st.session_state.bi_explore_section)
                if st.session_state.bi_explore_section in search_options
                else None
            ),
            label_visibility="collapsed",
            key="bi_explore_search_grp",
        )
        if search_choice and search_choice != st.session_state.bi_explore_section:
            st.session_state.bi_explore_section = search_choice
            st.rerun()

        # ── Group 2: Browse the Catalog ────────────────────────────
        st.markdown(
            '<div style="font-family: DM Mono, monospace; '
            'font-size: 10px; letter-spacing: 0.16em; '
            'text-transform: uppercase; '
            'color: rgba(255,255,255,0.55); '
            'margin: 14px 0 4px 0;">'
            '📋 Browse the Catalog</div>',
            unsafe_allow_html=True,
        )
        catalog_options = [
            "Browse Assays", "Assay Detail", "Compare", "Analyst Steps",
        ]
        catalog_choice = st.radio(
            "Browse catalog",
            catalog_options,
            index=(
                catalog_options.index(st.session_state.bi_explore_section)
                if st.session_state.bi_explore_section in catalog_options
                else None
            ),
            label_visibility="collapsed",
            key="bi_explore_catalog_grp",
        )
        if catalog_choice and catalog_choice != st.session_state.bi_explore_section:
            st.session_state.bi_explore_section = catalog_choice
            st.rerun()

        # ── Group 3: Library Insights ──────────────────────────────
        st.markdown(
            '<div style="font-family: DM Mono, monospace; '
            'font-size: 10px; letter-spacing: 0.16em; '
            'text-transform: uppercase; '
            'color: rgba(255,255,255,0.55); '
            'margin: 14px 0 4px 0;">'
            '📊 Library Insights</div>',
            unsafe_allow_html=True,
        )
        insights_options = [
            "Dashboard", "Instrument Coverage", "AI Intelligence",
        ]
        insights_choice = st.radio(
            "Library insights",
            insights_options,
            index=(
                insights_options.index(st.session_state.bi_explore_section)
                if st.session_state.bi_explore_section in insights_options
                else None
            ),
            label_visibility="collapsed",
            key="bi_explore_insights_grp",
        )
        if insights_choice and insights_choice != st.session_state.bi_explore_section:
            st.session_state.bi_explore_section = insights_choice
            st.rerun()

        section = st.session_state.bi_explore_section
    else:  # "⚙ Configure"
        st.markdown(
            f'<div style="{_MODE_HEADER_STYLE}">Configure</div>',
            unsafe_allow_html=True,
        )
        section = st.radio(
            "Configure section",
            ["Deck Designer"],
            label_visibility="collapsed",
            key="bi_config_section",
        )

    st.session_state.section = section

    st.divider()
    selected_field = st.selectbox(
        "Field",
        list(FIELD_MAP.keys()),
        index=list(FIELD_MAP.keys()).index(st.session_state.selected_field),
        key="field_selector",
    )
    if selected_field != st.session_state.selected_field:
        st.session_state.selected_field = selected_field
        ASSAYS = load_field(selected_field)
        ALL_IDS = [a["assay_id"] for a in ASSAYS]
        st.rerun()

    st.divider()
    search_term = st.text_input("\U0001f50d Quick search", "", key="sidebar_search")

st.sidebar.markdown("---")
st.sidebar.markdown("**Session**")

if st.sidebar.button("📋 Export Session Report", key="export_session"):
    import datetime as _dt

    report_lines = [
        "=" * 60,
        "BIOINTERFACE — SESSION REPORT",
        "=" * 60,
        f"Generated: {_dt.datetime.now():%Y-%m-%d %H:%M}",
        f"Field: {st.session_state.get('selected_field', '')}",
        f"Selected nav: {section}",
        "",
    ]

    conv = st.session_state.get("ask_conversation", [])
    if conv:
        report_lines.append("=" * 60)
        report_lines.append("ASK BIOINTERFACE CONVERSATION")
        report_lines.append("=" * 60)
        for i, turn in enumerate(conv, 1):
            report_lines.append("")
            report_lines.append(f"Turn {i}:")
            report_lines.append(f"Q: {turn['query']}")
            if turn.get("expanded_query") and turn["expanded_query"] != turn["query"]:
                report_lines.append(f"Expanded: {turn['expanded_query']}")
            report_lines.append(f"A: {turn.get('answer_summary', '')[:500]}")
            if turn.get("matched_assay"):
                report_lines.append(f"Matched assay: {turn['matched_assay']}")
        report_lines.append("")

    if "planner_select" in st.session_state:
        sel = st.session_state.planner_select
        if sel:
            report_lines.append("=" * 60)
            report_lines.append("RUN PLANNER SELECTION")
            report_lines.append("=" * 60)
            for s in sel:
                report_lines.append(f"  • {s}")
            report_lines.append("")

    report_lines.extend([
        "=" * 60,
        "PLATFORM CAPABILITIES USED",
        "=" * 60,
        "• Field-aware assay library (30 assays)",
        "• PyLabRobot protocol generator",
        "• 202-chunk RAG corpus over ICH/FDA guidelines",
        "• Hybrid search + Claude reranking",
        "• Multi-hop query decomposition",
        "• AI quality correlation across batches",
        "• AutoMATE 96 integration with head selection",
        "• System Run Planner with Gantt visualisation",
        "",
        "Generated by BioInterface v1.0",
    ])

    report_text = "\n".join(report_lines)

    st.sidebar.download_button(
        "⬇ Download report",
        data=report_text,
        file_name=f"biointerface_session_{_dt.datetime.now():%Y%m%d_%H%M}.txt",
        mime="text/plain",
        key="dl_session_report",
    )

# ── Default landing page for Run mode ────────────────────────────────────
# Run mode's sub-nav uses index=None so no sub-item is selected by default.
# When that's the case, the wizard is the natural landing page.
if mode == "🧪 Run an Experiment" and not section:
    section = "New Run"

# ── Quick search override ────────────────────────────────────────────────
if search_term.strip():
    section = "Search"


# ═══════════════════════════════════════════════════════════════════════
#  SECTION: DASHBOARD
# ═══════════════════════════════════════════════════════════════════════
if section == "Ask BioInterface":
    st.title("🧠 Ask BioInterface")
    st.caption(
        "Ask any question about biopharma analytical methods. "
        "BioInterface searches its knowledge corpus (ICH, FDA, EMA "
        "guidelines + 30 assay library) and answers in two channels — "
        "scientist explanation and robot protocol."
    )

    if "ask_conversation" not in st.session_state:
        st.session_state.ask_conversation = []

    if st.session_state.ask_conversation:
        with st.expander(
            f"💬 Conversation history ({len(st.session_state.ask_conversation)} turns)",
            expanded=False,
        ):
            for i, turn in enumerate(st.session_state.ask_conversation, 1):
                st.markdown(f"**Turn {i}:**")
                st.markdown(f"❓ {turn['query']}")
                st.markdown(f"💬 *{turn.get('answer_summary', '')[:300]}...*")
                st.markdown("---")

        if st.button("🗑 Clear conversation", key="clear_conv"):
            st.session_state.ask_conversation = []
            st.rerun()

    st.markdown("---")

    st.caption("Try one of these:")
    ex1, ex2, ex3 = st.columns(3)

    example_queries = {
        "ex_1": "How do I detect aggregation in my mAb and what does the robot need to do?",
        "ex_2": "What ICH validation parameters apply to a quantitative IEX charge variant assay?",
        "ex_3": "I need to release-test a mAb batch — what assays should I run?",
    }

    if "ask_query" not in st.session_state:
        st.session_state.ask_query = ""

    if ex1.button("🔬 Aggregation in mAb", key="btn_ex1", use_container_width=True):
        st.session_state.ask_query = example_queries["ex_1"]
    if ex2.button("📋 ICH validation params", key="btn_ex2", use_container_width=True):
        st.session_state.ask_query = example_queries["ex_2"]
    if ex3.button("✅ mAb release testing", key="btn_ex3", use_container_width=True):
        st.session_state.ask_query = example_queries["ex_3"]

    query = st.text_area(
        "Your question",
        value=st.session_state.ask_query,
        height=100,
        placeholder="e.g. What is Z-factor and what threshold should I use to accept an HTS plate?",
        key="ask_input",
    )

    col_btn1, col_btn2 = st.columns([3, 1])
    with col_btn1:
        ask_button = st.button(
            "Ask BioInterface",
            type="primary",
            disabled=not AI_AVAILABLE or not query.strip(),
            use_container_width=True,
        )
    with col_btn2:
        if st.button("Clear", use_container_width=True):
            st.session_state.ask_query = ""
            st.rerun()

    if not AI_AVAILABLE:
        st.warning("AI not configured. Add ANTHROPIC_API_KEY and VOYAGE_API_KEY to .env file.")

    if ask_button and query.strip():
        with st.spinner(
            "BioInterface AI is searching 202 corpus chunks "
            "and generating a grounded answer..."
        ):
            from ai_layer import expand_query_with_context, search_corpus_multihop
            expansion = expand_query_with_context(query, st.session_state.ask_conversation)
            retrieval_query = expansion["expanded_query"]

            if expansion["is_followup"] and retrieval_query != query:
                with st.expander("🔄 Follow-up detected — expanded query"):
                    st.caption(f"**Original:** {query}")
                    st.caption(f"**Expanded for retrieval:** {retrieval_query}")
                    st.caption(f"_{expansion.get('reasoning', '')}_")

            multihop_result = search_corpus_multihop(retrieval_query, top_k=5)
            chunks = multihop_result["chunks"]
            decomposition = multihop_result["decomposition"]

            from ai_layer import retrieval_quality_check, suggest_related_topics
            quality = retrieval_quality_check(chunks)

            if quality["recommendation"] == "refuse":
                st.error(
                    "🚫 **Out of corpus** — BioInterface does not have authoritative "
                    "information on this topic"
                )
                st.markdown(f"**Why:** {quality['reason']}")
                st.markdown(
                    f"**Top retrieval similarity:** {quality['top_similarity']:.2f} "
                    f"(threshold: 0.35)"
                )
                st.markdown(f"**Relevant chunks found:** {quality['n_relevant']}")

                with st.spinner("BioInterface is searching 202 corpus chunks for related topics..."):
                    suggestions = suggest_related_topics(query)

                if suggestions:
                    st.markdown("---")
                    st.markdown("**Topics you could ask about instead:**")
                    for s in suggestions:
                        st.markdown(f"• **{s['topic']}** — {s['why_related']}")
                else:
                    st.info(
                        "No closely related topics found in corpus. "
                        "Try rephrasing or check if your topic falls within "
                        "ICH/FDA biopharma analytical scope."
                    )
                st.stop()

            elif quality["recommendation"] == "warn":
                st.warning(
                    f"⚠ **Borderline retrieval** — answer may be partial. "
                    f"Top similarity: {quality['top_similarity']:.2f}"
                )
                st.caption(quality["reason"])

            # Calibrated confidence based on retrieval signals
            from ai_layer import compute_retrieval_confidence, classify_query_intent
            intent_info = classify_query_intent(query)
            retrieval_conf = compute_retrieval_confidence(chunks, intent_info)

            if not chunks:
                st.error("No relevant chunks retrieved. The corpus may not be embedded yet.")
            else:
                context_text = "\n\n---\n\n".join([
                    f"[Source: {c['source_file']} | Relevance: {c['similarity']:.2f}]\n{c['content']}"
                    for c in chunks
                ])

                from ai_layer import _call_claude

                system_prompt = """You are BioInterface — an AI interface between biopharma scientists and lab robots. Given a scientist's question and retrieved context from regulatory documents and the assay library, generate a structured response with TWO channels.

SCIENTIST CHANNEL — plain English explanation calibrated to a biopharma scientist. Cite specific sources from the retrieved context. Be precise about what the assay measures, what the result means, and what acceptance criteria apply.

ROBOT CHANNEL — if the question requires running a physical assay, generate a structured protocol outline. For assays in the BioInterface library (BIO_001 through BIO_018, HTS_001 through HTS_012), reference the assay ID directly. For novel assays not in the library, generate a numbered step list with volumes, timing, and acceptance criteria drawn from the source material.

Return JSON only — no markdown fences:
{
  "scientist_answer": "Plain English explanation...",
  "robot_required": true,
  "robot_channel": {
    "matched_assay_id": "BIO_003",
    "is_novel": false,
    "protocol_summary": "Brief description...",
    "key_steps": ["Step 1...", "Step 2..."],
    "acceptance_criteria": "From the source material..."
  },
  "sources_cited": [
    {"source": "ICH Q6B Guideline.pdf", "relevance": "explains why this source matters"}
  ],
  "confidence": "high"
}

If robot_required is false, set robot_channel to null.
Confidence options: high, medium, low."""

                user_message = f"""Question: {query}

Retrieved context from BioInterface corpus:
{context_text}"""

                try:
                    response = _call_claude(
                        system_prompt,
                        user_message,
                        expect_json=True,
                        max_tokens=4000,
                        model="claude-sonnet-4-6",
                    )
                    import json
                    result = json.loads(response)

                    st.markdown("---")

                    # Use calibrated retrieval confidence, not Claude's self-report
                    conf = retrieval_conf["confidence"]
                    conf_score = retrieval_conf["score"]
                    conf_color = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(conf, "⚪")
                    st.markdown(
                        f"**Confidence:** {conf_color} {conf.upper()} ({conf_score}/100) | "
                        f"**Sources retrieved:** {len(chunks)}"
                    )

                    with st.expander("Why this confidence?"):
                        st.caption(retrieval_conf["reasoning"])
                        f = retrieval_conf["factors"]
                        fc1, fc2, fc3, fc4 = st.columns(4)
                        fc1.metric("Top relevance", f"{f['top_relevance']:.2f}")
                        fc2.metric("Score gap", f"{f['score_gap']:.2f}")
                        fc3.metric("Relevant chunks", f["n_high_relevance"])
                        fc4.metric("Source diversity", f["source_diversity"])

                    sc_col, rc_col = st.columns(2)

                    with sc_col:
                        st.subheader("🔬 Scientist Channel")
                        st.markdown(result.get("scientist_answer", "No answer generated."))

                        if result.get("sources_cited"):
                            st.markdown("---")
                            st.caption("**Sources cited:**")
                            chunk_sections = {
                                c["source_file"]: (c.get("metadata") or {}).get("section", "")
                                for c in chunks
                            }
                            for s in result["sources_cited"]:
                                section = chunk_sections.get(s.get("source", ""), "")
                                section_display = (
                                    f" — *{section}*"
                                    if section and section != "Preamble"
                                    else ""
                                )
                                st.markdown(
                                    f"📄 **{s.get('source', '')}**{section_display}  \n"
                                    f"*{s.get('relevance', '')}*"
                                )

                    with rc_col:
                        st.subheader("🤖 Robot Channel")
                        rc = result.get("robot_channel")
                        if not result.get("robot_required", False) or rc is None:
                            st.info(
                                "This question does not require a physical robot protocol "
                                "— informational only."
                            )
                        else:
                            if rc.get("is_novel"):
                                st.warning(
                                    "⚠ Novel assay — not in library. Protocol generated from "
                                    "regulatory sources."
                                )
                            else:
                                aid = rc.get("matched_assay_id", "Unknown")
                                st.success(f"✓ Matched library assay: **{aid}**")

                            st.markdown(f"**{rc.get('protocol_summary', '')}**")

                            steps = rc.get("key_steps", [])
                            if steps:
                                st.markdown("**Key steps:**")
                                for i, s in enumerate(steps, 1):
                                    st.markdown(f"{i}. {s}")

                            ac = rc.get("acceptance_criteria", "")
                            if ac:
                                st.markdown("**Acceptance criteria:**")
                                st.markdown(ac)

                            if not rc.get("is_novel"):
                                aid = rc.get("matched_assay_id")
                                matched = next((a for a in ASSAYS if a["assay_id"] == aid), None)
                                if matched:
                                    code = generate_protocol(matched)
                                    st.download_button(
                                        f"⬇ Export {aid} PyLabRobot Protocol",
                                        data=code,
                                        file_name=f"{aid.lower()}_protocol.py",
                                        mime="text/x-python",
                                        key=f"ask_export_{aid}",
                                    )

                    # Save turn to conversation history
                    answer_text = result.get("scientist_answer", "")
                    st.session_state.ask_conversation.append({
                        "query": query,
                        "expanded_query": retrieval_query,
                        "answer_summary": answer_text[:500],
                        "matched_assay": (
                            (result.get("robot_channel") or {}).get("matched_assay_id")
                        ),
                    })
                    if len(st.session_state.ask_conversation) > 5:
                        st.session_state.ask_conversation = (
                            st.session_state.ask_conversation[-5:]
                        )

                    st.markdown("---")
                    if decomposition.get("was_decomposed"):
                        with st.expander(
                            f"🔬 Multi-hop retrieval — "
                            f"{len(decomposition['sub_questions'])} sub-questions"
                        ):
                            st.caption(f"Strategy: **{decomposition['synthesis_strategy']}**")
                            if decomposition.get("reasoning"):
                                st.caption(decomposition["reasoning"])
                            st.markdown("**Sub-questions:**")
                            for i, sq in enumerate(decomposition["sub_questions"], 1):
                                st.markdown(f"{i}. {sq}")

                    with st.expander(f"🔍 View retrieved chunks ({len(chunks)})"):
                        for i, c in enumerate(chunks, 1):
                            section = (c.get("metadata") or {}).get("section", "")
                            section_str = (
                                f" → {section}"
                                if section and section != "Preamble"
                                else ""
                            )
                            st.markdown(
                                f"**{i}. {c['source_file']}**{section_str}  \n"
                                f"*similarity: {c['similarity']:.3f}*"
                            )
                            st.markdown(f"_{c['content'][:400]}..._")
                            st.markdown("---")

                except Exception as e:
                    st.error(f"Error generating answer: {e}")


elif section == "New Run":
    st.title("🧪 New Experiment Run")
    st.caption("Configure and execute an experiment in 4 steps.")

    # ── Wizard state ──────────────────────────────────────────────
    if "newrun_step" not in st.session_state:
        st.session_state.newrun_step = 1
    if "newrun_assay" not in st.session_state:
        st.session_state.newrun_assay = None
    if "newrun_custom_protocol" not in st.session_state:
        st.session_state.newrun_custom_protocol = None
    if "newrun_deck" not in st.session_state:
        st.session_state.newrun_deck = None
    if "newrun_deployment" not in st.session_state:
        st.session_state.newrun_deployment = "manual"

    current_step = st.session_state.newrun_step

    # ── Stepper ───────────────────────────────────────────────────
    steps_meta = [
        (1, "What to run", "📋"),
        (2, "Pick deck", "🛠"),
        (3, "Deployment", "🚀"),
        (4, "Review & run", "✅"),
    ]
    stepper_html = (
        '<div style="display:flex; align-items:center; gap:6px; '
        'padding:14px; background:white; border:1px solid #d4cfc4; '
        'border-radius:10px; margin-bottom:24px;">'
    )
    for sn, slabel, semoji in steps_meta:
        if sn < current_step:
            bg, color, badge = "#1a6b4a", "white", "✓"
        elif sn == current_step:
            bg, color, badge = "#1a3a5c", "white", str(sn)
        else:
            bg, color, badge = "#d4cfc4", "#6b6560", str(sn)
        stepper_html += (
            f'<div style="display:flex; align-items:center; gap:8px; '
            f'padding:8px 14px; background:{bg}; color:{color}; '
            f'border-radius:6px; flex:1;">'
            f'<div style="background:rgba(255,255,255,0.2); '
            f'padding:2px 8px; border-radius:10px; '
            f'font-family:DM Mono,monospace; font-size:11px; '
            f'font-weight:600;">{badge}</div>'
            f'<div style="font-size:13px; font-weight:500;">'
            f'{semoji} {slabel}</div></div>'
        )
        if sn < 4:
            stepper_html += (
                '<div style="width:14px; height:2px; background:#d4cfc4;"></div>'
            )
    stepper_html += "</div>"
    st.markdown(stepper_html, unsafe_allow_html=True)

    # ════════════ STEP 1 — Pick what to run ════════════
    if current_step == 1:
        st.subheader("Step 1 — What do you want to run?")
        st.caption(
            "Pick from the library OR describe a custom protocol "
            "in plain English."
        )

        s1c1, s1c2 = st.columns(2)

        with s1c1:
            st.markdown("**📚 From library**")

            # The wizard's field selectbox is a live mirror of the sidebar's
            # `selected_field`. Pre-render reconcile pulls sidebar→wizard;
            # on_change pushes wizard→sidebar so the rest of the app
            # (assay list, AI status) stays consistent.
            def _sync_wizard_field_to_sidebar():
                _new = st.session_state.get("nr_field")
                if _new and _new != st.session_state.selected_field:
                    st.session_state.selected_field = _new

            _field_options_nr = list(FIELD_MAP.keys())
            if (
                st.session_state.get("nr_field")
                != st.session_state.selected_field
            ):
                st.session_state["nr_field"] = st.session_state.selected_field

            field_choice = st.selectbox(
                "Field",
                _field_options_nr,
                key="nr_field",
                on_change=_sync_wizard_field_to_sidebar,
            )

            field_map_nr = {
                "Biopharma / CDMO": ("field_01_biopharma_v2", "BIOPHARMA_ASSAYS"),
                "Genomics / NGS": ("field_03_genomics_ngs", "GENOMICS_ASSAYS"),
                "Drug Discovery / HTS": ("field_04_drug_discovery_hts_v2", "HTS_ASSAYS"),
                "Core Lab Methods": ("field_05_core_lab_methods", "CORE_LAB_METHODS_ASSAYS"),
            }
            mod_name, list_name = field_map_nr[field_choice]

            try:
                mod = __import__(mod_name)
                assay_list = getattr(mod, list_name)
            except Exception as _e:
                st.error(f"Could not load {field_choice}: {_e}")
                assay_list = []

            if assay_list:
                assay_labels = [
                    f"{a['assay_id']} — {a['name']}" for a in assay_list
                ]
                picked_label = st.selectbox(
                    "Assay",
                    ["(none)"] + assay_labels,
                    key="nr_assay_label",
                )
                if picked_label != "(none)":
                    idx = assay_labels.index(picked_label)
                    chosen = assay_list[idx]
                    st.session_state.newrun_assay = chosen
                    st.session_state.newrun_custom_protocol = None
                    st.success(f"✓ {chosen['name']}")
                    st.caption(
                        f"Steps: {len(chosen.get('protocol_steps_v3', []))} · "
                        f"Difficulty: {chosen.get('automation_difficulty', '—')}"
                    )

        with s1c2:
            st.markdown("**🤖 Or describe a custom protocol**")
            custom_text = st.text_area(
                "Describe steps in plain English",
                height=200,
                placeholder=(
                    "1. Add 100 uL buffer to all wells\n"
                    "2. Mix at 600 rpm for 30 sec\n"
                    "3. Incubate at 37C for 15 min\n"
                    "4. Read absorbance at 450 nm"
                ),
                key="nr_custom_text",
            )

            if st.button(
                "🤖 Parse custom protocol",
                disabled=not custom_text.strip() or not AI_AVAILABLE,
                use_container_width=True,
                key="nr_parse_btn",
            ):
                with st.spinner("BioInterface AI is parsing..."):
                    from ai_layer import parse_custom_protocol
                    parsed = parse_custom_protocol(custom_text)
                if parsed.get("parsed_steps"):
                    custom_assay = {
                        "assay_id": "CUSTOM",
                        "name": "Custom Protocol",
                        "field": "Custom",
                        "protocol_steps_v3": parsed["parsed_steps"],
                        "automation_difficulty": "moderate",
                        "instruments_needed": parsed.get("instruments_needed", []),
                    }
                    st.session_state.newrun_custom_protocol = custom_assay
                    st.session_state.newrun_assay = None
                    st.success(f"✓ Parsed {len(parsed['parsed_steps'])} steps")
                else:
                    st.error("Could not parse the input")

        st.markdown("---")
        if st.session_state.newrun_assay:
            st.info(
                f"**Current selection:** "
                f"{st.session_state.newrun_assay['name']} (library)"
            )
        elif st.session_state.newrun_custom_protocol:
            st.info(
                f"**Current selection:** Custom Protocol "
                f"({len(st.session_state.newrun_custom_protocol['protocol_steps_v3'])} steps)"
            )
        else:
            st.warning(
                "Pick from library OR parse a custom protocol to continue."
            )

        nav_c1, nav_c2 = st.columns([5, 1])
        with nav_c2:
            can_continue = (
                st.session_state.newrun_assay
                or st.session_state.newrun_custom_protocol
            )
            if st.button(
                "Next →",
                type="primary",
                disabled=not can_continue,
                use_container_width=True,
                key="nr_next_1",
            ):
                st.session_state.newrun_step = 2
                st.rerun()

    # ════════════ STEP 2 — Pick deck ════════════
    elif current_step == 2:
        st.subheader("Step 2 — Which deck layout?")
        st.caption(
            "Optional. Select a saved deck so generated code uses your "
            "real position assignments."
        )

        from supabase import create_client as _cc_nr
        import os as _os_nr

        try:
            _sb_nr = _cc_nr(
                _os_nr.environ.get("SUPABASE_URL"),
                _os_nr.environ.get("SUPABASE_KEY"),
            )
            decks = _sb_nr.table("deck_configurations").select("*").order(
                "updated_at", desc=True
            ).execute().data
        except Exception as _e:
            st.warning(f"Could not load decks: {_e}")
            decks = []

        deck_labels = ["(No deck — use placeholders)"] + [
            f"{d['name']} ({d['deck_type']})" for d in decks
        ]
        chosen_label = st.selectbox("Deck", deck_labels, key="nr_deck_label")

        if chosen_label == "(No deck — use placeholders)":
            st.session_state.newrun_deck = None
            st.info(
                "Generated code will use placeholder positions. "
                "You can edit them after download."
            )
        else:
            idx = deck_labels.index(chosen_label) - 1
            st.session_state.newrun_deck = decks[idx]
            svg = deck_designer.render_deck_svg(
                decks[idx]["positions"], decks[idx]["deck_type"]
            )
            st.markdown(svg, unsafe_allow_html=True)

        st.markdown("---")
        st.caption(
            "Don't have a deck configured yet? Open Deck Designer "
            "from the Configure menu (switch modes in sidebar)."
        )

        nav_c1, nav_c2, nav_c3 = st.columns([1, 4, 1])
        with nav_c1:
            if st.button("← Back", use_container_width=True, key="nr_back_2"):
                st.session_state.newrun_step = 1
                st.rerun()
        with nav_c3:
            if st.button(
                "Next →",
                type="primary",
                use_container_width=True,
                key="nr_next_2",
            ):
                st.session_state.newrun_step = 3
                st.rerun()

    # ════════════ STEP 3 — Deployment ════════════
    elif current_step == 3:
        st.subheader("Step 3 — How will it run?")
        st.caption(
            "Pick the deployment context. Affects how plate transitions "
            "between instruments are handled in the generated code."
        )

        deploy_options = [
            (
                "manual", "👤 Manual",
                "Analyst transfers plates between instruments. "
                "~60 sec per transition.",
            ),
            (
                "robotic_arm", "🦾 Robotic arm",
                "Hamilton VANTAGE-style integrated workcell. "
                "~30 sec per transition.",
            ),
            (
                "rail_robot", "🚊 Rail robot",
                "rail-based transport system. "
                "~20 sec per transition.",
            ),
            (
                "scheduler", "⚙ Scheduler",
                "UniteLabs-style centralized scheduler. "
                "~25 sec per transition.",
            ),
        ]

        s3_cols = st.columns(4)
        for i, (val, label, desc) in enumerate(deploy_options):
            with s3_cols[i]:
                is_selected = st.session_state.newrun_deployment == val
                bg = "#1a3a5c" if is_selected else "white"
                color = "white" if is_selected else "#1a3a5c"

                st.markdown(
                    f'<div style="background:{bg}; color:{color}; '
                    f'border:2px solid #1a3a5c; border-radius:8px; '
                    f'padding:14px; min-height:120px;">'
                    f'<div style="font-weight:600; font-size:14px; '
                    f'margin-bottom:8px;">{label}</div>'
                    f'<div style="font-size:11px; opacity:0.85; '
                    f'line-height:1.5;">{desc}</div></div>',
                    unsafe_allow_html=True,
                )

                if st.button(
                    "Select" if not is_selected else "✓ Selected",
                    use_container_width=True,
                    key=f"nr_deploy_{val}",
                ):
                    st.session_state.newrun_deployment = val
                    st.rerun()

        st.markdown("---")
        nav_c1, nav_c2, nav_c3 = st.columns([1, 4, 1])
        with nav_c1:
            if st.button("← Back", use_container_width=True, key="nr_back_3"):
                st.session_state.newrun_step = 2
                st.rerun()
        with nav_c3:
            if st.button(
                "Next →",
                type="primary",
                use_container_width=True,
                key="nr_next_3",
            ):
                st.session_state.newrun_step = 4
                st.rerun()

    # ════════════ STEP 4 — Review and execute ════════════
    elif current_step == 4:
        st.subheader("Step 4 — Review and run")

        active_assay = (
            st.session_state.newrun_assay
            or st.session_state.newrun_custom_protocol
        )
        deck = st.session_state.newrun_deck
        deploy = st.session_state.newrun_deployment

        from rail_protocol_generator import generate_execution_plan as _gen_plan_nr
        plan = _gen_plan_nr(active_assay, deployment_context=deploy)

        st.markdown("**📋 Run summary**")
        sm_c1, sm_c2, sm_c3, sm_c4 = st.columns(4)
        sm_c1.metric("Total steps", len(plan["all_steps"]))
        sm_c2.metric("Duration", f"{plan['total_duration_minutes']:.1f} min")
        sm_c3.metric("Instruments", len(plan["instruments_required"]))
        sm_c4.metric("Transports", plan["transport_steps_count"])

        st.markdown(
            f"**Assay:** {active_assay['name']}  \n"
            f"**Deck:** {deck['name'] if deck else 'Placeholders'}  \n"
            f"**Deployment:** `{deploy}`"
        )

        with st.expander("📊 Pipeline preview"):
            html = pipeline_visualizer.render_pipeline_html(
                plan["all_steps"], step_statuses={}, orientation="vertical"
            )
            st.markdown(html, unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("**Choose action:**")

        ac1, ac2, ac3 = st.columns(3)

        with ac1:
            if st.button(
                "▶ Run Pipeline (Simulated)",
                type="primary",
                use_container_width=True,
                key="nr_run",
            ):
                import datetime as _dt_nr
                st.session_state.active_pipeline = {
                    "run_id": f"RUN-{_dt_nr.datetime.now():%Y%m%d-%H%M%S}",
                    "assay": active_assay,
                    "deployment": deploy,
                    "steps": plan["all_steps"],
                    "started_at": _dt_nr.datetime.now().isoformat(),
                    "speed_multiplier": 0.01,
                }
                st.session_state.pipeline_step_statuses = {}
                st.session_state.pipeline_running = True
                # Request navigation to Pipeline Runner on next rerun.
                # Direct assignment to bi_run_section here would raise
                # StreamlitAPIException because the radio was already
                # instantiated this run. The pre-radio sidebar handler
                # consumes nav_request before the radios render.
                st.session_state.nav_request = "Pipeline Runner"
                st.rerun()

        with ac2:
            target_choice = st.selectbox(
                "Code format",
                [
                    "PyLabRobot",
                    "UniteLabs",
                    "Rail System",
                    "Opentrons",
                    "Execution Plan JSON",
                ],
                key="nr_target",
                label_visibility="collapsed",
            )
            target_map_nr = {
                "PyLabRobot": "pylabrobot",
                "UniteLabs": "unitelabs",
                "Rail System": "rail_system",
                "Opentrons": "opentrons",
                "Execution Plan JSON": "json",
            }
            if target_map_nr[target_choice] == "json":
                from rail_protocol_generator import export_execution_plan_json as _exp_json
                code = _exp_json(active_assay, deployment_context=deploy)
                ext = "json"
                mime = "application/json"
            else:
                from rail_protocol_generator import generate_orchestrator_code as _gen_code_nr
                code = _gen_code_nr(
                    active_assay,
                    target=target_map_nr[target_choice],
                    deployment_context=deploy,
                    deck_config=deck,
                )
                ext = "py"
                mime = "text/x-python"

            st.download_button(
                f"⬇ Download {target_choice}",
                data=code,
                file_name=f"{active_assay['assay_id'].lower()}_{target_map_nr[target_choice]}.{ext}",
                mime=mime,
                use_container_width=True,
                key="nr_dl",
            )

        with ac3:
            template_name = st.text_input(
                "Template name",
                placeholder="e.g. NGS standard run",
                key="nr_tpl_name",
                label_visibility="collapsed",
            )
            if st.button(
                "💾 Save as Template",
                use_container_width=True,
                disabled=not template_name.strip(),
                key="nr_save_tpl",
            ):
                try:
                    from supabase import create_client as _cc_tpl
                    import os as _os_tpl
                    _sb_tpl = _cc_tpl(
                        _os_tpl.environ.get("SUPABASE_URL"),
                        _os_tpl.environ.get("SUPABASE_KEY"),
                    )
                    _sb_tpl.table("pipeline_runs").insert({
                        "run_id": f"TPL-{template_name}",
                        "assay_id": active_assay["assay_id"],
                        "assay_name": active_assay["name"],
                        "deployment_context": deploy,
                        "status": "template",
                        "pipeline_definition": {
                            "steps": plan["all_steps"],
                            "deck_id": deck["id"] if deck else None,
                        },
                        "notes": f"Template: {template_name}",
                    }).execute()
                    st.success(f"✓ Saved as '{template_name}'")
                except Exception as _e:
                    st.error(f"Save failed: {_e}")

        st.markdown("---")
        nav_c1, nav_c2, nav_c3 = st.columns([1, 4, 1])
        with nav_c1:
            if st.button("← Back", use_container_width=True, key="nr_back_4"):
                st.session_state.newrun_step = 3
                st.rerun()
        with nav_c3:
            if st.button(
                "🔄 Start over",
                use_container_width=True,
                key="nr_reset",
            ):
                for _key in [
                    "newrun_step", "newrun_assay",
                    "newrun_custom_protocol",
                    "newrun_deck", "newrun_deployment",
                ]:
                    if _key in st.session_state:
                        del st.session_state[_key]
                st.rerun()


elif section == "Custom Protocol Builder":
    st.title("🔧 Custom Protocol Builder")
    st.caption(
        "Describe your experiment in plain English. "
        "BioInterface AI parses each step, validates parameters, and generates "
        "executable PyLabRobot code for any robot — including steps not in the library."
    )

    st.markdown("---")

    st.caption("**Try a starter template:**")
    et1, et2, et3 = st.columns(3)

    template_simple = (
        "1. Add 100 uL of buffer to all wells of plate 1\n"
        "2. Add 50 uL of sample to columns 1-6\n"
        "3. Mix at 600 rpm for 30 seconds\n"
        "4. Incubate at 37 degrees C for 15 minutes\n"
        "5. Read absorbance at 450 nm"
    )
    template_centrifuge = (
        "1. Resuspend cells in 200 uL PBS\n"
        "2. Centrifuge at 4000 rpm for 5 minutes\n"
        "3. Discard supernatant\n"
        "4. Add 100 uL fresh medium\n"
        "5. Mix at 400 rpm for 1 minute\n"
        "6. Incubate at 37 degrees C for 30 minutes"
    )
    template_titration = (
        "1. Prepare 1:2 serial dilution from row A (starting 100 uL) to row H\n"
        "2. Add 100 uL diluent to rows B through H\n"
        "3. Transfer 100 uL from row A to row B and mix\n"
        "4. Repeat transfer down rows\n"
        "5. Read OD at 600 nm at time 0 and every 10 min for 1 hour"
    )

    if "custom_protocol_input" not in st.session_state:
        st.session_state.custom_protocol_input = ""

    if et1.button("📝 Simple ELISA-style", use_container_width=True, key="tpl_simple"):
        st.session_state.custom_protocol_input = template_simple
    if et2.button("🔬 Cell prep + incubation", use_container_width=True, key="tpl_centrifuge"):
        st.session_state.custom_protocol_input = template_centrifuge
    if et3.button("📊 Serial dilution + kinetic", use_container_width=True, key="tpl_titration"):
        st.session_state.custom_protocol_input = template_titration

    st.markdown("**Your protocol steps:**")
    natural_input = st.text_area(
        "One step per line — describe in natural language",
        value=st.session_state.custom_protocol_input,
        height=200,
        placeholder=(
            "1. Add 100 uL of reagent A to all wells\n"
            "2. Mix at 600 rpm for 1 minute\n"
            "3. Incubate at room temp for 10 minutes\n"
            "4. Read fluorescence at 488/520 nm"
        ),
        key="custom_input_area",
    )

    col_b1, col_b2 = st.columns([3, 1])
    with col_b1:
        parse_button = st.button(
            "🤖 Parse & Generate Protocol",
            type="primary",
            disabled=not natural_input.strip() or not AI_AVAILABLE,
            use_container_width=True,
            key="custom_parse_btn",
        )
    with col_b2:
        if st.button("Clear", use_container_width=True, key="custom_clear_btn"):
            st.session_state.custom_protocol_input = ""
            st.rerun()

    if parse_button and natural_input.strip():
        with st.spinner("BioInterface AI is parsing steps and validating parameters..."):
            from ai_layer import parse_custom_protocol
            parsed = parse_custom_protocol(natural_input)
        st.session_state.custom_parsed_result = parsed
        st.session_state.custom_input_used = natural_input

    parsed = st.session_state.get("custom_parsed_result")

    if parsed and parsed.get("parsed_steps"):
        st.markdown("---")

        sm1, sm2, sm3 = st.columns(3)
        sm1.metric("Steps parsed", len(parsed["parsed_steps"]))
        sm2.metric("Total duration", f"{parsed['total_duration_minutes']:.1f} min")
        sm3.metric("Instruments", len(parsed["instruments_needed"]))

        st.markdown(f"**Summary:** {parsed['summary']}")

        if parsed.get("warnings"):
            for w in parsed["warnings"]:
                st.warning(f"⚠ {w}")

        st.markdown("---")
        st.subheader("📋 Parsed Steps")

        for step in parsed["parsed_steps"]:
            with st.expander(f"Step {step['step_number']}: {step['description']}"):
                sc1, sc2 = st.columns([2, 1])
                with sc1:
                    st.markdown(f"**Action:** {step['action']}")
                    st.markdown(f"**Instrument:** {step['instrument']}")
                    st.markdown(f"**Duration:** {step['duration_minutes']:.2f} min")
                with sc2:
                    st.markdown("**Parameters:**")
                    for k, v in step.get("parameters", {}).items():
                        st.markdown(f"- {k}: `{v}`")
                if step.get("warnings"):
                    st.warning("Step warnings: " + ", ".join(step["warnings"]))

        st.markdown("---")

        if st.button(
            "⚙ Generate PyLabRobot Code",
            type="primary",
            use_container_width=True,
            key="custom_gen_code_btn",
        ):
            with st.spinner("BioInterface AI is generating executable code..."):
                from ai_layer import generate_custom_protocol_code
                code = generate_custom_protocol_code(parsed["parsed_steps"])
            st.session_state.custom_generated_code = code

        generated_code = st.session_state.get("custom_generated_code")
        if generated_code:
            st.markdown("---")
            st.subheader("🤖 Generated PyLabRobot Code")
            st.code(generated_code, language="python")

            import datetime as _dt_custom
            filename = f"custom_protocol_{_dt_custom.datetime.now():%Y%m%d_%H%M}.py"
            st.download_button(
                "⬇ Download .py file",
                data=generated_code,
                file_name=filename,
                mime="text/x-python",
                key="dl_custom_protocol",
            )

        st.markdown("---")
        st.caption("**Save this protocol for re-use:**")
        sc1, sc2 = st.columns([3, 1])
        with sc1:
            save_name = st.text_input(
                "Protocol name",
                placeholder="e.g. My Custom ELISA Variant",
                key="custom_save_name",
            )
        with sc2:
            if st.button(
                "💾 Save",
                disabled=not save_name.strip(),
                use_container_width=True,
                key="custom_save_btn",
            ):
                try:
                    from supabase import create_client
                    import os, datetime as _dt_save
                    sb_save = create_client(
                        os.environ.get("SUPABASE_URL"),
                        os.environ.get("SUPABASE_KEY"),
                    )
                    sb_save.table("custom_protocols").insert({
                        "name": save_name,
                        "natural_input": st.session_state.get("custom_input_used", ""),
                        "parsed_steps": parsed,
                        "created_at": _dt_save.datetime.now().isoformat(),
                    }).execute()
                    st.success(f"✓ Saved as '{save_name}'")
                except Exception as e:
                    st.error(f"Save failed: {e}")

    elif parsed is not None:
        st.error("Could not parse any steps from the input.")
        for w in parsed.get("warnings", []):
            st.warning(w)


elif section == "Deck Designer":
    st.title("🛠️ Deck Designer")
    st.caption(
        "Define your physical workcell deck layout. "
        "BioInterface uses this configuration to generate protocol code "
        "with real position assignments matching your actual hardware."
    )

    st.markdown("---")

    from supabase import create_client
    import os
    sb_dd = create_client(
        os.environ.get("SUPABASE_URL"),
        os.environ.get("SUPABASE_KEY"),
    )

    # Try to load saved decks; surface a helpful error if the table is missing
    existing_decks = []
    table_missing = False
    try:
        existing_decks = sb_dd.table("deck_configurations").select("*").order(
            "updated_at", desc=True
        ).execute().data
    except Exception as e:
        msg = str(e)
        if "PGRST" in msg or "deck_configurations" in msg or "schema cache" in msg.lower():
            table_missing = True
        else:
            st.error(f"Failed to load decks: {e}")

    if table_missing:
        st.error(
            "**`deck_configurations` table not found in Supabase.** "
            "Run the SQL migration from the Deck Designer feature spec "
            "(CREATE TABLE deck_configurations …) in your Supabase SQL editor "
            "to enable this section."
        )

    if "current_deck_id" not in st.session_state:
        st.session_state.current_deck_id = None
    if "current_deck" not in st.session_state:
        st.session_state.current_deck = None

    dd_col1, dd_col2 = st.columns([1, 2])

    with dd_col1:
        st.markdown("**Saved decks:**")
        if existing_decks:
            for deck in existing_decks:
                btn_label = f"📦 {deck['name']} ({deck['total_positions']} pos)"
                if st.button(btn_label, key=f"load_deck_{deck['id']}", use_container_width=True):
                    st.session_state.current_deck_id = deck["id"]
                    st.session_state.current_deck = deck
                    st.rerun()
        elif not table_missing:
            st.info("No saved decks yet.")

        st.markdown("---")
        st.markdown("**Create new deck:**")
        new_deck_template = st.selectbox(
            "Template:",
            list(deck_designer.DECK_TEMPLATES.keys()),
            format_func=lambda k: deck_designer.DECK_TEMPLATES[k]["name"],
        )
        new_deck_name = st.text_input(
            "Deck name", placeholder="e.g. NGS Library Prep — STAR 1"
        )

        create_clicked = st.button(
            "+ Create New Deck",
            type="primary",
            use_container_width=True,
            key="create_deck_btn",
        )
        if create_clicked:
            if not new_deck_name.strip():
                st.warning("⚠ Please enter a deck name first.")
            elif table_missing:
                st.error(
                    "Cannot create — `deck_configurations` table missing. "
                    "Run the SQL migration in Supabase first."
                )
            else:
                new_positions = deck_designer.make_default_positions(new_deck_template)
                new_deck = {
                    "name": new_deck_name.strip(),
                    "description": "",
                    "deck_type": new_deck_template,
                    "total_positions": len(new_positions),
                    "positions": new_positions,
                    "metadata": {},
                }
                try:
                    result = sb_dd.table("deck_configurations").insert(new_deck).execute()
                    st.session_state.current_deck = result.data[0]
                    st.session_state.current_deck_id = result.data[0]["id"]
                    st.success(
                        f"✓ Created '{new_deck_name}' "
                        f"({new_deck_template}, {len(new_positions)} positions)"
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"Create failed: {type(e).__name__}: {e}")

    with dd_col2:
        if st.session_state.get("current_deck"):
            current = st.session_state.current_deck
            st.markdown(f"### Editing: {current['name']}")
            st.caption(
                f"Type: `{current['deck_type']}` · {current['total_positions']} positions"
            )

            svg_str = deck_designer.render_deck_svg(
                current["positions"], current["deck_type"]
            )
            st.markdown(svg_str, unsafe_allow_html=True)

            st.markdown("---")
            st.markdown("**Configure positions:**")

            resource_options = [
                "empty",
                "tip_rack_1000ul", "tip_rack_200ul", "tip_rack_50ul",
                "reagent_reservoir_25ml", "reagent_reservoir_100ml",
                "source_plate_96", "source_plate_384",
                "destination_plate_96", "destination_plate_384",
                "magnetic_separator", "heater_shaker",
                "cold_block", "thermocycler_seat", "trash",
            ]

            updated_positions = []
            for i, pos in enumerate(current["positions"]):
                emoji = deck_designer.get_resource_emoji(pos["resource_type"])
                exp_label = (
                    f"{emoji} {pos['position_id']} — {pos['resource_type']} "
                    f"({pos.get('resource_label', '—')})"
                )
                with st.expander(exp_label):
                    pc1, pc2 = st.columns(2)
                    with pc1:
                        rt_idx = (
                            resource_options.index(pos["resource_type"])
                            if pos["resource_type"] in resource_options else 0
                        )
                        new_rt = st.selectbox(
                            "Resource type",
                            resource_options,
                            index=rt_idx,
                            key=f"rt_{i}_{current['id']}",
                        )
                    with pc2:
                        new_label = st.text_input(
                            "Resource label",
                            value=pos.get("resource_label", ""),
                            key=f"label_{i}_{current['id']}",
                        )
                    new_notes = st.text_input(
                        "Notes",
                        value=pos.get("notes", ""),
                        key=f"notes_{i}_{current['id']}",
                    )
                    updated_positions.append({
                        "position_id": pos["position_id"],
                        "position_label": pos["position_label"],
                        "resource_type": new_rt,
                        "resource_label": new_label,
                        "notes": new_notes,
                    })

            st.markdown("---")

            sb_col1, sb_col2 = st.columns(2)
            with sb_col1:
                if st.button("💾 Save Changes", type="primary", use_container_width=True):
                    try:
                        sb_dd.table("deck_configurations").update({
                            "positions": updated_positions,
                            "updated_at": "now()",
                        }).eq("id", current["id"]).execute()
                        st.session_state.current_deck["positions"] = updated_positions
                        st.success("Saved")
                    except Exception as e:
                        st.error(f"Save failed: {e}")

            with sb_col2:
                if st.button("⚙ Preview PyLabRobot Setup", use_container_width=True):
                    setup_code = deck_designer.deck_to_pylabrobot_setup(
                        updated_positions, current["deck_type"]
                    )
                    st.code(setup_code, language="python")

            with st.expander("⚠ Delete this deck"):
                confirm = st.text_input(
                    f"Type the deck name to confirm: '{current['name']}'",
                    key=f"confirm_delete_{current['id']}",
                )
                if st.button("Delete permanently", type="secondary", key=f"del_{current['id']}"):
                    if confirm == current["name"]:
                        sb_dd.table("deck_configurations").delete().eq(
                            "id", current["id"]
                        ).execute()
                        st.session_state.current_deck = None
                        st.session_state.current_deck_id = None
                        st.success("Deleted")
                        st.rerun()
                    else:
                        st.error("Confirmation text does not match")
        else:
            st.info("Select a saved deck on the left to edit, or create a new one.")


elif section == "Pipeline Runner":
    st.title("🔄 Experimental Pipeline Runner")
    st.caption(
        "Run any assay as a visual pipeline. Each step shows real-time "
        "status, instrument assignments, and timing — like CI/CD for the lab."
    )

    st.markdown("---")

    if "active_pipeline" not in st.session_state:
        st.session_state.active_pipeline = None
    if "pipeline_step_statuses" not in st.session_state:
        st.session_state.pipeline_step_statuses = {}
    if "pipeline_running" not in st.session_state:
        st.session_state.pipeline_running = False

    pr_col1, pr_col2 = st.columns([1, 2])

    with pr_col1:
        st.markdown("**Configure pipeline run:**")

        assay_options = {
            f"{a['assay_id']} — {a['name']}": a for a in ALL_ASSAYS_LIBRARY
        }

        deploy_map = {
            "Manual": "manual",
            "Robotic arm": "robotic_arm",
            "Rail robot": "rail_robot",
            "Scheduler": "scheduler",
        }
        _deploy_label_by_value = {v: k for k, v in deploy_map.items()}

        # Pre-render reconcile: when a pipeline is active (running or in
        # post-completion review), the config panel must mirror the actual
        # running assay/deployment so the left-side metrics line up with
        # the visualization on the right. Writing to the widget keys here,
        # before the widgets render, is the only legal way to do this.
        _active_pl = st.session_state.get("active_pipeline")
        _config_locked = bool(_active_pl)

        if _active_pl:
            _running_label = (
                f"{_active_pl['assay']['assay_id']} — "
                f"{_active_pl['assay']['name']}"
            )
            if _running_label in assay_options:
                st.session_state["pipeline_assay_select"] = _running_label

            _dep_label = _deploy_label_by_value.get(
                _active_pl.get("deployment")
            )
            if _dep_label:
                st.session_state["pipeline_deploy_ctx"] = _dep_label

        if _config_locked:
            st.caption(
                "🔒 Config locked while a pipeline is active. "
                "Click *Start a new run* below to unlock."
            )

        selected_label = st.selectbox(
            "Select assay:",
            list(assay_options.keys()),
            key="pipeline_assay_select",
            disabled=_config_locked,
        )
        selected_assay = assay_options[selected_label]

        deployment_choice = st.radio(
            "Deployment:",
            list(deploy_map.keys()),
            key="pipeline_deploy_ctx",
            disabled=_config_locked,
        )
        deployment = deploy_map[deployment_choice]

        sim_speed = st.select_slider(
            "Simulation speed:",
            options=["1x (real time)", "10x", "100x", "instant"],
            value="100x",
            disabled=_config_locked,
        )
        speed_map = {
            "1x (real time)": 1.0,
            "10x": 0.1,
            "100x": 0.01,
            "instant": 0.001,
        }
        speed_multiplier = speed_map[sim_speed]

        st.markdown("---")

        from rail_protocol_generator import generate_execution_plan as _gen_plan_pl
        plan = _gen_plan_pl(selected_assay, deployment_context=deployment)
        steps = plan["all_steps"]

        st.metric("Pipeline steps", len(steps))
        st.metric("Estimated duration", f"{plan['total_duration_minutes']:.1f} min")
        st.metric("Instruments", len(plan["instruments_required"]))

        st.markdown("---")

        if not st.session_state.pipeline_running:
            if st.button(
                "▶ Run Pipeline (Simulated)",
                type="primary",
                use_container_width=True,
                key="run_pipeline_btn",
            ):
                run_id = f"RUN-{_datetime.now():%Y%m%d-%H%M%S}"
                st.session_state.active_pipeline = {
                    "run_id": run_id,
                    "assay": selected_assay,
                    "deployment": deployment,
                    "steps": steps,
                    "started_at": _datetime.now().isoformat(),
                    "speed_multiplier": speed_multiplier,
                }
                st.session_state.pipeline_step_statuses = {}
                st.session_state.pipeline_running = True

                try:
                    from supabase import create_client as _cc_pl
                    import os as _os_pl
                    _sb_pl = _cc_pl(
                        _os_pl.environ.get("SUPABASE_URL"),
                        _os_pl.environ.get("SUPABASE_KEY"),
                    )
                    _sb_pl.table("pipeline_runs").insert({
                        "run_id": run_id,
                        "assay_id": selected_assay["assay_id"],
                        "assay_name": selected_assay["name"],
                        "deployment_context": deployment,
                        "status": "running",
                        "pipeline_definition": {
                            "steps": steps,
                            "total_duration_min": plan["total_duration_minutes"],
                        },
                        "started_at": _datetime.now().isoformat(),
                    }).execute()
                except Exception as _e:
                    msg = str(_e)
                    if "PGRST" in msg or "pipeline_runs" in msg or "schema cache" in msg.lower():
                        st.warning(
                            "`pipeline_runs` table not found — simulation will run but won't persist. "
                            "Run the SQL migration to enable history."
                        )
                    else:
                        st.warning(f"Run logging skipped: {_e}")

                st.rerun()
        else:
            if st.button(
                "⛔ Cancel Run",
                type="secondary",
                use_container_width=True,
                key="cancel_pipeline_btn",
            ):
                st.session_state.pipeline_running = False
                st.session_state.active_pipeline = None
                st.session_state.pipeline_step_statuses = {}
                st.rerun()

    with pr_col2:
        if st.session_state.active_pipeline:
            active = st.session_state.active_pipeline
            steps = active["steps"]
            statuses = st.session_state.pipeline_step_statuses

            st.markdown(f"### Pipeline: {active['assay']['name']}")
            st.caption(
                f"Run ID: `{active['run_id']}` · "
                f"Deployment: `{active['deployment']}`"
            )

            summary = pipeline_visualizer.compute_run_summary(steps, statuses)

            sm1, sm2, sm3, sm4 = st.columns(4)
            sm1.metric("Progress", f"{summary['progress_pct']}%")
            sm2.metric("Completed", summary["completed"])
            sm3.metric("Running", summary["running"])
            sm4.metric("Pending", summary["pending"])

            st.progress(summary["progress_pct"] / 100)

            st.markdown("---")

            pipeline_html = pipeline_visualizer.render_pipeline_html(
                steps, step_statuses=statuses, orientation="vertical"
            )
            st.markdown(pipeline_html, unsafe_allow_html=True)

            if st.session_state.pipeline_running:
                next_step = None
                for step in steps:
                    step_key = str(step.get("step_number", 0))
                    s = statuses.get(step_key, {"status": "pending"})
                    if s.get("status") == "pending":
                        next_step = step
                        break

                if next_step is None:
                    # Completed all steps
                    st.session_state.pipeline_running = False
                    st.success("🎉 Pipeline completed successfully!")
                    try:
                        from supabase import create_client as _cc_done
                        import os as _os_done
                        _sb_done = _cc_done(
                            _os_done.environ.get("SUPABASE_URL"),
                            _os_done.environ.get("SUPABASE_KEY"),
                        )
                        total_dur = sum(
                            step.get("duration_seconds", 0) for step in steps
                        )
                        _sb_done.table("pipeline_runs").update({
                            "status": "completed",
                            "step_statuses": statuses,
                            "completed_at": _datetime.now().isoformat(),
                            "total_duration_seconds": total_dur,
                        }).eq("run_id", active["run_id"]).execute()
                    except Exception:
                        pass
                    st.rerun()
                else:
                    step_key = str(next_step.get("step_number", 0))
                    if (step_key not in statuses
                            or statuses[step_key].get("status") != "running"):
                        statuses[step_key] = {
                            "status": "running",
                            "started_at": _datetime.now().isoformat(),
                        }
                        st.session_state.pipeline_step_statuses = statuses
                        st.rerun()
                    else:
                        sim_duration = (
                            next_step.get("duration_seconds", 30)
                            * active["speed_multiplier"]
                        )
                        _time.sleep(min(sim_duration, 3))
                        statuses[step_key] = {
                            "status": "completed",
                            "started_at": statuses[step_key]["started_at"],
                            "completed_at": _datetime.now().isoformat(),
                        }
                        st.session_state.pipeline_step_statuses = statuses
                        st.rerun()
            else:
                # pipeline_running == False with active_pipeline still set
                # is the post-completion (or post-cancel) state. If every
                # step is "completed", offer the upload-data hand-off.
                _all_done = bool(steps) and all(
                    statuses.get(
                        str(s.get("step_number", 0)), {}
                    ).get("status") == "completed"
                    for s in steps
                )
                if _all_done:
                    st.markdown("---")
                    st.success(
                        "🎉 Pipeline completed. Capture instrument "
                        "outputs to evaluate against the assay's "
                        "acceptance criteria."
                    )
                    _pc1, _pc2 = st.columns(2)
                    if _pc1.button(
                        "📥 Upload Run Data for this run",
                        type="primary",
                        use_container_width=True,
                        key="pr_post_upload_btn",
                    ):
                        # Cross-page hand-off via the pre-radio handler
                        # in the sidebar (consumes nav_request before the
                        # widgets render). ud_preselect_run_id is read
                        # by the Upload Run Data page to pre-select this
                        # run in its dropdown.
                        st.session_state["ud_preselect_run_id"] = (
                            active["run_id"]
                        )
                        st.session_state.nav_request = "Upload Run Data"
                        st.rerun()
                    if _pc2.button(
                        "🆕 Start a new run",
                        use_container_width=True,
                        key="pr_post_new_btn",
                    ):
                        st.session_state.active_pipeline = None
                        st.session_state.pipeline_step_statuses = {}
                        st.rerun()
        else:
            st.info(
                "Configure a pipeline on the left and click "
                "▶ Run Pipeline to begin."
            )

            st.markdown("---")
            st.markdown("**Recent runs:**")
            try:
                from supabase import create_client as _cc_recent
                import os as _os_recent
                _sb_recent = _cc_recent(
                    _os_recent.environ.get("SUPABASE_URL"),
                    _os_recent.environ.get("SUPABASE_KEY"),
                )
                recent = _sb_recent.table("pipeline_runs").select(
                    "run_id,assay_id,assay_name,status,started_at,completed_at"
                ).order("started_at", desc=True).limit(10).execute().data

                if recent:
                    st.dataframe(
                        pd.DataFrame(recent),
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.caption("No pipeline runs yet.")
            except Exception as _e:
                msg = str(_e)
                if "PGRST" in msg or "pipeline_runs" in msg or "schema cache" in msg.lower():
                    st.caption(
                        "`pipeline_runs` table not found — run the SQL migration "
                        "to enable run history."
                    )
                else:
                    st.caption(f"Could not load history: {_e}")


elif section == "Upload Run Data":
    st.title("📥 Upload Run Data")
    st.caption(
        "Upload instrument output files to ingest results "
        "for a completed run. Supported formats grow as "
        "parsers are added."
    )

    st.markdown("---")

    # Step 1: Pick a pipeline run to attach data to
    from supabase import create_client
    import os as _os_ud
    sb_ud = create_client(
        _os_ud.environ.get("SUPABASE_URL"),
        _os_ud.environ.get("SUPABASE_KEY"),
    )

    try:
        recent_runs = sb_ud.table("pipeline_runs").select(
            "run_id,assay_id,assay_name,status,started_at"
        ).order(
            "started_at", desc=True
        ).limit(20).execute().data
    except Exception as _e_ud:
        st.error(f"Could not load runs: {_e_ud}")
        recent_runs = []

    run_labels = [
        f"{r['run_id']} — {r['assay_name']} ({r['status']})"
        for r in recent_runs
    ]

    def _find_assay_record(assay_id, assay_name):
        """Look up the full assay dict across all loaded fields. Tries
        assay_id first (canonical), then falls back to name match."""
        candidate_modules = [
            ("field_01_biopharma_v2", "BIOPHARMA_ASSAYS"),
            ("field_03_genomics_ngs", "GENOMICS_ASSAYS"),
            ("field_04_drug_discovery_hts_v2", "HTS_ASSAYS"),
        ]
        for mod_name, list_attr in candidate_modules:
            try:
                _mod = __import__(mod_name)
                _list = getattr(_mod, list_attr, [])
            except Exception:
                continue
            for a in _list:
                if assay_id and a.get("assay_id") == assay_id:
                    return a
            for a in _list:
                if assay_name and a.get("name") == assay_name:
                    return a
        return None

    if not run_labels:
        st.info("No pipeline runs yet. Go to New Run to create one.")
    else:
        # If we arrived here via a Pipeline Runner hand-off, pre-select
        # the run before the selectbox instantiates. (Pop after consuming
        # so the preselect doesn't override later manual choices.)
        _preselect = st.session_state.pop("ud_preselect_run_id", None)
        if _preselect:
            for _r, _label in zip(recent_runs, run_labels):
                if _r["run_id"] == _preselect:
                    st.session_state["ud_run_select"] = _label
                    break

        chosen_run_label = st.selectbox(
            "Select pipeline run:",
            run_labels,
            key="ud_run_select",
        )
        chosen_run = recent_runs[
            run_labels.index(chosen_run_label)
        ]

        st.markdown("---")

        # Step 2: Upload file
        st.markdown("**Upload instrument output file:**")
        uploaded_file = st.file_uploader(
            "Drop file here",
            type=[
                "csv", "xls", "xlsx", "txt",
                "json", "ome", "ckb",
            ],
            key="ud_file_upload",
        )

        if uploaded_file is not None:
            file_name = uploaded_file.name
            file_bytes = uploaded_file.read()

            # Try to decode as text first
            try:
                file_content = file_bytes.decode('utf-8')
                is_binary = False
            except UnicodeDecodeError:
                file_content = file_bytes
                is_binary = True

            import run_data_ingestion as rdi

            detected_fmt = rdi.detect_file_format(
                file_name,
                file_content if not is_binary else None,
            )

            ic1, ic2 = st.columns(2)
            ic1.metric("File", file_name)
            ic2.metric("Detected format", detected_fmt)

            if st.button(
                "📥 Ingest File",
                type="primary",
                use_container_width=True,
                key="ud_ingest_btn",
            ):
                with st.spinner(
                    "BioInterface is ingesting the file..."
                ):
                    try:
                        # Store raw upload
                        upload_record = rdi.store_uploaded_file(
                            pipeline_run_id=chosen_run["run_id"],
                            file_name=file_name,
                            file_content=file_content,
                            file_format=detected_fmt,
                            is_binary=is_binary,
                        )

                        # Try to parse
                        parse_result = rdi.parse_uploaded_file(
                            file_name=file_name,
                            file_content=(
                                file_content if not is_binary
                                else file_content.decode(
                                    'latin-1', errors='replace'
                                )
                            ),
                            expected_format=detected_fmt,
                        )

                        if parse_result["success"]:
                            # Evaluate acceptance criteria BEFORE storage
                            # so pass_fail + acceptance_criteria_met land
                            # in the run_results row.
                            assay_record_ev = _find_assay_record(
                                chosen_run.get("assay_id"),
                                chosen_run.get("assay_name"),
                            )
                            criteria_ev = (
                                (assay_record_ev or {}).get(
                                    "acceptance_criteria"
                                ) or {}
                            )
                            if criteria_ev:
                                rdi.evaluate_and_enrich_results(
                                    parse_result["results"], criteria_ev
                                )

                            count = rdi.store_parsed_results(
                                chosen_run["run_id"],
                                upload_record["id"],
                                parse_result["results"],
                            )
                            rdi.update_upload_status(
                                upload_record["id"], "parsed"
                            )
                            st.success(
                                f"✓ Ingested {count} results "
                                f"from {file_name}"
                            )

                            # Stash for the verdict UI block below. We
                            # keep assay_record alongside results so the
                            # criteria expander can list every criterion
                            # the assay defines, not just the matched ones.
                            st.session_state["ud_last_parse"] = {
                                "run_id": chosen_run["run_id"],
                                "assay_record": assay_record_ev,
                                "file_name": file_name,
                                "results": parse_result["results"],
                            }
                        else:
                            rdi.update_upload_status(
                                upload_record["id"],
                                "failed",
                                parse_result["error"],
                            )
                            st.warning(
                                f"⚠ File stored but not parsed: "
                                f"{parse_result['error']}"
                            )
                            st.caption(
                                "Add a parser for this format "
                                "in run_data_ingestion.py "
                                "to enable automatic parsing."
                            )

                    except Exception as _ing_err:
                        st.error(f"Ingestion failed: {_ing_err}")

        # Acceptance-criteria verdict UI for the most recent successful
        # parse on this run. Reads pass_fail + acceptance_criteria_met
        # straight off the enriched records (set at parse time by
        # rdi.evaluate_and_enrich_results — same values now persisted in
        # the run_results row).
        _last_parse = st.session_state.get("ud_last_parse")
        if (
            _last_parse
            and _last_parse.get("run_id") == chosen_run["run_id"]
            and _last_parse.get("results")
        ):
            st.markdown("---")
            st.markdown(
                "**Acceptance criteria evaluation — "
                f"{_last_parse['file_name']}**"
            )

            assay_record = _last_parse.get("assay_record")
            results_lp = _last_parse["results"]

            if assay_record is None:
                st.caption(
                    "⚠ Could not find this run's assay in the loaded "
                    "library — samples were stored but criteria couldn't "
                    "be evaluated."
                )
            else:
                criteria = assay_record.get("acceptance_criteria") or {}
                if not criteria:
                    st.caption(
                        f"Assay `{assay_record.get('name')}` has no "
                        "acceptance_criteria defined."
                    )

                # Run-level verdict across samples
                sample_verdicts = [
                    r.get("pass_fail") or "not_evaluated" for r in results_lp
                ]
                if not sample_verdicts:
                    run_verdict = "not_evaluated"
                elif all(v == "pass" for v in sample_verdicts):
                    run_verdict = "pass"
                elif any(v == "fail" for v in sample_verdicts):
                    run_verdict = "fail"
                elif all(v == "not_evaluated" for v in sample_verdicts):
                    run_verdict = "not_evaluated"
                else:
                    run_verdict = "partial"

                verdict_color = {
                    "pass": "#1a6b4a",
                    "fail": "#a02020",
                    "partial": "#a06020",
                    "not_evaluated": "#6b6560",
                }[run_verdict]
                verdict_label = {
                    "pass": "✓ ALL SAMPLES PASS",
                    "fail": "✗ ONE OR MORE SAMPLES FAIL",
                    "partial": "◐ PARTIAL — SOME CRITERIA UNEVALUATED",
                    "not_evaluated": "— NO APPLICABLE CRITERIA",
                }[run_verdict]
                st.markdown(
                    f'<div style="display:inline-block; '
                    f'padding:6px 14px; background:{verdict_color}; '
                    f'color:white; border-radius:6px; '
                    f'font-family:DM Mono,monospace; font-size:12px; '
                    f'letter-spacing:0.08em; margin-bottom:10px;">'
                    f'{verdict_label}</div>',
                    unsafe_allow_html=True,
                )

                # Per-sample table read straight off the enriched records
                import pandas as _pd_ev
                table_data = []
                for r in results_lp:
                    measurements = r.get("measurements") or {}
                    primary_val = next(
                        (
                            v for k, v in measurements.items()
                            if isinstance(v, (int, float))
                            and "raw" not in k.lower()
                        ),
                        None,
                    )
                    met = r.get("acceptance_criteria_met") or []
                    if met:
                        crit_summary = "; ".join(
                            f"{c['criterion']}: "
                            f"{'✓' if c['passed'] else ('✗' if c['passed'] is False else '?')}"
                            for c in met
                        )
                        rule_summary = "; ".join(
                            f"{c['criterion']}={c['rule']}"
                            for c in met
                        )
                    else:
                        crit_summary = "—"
                        rule_summary = "no applicable criteria"
                    table_data.append({
                        "Sample": r.get("sample_id"),
                        "Value": primary_val,
                        "Units": measurements.get("units") or "",
                        "Verdict": r.get("pass_fail") or "not_evaluated",
                        "Criteria": crit_summary,
                        "Rule(s)": rule_summary,
                    })
                st.dataframe(
                    _pd_ev.DataFrame(table_data),
                    use_container_width=True,
                    hide_index=True,
                )

                # Per-sample evaluation cards: one card per (sample,
                # criterion) pair drawn from each record's enriched
                # acceptance_criteria_met list. This is the rich detail
                # the dataframe summary table can't show — the actual
                # rule string and the measured numeric value side by side.
                _card_entries = []
                for r in results_lp:
                    sid = r.get("sample_id") or "?"
                    for item in (r.get("acceptance_criteria_met") or []):
                        _card_entries.append((sid, item))

                if _card_entries:
                    with st.expander(
                        "All acceptance criteria for this assay"
                    ):
                        for sid, item in _card_entries:
                            criterion = item.get("criterion", "unknown")
                            rule = item.get("rule", "—")
                            value = item.get("value", "—")
                            passed = item.get("passed")
                            if passed is True:
                                icon, color = "✓", "#1a6b4a"
                            elif passed is False:
                                icon, color = "✗", "#c84b1f"
                            else:
                                icon, color = "—", "#6b6560"
                            st.markdown(
                                f'<div style="margin: 6px 0; '
                                f'padding: 8px 12px; background: white; '
                                f'border: 1px solid #d4cfc4; '
                                f'border-left: 4px solid {color}; '
                                f'border-radius: 6px;">'
                                f'<span style="font-weight: 600; '
                                f'color: {color};">{icon} {criterion}'
                                f'</span>'
                                f'<span style="margin-left: 10px; '
                                f'font-family: DM Mono, monospace; '
                                f'font-size: 11px; color: #6b6560;">'
                                f'sample <strong>{sid}</strong></span>'
                                f'<div style="font-size: 12px; '
                                f'color: #6b6560; margin-top: 4px;">'
                                f'Rule: <code>{rule}</code> · '
                                f'Measured: <strong>{value}</strong>'
                                f'</div></div>',
                                unsafe_allow_html=True,
                            )
                elif criteria:
                    # Fall back to listing the assay's raw criteria when
                    # nothing matched any sample (e.g. the parser emitted
                    # measurements that don't line up with any criterion).
                    with st.expander(
                        "All acceptance criteria for this assay"
                    ):
                        st.caption(
                            "No measurements matched these criteria; "
                            "showing the raw rules from the assay:"
                        )
                        for cname, rule in criteria.items():
                            st.markdown(f"- **{cname}**: `{rule}`")

        # Show recent uploads for this run
        st.markdown("---")
        st.markdown("**Recent uploads for this run:**")
        try:
            recent_uploads = sb_ud.table(
                "run_data_uploads"
            ).select("*").eq(
                "pipeline_run_id", chosen_run["run_id"]
            ).order(
                "uploaded_at", desc=True
            ).limit(10).execute().data

            if recent_uploads:
                import pandas as _pd_ud
                df_ud = _pd_ud.DataFrame([
                    {
                        "File": u["file_name"],
                        "Format": u["file_format"],
                        "Status": u["parse_status"],
                        "Uploaded": u["uploaded_at"][:19],
                    }
                    for u in recent_uploads
                ])
                st.dataframe(
                    df_ud,
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.caption("No uploads yet for this run.")
        except Exception as _up_err:
            st.caption(f"Could not load uploads: {_up_err}")


elif section == "Dashboard":
    st.title("\U0001f9ea BioInterface — Dashboard v2.0")
    st.caption("18 robot-executable assay protocols with analyst step labeling, workbench assignments, and structured acceptance criteria")

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Total Assays", len(ASSAYS))
    avg_robot = sum(a.get("robot_active_minutes", 0) for a in ASSAYS) / len(ASSAYS)
    k2.metric("Avg Robot Time", f"{avg_robot:.0f} min")
    total_steps = sum(len(a["robot_steps"]) for a in ASSAYS)
    k3.metric("Total Robot Steps", total_steps)
    k4.metric("Analyst Steps", total_analyst)
    all_regs = set(r for a in ASSAYS for r in a.get("regulatory", []))
    k5.metric("Regulatory Refs", len(all_regs))

    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Robot Active Time vs Total Duration")
        df = assay_df()
        fig = go.Figure()
        fig.add_trace(go.Bar(y=df["ID"], x=df["Robot (min)"], name="Robot Active (min)",
                             orientation="h", marker_color="#3498db"))
        fig.add_trace(go.Bar(y=df["ID"], x=df["Total (hr)"] * 60, name="Total Duration (min)",
                             orientation="h", marker_color="#e74c3c", opacity=0.5))
        fig.update_layout(barmode="overlay", yaxis=dict(autorange="reversed"),
                          height=500, margin=dict(l=0, r=0, t=10, b=0),
                          xaxis_title="Minutes", legend=dict(orientation="h", y=-0.1))
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Automation Difficulty")
        diff_df = pd.DataFrame([{"Difficulty": k.capitalize(), "Count": v} for k, v in diff_counts.items()])
        fig2 = px.pie(diff_df, names="Difficulty", values="Count", color="Difficulty",
                      color_discrete_map={"Easy": "#2ecc71", "Medium": "#f39c12", "Complex": "#e74c3c"},
                      hole=0.4, height=500)
        fig2.update_traces(textinfo="label+value+percent")
        fig2.update_layout(margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig2, use_container_width=True)

    # ── Autonomy Level Distribution ───────────────────────────────
    st.subheader("Autonomy Level Distribution")
    from collections import Counter as _Counter  # local alias to avoid shadowing
    LEVEL_HEX = {1: "#3498db", 2: "#2ecc71", 3: "#f39c12", 4: "#e74c3c"}
    LEVEL_LABEL = {
        1: "Level 1 — Fixed execution",
        2: "Level 2 — Read & review",
        3: "Level 3 — Flag & decide",
        4: "Level 4 — Autonomous decision",
    }
    aut_counts = _Counter(a.get("autonomy_level", 1) for a in ASSAYS)
    aut_rows = [
        {"Level": LEVEL_LABEL[lvl], "Count": aut_counts.get(lvl, 0)}
        for lvl in [4, 3, 2, 1]  # render Level 4 at top, Level 1 at bottom
    ]
    aut_df = pd.DataFrame(aut_rows)
    fig_aut = px.bar(
        aut_df, y="Level", x="Count", orientation="h", color="Level",
        color_discrete_map={LEVEL_LABEL[lvl]: LEVEL_HEX[lvl] for lvl in [1, 2, 3, 4]},
        height=280, text="Count",
    )
    fig_aut.update_traces(textposition="outside")
    fig_aut.update_layout(
        margin=dict(l=0, r=0, t=10, b=0),
        showlegend=False,
        xaxis_title="Assays in this field",
        yaxis_title="",
    )
    st.plotly_chart(fig_aut, use_container_width=True)

    # ── Instrument Coverage Across Library ───────────────────────────
    st.markdown("---")
    st.subheader("📦 Instrument Coverage Across Library")
    st.caption(
        "What instruments are used across the assay library, "
        "and how much each instrument is utilised."
    )

    with st.spinner("Computing instrument coverage..."):
        instrument_usage = get_instrument_usage_across_library()

    if instrument_usage:
        inst_df = pd.DataFrame([
            {
                "Instrument": data["instrument"],
                "Assays Using": data["assay_count"],
                "Total Steps": data["total_steps"],
                "Active Time (min)": round(data["total_duration_seconds"] / 60, 1),
            }
            for data in instrument_usage.values()
        ])
        inst_df = inst_df.sort_values("Assays Using", ascending=False)

        fig_inst = px.bar(
            inst_df,
            x="Instrument",
            y="Assays Using",
            text="Assays Using",
            color="Assays Using",
            color_continuous_scale=["#d4cfc4", "#1a3a5c"],
        )
        fig_inst.update_traces(
            textposition="outside",
            textfont=dict(family="DM Mono", size=11),
        )
        fig_inst.update_layout(
            plot_bgcolor="white",
            paper_bgcolor="white",
            height=320,
            margin=dict(l=10, r=10, t=20, b=40),
            showlegend=False,
            xaxis=dict(title="", tickangle=-25),
            yaxis=dict(title="Number of assays"),
        )
        st.plotly_chart(fig_inst, use_container_width=True)

        with st.expander("View full instrument coverage table"):
            st.dataframe(inst_df, use_container_width=True, hide_index=True)

    col3, col4 = st.columns(2)

    with col3:
        st.subheader("Assays per Workbench")
        df = assay_df()
        wb_data = df.groupby("WB").size().reset_index(name="Count")
        fig3 = px.bar(wb_data, x="WB", y="Count", color="WB",
                      color_discrete_sequence=["#3498db", "#2ecc71", "#e74c3c"],
                      height=400)
        fig3.update_layout(margin=dict(l=0, r=0, t=10, b=0), showlegend=False)
        st.plotly_chart(fig3, use_container_width=True)

    with col4:
        st.subheader("Throughput (Samples per Run)")
        fig4 = px.bar(df, y="ID", x="Samples/Run", color="Difficulty",
                      color_discrete_map={"Easy": "#2ecc71", "Medium": "#f39c12", "Complex": "#e74c3c"},
                      orientation="h", height=500)
        fig4.update_layout(yaxis=dict(autorange="reversed"), margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig4, use_container_width=True)

    col5, col6 = st.columns(2)

    with col5:
        st.subheader("Top Regulatory Standards")
        reg_count = {}
        for a in ASSAYS:
            for r in a.get("regulatory", []):
                reg_count[r] = reg_count.get(r, 0) + 1
        reg_df = pd.DataFrame(sorted(reg_count.items(), key=lambda x: x[1], reverse=True)[:12],
                              columns=["Standard", "Assays"])
        fig5 = px.bar(reg_df, y="Standard", x="Assays", orientation="h", height=400,
                      color_discrete_sequence=["#3498db"])
        fig5.update_layout(yaxis=dict(autorange="reversed"), margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig5, use_container_width=True)

    with col6:
        st.subheader("Analyst Steps per Assay")
        df = assay_df()
        analyst_df = df[df["Analyst Steps"] > 0].sort_values("Analyst Steps", ascending=False)
        fig6 = px.bar(analyst_df, y="ID", x="Analyst Steps", orientation="h", height=400,
                      color_discrete_sequence=["#f39c12"])
        fig6.update_layout(yaxis=dict(autorange="reversed"), margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig6, use_container_width=True)

    st.subheader("Product Type Coverage")
    heat_data = []
    for a in ASSAYS:
        row = {p: (1 if p in a.get("product_types", []) else 0) for p in ALL_PRODUCTS}
        row["Assay"] = a["assay_id"]
        heat_data.append(row)
    heat_df = pd.DataFrame(heat_data).set_index("Assay")
    fig7 = go.Figure(data=go.Heatmap(
        z=heat_df.values, x=[p[:25] for p in heat_df.columns], y=heat_df.index,
        colorscale=[[0, "#f0f0f0"], [1, "#3498db"]], showscale=False,
        hovertemplate="Assay: %{y}<br>Product: %{x}<br>Covered: %{z}<extra></extra>",
    ))
    fig7.update_layout(height=500, margin=dict(l=0, r=0, t=10, b=0), yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig7, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════
#  SECTION: BROWSE ASSAYS
# ═══════════════════════════════════════════════════════════════════════
elif section == "Browse Assays":
    st.title("\U0001f4cb Browse Assays")

    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        filt_product = st.multiselect("Filter by Product Type", ALL_PRODUCTS, default=[])
    with fc2:
        filt_diff = st.multiselect("Filter by Difficulty", [d.capitalize() for d in ALL_DIFFS], default=[])
    with fc3:
        filt_wb = st.multiselect("Filter by Workbench", ALL_WORKBENCHES, default=[])

    _instrument_usage_browse = get_instrument_usage_across_library()
    filt_instruments = st.multiselect(
        "Filter by instrument used",
        options=sorted(_instrument_usage_browse.keys()),
        default=[],
        help="Show only assays that use ALL selected instruments",
    )

    # Organism filter — only render when at least one assay in the
    # currently-loaded field exposes an "organism" attribute. Newer
    # fields (Core Lab Methods) carry it; older fields don't.
    _organism_options = sorted({
        a.get("organism") or "Not specified"
        for a in ASSAYS
        if a.get("organism")
    })
    filt_organism = []
    if _organism_options:
        filt_organism = st.multiselect(
            "Filter by organism",
            options=_organism_options,
            default=[],
            help="Only shown for fields whose assays specify an organism (e.g. Core Lab Methods).",
        )

    filtered = ASSAYS
    if filt_product:
        filtered = [a for a in filtered if any(p in a.get("product_types", []) for p in filt_product)]
    if filt_diff:
        filtered = [a for a in filtered if a["automation_difficulty"].capitalize() in filt_diff]
    if filt_wb:
        filtered = [a for a in filtered if a.get("workbench_id") in filt_wb]
    if filt_organism:
        filtered = [
            a for a in filtered
            if (a.get("organism") or "Not specified") in filt_organism
        ]
    if filt_instruments:
        from rail_protocol_generator import generate_execution_plan as _gen_plan
        def _has_all_instruments(assay, required):
            plan = _gen_plan(assay, inject_transport=False)
            phase_insts = {p["instrument"] for p in plan["execution_phases"]}
            return all(inst in phase_insts for inst in required)
        filtered = [a for a in filtered if _has_all_instruments(a, filt_instruments)]

    st.caption(f"Showing {len(filtered)} of {len(ASSAYS)} assays")

    rows = []
    for a in filtered:
        rows.append({
            "ID": a["assay_id"],
            "Name": a["name"],
            "Difficulty": a["automation_difficulty"].capitalize(),
            "Robot (min)": a.get("robot_active_minutes", 0),
            "Total (hr)": a.get("total_assay_duration_hours", 0),
            "Samples/Run": a.get("throughput_samples_per_run", 0),
            "WB": a.get("workbench_id", "N/A"),
            "Detection": a.get("detection", ""),
            "Analyst Steps": count_analyst_steps(a),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=600)

    st.markdown("---")
    for a in filtered:
        badge = DIFF_BADGE[a["automation_difficulty"]]
        analyst_n = count_analyst_steps(a)
        analyst_tag = f" \u2022 {analyst_n} analyst step(s)" if analyst_n > 0 else ""
        with st.expander(f"{a['assay_id']} -- {a['name']}{analyst_tag}"):
            bc1, bc2, bc3, bc4, bc5 = st.columns(5)
            bc1.metric("Robot Time", f"{a.get('robot_active_minutes', 0)} min")
            bc2.metric("Total", f"{a.get('total_assay_duration_hours', 0)} hr")
            bc3.metric("Samples/Run", a.get("throughput_samples_per_run", 0))
            bc4.metric("Workbench", a.get("workbench_id", "N/A"))
            bc5.markdown(f"<span class='{badge}'>{a['automation_difficulty'].upper()}</span>", unsafe_allow_html=True)
            st.markdown(f"**Purpose:** {a['purpose']}")
            # Optional fields surfaced when present (Core Lab Methods carries these)
            if a.get("organism"):
                _ec = a.get("experiment_category")
                st.markdown(
                    f"**Organism:** {a['organism']}"
                    + (f" · **Category:** {_ec}" if _ec else "")
                )
            if a.get("automation_level_note"):
                st.markdown(f"**Automation:** {a['automation_level_note']}")
            st.markdown(f"**Detection:** {a.get('detection', '')}")
            st.markdown(f"**Environment:** {a.get('environment_requirement', '')}")
            st.markdown(f"**Platform:** {a.get('platform_compatibility', '')}")
            st.markdown(f"**Products:** {', '.join(a.get('product_types', []))}")
            st.markdown(f"**Regulatory:** {', '.join(a.get('regulatory', []))}")
            if a.get("notes"):
                st.info(f"**Notes:** {a['notes']}")


# ═══════════════════════════════════════════════════════════════════════
#  SECTION: INSTRUMENT COVERAGE
# ═══════════════════════════════════════════════════════════════════════
elif section == "Instrument Coverage":
    st.title("📦 Instrument Coverage")
    st.caption(
        "Detailed view of every instrument used across the BioInterface "
        "assay library — which assays use each instrument, what step types "
        "it handles, and total active time."
    )

    st.markdown("---")

    with st.spinner("Loading instrument data..."):
        instrument_usage = get_instrument_usage_across_library()

    if not instrument_usage:
        st.warning("No instrument data available.")
    else:
        n_assays = len(ALL_ASSAYS_LIBRARY)
        sm1, sm2, sm3 = st.columns(3)
        sm1.metric("Distinct instruments", len(instrument_usage))
        sm2.metric("Total assays in library", n_assays)
        avg_inst_per_assay = (
            sum(d["assay_count"] for d in instrument_usage.values()) / n_assays
            if n_assays else 0
        )
        sm3.metric("Avg instruments per assay", f"{avg_inst_per_assay:.1f}")

        st.markdown("---")

        sorted_instruments = sorted(
            instrument_usage.values(),
            key=lambda d: d["assay_count"],
            reverse=True,
        )

        for data in sorted_instruments:
            inst = data["instrument"]
            with st.container():
                st.markdown(f"### 📦 `{inst}`")

                ic1, ic2, ic3 = st.columns(3)
                ic1.metric("Assays using", f"{data['assay_count']} / {n_assays}")
                ic2.metric("Total steps", data["total_steps"])
                ic3.metric("Active time", f"{data['total_duration_seconds'] / 60:.0f} min")

                st.markdown("**Step types this instrument handles:**")
                step_chips = " ".join([f"`{st_type}`" for st_type in data["step_types"]])
                st.markdown(step_chips)

                with st.expander(
                    f"View {data['assay_count']} assays using {inst}"
                ):
                    cols_per_row = 3
                    assays_list = data["assays_using"]
                    for i in range(0, len(assays_list), cols_per_row):
                        cols = st.columns(cols_per_row)
                        for j, assay_id in enumerate(assays_list[i:i + cols_per_row]):
                            with cols[j]:
                                assay_name = next(
                                    (a["name"] for a in ALL_ASSAYS_LIBRARY
                                     if a["assay_id"] == assay_id),
                                    assay_id,
                                )
                                ellipsis = "..." if len(assay_name) > 60 else ""
                                st.markdown(
                                    f"**{assay_id}**\n\n{assay_name[:60]}{ellipsis}"
                                )

                st.markdown("---")


# ═══════════════════════════════════════════════════════════════════════
#  SECTION: ASSAY DETAIL
# ═══════════════════════════════════════════════════════════════════════
elif section == "Assay Detail":
    st.title("\U0001f52c Assay Detail")

    selected_id = st.selectbox("Select Assay", ALL_IDS,
                               format_func=lambda x: f"{x} -- {next(a['name'] for a in ASSAYS if a['assay_id'] == x)}")
    a = next(a for a in ASSAYS if a["assay_id"] == selected_id)
    badge = DIFF_BADGE[a["automation_difficulty"]]
    analyst_n = count_analyst_steps(a)

    st.markdown(f"## {a['name']}")
    tags = f"<span class='{badge}'>{a['automation_difficulty'].upper()}</span> &nbsp; "
    tags += f"<span class='badge-blue'>{a.get('workbench_id', 'N/A')}</span> &nbsp; "
    tags += f"<span class='badge-purple'>{a.get('environment_requirement', 'N/A')[:30]}</span>"
    if analyst_n > 0:
        tags += f" &nbsp; <span class='badge-amber'>{analyst_n} analyst step(s)</span>"
    st.markdown(tags, unsafe_allow_html=True)

    # ── AUTONOMY LEVEL BADGE ───────────────────────────────────
    LEVEL_BADGES = {
        1: ("🔵", "Level 1 — Fixed execution", "#1a3a5c"),
        2: ("🟢", "Level 2 — Read and review", "#1a5c2a"),
        3: ("🟡", "Level 3 — Flag and decide", "#5c4a1a"),
        4: ("🔴", "Level 4 — Autonomous decision", "#5c1a1a"),
    }
    level = a.get("autonomy_level", 1)
    icon, label, color = LEVEL_BADGES.get(level, LEVEL_BADGES[1])
    reason = a.get("autonomy_level_reason", "")
    st.markdown(
        f'<div style="display:inline-block;padding:6px 14px;'
        f'border-radius:20px;background:{color};color:white;'
        f'font-size:12px;font-weight:600;margin-top:8px;margin-bottom:4px">'
        f'{icon} {label}</div>',
        unsafe_allow_html=True
    )
    if reason:
        st.caption(f"Autonomy: {reason}")

    st.markdown(f"**Purpose:** {a['purpose']}")

    st.markdown("---")

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Robot Time", f"{a.get('robot_active_minutes', 0)} min")
    m2.metric("Total Duration", f"{a.get('total_assay_duration_hours', 0)} hr")
    m3.metric("Samples/Run", a.get("throughput_samples_per_run", 0))
    m4.metric("Sample Volume", f"{a.get('sample_volume_uL', 0)} uL")
    m5.metric("Detection", a.get("detection", "")[:30])

    st.markdown("---")

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "\U0001f916 Robot Steps", "\U0001f5fa Deck Layout",
        "\U0001f9ea Instruments & Reagents", "\U0001f4dc Acceptance Criteria",
        "\U0001f4cb Regulatory"
    ])

    with tab1:
        st.subheader("Robot Step Instructions")
        st.caption(f"{len(a['robot_steps'])} steps | {analyst_n} analyst intervention(s)")

        for i, step in enumerate(a["robot_steps"], 1):
            if "[ANALYST STEP" in step:
                st.markdown(f"<div class='analyst-step'><strong>>>> ANALYST STEP:</strong> {step}</div>",
                            unsafe_allow_html=True)
            else:
                st.markdown(f"**{i}.** {step}")

        if a.get("throughput_notes"):
            st.caption(f"Throughput: {a['throughput_notes']}")

        st.markdown("---")

        # ── STEP CLASSIFICATION SUMMARY (PyLabRobot generation) ─────────
        from collections import Counter
        steps = a.get("robot_steps", [])
        automate_steps = a.get("automate_96_steps", [])
        classifications = [classify_step(s, i + 1, automate_steps)[0] for i, s in enumerate(steps)]
        counts = Counter(classifications)

        st.caption("Step classification for PyLabRobot generation")
        emoji_map = {
            "LIQUID_HANDLER": "🔵",
            "TRANSPORT": "🟢",
            "WAIT": "🟡",
            "ANALYST_PAUSE": "🔴",
            "INSTRUMENT_TRIGGER": "🟣",
            "OTHER": "⚫",
        }
        if counts:
            cls_cols = st.columns(len(counts))
            for i, (cls, count) in enumerate(sorted(counts.items())):
                cls_cols[i].metric(f"{emoji_map.get(cls, '⚪')} {cls}", count)

        with st.expander("View generated PyLabRobot protocol"):
            protocol_code = generate_protocol(a)
            st.code(protocol_code, language="python")

        st.markdown("---")

        # ── EXPORT PROTOCOL BUTTON ──────────────────────────────────────
        # Generates a plain-text protocol file formatted for Rail System.
        # This is the file Chase Olle's system loads directly.
        export_text = build_export_text(a)
        st.download_button(
            label="⬇ Export for Rail System",
            data=export_text,
            file_name=f"protocol_{a['assay_id']}_{a['name'].replace(' ', '_').replace('/', '-')}.txt",
            mime="text/plain",
            help="Downloads a plain-text protocol file formatted for the Rail System execution engine",
            type="primary",
        )
        st.caption("Downloads a numbered instruction file the Rail System system can load directly.")

        if a.get("automate_96_steps"):
            st.download_button(
                label="⬇ Export AutoMATE 96 Protocol",
                data=build_automate_export(a),
                file_name=f"automate96_{a['assay_id']}.txt",
                mime="text/plain",
                key=f"automate_export_{a['assay_id']}"
            )
            st.caption("Downloads only the steps the Accuris AutoMATE 96 executes, with recommended head and deck positions.")

        st.download_button(
            label="⬇ Export Executable Protocol (.py)",
            data=generate_protocol(a),
            file_name=f"{a['assay_id'].lower()}_protocol.py",
            mime="text/x-python",
            key=f"ror_export_{a['assay_id']}"
        )
        st.caption("Downloads a runnable PyLabRobot Python module — same generator used to populate `protocols/`.")

        # ── Multi-Instrument Execution Plan ────────────────────────
        st.markdown("---")
        st.subheader("🎯 Multi-Instrument Execution Plan")
        st.caption(
            "Structured plan that any orchestrator can consume. "
            "Pick a deployment context to see how plate transport "
            "between instruments will be handled."
        )

        deployment_choice = st.radio(
            "Deployment context:",
            [
                "Manual (analyst transfers)",
                "Robotic arm (Hamilton VANTAGE-style)",
                "Rail robot (Rail System-style)",
                "Scheduler (UniteLabs-style)",
            ],
            horizontal=True,
            key=f"deploy_ctx_{a['assay_id']}",
        )

        deploy_map = {
            "Manual (analyst transfers)": "manual",
            "Robotic arm (Hamilton VANTAGE-style)": "robotic_arm",
            "Rail robot (Rail System-style)": "rail_robot",
            "Scheduler (UniteLabs-style)": "scheduler",
        }
        deployment_context = deploy_map[deployment_choice]

        from rail_protocol_generator import (
            generate_execution_plan,
            export_execution_plan_json,
            generate_orchestrator_code,
        )

        # ── Deck context (optional — drives real position labels) ──
        st.markdown("**🛠️ Deck context for code generation:**")
        st.caption(
            "Optional. Choose a deck configuration to inject real position "
            "assignments into generated code. If no deck is chosen, code uses "
            "placeholder positions."
        )

        from supabase import create_client as _create_client
        import os as _os
        _sb_assay = _create_client(
            _os.environ.get("SUPABASE_URL"),
            _os.environ.get("SUPABASE_KEY"),
        )
        try:
            _available_decks = _sb_assay.table("deck_configurations").select(
                "id,name,deck_type"
            ).order("name").execute().data
        except Exception:
            _available_decks = []

        deck_options = ["(No deck — placeholders)"] + [
            f"{d['name']} ({d['deck_type']})" for d in _available_decks
        ]
        selected_deck_label = st.selectbox(
            "Deck:",
            deck_options,
            key=f"deck_select_{a['assay_id']}",
        )

        selected_deck = None
        if selected_deck_label != "(No deck — placeholders)":
            deck_idx = deck_options.index(selected_deck_label) - 1
            selected_deck_id = _available_decks[deck_idx]["id"]
            try:
                selected_deck = _sb_assay.table("deck_configurations").select(
                    "*"
                ).eq("id", selected_deck_id).execute().data[0]
            except Exception as _e:
                st.error(f"Could not load deck: {_e}")

        if selected_deck:
            with st.expander(f"View deck layout: {selected_deck['name']}"):
                st.markdown(
                    deck_designer.render_deck_svg(
                        selected_deck["positions"],
                        selected_deck["deck_type"],
                    ),
                    unsafe_allow_html=True,
                )

        plan = generate_execution_plan(a, deployment_context=deployment_context)

        ec1, ec2, ec3, ec4 = st.columns(4)
        ec1.metric("Total duration", f"{plan['total_duration_minutes']:.1f} min")
        ec2.metric("Instruments needed", len(plan["instruments_required"]))
        ec3.metric("Execution phases", len(plan["execution_phases"]))
        ec4.metric("Transport steps", plan["transport_steps_count"])

        if plan["instruments_required"]:
            st.caption("**Instruments required:**")
            inst_count = len(plan["instruments_required"])
            inst_cols = st.columns(min(inst_count, 4) or 1)
            for i, inst in enumerate(plan["instruments_required"]):
                inst_cols[i % len(inst_cols)].markdown(f"📦 `{inst}`")

        with st.expander(f"View {len(plan['execution_phases'])} execution phases"):
            for phase in plan["execution_phases"]:
                st.markdown(
                    f"**Phase {phase['phase_number']}: {phase['instrument']}**"
                )
                for step in phase["steps"]:
                    st.markdown(
                        f"  - Step {step['step_number']}: {step['description']}"
                    )

        st.markdown("**Export for orchestrator:**")
        oc1, oc2, oc3, oc4, oc5 = st.columns(5)

        with oc1:
            plan_json = export_execution_plan_json(a, deployment_context=deployment_context)
            st.download_button(
                "⬇ Execution Plan JSON",
                data=plan_json,
                file_name=f"{a['assay_id'].lower()}_{deployment_context}_execution_plan.json",
                mime="application/json",
                key=f"dl_plan_{a['assay_id']}",
            )

        with oc2:
            unitelabs_code = generate_orchestrator_code(
                a,
                target="unitelabs",
                deployment_context=deployment_context,
                deck_config=selected_deck,
            )
            st.download_button(
                "⬇ UniteLabs Python",
                data=unitelabs_code,
                file_name=f"{a['assay_id'].lower()}_{deployment_context}_unitelabs.py",
                mime="text/x-python",
                key=f"dl_unitelabs_{a['assay_id']}",
            )

        with oc3:
            ror_code = generate_orchestrator_code(
                a,
                target="rail_system",
                deployment_context=deployment_context,
                deck_config=selected_deck,
            )
            st.download_button(
                "⬇ Rail System Python",
                data=ror_code,
                file_name=f"{a['assay_id'].lower()}_{deployment_context}_ror.py",
                mime="text/x-python",
                key=f"dl_ror_{a['assay_id']}",
            )

        with oc4:
            pylabrobot_code = generate_orchestrator_code(
                a, target="pylabrobot", deck_config=selected_deck
            )
            st.download_button(
                "⬇ PyLabRobot Python",
                data=pylabrobot_code,
                file_name=f"{a['assay_id'].lower()}_pylabrobot.py",
                mime="text/x-python",
                key=f"dl_plr_{a['assay_id']}",
            )

        with oc5:
            opentrons_code = generate_orchestrator_code(
                a,
                target="opentrons",
                deployment_context=deployment_context,
                deck_config=selected_deck,
            )
            st.download_button(
                "⬇ Opentrons Python",
                data=opentrons_code,
                file_name=f"{a['assay_id'].lower()}_opentrons.py",
                mime="text/x-python",
                key=f"dl_opentrons_{a['assay_id']}",
            )

    with tab2:
        st.subheader("Robot Deck Layout")
        deck = a.get("robot_deck_layout", {})
        if deck:
            deck_rows = [{"Position": pos, "Contents": desc} for pos, desc in deck.items()]
            st.dataframe(pd.DataFrame(deck_rows), use_container_width=True, hide_index=True)
        else:
            st.info("No deck layout defined for this assay.")

    with tab3:
        ic1, ic2, ic3 = st.columns(3)
        with ic1:
            st.subheader("Instruments")
            for inst in a.get("instruments_needed", []):
                st.markdown(f"- {inst}")
        with ic2:
            st.subheader("Consumables")
            for c in a.get("consumables", []):
                st.markdown(f"- {c}")
        with ic3:
            st.subheader("Reagents")
            for r in a.get("reagents", []):
                st.markdown(f"- {r}")

        st.markdown("---")
        st.markdown("**AutoMATE 96 Head Recommendation**")

        head = a.get("automate_96_head", "not applicable")
        head_note = a.get("automate_96_head_note", "")
        tagged_steps = a.get("automate_96_steps", [])

        if head == "not applicable" or not tagged_steps:
            st.info("No AutoMATE 96 steps for this assay — instrument not "
                    "required in this workflow.")
        else:
            hc1, hc2, hc3 = st.columns(3)
            hc1.metric("Recommended head", head)
            hc2.metric("AutoMATE 96 steps", len(tagged_steps))
            hc3.metric("Total steps",
                       len(a.get("robot_steps", [])))
            if head_note:
                st.caption(head_note)

            if a.get("automate_96_head_change", False):
                st.warning("Head change required mid-run — "
                           "plan for instrument pause between steps.")
            else:
                st.success("No head change required — "
                           "single head covers all AutoMATE 96 steps.")

    with tab4:
        st.subheader("Acceptance Criteria")
        ac = a.get("acceptance_criteria", {})
        if ac:
            for k, v in ac.items():
                st.markdown(f"- **{k.replace('_', ' ').title()}:** {v}")
        else:
            st.info("No acceptance criteria defined.")

    with tab5:
        st.subheader("Regulatory References")
        for r in a.get("regulatory", []):
            st.markdown(f"- {r}")

    if a.get("notes"):
        st.markdown("---")
        st.info(f"**Notes:** {a['notes']}")

    st.markdown("---")
    pcol1, pcol2 = st.columns(2)
    with pcol1:
        st.subheader("Product Types")
        ptags = " &nbsp; ".join(f"<span class='badge-blue'>{p}</span>" for p in a.get("product_types", []))
        st.markdown(ptags, unsafe_allow_html=True)
    with pcol2:
        st.subheader("Platform")
        st.markdown(f"**Environment:** {a.get('environment_requirement', 'N/A')}")
        st.markdown(f"**Compatibility:** {a.get('platform_compatibility', 'N/A')}")


# ═══════════════════════════════════════════════════════════════════════
#  SECTION: COMPARE
# ═══════════════════════════════════════════════════════════════════════
elif section == "Compare":
    st.title("\U0001f504 Compare Assays")

    selected = st.multiselect(
        "Select assays to compare (2+)", ALL_IDS, default=ALL_IDS[:3],
        format_func=lambda x: f"{x} -- {next(a['name'] for a in ASSAYS if a['assay_id'] == x)[:40]}",
    )

    if len(selected) < 2:
        st.warning("Select at least 2 assays to compare.")
    else:
        compare_assays = [a for a in ASSAYS if a["assay_id"] in selected]
        comp_rows = []
        for a in compare_assays:
            comp_rows.append({
                "ID": a["assay_id"],
                "Name": a["name"][:40],
                "Difficulty": a["automation_difficulty"].capitalize(),
                "Robot (min)": a.get("robot_active_minutes", 0),
                "Total (hr)": a.get("total_assay_duration_hours", 0),
                "Samples/Run": a.get("throughput_samples_per_run", 0),
                "Sample (uL)": a.get("sample_volume_uL", 0),
                "WB": a.get("workbench_id", "N/A"),
                "Robot Steps": len(a["robot_steps"]),
                "Analyst Steps": count_analyst_steps(a),
                "Instruments": len(a.get("instruments_needed", [])),
                "Reagents": len(a.get("reagents", [])),
            })
        comp_df = pd.DataFrame(comp_rows)
        st.dataframe(comp_df, use_container_width=True, hide_index=True)

        st.markdown("---")
        cc1, cc2 = st.columns(2)
        with cc1:
            fig = px.bar(comp_df, x="ID", y="Robot (min)", color="Difficulty",
                         color_discrete_map={"Easy": "#2ecc71", "Medium": "#f39c12", "Complex": "#e74c3c"},
                         title="Robot Active Time")
            st.plotly_chart(fig, use_container_width=True)
        with cc2:
            fig2 = px.bar(comp_df, x="ID", y="Samples/Run", color="Difficulty",
                          color_discrete_map={"Easy": "#2ecc71", "Medium": "#f39c12", "Complex": "#e74c3c"},
                          title="Throughput (Samples/Run)")
            st.plotly_chart(fig2, use_container_width=True)

        st.subheader("Radar Comparison")
        categories_radar = ["Robot (min)", "Sample (uL)", "Robot Steps", "Analyst Steps", "Instruments", "Reagents"]
        fig3 = go.Figure()
        for _, row in comp_df.iterrows():
            vals = [row[c] for c in categories_radar]
            maxvals = [comp_df[c].max() for c in categories_radar]
            norm = [v / m if m > 0 else 0 for v, m in zip(vals, maxvals)]
            norm.append(norm[0])
            fig3.add_trace(go.Scatterpolar(
                r=norm, theta=categories_radar + [categories_radar[0]],
                name=row["ID"], fill="toself", opacity=0.5,
            ))
        fig3.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 1])),
                           height=450, margin=dict(l=40, r=40, t=40, b=40))
        st.plotly_chart(fig3, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════
#  SECTION: ANALYST STEPS
# ═══════════════════════════════════════════════════════════════════════
elif section == "Analyst Steps":
    st.title("\U0001f9d1\u200d\U0001f52c Analyst Intervention Points")
    st.caption("Steps where the robot pauses and requires human analyst review before continuing")

    total_a = sum(count_analyst_steps(a) for a in ASSAYS)
    assays_with = sum(1 for a in ASSAYS if count_analyst_steps(a) > 0)
    assays_without = len(ASSAYS) - assays_with

    ka1, ka2, ka3 = st.columns(3)
    ka1.metric("Total Analyst Steps", total_a)
    ka2.metric("Assays with Analyst Steps", assays_with)
    ka3.metric("Fully Automated", assays_without)

    st.markdown("---")

    for a in ASSAYS:
        steps = [s for s in a.get("robot_steps", []) if "[ANALYST STEP" in s]
        if steps:
            badge = DIFF_BADGE[a["automation_difficulty"]]
            with st.expander(f"{a['assay_id']} -- {a['name']} ({len(steps)} analyst step(s))", expanded=False):
                st.markdown(f"<span class='{badge}'>{a['automation_difficulty'].upper()}</span> &nbsp; "
                            f"<span class='badge-blue'>{a.get('workbench_id', 'N/A')}</span>",
                            unsafe_allow_html=True)
                for step in steps:
                    st.markdown(f"<div class='analyst-step'>{step}</div>", unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("Fully Automated Assays (No Analyst Steps)")
    for a in ASSAYS:
        if count_analyst_steps(a) == 0:
            st.markdown(f"- **{a['assay_id']}** -- {a['name']}")


# ═══════════════════════════════════════════════════════════════════════
#  SECTION: SEARCH
# ═══════════════════════════════════════════════════════════════════════
elif section == "Search":
    st.title("\U0001f50d Search Assays")

    query = search_term.strip() if search_term.strip() else ""
    query = st.text_input("Search by keyword (name, purpose, reagent, instrument, product, environment)",
                          value=query, key="main_search")

    if query.strip():
        results = search_assays(query)
        st.caption(f"Found {len(results)} assay(s) for \"{query}\"")
        if not results:
            st.info("No assays matched your search. Try a different keyword.")
        else:
            for a in results:
                badge = DIFF_BADGE[a["automation_difficulty"]]
                analyst_n = count_analyst_steps(a)
                with st.expander(f"{a['assay_id']} -- {a['name']}", expanded=True):
                    ec1, ec2, ec3, ec4 = st.columns(4)
                    ec1.metric("Robot Time", f"{a.get('robot_active_minutes', 0)} min")
                    ec2.metric("Samples/Run", a.get("throughput_samples_per_run", 0))
                    ec3.metric("Workbench", a.get("workbench_id", "N/A"))
                    ec4.markdown(f"<span class='{badge}'>{a['automation_difficulty'].upper()}</span>",
                                 unsafe_allow_html=True)
                    st.markdown(f"**Purpose:** {a['purpose']}")
                    st.markdown(f"**Detection:** {a.get('detection', '')}")
                    st.markdown(f"**Environment:** {a.get('environment_requirement', '')}")
                    st.markdown(f"**Regulatory:** {', '.join(a.get('regulatory', []))}")
    else:
        st.info("Enter a keyword to search across assay names, purposes, reagents, instruments, products, and environments.")


# ═══════════════════════════════════════════════════════════════════════
#  SECTION: AI INTELLIGENCE
# ═══════════════════════════════════════════════════════════════════════
elif section == "AI Intelligence":
    st.title("\U0001f916 AI Intelligence")
    st.caption("Powered by Claude — natural language search, root cause analysis, batch quality correlation")

    if not AI_AVAILABLE:
        # ── Setup instructions shown until API key is configured ──
        st.warning("AI Intelligence is not active yet. Complete the setup steps below to enable it.")
        st.markdown("---")

        st.subheader("Setup — 3 steps")

        with st.expander("Step 1 — Install dependencies", expanded=True):
            st.code("pip install anthropic supabase python-dotenv", language="bash")

        with st.expander("Step 2 — Create .env file in this folder", expanded=True):
            st.code("""ANTHROPIC_API_KEY=[secret removed]
SUPABASE_URL=https://yourproject.supabase.co
SUPABASE_KEY=eyJhbGci...""", language="bash")
            st.caption("Get your Anthropic API key at console.anthropic.com → API Keys → Create Key")
            st.caption("Get Supabase credentials from your project → Settings → API")

        with st.expander("Step 3 — Add ai_layer.py to this folder", expanded=True):
            st.markdown("Copy `ai_layer.py` (generated in the build chat) into the same folder as `assay_tool.py`.")
            st.markdown("Then restart Streamlit: `streamlit run assay_tool.py`")

        st.markdown("---")
        st.info("Once set up, this section unlocks: natural language protocol search, AI root cause analysis, and cross-batch quality correlation.")

    else:
        # ── AI is active — show all three features ──
        ai_tab1, ai_tab2, ai_tab3, ai_tab4 = st.tabs([
            "🔍 Natural Language Search",
            "🔬 Root Cause Analysis",
            "📊 Batch Quality Correlation",
            "🤖 AutoMATE 96 Optimisation"
        ])

        # ── AI TAB 1: Natural language search ──────────────────────────
        with ai_tab1:
            st.subheader("Ask a question — get the right assay")
            st.caption("AI searches all 18 assays and returns ranked results with reasoning. "
                       "No need to know field names or filter logic.")

            example_queries = [
                "which assays cover mAb release testing under 30 minutes robot time?",
                "find fully automated assays for CHO cell culture monitoring",
                "what assays run on WB1 and are easy difficulty?",
                "show me complex assays that need a clean room environment",
            ]

            ai_query = st.text_input(
                "Enter your question in plain English",
                placeholder="e.g. which assays cover mAb quality attributes under 30 min robot time?",
                key="ai_search_input"
            )

            st.caption("Example queries:")
            cols = st.columns(2)
            for i, eq in enumerate(example_queries):
                if cols[i % 2].button(f'"{eq[:55]}..."', key=f"ex_{i}", use_container_width=True):
                    ai_query = eq

            if ai_query.strip():
                with st.spinner("BioInterface AI is searching the corpus..."):
                    try:
                        results = search_protocols(ai_query.strip(), top_n=5)
                        if results:
                            st.markdown(f"**{len(results)} result(s) for:** _{ai_query}_")
                            st.markdown("---")
                            for r in results:
                                assay = next((a for a in ASSAYS if a["assay_id"] == r.get("assay_id")), None)
                                match_color = {"high": "badge-green", "medium": "badge-amber", "low": "badge-red"}.get(
                                    r.get("match_score", "low"), "badge-blue")
                                with st.expander(
                                    f"#{r.get('rank')} — {r.get('assay_id')} — {r.get('name', '')}",
                                    expanded=r.get("rank") == 1
                                ):
                                    st.markdown(
                                        f"<span class='{match_color}'>{r.get('match_score', '').upper()} MATCH</span>",
                                        unsafe_allow_html=True)
                                    st.markdown(f"**Why this assay:** {r.get('rationale', '')}")
                                    if assay:
                                        mc1, mc2, mc3 = st.columns(3)
                                        mc1.metric("Robot Time", f"{assay.get('robot_active_minutes', 0)} min")
                                        mc2.metric("Samples/Run", assay.get("throughput_samples_per_run", 0))
                                        mc3.metric("Workbench", assay.get("workbench_id", "N/A"))
                                        st.markdown(f"**Purpose:** {assay.get('purpose', '')}")

                                        # Export button directly from search results
                                        export_text = build_export_text(assay)
                                        st.download_button(
                                            label="⬇ Export this protocol",
                                            data=export_text,
                                            file_name=f"protocol_{assay['assay_id']}.txt",
                                            mime="text/plain",
                                            key=f"export_search_{assay['assay_id']}"
                                        )
                        else:
                            st.info("No results returned. Try rephrasing your question.")
                    except Exception as e:
                        st.error(f"AI search error: {e}. Check your ANTHROPIC_API_KEY in the .env file.")

        # ── AI TAB 2: Root cause analysis ──────────────────────────────
        with ai_tab2:
            st.subheader("Root cause analysis — when a run fails")
            st.caption("Enter the details of a failed run. AI diagnoses the most likely cause "
                       "and recommends corrective action — replacing the standard 1-2 hour analyst investigation.")

            rca_col1, rca_col2 = st.columns(2)
            with rca_col1:
                rca_assay = st.selectbox(
                    "Assay that failed",
                    ALL_IDS,
                    format_func=lambda x: f"{x} — {next(a['name'] for a in ASSAYS if a['assay_id'] == x)}"
                )
            with rca_col2:
                rca_assay_obj = next(a for a in ASSAYS if a["assay_id"] == rca_assay)
                criteria_keys = list(rca_assay_obj.get("acceptance_criteria", {}).keys())
                failed_criteria = st.multiselect(
                    "Which acceptance criteria failed?",
                    criteria_keys,
                    default=criteria_keys[:1] if criteria_keys else []
                )

            rca_notes = st.text_area(
                "Run notes — what did you observe? (any detail helps the AI)",
                placeholder="e.g. QC recovery was 78% (spec 85-115%). Column pressure spiked during run. Reagent lot changed this week.",
                height=100
            )

            rca_raw = st.text_area(
                "Raw results (optional — paste key numbers)",
                placeholder='e.g. {"standard_curve_r2": 0.9994, "qc_recovery_pct": 78, "column_pressure_bar": 310}',
                height=80
            )

            if st.button("Run Root Cause Analysis", type="primary", disabled=not failed_criteria):
                if not failed_criteria:
                    st.warning("Select at least one failed acceptance criterion.")
                else:
                    import json
                    raw_results = {}
                    if rca_raw.strip():
                        try:
                            raw_results = json.loads(rca_raw)
                        except Exception:
                            raw_results = {"notes": rca_raw}

                    run_record = {
                        "assay_id": rca_assay,
                        "raw_results": raw_results,
                        "notes": rca_notes,
                        "status": "fail"
                    }

                    with st.spinner(
                        "BioInterface AI is investigating root cause..."
                    ):
                        try:
                            rca_result = analyze_run_failure(rca_assay, run_record, failed_criteria)

                            conf_color = {"high": "badge-green", "medium": "badge-amber", "low": "badge-red"}.get(
                                rca_result.get("confidence", "low"), "badge-blue")

                            st.markdown("---")
                            st.markdown("### Root Cause Analysis Report")

                            st.markdown(
                                f"<span class='{conf_color}'>{rca_result.get('confidence', '').upper()} CONFIDENCE</span> &nbsp; "
                                + ('<span class="badge-red">DEVIATION REPORT REQUIRED</span>' if rca_result.get('requires_investigation') else '<span class="badge-green">NO FORMAL INVESTIGATION REQUIRED</span>'),
                                unsafe_allow_html=True)

                            st.markdown(f"**Most likely root cause:**")
                            st.markdown(f"<div class='ai-result'>{rca_result.get('most_likely_root_cause', 'Not determined')}</div>",
                                       unsafe_allow_html=True)

                            if rca_result.get("contributing_factors"):
                                st.markdown("**Contributing factors:**")
                                for f in rca_result["contributing_factors"]:
                                    st.markdown(f"- {f}")

                            st.markdown(f"**Corrective action (before next run):**")
                            st.markdown(f"<div class='ai-result'>{rca_result.get('corrective_action', 'Not determined')}</div>",
                                       unsafe_allow_html=True)

                            if rca_result.get("preventive_action"):
                                st.markdown(f"**Preventive action (systemic fix):** {rca_result['preventive_action']}")

                        except Exception as e:
                            st.error(f"RCA error: {e}")

        # ── AI TAB 3: Batch quality correlation ────────────────────────
        with ai_tab3:
            st.subheader("Cross-assay batch quality correlation")
            st.caption("AI connects results across multiple assays for the same batch — identifying coordinated "
                       "quality signals that no individual assay report would reveal.")

            batch_id_input = st.text_input(
                "Batch ID",
                placeholder="e.g. CHO-047-DS-031",
                help="Must match the batch_id used when storing run records in Supabase"
            )

            corr_assays = st.multiselect(
                "Assays to include (leave blank for all)",
                ALL_IDS,
                default=[],
                format_func=lambda x: f"{x} — {next(a['name'] for a in ASSAYS if a['assay_id'] == x)[:40]}"
            )

            if st.button("Run Correlation Analysis", type="primary"):
                if not batch_id_input.strip():
                    st.warning("Enter a batch ID.")
                else:
                    with st.spinner(
                        "BioInterface AI is correlating quality signals across batches..."
                    ):
                        try:
                            corr_result = correlate_batch_quality(
                                batch_id_input.strip(),
                                assay_ids=corr_assays if corr_assays else None
                            )

                            st.markdown("---")
                            st.markdown("### Batch Quality Correlation Report")

                            if corr_result.get("correlation_detected"):
                                signal_color = {
                                    "strong": "badge-red",
                                    "moderate": "badge-amber",
                                    "weak": "badge-blue"
                                }.get(corr_result.get("signal_strength", "weak"), "badge-blue")

                                st.markdown(
                                    f"<span class='badge-red'>CORRELATION DETECTED</span> &nbsp; "
                                    f"<span class='{signal_color}'>{corr_result.get('signal_strength', '').upper()} SIGNAL</span> &nbsp; "
                                    + ("<span class='badge-red'>QA ESCALATION RECOMMENDED</span>" if corr_result.get('escalate_to_qa') else ""),
                                    unsafe_allow_html=True)
                            else:
                                st.markdown("<span class='badge-green'>NO CORRELATION DETECTED</span>",
                                           unsafe_allow_html=True)

                            st.markdown("**Finding:**")
                            st.markdown(f"<div class='ai-result'>{corr_result.get('narrative', 'No narrative returned.')}</div>",
                                       unsafe_allow_html=True)

                            if corr_result.get("affected_assays"):
                                st.markdown(f"**Assays involved:** {', '.join(corr_result['affected_assays'])}")

                            if corr_result.get("process_hypothesis"):
                                st.markdown(f"**Process hypothesis:** {corr_result['process_hypothesis']}")

                            if corr_result.get("recommended_action"):
                                st.markdown(f"**Recommended action:**")
                                st.markdown(f"<div class='ai-result'>{corr_result['recommended_action']}</div>",
                                           unsafe_allow_html=True)

                        except Exception as e:
                            st.error(f"Correlation error: {e}. Make sure run records are stored in Supabase for batch {batch_id_input}.")

        # ── AI TAB 4: AutoMATE 96 optimisation ─────────────────────────
        with ai_tab4:
            st.subheader("AutoMATE 96 optimisation — AI instrument assignment and volume check")
            st.caption("Ask AI to split an assay across Rail robot + AutoMATE 96, "
                       "or flag volume incompatibilities with the AutoMATE 96 head ranges.")

            opt_assay = st.selectbox(
                "Select assay",
                ALL_IDS,
                format_func=lambda x: f"{x} — {next(a['name'] for a in ASSAYS if a['assay_id'] == x)}",
                key="opt_assay_select"
            )
            opt_assay_obj = next(a for a in ASSAYS if a["assay_id"] == opt_assay)

            oc1, oc2 = st.columns(2)
            with oc1:
                opt_go = st.button("Assign Instrument Steps", type="primary", key="opt_assign_btn")
            with oc2:
                vol_go = st.button("Check Volume Compatibility", key="opt_volcheck_btn")

            # ── Assign Instrument Steps ─────────────────────────────
            if opt_go:
                with st.spinner("BioInterface AI is assigning instrument steps..."):
                    try:
                        result = assign_instrument_steps(opt_assay)

                        st.markdown("---")
                        st.markdown(f"### Instrument assignment — {opt_assay}")

                        mc1, mc2, mc3 = st.columns(3)
                        mc1.metric("AutoMATE 96", result.get("automate_96_count", 0))
                        mc2.metric("Rail robot", result.get("rail_robot_count", 0))
                        mc3.metric("Total steps", len(result.get("assignments", [])))

                        if result.get("summary"):
                            st.markdown(f"**Summary:** {result['summary']}")

                        assignments = result.get("assignments", [])
                        if assignments:
                            color_map = {
                                "automate_96": "#fef3c7",
                                "rail_robot": "#dbeafe",
                                "analyst": "#fce7f3",
                            }
                            badge_map = {
                                "automate_96": "badge-amber",
                                "rail_robot": "badge-blue",
                                "analyst": "badge-purple",
                            }
                            for a_item in assignments:
                                inst = a_item.get("instrument", "rail_robot")
                                bg = color_map.get(inst, "#f3f4f6")
                                badge = badge_map.get(inst, "badge-blue")
                                st.markdown(
                                    f"<div style='background:{bg};padding:10px;border-radius:6px;margin:4px 0'>"
                                    f"<span class='{badge}'>{inst.upper().replace('_', ' ')}</span> "
                                    f"&nbsp;<strong>Step {a_item.get('step_num')}</strong>: "
                                    f"{a_item.get('step_text', '')[:180]}"
                                    f"<br><em>→ {a_item.get('reasoning', '')}</em>"
                                    f"</div>",
                                    unsafe_allow_html=True
                                )
                        else:
                            st.info("No assignments returned. Check that ANTHROPIC_API_KEY is set.")

                    except Exception as e:
                        st.error(f"AI assignment error: {e}")

            # ── Check Volume Compatibility ──────────────────────────
            if vol_go:
                with st.spinner("BioInterface AI is checking volume compatibility..."):
                    try:
                        result = check_volume_compatibility(opt_assay)

                        st.markdown("---")
                        st.markdown(f"### Volume compatibility — {opt_assay}")

                        if result.get("compatible"):
                            st.markdown(
                                "<span class='badge-green'>COMPATIBLE</span>",
                                unsafe_allow_html=True
                            )
                        else:
                            st.markdown(
                                "<span class='badge-red'>INCOMPATIBLE — REVIEW FLAGS</span>",
                                unsafe_allow_html=True
                            )

                        if result.get("head_changes_required"):
                            st.warning("Head change required mid-run — plan for instrument pause between steps.")
                        else:
                            st.success("No head change required — single head covers every AutoMATE 96 step.")

                        flags = result.get("flags", [])
                        if flags:
                            st.markdown(f"**{len(flags)} flag(s):**")
                            for f in flags:
                                st.markdown(
                                    f"- **Step {f.get('step_num')}** · volume `{f.get('volume', 'n/a')}` · "
                                    f"issue: {f.get('issue', '')}  \n"
                                    f"  → _{f.get('suggestion', '')}_"
                                )
                        else:
                            st.info("No volume flags raised.")

                        if result.get("recommendation"):
                            st.markdown("**Recommendation:**")
                            st.markdown(
                                f"<div class='ai-result'>{result['recommendation']}</div>",
                                unsafe_allow_html=True
                            )

                    except Exception as e:
                        st.error(f"Volume check error: {e}")


# ═══════════════════════════════════════════════════════════════════════
#  SECTION: EXPERIMENT WIZARD
# ═══════════════════════════════════════════════════════════════════════

elif section == "Experiment Wizard":
    st.title("🧙 Experiment Design Wizard")
    st.caption(
        "Answer five questions — get a recommended assay panel with robot time estimate, "
        "reagent list, and run order. Powered by your assay library and AI."
    )

    st.markdown("---")

    # ── TWO MODES ────────────────────────────────────────────────────
    wizard_mode = st.radio(
        "How do you want to describe your experiment?",
        ["Guided (answer questions)", "Free text (describe in plain English)"],
        horizontal=True,
        key="wizard_mode"
    )

    st.markdown("---")

    # ════════════════════════════════════════════════════════════════
    #  MODE 1 — GUIDED (form-based, no AI required)
    # ════════════════════════════════════════════════════════════════
    if wizard_mode == "Guided (answer questions)":

        st.subheader("Tell us about your experiment")

        wc1, wc2 = st.columns(2)

        with wc1:
            # Q1 — Biological question maps to product_types
            bio_question = st.selectbox(
                "1. What are you working on?",
                [
                    "mAb / Fc-fusion protein characterisation",
                    "Cell culture process monitoring",
                    "Drug substance release testing",
                    "In-process quality checks",
                    "Formulation development",
                    "Cell viability and metabolite monitoring",
                    "Bioburden and sterility testing",
                    "Buffer and media QC",
                ],
                key="w_bio_question"
            )

            # Q2 — Sample type
            sample_type = st.selectbox(
                "2. What sample type do you have?",
                [
                    "Bioreactor harvest / conditioned medium",
                    "Post-Protein A eluate",
                    "Purified drug substance",
                    "Formulated drug product",
                    "Cell culture supernatant",
                    "Process buffer",
                    "Cell culture media",
                    "In-process intermediate",
                ],
                key="w_sample_type"
            )

            # Q3 — Sample count
            sample_count = st.slider(
                "3. How many samples per run?",
                min_value=1, max_value=96, value=12, step=1,
                key="w_sample_count"
            )

        with wc2:
            # Q4 — Timeline
            timeline_hours = st.selectbox(
                "4. What is your time constraint?",
                [
                    "Under 1 hour (urgent in-process check)",
                    "Half day (1–4 hours)",
                    "Full day (4–8 hours)",
                    "Overnight (8–24 hours)",
                    "Multi-day (>24 hours) — ok for release testing",
                ],
                key="w_timeline"
            )

            # Q5 — Environment
            environment = st.selectbox(
                "5. What environment are you working in?",
                [
                    "Standard lab bench (BSL-1) — any assay",
                    "BSL-2 containment available",
                    "ISO Class 5 / Grade A clean room available",
                    "Standard bench only — exclude sterility assays",
                ],
                key="w_environment"
            )

            # Optional — automation difficulty preference
            max_difficulty = st.select_slider(
                "Maximum automation complexity",
                options=["easy", "easy + medium", "all (including complex)"],
                value="easy + medium",
                key="w_difficulty"
            )

        st.markdown("---")

        if st.button("Generate Recommended Panel", type="primary", key="w_run_guided"):

            # ── Map answers to filters ──────────────────────────────
            product_map = {
                "mAb / Fc-fusion protein characterisation":
                    ["Monoclonal Antibodies", "Fc-fusion proteins"],
                "Cell culture process monitoring":
                    ["CHO cell culture", "HEK293 culture"],
                "Drug substance release testing":
                    ["Monoclonal Antibodies", "Fc-fusion proteins", "Bispecific antibodies"],
                "In-process quality checks":
                    ["CHO cell culture", "In-process samples"],
                "Formulation development":
                    ["Drug substance", "Drug product formulations"],
                "Cell viability and metabolite monitoring":
                    ["CHO cell culture", "HEK293 culture"],
                "Bioburden and sterility testing":
                    ["Drug substance bulk", "In-process samples"],
                "Buffer and media QC":
                    ["Process buffers", "Cell culture media"],
            }

            timeline_map = {
                "Under 1 hour (urgent in-process check)": 60,
                "Half day (1–4 hours)": 240,
                "Full day (4–8 hours)": 480,
                "Overnight (8–24 hours)": 1440,
                "Multi-day (>24 hours) — ok for release testing": 99999,
            }

            env_exclude = {
                "Standard bench only — exclude sterility assays":
                    ["Complex", "ISO Class 5"],
            }

            allowed_diffs = {
                "easy": ["easy"],
                "easy + medium": ["easy", "medium"],
                "all (including complex)": ["easy", "medium", "complex"],
            }

            target_products = product_map.get(bio_question, [])
            max_total_minutes = timeline_map.get(timeline_hours, 99999)
            allowed_difficulties = allowed_diffs.get(max_difficulty, ["easy", "medium"])

            # ── Filter assays ───────────────────────────────────────
            filtered = []
            for a in ASSAYS:
                # Product type match
                assay_products = a.get("product_types", [])
                product_match = any(
                    tp.lower() in " ".join(assay_products).lower()
                    for tp in target_products
                ) if target_products else True

                # Throughput match
                throughput_match = a.get("throughput_samples_per_run", 0) >= sample_count * 0.5

                # Timeline match (total duration in hours × 60)
                total_mins = a.get("total_assay_duration_hours", 0) * 60
                timeline_match = total_mins <= max_total_minutes

                # Difficulty match
                diff_match = a.get("automation_difficulty", "easy") in allowed_difficulties

                # Environment match
                env_ok = True
                if environment == "Standard bench only — exclude sterility assays":
                    if "complex" in a.get("automation_difficulty", "") and \
                       "Class 5" in a.get("environment_requirement", ""):
                        env_ok = False

                if product_match and throughput_match and timeline_match and diff_match and env_ok:
                    filtered.append(a)

            # ── Display results ─────────────────────────────────────
            if not filtered:
                st.warning(
                    "No assays matched all your criteria. "
                    "Try relaxing the timeline or difficulty constraints."
                )
            else:
                # Sort by robot active time (fastest first)
                filtered.sort(key=lambda x: x.get("robot_active_minutes", 0))

                st.success(
                    f"Found {len(filtered)} recommended assay(s) for your experiment"
                )

                # Summary metrics
                total_robot_min = sum(a.get("robot_active_minutes", 0) for a in filtered)
                workbenches = set(a.get("workbench_id", "N/A") for a in filtered)
                all_regs = set(r for a in filtered for r in a.get("regulatory", []))

                sm1, sm2, sm3, sm4 = st.columns(4)
                sm1.metric("Assays recommended", len(filtered))
                sm2.metric("Total robot time", f"{total_robot_min} min")
                sm3.metric("Workbenches needed", len(workbenches))
                sm4.metric("Regulatory refs", len(all_regs))

                st.markdown("---")
                st.subheader("Recommended panel — run in this order")

                for i, a in enumerate(filtered, 1):
                    badge = DIFF_BADGE[a["automation_difficulty"]]
                    with st.expander(
                        f"#{i} — {a['assay_id']} — {a['name']} "
                        f"({a.get('robot_active_minutes', 0)} min robot time)",
                        expanded=i <= 3
                    ):
                        ec1, ec2, ec3, ec4 = st.columns(4)
                        ec1.metric("Robot time", f"{a.get('robot_active_minutes', 0)} min")
                        ec2.metric("Samples/run", a.get("throughput_samples_per_run", 0))
                        ec3.metric("Workbench", a.get("workbench_id", "N/A"))
                        ec4.markdown(
                            f"<span class='{badge}'>"
                            f"{a['automation_difficulty'].upper()}</span>",
                            unsafe_allow_html=True
                        )
                        st.markdown(f"**Purpose:** {a['purpose']}")
                        st.markdown(
                            f"**Environment:** {a.get('environment_requirement', 'N/A')}"
                        )

                        # Export button per assay
                        export_text = build_export_text(a)
                        st.download_button(
                            label=f"⬇ Export {a['assay_id']} protocol",
                            data=export_text,
                            file_name=f"protocol_{a['assay_id']}.txt",
                            mime="text/plain",
                            key=f"wizard_export_{a['assay_id']}"
                        )

                st.markdown("---")

                # Aggregated reagent list
                st.subheader("Reagents to order — full panel")
                reagent_map = {}
                for a in filtered:
                    for r in a.get("reagents", []):
                        reagent_map.setdefault(r, []).append(a["assay_id"])

                for reagent, used_in in sorted(reagent_map.items()):
                    shared = len(used_in) > 1
                    shared_tag = (
                        f" — shared across {', '.join(used_in)}" if shared else ""
                    )
                    bullet = "✦" if shared else "•"
                    st.markdown(f"{bullet} **{reagent}**{shared_tag}")

                st.caption(
                    "✦ = shared reagent — order once. "
                    "• = single-assay reagent."
                )

                # Export full panel plan
                panel_lines = []
                panel_lines.append("RAIL SYSTEM — EXPERIMENT PANEL PLAN")
                panel_lines.append("=" * 60)
                panel_lines.append(f"Biological objective : {bio_question}")
                panel_lines.append(f"Sample type          : {sample_type}")
                panel_lines.append(f"Sample count         : {sample_count}")
                panel_lines.append(f"Timeline             : {timeline_hours}")
                panel_lines.append(f"Environment          : {environment}")
                panel_lines.append(f"Total robot time     : {total_robot_min} minutes")
                panel_lines.append("")
                panel_lines.append("RECOMMENDED ASSAY SEQUENCE")
                panel_lines.append("-" * 60)
                for i, a in enumerate(filtered, 1):
                    panel_lines.append(
                        f"#{i:02d}  {a['assay_id']}  {a['name']}  "
                        f"({a.get('robot_active_minutes', 0)} min robot)  "
                        f"[{a['automation_difficulty'].upper()}]"
                    )
                panel_lines.append("")
                panel_lines.append("REAGENTS REQUIRED")
                panel_lines.append("-" * 60)
                for reagent, used_in in sorted(reagent_map.items()):
                    panel_lines.append(
                        f"  {reagent}  [{', '.join(used_in)}]"
                    )

                st.download_button(
                    label="⬇ Export full panel plan",
                    data="\n".join(panel_lines),
                    file_name="experiment_panel_plan.txt",
                    mime="text/plain",
                    key="wizard_export_panel"
                )

    # ════════════════════════════════════════════════════════════════
    #  MODE 2 — FREE TEXT (AI-powered, requires ai_layer.py)
    # ════════════════════════════════════════════════════════════════
    else:
        st.subheader("Describe your experiment in plain English")
        st.caption(
            "No need to know assay names or field names. "
            "Just describe what you are trying to do."
        )

        placeholder_examples = [
            "I want to characterise my mAb before filing a BLA — "
            "I have 50 samples and 2 days",
            "We are running a CHO fed-batch and need in-process checks "
            "every 24 hours during the culture",
            "I need to confirm drug substance quality before formulation — "
            "sterility, protein content, aggregation, and pH",
            "Quick check on 12 bioreactor samples before the end of shift — "
            "viability, glucose, lactate",
        ]

        free_text = st.text_area(
            "Describe your experiment",
            placeholder="e.g. I need to release test a mAb batch before shipment — "
            "I have 24 samples and need results within 8 hours",
            height=120,
            key="wizard_free_text"
        )

        st.caption("Example prompts:")
        ex_cols = st.columns(2)
        for i, ex in enumerate(placeholder_examples):
            if ex_cols[i % 2].button(
                f'"{ex[:65]}..."',
                key=f"wex_{i}",
                use_container_width=True
            ):
                free_text = ex

        if st.button(
            "Generate Panel with AI",
            type="primary",
            key="wizard_ai_run",
            disabled=not AI_AVAILABLE
        ):
            if not free_text.strip():
                st.warning("Enter a description of your experiment first.")
            elif not AI_AVAILABLE:
                st.error(
                    "AI is not active. Set up ai_layer.py and .env file first."
                )
            else:
                with st.spinner(
                    "BioInterface AI is reasoning over the corpus to select the best assay panel..."
                ):
                    try:
                        # Enrich the query to get panel-level recommendations
                        enriched_query = (
                            f"{free_text.strip()} — "
                            "recommend the complete assay panel in priority order, "
                            "considering robot time efficiency and regulatory coverage"
                        )
                        results = search_protocols(enriched_query, top_n=8)

                        if results:
                            st.success(
                                f"AI recommended {len(results)} assay(s) for your experiment"
                            )
                            st.markdown("---")

                            ai_assays = [
                                a for a in ASSAYS
                                if a["assay_id"] in [r.get("assay_id") for r in results]
                            ]
                            total_robot = sum(
                                a.get("robot_active_minutes", 0)
                                for a in ai_assays
                            )

                            am1, am2 = st.columns(2)
                            am1.metric("Assays recommended", len(results))
                            am2.metric("Total robot time", f"{total_robot} min")

                            st.markdown("---")
                            st.subheader("AI recommended panel")

                            for r in results:
                                assay = next(
                                    (a for a in ASSAYS
                                     if a["assay_id"] == r.get("assay_id")),
                                    None
                                )
                                match_color = {
                                    "high": "badge-green",
                                    "medium": "badge-amber",
                                    "low": "badge-red"
                                }.get(r.get("match_score", "low"), "badge-blue")

                                with st.expander(
                                    f"#{r.get('rank')} — "
                                    f"{r.get('assay_id')} — {r.get('name', '')}",
                                    expanded=r.get("rank") == 1
                                ):
                                    st.markdown(
                                        f"<span class='{match_color}'>"
                                        f"{r.get('match_score','').upper()} MATCH"
                                        f"</span>",
                                        unsafe_allow_html=True
                                    )
                                    st.markdown(
                                        f"**Why this assay:** {r.get('rationale', '')}"
                                    )
                                    if assay:
                                        mc1, mc2, mc3 = st.columns(3)
                                        mc1.metric(
                                            "Robot time",
                                            f"{assay.get('robot_active_minutes', 0)} min"
                                        )
                                        mc2.metric(
                                            "Samples/run",
                                            assay.get("throughput_samples_per_run", 0)
                                        )
                                        mc3.metric(
                                            "Workbench",
                                            assay.get("workbench_id", "N/A")
                                        )
                                        st.markdown(
                                            f"**Purpose:** {assay.get('purpose', '')}"
                                        )

                                        export_text = build_export_text(assay)
                                        st.download_button(
                                            label=f"⬇ Export {assay['assay_id']} protocol",
                                            data=export_text,
                                            file_name=f"protocol_{assay['assay_id']}.txt",
                                            mime="text/plain",
                                            key=f"wizard_ai_export_{assay['assay_id']}"
                                        )
                        else:
                            st.info(
                                "AI could not find matching assays. "
                                "Try rephrasing your description."
                            )
                    except Exception as e:
                        st.error(f"AI wizard error: {e}")

        if not AI_AVAILABLE:
            st.info(
                "Free text mode requires AI Intelligence to be active. "
                "Complete the AI setup first, or use Guided mode above "
                "which works without AI."
            )


# ═══════════════════════════════════════════════════════════════════════
#  SECTION: SYSTEM RUN PLANNER
# ═══════════════════════════════════════════════════════════════════════

elif section == "System Run Planner":
    st.title("⚙ System Run Planner")
    st.caption(
        "Plan a multi-assay run across Rail System and AutoMATE 96 — "
        "see estimated timeline and instrument handoffs."
    )

    st.markdown("---")

    assay_options = {f"{a['assay_id']} — {a['name']}": a["assay_id"] for a in ASSAYS}
    selected_labels = st.multiselect(
        "Select assays to include in the run",
        list(assay_options.keys()),
        key="planner_select",
    )
    selected_ids = [assay_options[label] for label in selected_labels]
    # Preserve user's selection order (multiselect returns in click order)
    selected_assays = [next(a for a in ASSAYS if a["assay_id"] == sid) for sid in selected_ids]

    if not selected_assays:
        st.info("Select one or more assays above to see the run plan.")
    else:
        st.markdown("---")

        total_robot_min = sum(a.get("robot_active_minutes", 0) for a in selected_assays)
        total_automate_steps = sum(len(a.get("automate_96_steps", [])) for a in selected_assays)
        workbenches = sorted(set(a.get("workbench_id", "N/A") for a in selected_assays))

        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric("Assays selected", len(selected_assays))
        mc2.metric("Robot active minutes", total_robot_min)
        mc3.metric("AutoMATE 96 steps", total_automate_steps)
        mc4.metric("Workbenches needed", len(workbenches))

        st.markdown("---")

        st.subheader("Instrument timeline (minutes from run start)")

        bars = []
        cumulative = 0
        for a in selected_assays:
            rail_start = cumulative
            rail_dur = a.get("robot_active_minutes", 0)
            rail_end = rail_start + rail_dur

            total_steps = len(a.get("robot_steps", [])) or 1
            automate_count = len(a.get("automate_96_steps", []))
            automate_frac = automate_count / total_steps
            automate_dur = rail_dur * automate_frac
            automate_start = rail_start + 2 if automate_dur > 0 else None
            automate_end = (automate_start + automate_dur) if automate_dur > 0 else None

            bars.append({
                "aid": a["assay_id"],
                "rail_start": rail_start,
                "rail_end": rail_end,
                "rail_dur": rail_dur,
                "automate_start": automate_start,
                "automate_end": automate_end,
                "automate_dur": automate_dur,
            })
            cumulative = rail_end

        fig = go.Figure()
        for b in bars:
            fig.add_trace(go.Bar(
                y=["Rail Robot"],
                x=[b["rail_dur"]],
                base=[b["rail_start"]],
                orientation="h",
                marker_color="#3b82f6",
                text=[b["aid"]],
                textposition="inside",
                insidetextanchor="middle",
                hovertemplate=(
                    f"{b['aid']}<br>Rail Robot<br>"
                    f"Start: {b['rail_start']} min<br>"
                    f"Duration: {b['rail_dur']} min<extra></extra>"
                ),
                showlegend=False,
            ))
            if b["automate_dur"] > 0:
                fig.add_trace(go.Bar(
                    y=["AutoMATE 96"],
                    x=[b["automate_dur"]],
                    base=[b["automate_start"]],
                    orientation="h",
                    marker_color="#f59e0b",
                    text=[b["aid"]],
                    textposition="inside",
                    insidetextanchor="middle",
                    hovertemplate=(
                        f"{b['aid']}<br>AutoMATE 96<br>"
                        f"Start: {b['automate_start']:.1f} min<br>"
                        f"Duration: {b['automate_dur']:.1f} min<extra></extra>"
                    ),
                    showlegend=False,
                ))

        fig.update_layout(
            barmode="stack",
            xaxis_title="Minutes from run start",
            yaxis_title="",
            height=260,
            margin=dict(l=20, r=20, t=20, b=40),
            plot_bgcolor="rgba(0,0,0,0)",
        )
        fig.update_yaxes(categoryorder="array", categoryarray=["AutoMATE 96", "Rail Robot"])
        st.plotly_chart(fig, use_container_width=True)

        st.caption(
            f"Total wall-clock time: **{cumulative} min** (sequential rail execution). "
            "AutoMATE 96 bars overlap the Rail Robot bar to show parallel operation — "
            "AutoMATE duration estimated as robot active minutes × (AutoMATE steps / total steps)."
        )

        st.markdown("---")

        st.subheader("Instrument handoffs")
        table_rows = []
        for a in selected_assays:
            total_steps = len(a.get("robot_steps", []))
            automate_steps = len(a.get("automate_96_steps", []))
            rail_steps = total_steps - automate_steps
            table_rows.append({
                "Assay ID": a["assay_id"],
                "Assay Name": a["name"],
                "Rail Steps": rail_steps,
                "AutoMATE Steps": automate_steps,
                "Head": a.get("automate_96_head", "not applicable"),
                "Workbench": a.get("workbench_id", "N/A"),
                "Robot min": a.get("robot_active_minutes", 0),
            })
        st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)

        st.markdown("---")

        st.subheader("Combined reagent list")
        reagent_map = {}
        for a in selected_assays:
            for r in a.get("reagents", []):
                reagent_map.setdefault(r, []).append(a["assay_id"])

        shared = sorted(
            [(r, aids) for r, aids in reagent_map.items() if len(aids) > 1],
            key=lambda x: (-len(x[1]), x[0]),
        )
        single = sorted(
            [(r, aids) for r, aids in reagent_map.items() if len(aids) == 1],
            key=lambda x: x[0],
        )

        if shared:
            st.markdown("**✦ Shared reagents (order once, used across multiple assays)**")
            for r, aids in shared:
                st.markdown(f"✦ **{r}** — used in {', '.join(aids)}")

        if single:
            if shared:
                st.markdown("")
            st.markdown("**Single-assay reagents**")
            for r, aids in single:
                st.markdown(f"• {r} — {aids[0]}")

        st.markdown("---")

        plan_lines = []
        plan_lines.append("=" * 70)
        plan_lines.append("RAIL SYSTEM — SYSTEM RUN PLAN")
        plan_lines.append("=" * 70)
        plan_lines.append(f"Assays selected     : {len(selected_assays)}")
        plan_lines.append(f"Total run time est. : {cumulative} minutes (sequential rail)")
        plan_lines.append(f"Robot active min    : {total_robot_min}")
        plan_lines.append(f"AutoMATE 96 steps   : {total_automate_steps}")
        plan_lines.append(f"Workbenches needed  : {', '.join(workbenches)}")
        plan_lines.append("")
        plan_lines.append("ASSAY SEQUENCE")
        plan_lines.append("-" * 70)
        for i, (a, b) in enumerate(zip(selected_assays, bars), 1):
            total_steps = len(a.get("robot_steps", []))
            automate_steps = len(a.get("automate_96_steps", []))
            rail_steps = total_steps - automate_steps
            plan_lines.append(f"  #{i:02d}  {a['assay_id']}  {a['name']}")
            plan_lines.append(
                f"        Rail {b['rail_start']}–{b['rail_end']} min "
                f"({rail_steps} rail steps)  |  "
                f"AutoMATE 96: {automate_steps} step(s), head {a.get('automate_96_head', 'n/a')}  |  "
                f"WB: {a.get('workbench_id', 'N/A')}"
            )
        plan_lines.append("")
        plan_lines.append("INSTRUMENT HANDOFFS")
        plan_lines.append("-" * 70)
        plan_lines.append(f"{'Assay':<12}{'Rail':>6}{'AutoMATE':>10}{'Head':>18}{'WB':>6}{'Min':>6}")
        for row in table_rows:
            plan_lines.append(
                f"{row['Assay ID']:<12}{row['Rail Steps']:>6}{row['AutoMATE Steps']:>10}"
                f"{row['Head']:>18}{row['Workbench']:>6}{row['Robot min']:>6}"
            )
        plan_lines.append("")
        plan_lines.append("REAGENTS REQUIRED")
        plan_lines.append("-" * 70)
        if shared:
            plan_lines.append("SHARED (order once):")
            for r, aids in shared:
                plan_lines.append(f"  ✦ {r}  [{', '.join(aids)}]")
        if single:
            plan_lines.append("SINGLE-ASSAY:")
            for r, aids in single:
                plan_lines.append(f"  • {r}  [{aids[0]}]")
        plan_lines.append("")
        plan_lines.append("=" * 70)
        plan_lines.append("Generated by BioInterface v1.0")
        plan_lines.append("=" * 70)

        st.download_button(
            label="⬇ Export full run plan",
            data="\n".join(plan_lines),
            file_name="system_run_plan.txt",
            mime="text/plain",
            key="planner_export",
            type="primary",
        )
