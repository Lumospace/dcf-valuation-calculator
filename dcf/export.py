"""把估值结果导出为多工作表 Excel。"""

from __future__ import annotations

from io import BytesIO

import pandas as pd

from .model import DCFResult

SHEET_NAMES = ["估值结果", "关键假设", "预测明细", "敏感性分析", "情景分析"]

PROJECTION_LABELS = {
    "year": "年度",
    "revenue": "营业收入",
    "growth": "收入增速",
    "ebit_margin": "EBIT 利润率",
    "ebit": "EBIT",
    "nopat": "税后 EBIT",
    "da": "折旧摊销",
    "capex": "资本开支",
    "delta_nwc": "营运资本增加",
    "fcff": "自由现金流",
    "discount_factor": "折现系数",
    "pv_fcff": "现金流现值",
}


def _assumption_frame(result: DCFResult) -> tuple[pd.DataFrame, pd.DataFrame]:
    inputs = result.inputs
    rows = [
        ("基期营业收入（元）", round(inputs.base_revenue, 2)),
        ("预测期年数", inputs.forecast_years),
        ("折现时点", "期中" if inputs.midyear else "期末"),
        ("税率", inputs.tax_rate),
        ("折旧摊销 / 收入", inputs.da_pct_revenue),
        ("资本开支 / 收入", inputs.capex_pct_revenue),
        ("营运资本 / 收入", inputs.nwc_pct_revenue),
        ("WACC", inputs.wacc),
        ("永续增长率", inputs.terminal_growth),
        ("终值方法", inputs.terminal_method),
        ("净负债（元）", round(inputs.net_debt, 2)),
        ("股本（股）", round(inputs.shares_outstanding, 2)),
    ]
    frame = pd.DataFrame(rows, columns=["项目", "取值"])

    schedule = pd.DataFrame(
        {
            "年度": list(range(1, inputs.forecast_years + 1)),
            "收入增速": list(inputs.revenue_growth),
            "EBIT 利润率": list(inputs.ebit_margin),
        }
    )
    return frame, schedule


def build_excel(
    result: DCFResult,
    sensitivity: pd.DataFrame,
    scenarios: pd.DataFrame,
) -> bytes:
    """生成包含结果、假设、预测、敏感性、情景五张表的 Excel 文件。"""
    buffer = BytesIO()
    assumptions, schedule = _assumption_frame(result)

    summary = pd.DataFrame(
        [
            ("企业价值（元）", round(result.enterprise_value, 2)),
            ("股权价值（元）", round(result.equity_value, 2)),
            ("每股价值（元）", round(result.value_per_share, 4)),
            ("终值占企业价值比例", round(result.tv_share_of_ev, 4)),
            ("隐含退出倍数（EV/EBITDA）", round(result.implied_exit_multiple, 2)),
        ],
        columns=["指标", "数值"],
    )

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="估值结果", index=False, startrow=0)
        warnings = pd.DataFrame({"风险提示": result.warnings or ["无"]})
        warnings.to_excel(writer, sheet_name="估值结果", index=False, startrow=len(summary) + 3)

        assumptions.to_excel(writer, sheet_name="关键假设", index=False)
        schedule.to_excel(writer, sheet_name="关键假设", index=False, startrow=len(assumptions) + 3)

        projection = result.projection.rename(columns=PROJECTION_LABELS)
        projection.to_excel(writer, sheet_name="预测明细", index=False)

        sensitivity.to_excel(writer, sheet_name="敏感性分析")
        scenarios.to_excel(writer, sheet_name="情景分析", index=False)

    return buffer.getvalue()
