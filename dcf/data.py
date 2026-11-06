"""SQLite 数据层：财务数据检索、清洗与口径转换。

约定：数据库内金额单位为万元、股本单位为万股；
清洗后统一换算为元与股，供估值模型直接使用。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from .model import DCFInputs, fade_schedule

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    company_id   TEXT PRIMARY KEY,
    company_name TEXT NOT NULL,
    industry     TEXT,
    unit         TEXT DEFAULT '万元'
);

CREATE TABLE IF NOT EXISTS financials (
    company_id        TEXT    NOT NULL,
    fiscal_year       INTEGER NOT NULL,
    revenue           REAL,
    ebit              REAL,
    da                REAL,
    capex             REAL,
    nwc               REAL,
    total_debt        REAL,
    cash              REAL,
    shares_outstanding REAL,
    PRIMARY KEY (company_id, fiscal_year),
    FOREIGN KEY (company_id) REFERENCES companies (company_id)
);
"""

NUMERIC_COLUMNS = [
    "revenue",
    "ebit",
    "da",
    "capex",
    "nwc",
    "total_debt",
    "cash",
    "shares_outstanding",
]


def connect(db_path: str | Path) -> sqlite3.Connection:
    return sqlite3.connect(str(db_path))


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def list_companies(conn: sqlite3.Connection) -> pd.DataFrame:
    """返回公司清单及覆盖年份、最新一期营业收入。"""
    sql = """
        SELECT  c.company_id,
                c.company_name,
                c.industry,
                COUNT(f.fiscal_year) AS years,
                MAX(f.fiscal_year)   AS latest_year,
                (SELECT ROUND(revenue, 2)
                   FROM financials
                  WHERE company_id = c.company_id
                  ORDER BY fiscal_year DESC
                  LIMIT 1)            AS latest_revenue_wan
          FROM  companies c
          LEFT  JOIN financials f ON f.company_id = c.company_id
         GROUP  BY c.company_id, c.company_name, c.industry
         ORDER  BY c.company_id
    """
    return pd.read_sql_query(sql, conn)


def load_financials(conn: sqlite3.Connection, company_id: str) -> pd.DataFrame:
    """按年份升序读取某公司的原始财务数据（未清洗）。"""
    sql = """
        SELECT  f.fiscal_year,
                f.revenue,
                f.ebit,
                f.da,
                f.capex,
                f.nwc,
                f.total_debt,
                f.cash,
                f.shares_outstanding,
                c.unit
          FROM  financials f
          JOIN  companies c ON c.company_id = f.company_id
         WHERE  f.company_id = ?
         ORDER  BY f.fiscal_year
    """
    return pd.read_sql_query(sql, conn, params=(company_id,))


def clean_financials(df: pd.DataFrame, unit: str = "万元") -> pd.DataFrame:
    """清洗财务数据：类型转换、去重、缺失值处理、单位换算、派生比率。"""
    out = df.copy()

    for col in NUMERIC_COLUMNS:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    out = out.drop_duplicates(subset="fiscal_year", keep="last")
    out = out[out["revenue"].notna() & (out["revenue"] > 0)]
    out = out.sort_values("fiscal_year").reset_index(drop=True)

    for col in ["da", "capex", "nwc"]:
        out[col] = out[col].fillna(out[col].median()).fillna(0.0)
    for col in ["total_debt", "cash"]:
        out[col] = out[col].fillna(0.0)

    out["shares_outstanding"] = out["shares_outstanding"].ffill().bfill()
    out = out[out["shares_outstanding"].notna() & (out["shares_outstanding"] > 0)]

    scale = 1e4 if unit == "万元" else 1.0
    for col in NUMERIC_COLUMNS:
        out[col] = out[col] * scale

    out["revenue_growth"] = out["revenue"].pct_change()
    out["ebit_margin"] = out["ebit"] / out["revenue"]
    return out.reset_index(drop=True)


def derive_assumptions(df: pd.DataFrame, lookback: int = 3) -> dict:
    """从清洗后的历史数据反推估值假设（取最近 lookback 年均值）。"""
    if df.empty:
        raise ValueError("无可用财务数据")

    recent = df.tail(lookback)
    growth_hist = df["revenue_growth"].dropna().tail(lookback)

    avg_growth = float(growth_hist.mean()) if len(growth_hist) else 0.0
    avg_growth = float(np.clip(avg_growth, -0.2, 0.5))

    margin = float(recent["ebit_margin"].mean())
    if not np.isfinite(margin):
        raise ValueError("缺少 EBIT 数据，无法反推利润率假设")

    return {
        "base_revenue": float(df["revenue"].iloc[-1]),
        "revenue_growth": avg_growth,
        "ebit_margin": margin,
        "da_pct_revenue": float((recent["da"] / recent["revenue"]).mean()),
        "capex_pct_revenue": float((recent["capex"] / recent["revenue"]).mean()),
        "nwc_pct_revenue": float((recent["nwc"] / recent["revenue"]).mean()),
        "net_debt": float(df["total_debt"].iloc[-1] - df["cash"].iloc[-1]),
        "shares_outstanding": float(df["shares_outstanding"].iloc[-1]),
    }


def build_inputs_from_financials(
    df: pd.DataFrame,
    wacc: float,
    terminal_growth: float,
    years: int = 5,
    tax_rate: float = 0.25,
    midyear: bool = True,
) -> DCFInputs:
    """把历史财务数据转换为模型输入：增速由历史均值线性收敛至永续增速。"""
    assumptions = derive_assumptions(df)
    growth = fade_schedule(assumptions["revenue_growth"], terminal_growth, years)
    margin = np.full(years, assumptions["ebit_margin"])

    return DCFInputs(
        base_revenue=assumptions["base_revenue"],
        revenue_growth=growth,
        ebit_margin=margin,
        tax_rate=tax_rate,
        da_pct_revenue=assumptions["da_pct_revenue"],
        capex_pct_revenue=assumptions["capex_pct_revenue"],
        nwc_pct_revenue=assumptions["nwc_pct_revenue"],
        wacc=wacc,
        terminal_growth=terminal_growth,
        net_debt=assumptions["net_debt"],
        shares_outstanding=assumptions["shares_outstanding"],
        forecast_years=years,
        midyear=midyear,
    )
