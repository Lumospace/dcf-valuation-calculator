"""DCF 估值计算器 · Streamlit 界面。

运行：streamlit run app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from dcf.data import (
    clean_financials,
    connect,
    derive_assumptions,
    list_companies,
    load_financials,
)
from dcf.export import build_excel
from dcf.model import DCFInputs, fade_schedule, run_dcf
from dcf.sample_data import generate_sample_db
from dcf.sensitivity import build_scenarios, build_sensitivity

DB_PATH = ROOT / "data" / "sample_financials.db"

MANUAL_DEFAULTS = {
    "base_revenue": 50e8,
    "revenue_growth": 0.10,
    "ebit_margin": 0.15,
    "da_pct_revenue": 0.05,
    "capex_pct_revenue": 0.06,
    "nwc_pct_revenue": 0.10,
    "net_debt": 5e8,
    "shares_outstanding": 5e8,
}


def _clip(value: float, low: float, high: float) -> float:
    return float(min(max(value, low), high))


def _yi(value: float) -> float:
    """元 → 亿元。"""
    return value / 1e8


def _heatmap(frame: pd.DataFrame):
    values = frame.to_numpy(dtype=float)
    low = np.nanmin(values)
    high = np.nanmax(values)

    def style_cell(value):
        if pd.isna(value):
            return "background-color: #f2f2f2; color: #9a9a9a"
        ratio = 0.5 if high <= low else (value - low) / (high - low)
        red = int(238 - 148 * ratio)
        green = int(244 - 94 * ratio)
        blue = int(250 - 50 * ratio)
        text = "#ffffff" if ratio > 0.65 else "#1f2d3d"
        return f"background-color: rgb({red},{green},{blue}); color: {text}"

    return frame.style.map(style_cell).format("{:,.2f}", na_rep="—")


st.set_page_config(page_title="DCF 估值计算器", layout="wide")

if not DB_PATH.exists():
    generate_sample_db(DB_PATH)

st.title("DCF 估值计算器")
st.caption("企业自由现金流（FCFF）两段式模型：显性预测期 + Gordon 永续增长｜金额单位：亿元")

with st.sidebar:
    st.subheader("数据源")
    source = st.radio("假设来源", ["样本公司（SQLite）", "手动输入"])
    company_id = None

    if source == "样本公司（SQLite）":
        conn = connect(DB_PATH)
        companies = list_companies(conn)
        options = list(companies["company_id"])
        labels = {
            row["company_id"]: f"{row['company_name']} · {row['industry']}（{row['company_id']}）"
            for _, row in companies.iterrows()
        }
        company_id = st.selectbox("选择公司", options, format_func=lambda x: labels[x])

        raw = load_financials(conn, company_id)
        cleaned = clean_financials(raw, unit="万元")
        defaults = derive_assumptions(cleaned)
        token = company_id
    else:
        raw = cleaned = None
        defaults = dict(MANUAL_DEFAULTS)
        token = "manual"

    st.divider()
    st.subheader("估值假设")

    years = int(
        st.number_input("预测期年数", min_value=3, max_value=10, value=5, step=1, key=f"years_{token}")
    )
    base_revenue = st.number_input(
        "基期营业收入（亿元）",
        min_value=0.1,
        max_value=5000.0,
        value=round(_yi(defaults["base_revenue"]), 2),
        step=0.5,
        key=f"base_{token}",
    )
    growth_start = st.slider(
        "首年收入增速", -20.0, 50.0,
        round(_clip(defaults["revenue_growth"], -0.2, 0.5) * 100, 1), 0.5,
        format="%.1f%%", key=f"gs_{token}",
    )
    growth_end = st.slider(
        "末年收入增速", -10.0, 30.0,
        round(_clip(defaults["revenue_growth"] * 0.6, -0.1, 0.3) * 100, 1), 0.5,
        format="%.1f%%", key=f"ge_{token}",
    )
    ebit_margin = st.slider(
        "EBIT 利润率", 0.0, 60.0,
        round(_clip(defaults["ebit_margin"], 0.0, 0.6) * 100, 1), 0.5,
        format="%.1f%%", key=f"m_{token}",
    )
    tax_rate = st.slider("所得税率", 0.0, 40.0, 25.0, 1.0, format="%.0f%%", key=f"tax_{token}")
    da_ratio = st.slider(
        "折旧摊销 / 收入", 0.0, 20.0,
        round(_clip(defaults["da_pct_revenue"], 0.0, 0.2) * 100, 1), 0.5,
        format="%.1f%%", key=f"da_{token}",
    )
    capex_ratio = st.slider(
        "资本开支 / 收入", 0.0, 30.0,
        round(_clip(defaults["capex_pct_revenue"], 0.0, 0.3) * 100, 1), 0.5,
        format="%.1f%%", key=f"capex_{token}",
    )
    nwc_ratio = st.slider(
        "营运资本 / 收入", 0.0, 40.0,
        round(_clip(defaults["nwc_pct_revenue"], 0.0, 0.4) * 100, 1), 0.5,
        format="%.1f%%", key=f"nwc_{token}",
    )
    wacc = st.slider("WACC", 4.0, 25.0, 9.0, 0.1, format="%.1f%%", key=f"wacc_{token}")
    terminal_growth = st.slider(
        "永续增长率", -2.0, 5.0, 2.0, 0.1, format="%.1f%%", key=f"tg_{token}"
    )
    net_debt = st.number_input(
        "净负债（亿元）",
        min_value=-5000.0,
        max_value=5000.0,
        value=round(_yi(defaults["net_debt"]), 2),
        step=0.5,
        key=f"nd_{token}",
    )
    shares_wan = st.number_input(
        "股本（万股）",
        min_value=1.0,
        max_value=1e7,
        value=round(defaults["shares_outstanding"] / 1e4, 0),
        step=100.0,
        key=f"sh_{token}",
    )
    midyear = st.checkbox("期中折现（mid-year）", value=True, key=f"my_{token}")

growth = fade_schedule(growth_start / 100, growth_end / 100, years)
margin = np.full(years, ebit_margin / 100)

inputs = DCFInputs(
    base_revenue=base_revenue * 1e8,
    revenue_growth=growth,
    ebit_margin=margin,
    tax_rate=tax_rate / 100,
    da_pct_revenue=da_ratio / 100,
    capex_pct_revenue=capex_ratio / 100,
    nwc_pct_revenue=nwc_ratio / 100,
    wacc=wacc / 100,
    terminal_growth=terminal_growth / 100,
    net_debt=net_debt * 1e8,
    shares_outstanding=shares_wan * 1e4,
    forecast_years=years,
    midyear=midyear,
)

try:
    result = run_dcf(inputs)
except ValueError as exc:
    st.error(f"参数不合法：{exc}")
    st.stop()

metrics = st.columns(4)
metrics[0].metric("企业价值（亿元）", f"{_yi(result.enterprise_value):,.1f}")
metrics[1].metric("股权价值（亿元）", f"{_yi(result.equity_value):,.1f}")
metrics[2].metric("每股价值（元）", f"{result.value_per_share:,.2f}")
metrics[3].metric("终值占企业价值", f"{result.tv_share_of_ev:.0%}")

for warning in result.warnings:
    st.warning(warning)

sensitivity = build_sensitivity(inputs)
scenarios = build_scenarios(inputs)

valid = sensitivity.to_numpy(dtype=float)
low_value, high_value = float(np.nanmin(valid)), float(np.nanmax(valid))
st.caption(
    f"敏感性区间：每股 {low_value:,.2f} – {high_value:,.2f} 元"
    f"（对应股权价值 {_yi(low_value * inputs.shares_outstanding):,.1f} – "
    f"{_yi(high_value * inputs.shares_outstanding):,.1f} 亿元）"
)

tab_projection, tab_sensitivity, tab_scenarios, tab_data = st.tabs(
    ["预测明细", "敏感性分析", "情景分析", "基础数据"]
)

with tab_projection:
    projection = result.projection
    display = pd.DataFrame(
        {
            "年度": [f"Y{int(year)}" for year in projection["year"]],
            "营业收入": projection["revenue"] / 1e8,
            "收入增速": projection["growth"] * 100,
            "EBIT 利润率": projection["ebit_margin"] * 100,
            "EBIT": projection["ebit"] / 1e8,
            "税后 EBIT": projection["nopat"] / 1e8,
            "折旧摊销": projection["da"] / 1e8,
            "资本开支": projection["capex"] / 1e8,
            "营运资本增加": projection["delta_nwc"] / 1e8,
            "自由现金流": projection["fcff"] / 1e8,
            "折现系数": projection["discount_factor"],
            "现金流现值": projection["pv_fcff"] / 1e8,
        }
    )
    st.dataframe(
        display,
        hide_index=True,
        width="stretch",
        column_config={
            "收入增速": st.column_config.NumberColumn(format="%.1f%%"),
            "EBIT 利润率": st.column_config.NumberColumn(format="%.1f%%"),
            "折现系数": st.column_config.NumberColumn(format="%.4f"),
            "营业收入": st.column_config.NumberColumn(format="%.2f"),
            "自由现金流": st.column_config.NumberColumn(format="%.2f"),
        },
    )

    chart = pd.DataFrame(
        {
            "营业收入（亿元）": projection["revenue"] / 1e8,
            "自由现金流（亿元）": projection["fcff"] / 1e8,
        },
        index=[f"Y{int(year)}" for year in projection["year"]],
    )
    st.line_chart(chart)

    st.info(
        f"预测期现金流现值 {_yi(result.pv_fcff):,.1f} 亿元 + 终值现值 "
        f"{_yi(result.pv_terminal):,.1f} 亿元 = 企业价值 {_yi(result.enterprise_value):,.1f} 亿元；"
        f"扣除净负债后股权价值 {_yi(result.equity_value):,.1f} 亿元。"
    )

with tab_sensitivity:
    st.caption("行：WACC；列：永续增长率；单元格：每股价值（元）。灰色为不满足模型约束的组合。")
    st.dataframe(_heatmap(sensitivity), width="stretch")

with tab_scenarios:
    scenario_view = scenarios.copy()
    scenario_view["企业价值（亿元）"] = scenario_view["企业价值"] / 1e8
    scenario_view["股权价值（亿元）"] = scenario_view["股权价值"] / 1e8
    st.dataframe(
        scenario_view[
            ["情景", "收入增速乘数", "利润率乘数", "企业价值（亿元）", "股权价值（亿元）", "每股价值", "相对基准"]
        ],
        hide_index=True,
        width="stretch",
        column_config={
            "每股价值": st.column_config.NumberColumn(format="%.2f"),
            "相对基准": st.column_config.NumberColumn(format="%.1f%%"),
        },
    )
    st.bar_chart(scenarios.set_index("情景")["每股价值"])

with tab_data:
    if raw is None:
        st.info("当前为手动输入模式。切换到「样本公司（SQLite）」可查看数据库中的原始财务数据。")
    else:
        st.subheader("清洗后数据（元 / 股）")
        st.dataframe(cleaned, hide_index=True, width="stretch")

        with st.expander("原始数据（万元 / 万股）"):
            st.dataframe(raw, hide_index=True, width="stretch")

        st.subheader("由历史数据反推的假设")
        assumption_frame = pd.DataFrame(
            [
                ("基期营业收入（亿元）", f"{_yi(defaults['base_revenue']):,.2f}"),
                ("历史平均增速", f"{defaults['revenue_growth']:.1%}"),
                ("历史平均 EBIT 利润率", f"{defaults['ebit_margin']:.1%}"),
                ("折旧摊销 / 收入", f"{defaults['da_pct_revenue']:.1%}"),
                ("资本开支 / 收入", f"{defaults['capex_pct_revenue']:.1%}"),
                ("营运资本 / 收入", f"{defaults['nwc_pct_revenue']:.1%}"),
                ("净负债（亿元）", f"{_yi(defaults['net_debt']):,.2f}"),
                ("股本（万股）", f"{defaults['shares_outstanding'] / 1e4:,.0f}"),
            ],
            columns=["项目", "取值"],
        )
        st.dataframe(assumption_frame, hide_index=True, width="stretch")
        st.caption("清洗规则：类型转换 → 按年份去重 → 剔除收入缺失/非正样本 → 缺失项按中位数填补 → 万元换算为元。")

excel_bytes = build_excel(result, sensitivity, scenarios)
st.download_button(
    "下载 Excel 测算表",
    data=excel_bytes,
    file_name=f"DCF_{token}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

st.caption("模型仅供内部测算与方法演示，不构成投资建议。样本公司数据均为虚构。")
