#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
河区调度模型 - Streamlit 界面

围绕 src/district/scheduler.py 中未改动的调度核心，提供最小的交互界面：
上传（或使用内置样例）输入数据 -> 运行逐日调度 -> 浏览各分区结果 -> 导出。
"""
import tempfile
import zipfile
from pathlib import Path

import pandas as pd
import streamlit as st

from src.common.st_utils import page_config, excel_download, footer
from src.district.scheduler import DistrictScheduler
from src.district.config import DISTRICT_NAME_MAPPING

PROJECT_ROOT = Path(__file__).resolve().parent
SAMPLE_DIR = PROJECT_ROOT / "data" / "sample"

page_config("河区调度 | hydro-district", icon="🌊")

st.title("🌊 河区调度模型 — 19 河区逐日供需调度")
st.caption("上传分区输入数据（ZIP），或直接使用内置样例，运行逐日水平衡调度并浏览各分区结果。")

if "run_output_dir" not in st.session_state:
    st.session_state.run_output_dir = None
    st.session_state.run_results = None

with st.sidebar:
    st.header("输入数据")
    use_sample = st.button("▶ 使用内置样例数据运行", use_container_width=True)
    st.markdown("---")
    uploaded_zip = st.file_uploader(
        "或上传 ZIP（包含 input_*.txt + static_*.txt）", type=["zip"]
    )
    run_upload = st.button("▶ 运行上传的数据", use_container_width=True, disabled=uploaded_zip is None)

def _run_scheduler(data_dir: Path):
    tmp_out = Path(tempfile.mkdtemp(prefix="hydro_district_out_"))
    scheduler = DistrictScheduler(data_path=data_dir, output_path=tmp_out)
    with st.spinner("正在逐日计算供需平衡..."):
        results = scheduler.run()
    if results.get("status") != "success":
        st.error(f"计算失败: {results.get('message', '未知错误')}")
        return
    st.session_state.run_output_dir = tmp_out
    st.session_state.run_results = results
    st.success(results.get("message", "完成"))

if use_sample:
    _run_scheduler(SAMPLE_DIR)

if run_upload and uploaded_zip is not None:
    tmp_in = Path(tempfile.mkdtemp(prefix="hydro_district_in_"))
    with zipfile.ZipFile(uploaded_zip) as z:
        z.extractall(tmp_in)
    data_dir = tmp_in
    if not any(tmp_in.glob("input_*.txt")):
        for sub in tmp_in.iterdir():
            if sub.is_dir() and any(sub.glob("input_*.txt")):
                data_dir = sub
                break
    if not any(data_dir.glob("input_*.txt")):
        st.error("ZIP 内未找到 input_*.txt 文件")
    else:
        _run_scheduler(data_dir)

results = st.session_state.run_results
output_dir = st.session_state.run_output_dir

if results:
    st.subheader("调度汇总")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("处理分区数", results.get("districts_processed", 0))
    c2.metric("总需水量", f"{results.get('total_water_demand', 0):,.1f}")
    c3.metric("总来水量", f"{results.get('total_water_supply', 0):,.1f}")
    c4.metric("总缺水量", f"{results.get('total_shortage', 0):,.1f}")

    st.subheader("分区结果浏览器")
    available = {
        code: name
        for name, code in DISTRICT_NAME_MAPPING.items()
        if (output_dir / f"{code}.txt").exists()
    }
    if available:
        code = st.selectbox(
            "选择河区", options=list(available.keys()),
            format_func=lambda c: f"{available[c]} ({c})",
        )
        df = pd.read_csv(output_dir / f"{code}.txt", sep="\t")
        st.dataframe(df, use_container_width=True)
        plot_cols = [c for c in ["合计来水", "总需水量", "缺水(浙东需供)"] if c in df.columns]
        if plot_cols:
            st.line_chart(df.set_index("日期")[plot_cols])
        excel_download({available[code]: df}, filename=f"{code}.xlsx")
    else:
        st.warning("未找到分区输出文件")

footer("河区调度", repo_url="https://github.com/zengtianli/hydro-district")
