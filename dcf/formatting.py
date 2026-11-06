"""展示层数据整理：把模型输出转成图表可直接消费的形态。"""

from __future__ import annotations

import pandas as pd


def projection_chart_frame(projection: pd.DataFrame) -> pd.DataFrame:
    """营业收入与自由现金流走势，索引为 Y1..Yn。

    注意：先建 DataFrame 再赋索引，不能把索引作为构造参数，
    否则 pandas 会按新索引对齐原 Series，整列变成 NaN。
    """
    frame = pd.DataFrame(
        {
            "营业收入（亿元）": projection["revenue"] / 1e8,
            "自由现金流（亿元）": projection["fcff"] / 1e8,
        }
    )
    frame.index = [f"Y{int(year)}" for year in projection["year"]]
    return frame
