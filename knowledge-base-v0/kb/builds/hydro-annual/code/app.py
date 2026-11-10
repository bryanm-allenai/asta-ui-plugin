"""hydro-annual — 浙江省水资源年报数据查询与导出工具 (Streamlit)"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from src.annual.data_loader import (
    get_available_cities,
    get_available_tables,
    get_available_years,
    load_table,
)
from src.annual.query_core import query_data
from src.common.st_utils import excel_download, footer, page_config

page_config("浙江省水资源年报", icon="📊")

st.title("📊 浙江省水资源年报查询与导出")
st.caption("按市、报告类别、年份筛选浙江省水资源年报数据，并导出 Excel / CSV。")

years = get_available_years()
cities = get_available_cities(only_valid=True)
tables = get_available_tables()

with st.sidebar:
    st.header("查询条件")
    sel_table = st.selectbox("报告类别", tables)
    sel_years = st.multiselect("年份", years, default=years)
    sel_cities = st.multiselect("地级市", cities, default=cities)
    run = st.button("查询", type="primary")

if run:
    raw = load_table(table=sel_table, years=sel_years or None, cities=sel_cities or None)
    df = query_data(raw, cities=sel_cities or None, years=sel_years or None)
    st.session_state["last_df"] = df
    st.session_state["last_table"] = sel_table

if "last_df" in st.session_state:
    df = st.session_state["last_df"]
    table_name = st.session_state["last_table"]
    st.subheader(f"查询结果 · {table_name} · {len(df)} 行")
    if df.empty:
        st.warning("没有匹配的数据，请调整筛选条件。")
    else:
        st.dataframe(df, use_container_width=True)
        csv_bytes = df.to_csv(index=False).encode("utf-8-sig")
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "📥 下载 CSV",
                data=csv_bytes,
                file_name=f"{table_name}.csv",
                mime="text/csv",
            )
        with col2:
            excel_download({table_name: df}, filename=f"{table_name}.xlsx")
else:
    st.info("在左侧选择报告类别、年份与地级市后点击“查询”。")

footer("水资源年报查询工具")
