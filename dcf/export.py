"""把估值结果导出为多工作表 Excel。"""

from __future__ import annotations

from io import BytesIO

import pandas as pd
from openpyxl.utils import get_column_letter

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

SUMMARY_FORMATS = {2: "#,##0.00", 3: "#,##0.00", 4: "0.0000", 5: "0.0%", 6: '0.00"x"'}

ASSUMPTION_FORMATS = {
    2: "#,##0",
    3: "0",
    5: "0%",
    6: "0.0%",
    7: "0.0%",
    8: "0.0%",
    9: "0.0%",
    10: "0.0%",
    12: '0.00"x"',
    13: "#,##0",
    14: "#,##0",
}

PROJECTION_FORMATS = {
    1: "0",
    2: "#,##0",
    3: "0.0%",
    4: "0.0%",
    5: "#,##0",
    6: "#,##0",
    7: "#,##0",
    8: "#,##0",
    9: "#,##0",
    10: "#,##0",
    11: "0.0000",
    12: "#,##0",
}

SCENARIO_FORMATS = {2: "0.00", 3: "0.00", 4: "#,##0", 5: "#,##0", 6: "0.00", 7: "0.0%"}


def _format_column(worksheet, column: int, number_format: str, first_row: int, last_row: int) -> None:
    for row in range(first_row, last_row + 1):
        cell = worksheet.cell(row=row, column=column)
        if isinstance(cell.value, (int, float)):
            cell.number_format = number_format


def _format_columns(worksheet, column_formats: dict[int, str], first_row: int, last_row: int) -> None:
    for column, number_format in column_formats.items():
        _format_column(worksheet, column, number_format, first_row, last_row)


def _format_rows(worksheet, column: int, row_formats: dict[int, str], first_row: int, last_row: int) -> None:
    for row in range(first_row, last_row + 1):
        number_format = row_formats.get(row)
        if number_format is None:
            continue
        _format_column(worksheet, column, number_format, row, row)


def _autofit(worksheet, min_width: int = 10, max_width: int = 30) -> None:
    for cells in worksheet.columns:
        width = max(len(str(cell.value)) if cell.value is not None else 0 for cell in cells)
        letter = get_column_letter(cells[0].column)
        worksheet.column_dimensions[letter].width = min(max(min_width, width * 1.6), max_width)
    worksheet.freeze_panes = "A2"


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
        ("永续增长率", inputs.terminal_growth if inputs.terminal_method == "gordon" else None),
        ("终值方法", "Gordon 永续增长" if inputs.terminal_method == "gordon" else "退出倍数法"),
        ("退出倍数（EV/EBITDA）", inputs.exit_multiple),
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

        book = writer.book
        summary_sheet = book["估值结果"]
        _format_rows(summary_sheet, 2, SUMMARY_FORMATS, 2, 1 + len(summary))
        _autofit(summary_sheet)

        assumption_sheet = book["关键假设"]
        _format_rows(assumption_sheet, 2, ASSUMPTION_FORMATS, 2, 1 + len(assumptions))
        schedule_start = len(assumptions) + 4
        _format_columns(assumption_sheet, {1: "0", 2: "0.0%", 3: "0.0%"}, schedule_start, assumption_sheet.max_row)
        _autofit(assumption_sheet)

        projection_sheet = book["预测明细"]
        _format_columns(projection_sheet, PROJECTION_FORMATS, 2, projection_sheet.max_row)
        _autofit(projection_sheet)

        sensitivity_sheet = book["敏感性分析"]
        sensitivity_formats = {1: "0.0%"}
        sensitivity_formats.update({column: "#,##0.00" for column in range(2, len(sensitivity.columns) + 2)})
        _format_columns(sensitivity_sheet, sensitivity_formats, 2, sensitivity_sheet.max_row)
        _autofit(sensitivity_sheet)

        scenario_sheet = book["情景分析"]
        _format_columns(scenario_sheet, SCENARIO_FORMATS, 2, scenario_sheet.max_row)
        _autofit(scenario_sheet)

    return buffer.getvalue()
