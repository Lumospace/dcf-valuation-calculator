"""敏感性分析与情景分析。"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from .model import DCFInputs, run_dcf

_METRIC_FIELDS = {
    "per_share": "value_per_share",
    "equity": "equity_value",
    "ev": "enterprise_value",
}


def build_sensitivity(
    inputs: DCFInputs,
    wacc_deltas: tuple[float, ...] = (-0.02, -0.01, 0.0, 0.01, 0.02),
    g_deltas: tuple[float, ...] = (-0.01, -0.005, 0.0, 0.005, 0.01),
    metric: str = "per_share",
    multiple_deltas: tuple[float, ...] = (-2.0, -1.0, 0.0, 1.0, 2.0),
) -> pd.DataFrame:
    """构建 WACC × 第二变量的双变量敏感性表。

    Gordon 模式下第二变量为永续增长率，退出倍数模式下为退出倍数。
    参数组合不满足模型约束（如 WACC ≤ g）时该格记为 NaN，不中断整表计算。
    """
    if metric not in _METRIC_FIELDS:
        raise ValueError(f"metric 仅支持 {sorted(_METRIC_FIELDS)}")

    wacc_values = [round(inputs.wacc + d, 6) for d in wacc_deltas]

    if inputs.terminal_method == "exit_multiple":
        base = float(inputs.exit_multiple or 0.0)
        axis_values = sorted({max(1.0, round(base + d, 2)) for d in multiple_deltas})
        columns = [f"{value:.1f}x" for value in axis_values]
        overrides = [{"exit_multiple": value} for value in axis_values]
    else:
        axis_values = [round(inputs.terminal_growth + d, 6) for d in g_deltas]
        columns = [f"g={value:.2%}" for value in axis_values]
        overrides = [{"terminal_growth": value} for value in axis_values]

    data = np.full((len(wacc_values), len(axis_values)), np.nan)
    for i, wacc in enumerate(wacc_values):
        for j, override in enumerate(overrides):
            try:
                result = run_dcf(replace(inputs, wacc=wacc, **override))
            except ValueError:
                continue
            data[i, j] = getattr(result, _METRIC_FIELDS[metric])

    frame = pd.DataFrame(
        data,
        index=pd.Index(wacc_values, name="WACC"),
        columns=columns,
    )
    return frame.round(2)


def build_scenarios(
    inputs: DCFInputs,
    profiles: dict[str, tuple[float, float]] | None = None,
) -> pd.DataFrame:
    """按增速与利润率的乘数生成悲观 / 基准 / 乐观三档情景。

    profiles 的 value 为 (收入增速乘数, EBIT 利润率乘数)。
    """
    if profiles is None:
        profiles = {
            "悲观": (0.6, 0.85),
            "基准": (1.0, 1.0),
            "乐观": (1.3, 1.1),
        }

    rows = []
    base_per_share = None
    for name, (growth_mult, margin_mult) in profiles.items():
        growth = [g * growth_mult for g in inputs.revenue_growth]
        margin = [m * margin_mult for m in inputs.ebit_margin]
        result = run_dcf(replace(inputs, revenue_growth=growth, ebit_margin=margin))

        if base_per_share is None or name == "基准":
            base_per_share = result.value_per_share

        rows.append(
            {
                "情景": name,
                "收入增速乘数": growth_mult,
                "利润率乘数": margin_mult,
                "企业价值": result.enterprise_value,
                "股权价值": result.equity_value,
                "每股价值": result.value_per_share,
            }
        )

    frame = pd.DataFrame(rows)
    if base_per_share and not np.isnan(base_per_share):
        frame["相对基准"] = frame["每股价值"] / base_per_share - 1
    return frame
