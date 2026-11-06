"""DCF（自由现金流折现）估值引擎。

口径：企业自由现金流（FCFF）两段式模型
    显性预测期（默认 5 年）+ Gordon 永续增长终值

    FCFF = EBIT × (1 - 税率) + 折旧摊销 - 资本开支 - 净营运资本增加
    TV   = FCFF(n+1) / (WACC - g)          # Gordon 永续增长
    EV   = Σ PV(FCFF) + PV(TV)
    股权价值 = EV - 净负债
    每股价值 = 股权价值 / 股本
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd

PROJECTION_COLUMNS = [
    "year",
    "revenue",
    "growth",
    "ebit_margin",
    "ebit",
    "nopat",
    "da",
    "capex",
    "delta_nwc",
    "fcff",
    "discount_factor",
    "pv_fcff",
]


@dataclass(frozen=True)
class DCFInputs:
    """一次 DCF 测算所需的全部假设。金额单位为元，比率为小数。"""

    base_revenue: float
    revenue_growth: Sequence[float]
    ebit_margin: Sequence[float]
    tax_rate: float
    da_pct_revenue: float
    capex_pct_revenue: float
    nwc_pct_revenue: float
    wacc: float
    terminal_growth: float
    net_debt: float
    shares_outstanding: float
    forecast_years: int = 5
    midyear: bool = True
    terminal_method: str = "gordon"
    exit_multiple: float | None = None

    def as_dict(self) -> dict:
        return {
            "base_revenue": self.base_revenue,
            "tax_rate": self.tax_rate,
            "da_pct_revenue": self.da_pct_revenue,
            "capex_pct_revenue": self.capex_pct_revenue,
            "nwc_pct_revenue": self.nwc_pct_revenue,
            "wacc": self.wacc,
            "terminal_growth": self.terminal_growth,
            "net_debt": self.net_debt,
            "shares_outstanding": self.shares_outstanding,
            "forecast_years": self.forecast_years,
            "midyear": self.midyear,
            "terminal_method": self.terminal_method,
            "exit_multiple": self.exit_multiple,
        }


@dataclass
class DCFResult:
    inputs: DCFInputs
    projection: pd.DataFrame
    pv_fcff: float
    terminal_value: float
    pv_terminal: float
    enterprise_value: float
    equity_value: float
    value_per_share: float
    tv_share_of_ev: float
    implied_exit_multiple: float
    warnings: list[str]

    def summary(self) -> dict:
        return {
            "企业价值": self.enterprise_value,
            "股权价值": self.equity_value,
            "每股价值": self.value_per_share,
            "终值占 EV 比例": self.tv_share_of_ev,
            "隐含退出倍数": self.implied_exit_multiple,
        }


def _validate(inputs: DCFInputs) -> None:
    if inputs.base_revenue <= 0:
        raise ValueError("基期营业收入必须大于 0")
    if inputs.forecast_years < 1:
        raise ValueError("预测期年数至少为 1 年")
    if len(inputs.revenue_growth) != inputs.forecast_years:
        raise ValueError(
            f"收入增速需逐年给出，当前 {len(inputs.revenue_growth)} 个，"
            f"应为 {inputs.forecast_years} 个"
        )
    if len(inputs.ebit_margin) != inputs.forecast_years:
        raise ValueError(
            f"EBIT 利润率需逐年给出，当前 {len(inputs.ebit_margin)} 个，"
            f"应为 {inputs.forecast_years} 个"
        )
    if any(g <= -1 for g in inputs.revenue_growth):
        raise ValueError("收入增速不得低于 -100%")
    if inputs.wacc <= 0:
        raise ValueError("WACC 必须大于 0")
    if inputs.terminal_growth <= -1:
        raise ValueError("永续增长率不得低于 -100%")
    if inputs.terminal_method == "gordon" and inputs.terminal_growth >= inputs.wacc:
        raise ValueError("永续增长率必须小于 WACC，否则终值公式不成立")
    if inputs.shares_outstanding <= 0:
        raise ValueError("股本必须大于 0")
    if not 0 <= inputs.tax_rate <= 0.6:
        raise ValueError("税率应在 0%–60% 之间")
    if inputs.terminal_method not in {"gordon", "exit_multiple"}:
        raise ValueError("终值方法仅支持 gordon 或 exit_multiple")
    if inputs.terminal_method == "exit_multiple" and not inputs.exit_multiple:
        raise ValueError("使用退出倍数法时需提供 exit_multiple")


def project(inputs: DCFInputs) -> pd.DataFrame:
    """逐年测算收入、EBIT、FCFF 与折现系数。"""
    _validate(inputs)

    rows = []
    prev_revenue = inputs.base_revenue
    for i in range(inputs.forecast_years):
        growth = float(inputs.revenue_growth[i])
        margin = float(inputs.ebit_margin[i])

        revenue = prev_revenue * (1 + growth)
        ebit = revenue * margin
        nopat = ebit * (1 - inputs.tax_rate)
        da = revenue * inputs.da_pct_revenue
        capex = revenue * inputs.capex_pct_revenue
        delta_nwc = (revenue - prev_revenue) * inputs.nwc_pct_revenue
        fcff = nopat + da - capex - delta_nwc

        period = i + 0.5 if inputs.midyear else i + 1
        discount_factor = 1 / (1 + inputs.wacc) ** period

        rows.append(
            {
                "year": i + 1,
                "revenue": revenue,
                "growth": growth,
                "ebit_margin": margin,
                "ebit": ebit,
                "nopat": nopat,
                "da": da,
                "capex": capex,
                "delta_nwc": delta_nwc,
                "fcff": fcff,
                "discount_factor": discount_factor,
                "pv_fcff": fcff * discount_factor,
            }
        )
        prev_revenue = revenue

    return pd.DataFrame(rows, columns=PROJECTION_COLUMNS)


def terminal_value(final_fcff: float, wacc: float, growth: float) -> float:
    """Gordon 永续增长终值。"""
    if wacc <= growth:
        raise ValueError("WACC 必须大于永续增长率")
    return final_fcff * (1 + growth) / (wacc - growth)


def run_dcf(inputs: DCFInputs) -> DCFResult:
    """执行完整估值并返回结果与风险提示。"""
    projection = project(inputs)
    last = projection.iloc[-1]

    pv_fcff = float(projection["pv_fcff"].sum())

    if inputs.terminal_method == "gordon":
        tv = terminal_value(float(last["fcff"]), inputs.wacc, inputs.terminal_growth)
    else:
        ebitda = float(last["ebit"] + last["da"])
        tv = ebitda * float(inputs.exit_multiple)

    pv_terminal = tv * float(last["discount_factor"])
    enterprise_value = pv_fcff + pv_terminal
    equity_value = enterprise_value - inputs.net_debt
    value_per_share = equity_value / inputs.shares_outstanding

    tv_share = pv_terminal / enterprise_value if enterprise_value else float("nan")
    ebitda_last = float(last["ebit"] + last["da"])
    implied_multiple = enterprise_value / ebitda_last if ebitda_last > 0 else float("nan")

    warnings = []
    if tv_share > 0.85:
        warnings.append("终值占企业价值 85% 以上，估值结果对永续假设高度敏感")
    if inputs.wacc - inputs.terminal_growth < 0.02:
        warnings.append("WACC 与永续增长率差距不足 2 个百分点，终值不稳定")
    if inputs.terminal_growth > 0.05:
        warnings.append("永续增长率高于 5%，超出常见合理区间")
    if equity_value < 0:
        warnings.append("股权价值为负，净负债已超过企业价值")
    if (projection["fcff"] < 0).any():
        warnings.append("预测期内存在自由现金流为负的年份")

    return DCFResult(
        inputs=inputs,
        projection=projection,
        pv_fcff=pv_fcff,
        terminal_value=tv,
        pv_terminal=pv_terminal,
        enterprise_value=enterprise_value,
        equity_value=equity_value,
        value_per_share=value_per_share,
        tv_share_of_ev=tv_share,
        implied_exit_multiple=implied_multiple,
        warnings=warnings,
    )


def fade_schedule(start: float, end: float, years: int) -> np.ndarray:
    """在预测期内把首年水平线性过渡到末年水平。"""
    if years < 1:
        raise ValueError("预测期年数至少为 1 年")
    return np.linspace(start, end, years)
