"""Streamlit dashboard for exploring recorded or synthetic eye-tracking sessions.

Loads a gaze CSV (``t,x,y``) and an optional pupil CSV (``t,size[,unit]``),
runs them through itrace's analysis pipeline, and renders the resulting
fixations/saccades/microsaccades, main-sequence fit, pupillometry, and
quality diagnostics. Also exposes the synthetic-domain validation suite so a
recording's detection quality can be checked against known ground truth.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from itrace import io as itio
from itrace import pipeline, validation
from itrace.config import AnalysisConfig, DetectionConfig
from itrace.synthetic import SyntheticSessionSpec, synthetic_session
from itrace.types import GazeStream, PupilStream
from itrace.viz.dashboard import session_dashboard

st.set_page_config(page_title="iTrace session dashboard", layout="wide")
st.title("iTrace - eye-movement session dashboard")
st.write(
    "Load a recorded gaze/pupil CSV, or generate a synthetic session with known "
    "ground truth, then inspect fixations, saccades, microsaccades, the main "
    "sequence, pupillometry, and recording-quality diagnostics."
)

if "gaze" not in st.session_state:
    st.session_state.gaze = None
    st.session_state.pupil = None
    st.session_state.truth = None

with st.sidebar:
    st.header("1. Load a session")
    gaze_file = st.file_uploader("Gaze CSV (t,x,y)", type="csv", key="gaze_upload")
    pupil_file = st.file_uploader("Pupil CSV (t,size[,unit]) - optional", type="csv", key="pupil_upload")
    if st.button("Load uploaded CSV(s)"):
        if gaze_file is None:
            st.error("Upload a gaze CSV first.")
        else:
            with tempfile.TemporaryDirectory() as tmp:
                gaze_path = Path(tmp) / "gaze.csv"
                gaze_path.write_bytes(gaze_file.getvalue())
                st.session_state.gaze = itio.read_gaze_csv(gaze_path)
                if pupil_file is not None:
                    pupil_path = Path(tmp) / "pupil.csv"
                    pupil_path.write_bytes(pupil_file.getvalue())
                    st.session_state.pupil = itio.read_pupil_csv(pupil_path)
                else:
                    st.session_state.pupil = None
            st.session_state.truth = None
            st.success(f"Loaded {len(st.session_state.gaze)} gaze samples.")

    st.divider()
    st.header("2. Or generate synthetic ground truth")
    n_saccades = st.slider("Number of saccades", 2, 12, 6)
    dropout = st.slider("Dropout fraction", 0.0, 0.2, 0.0, 0.01)
    noise = st.slider("Gaze noise (deg)", 0.0, 0.1, 0.02, 0.005)
    seed = st.number_input("Seed", min_value=0, value=0, step=1)
    if st.button("Generate synthetic session"):
        spec = SyntheticSessionSpec(
            n_saccades=n_saccades, dropout_fraction=dropout, noise_deg=noise, seed=int(seed)
        )
        gaze, pupil, truth = synthetic_session(spec)
        st.session_state.gaze = gaze
        st.session_state.pupil = pupil
        st.session_state.truth = truth
        st.success(f"Generated a {len(truth.saccades)}-saccade synthetic session.")

    st.divider()
    st.header("3. Detection settings")
    velocity_threshold = st.slider("I-VT velocity threshold (deg/s)", 10.0, 100.0, 30.0, 5.0)
    include_micro = st.checkbox("Detect microsaccades (Engbert & Kliegl)", value=True)

gaze: GazeStream | None = st.session_state.gaze
pupil: PupilStream | None = st.session_state.pupil
truth = st.session_state.truth

if gaze is None:
    st.info("Load a CSV or generate a synthetic session from the sidebar to begin.")
    st.stop()

analysis_config = AnalysisConfig(
    detection=DetectionConfig(
        velocity_threshold_deg_s=velocity_threshold,
        include_microsaccades=include_micro,
    )
)
report = pipeline.analyze_session(gaze, pupil, config=analysis_config)

st.header("Session dashboard")
fig = session_dashboard(report, gaze, pupil)
st.pyplot(fig)

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Samples", report.n_samples)
col2.metric("Duration (s)", f"{report.duration_s:.2f}")
col3.metric("Fixations", len(report.fixations))
col4.metric("Saccades", len(report.saccades))
col5.metric("Microsaccades", len(report.microsaccades))

st.subheader("Main sequence fit")
if report.main_sequence:
    st.json(report.main_sequence)
else:
    st.write("Fewer than 3 saccades detected; no main-sequence fit.")

st.subheader("Saccades")
if report.saccades:
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "onset_t": s.onset_t,
                    "offset_t": s.offset_t,
                    "duration_s": s.duration_s,
                    "amplitude_deg": s.amplitude_deg,
                    "direction_deg": s.direction_deg,
                    "peak_velocity_deg_s": s.peak_velocity_deg_s,
                }
                for s in report.saccades
            ]
        )
    )
else:
    st.write("No saccades detected.")

if truth is not None:
    st.subheader("Synthetic ground truth (for comparison)")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "onset_t": t.onset_t,
                    "offset_t": t.offset_t,
                    "amplitude_deg": t.amplitude_deg,
                    "direction_deg": t.direction_deg,
                    "peak_velocity_deg_s": t.peak_velocity_deg_s,
                }
                for t in truth.saccades
            ]
        )
    )

st.subheader("Pupillometry")
if report.pupil:
    st.json(report.pupil)
else:
    st.write("No pupil data loaded.")

st.subheader("Recording-quality diagnostics")
st.json(report.quality)

st.header("Synthetic-domain validation (detector recovery vs. known ground truth)")
st.write(
    "Runs the built-in synthetic domains (clean desktop, webcam jitter, head-pose "
    "drift, low-light dropout), each repeated with several seeds, and compares "
    "detected saccades against the simulator's ground truth."
)
repetitions = st.slider("Repetitions per domain", 1, 5, 2)
if st.button("Run synthetic validation suite"):
    with st.spinner("Running synthetic-domain validation..."):
        suite = validation.synthetic_validation_suite(repetitions=repetitions)
    st.subheader("Cross-domain summary")
    st.json(suite["cross_domain"])
    for domain in suite["domains"]:
        with st.expander(f"{domain['label']} ({domain['domain']})"):
            st.json(domain["summary"])
