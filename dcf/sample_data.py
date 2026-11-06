"""生成演示用样本数据库（虚构公司，非真实财务数据）。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .data import init_db

START_YEAR = 2020

SAMPLE_COMPANIES = [
    {
        "company_id": "C001",
        "company_name": "恒瑞智造",
        "industry": "高端制造",
        "base_revenue": 120000.0,
        "growths": [0.13, 0.12, 0.10, 0.09],
        "margins": [0.120, 0.126, 0.133, 0.140, 0.147],
        "da_pct": 0.060,
        "capex_pct": 0.075,
        "nwc_pct": 0.120,
        "total_debt": 45000.0,
        "cash": 30000.0,
        "shares": 20000.0,
    },
    {
        "company_id": "C002",
        "company_name": "云启科技",
        "industry": "软件服务",
        "base_revenue": 62000.0,
        "growths": [0.22, 0.20, 0.18, 0.16],
        "margins": [0.180, 0.195, 0.210, 0.225, 0.240],
        "da_pct": 0.030,
        "capex_pct": 0.035,
        "nwc_pct": 0.080,
        "total_debt": 8000.0,
        "cash": 26000.0,
        "shares": 15000.0,
    },
    {
        "company_id": "C003",
        "company_name": "华辰医药",
        "industry": "医药制造",
        "base_revenue": 205000.0,
        "growths": [0.10, 0.08, 0.06, 0.05],
        "margins": [0.220, 0.215, 0.210, 0.205, 0.200],
        "da_pct": 0.050,
        "capex_pct": 0.065,
        "nwc_pct": 0.150,
        "total_debt": 60000.0,
        "cash": 42000.0,
        "shares": 30000.0,
        "missing": {(2022, "capex")},
    },
    {
        "company_id": "C004",
        "company_name": "明远消费",
        "industry": "消费零售",
        "base_revenue": 152000.0,
        "growths": [0.08, 0.09, 0.10, 0.10],
        "margins": [0.100, 0.105, 0.112, 0.118, 0.125],
        "da_pct": 0.040,
        "capex_pct": 0.050,
        "nwc_pct": 0.100,
        "total_debt": 20000.0,
        "cash": 36000.0,
        "shares": 25000.0,
    },
    {
        "company_id": "C005",
        "company_name": "中港物流",
        "industry": "物流运输",
        "base_revenue": 96000.0,
        "growths": [0.09, 0.10, 0.11, 0.10],
        "margins": [0.080, 0.083, 0.086, 0.089, 0.092],
        "da_pct": 0.080,
        "capex_pct": 0.100,
        "nwc_pct": 0.060,
        "total_debt": 55000.0,
        "cash": 18000.0,
        "shares": 12000.0,
        "missing": {(2021, "da")},
    },
]


def _revenue_series(config: dict) -> list[float]:
    series = [config["base_revenue"]]
    for growth in config["growths"]:
        series.append(series[-1] * (1 + growth))
    return series


def generate_sample_db(db_path: str | Path, overwrite: bool = True) -> Path:
    """按固定参数生成样本 SQLite 数据库，结果可复现。"""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and overwrite:
        path.unlink()

    conn = sqlite3.connect(path)
    try:
        init_db(conn)

        conn.executemany(
            "INSERT OR REPLACE INTO companies (company_id, company_name, industry, unit) VALUES (?, ?, ?, ?)",
            [
                (c["company_id"], c["company_name"], c["industry"], "万元")
                for c in SAMPLE_COMPANIES
            ],
        )

        rows = []
        for config in SAMPLE_COMPANIES:
            missing = config.get("missing", set())
            for offset, revenue in enumerate(_revenue_series(config)):
                year = START_YEAR + offset
                margin = config["margins"][offset]
                row = {
                    "company_id": config["company_id"],
                    "fiscal_year": year,
                    "revenue": round(revenue, 2),
                    "ebit": round(revenue * margin, 2),
                    "da": round(revenue * config["da_pct"], 2),
                    "capex": round(revenue * config["capex_pct"], 2),
                    "nwc": round(revenue * config["nwc_pct"], 2),
                    "total_debt": config["total_debt"],
                    "cash": config["cash"],
                    "shares_outstanding": config["shares"],
                }
                for field in ("da", "capex", "nwc"):
                    if (year, field) in missing:
                        row[field] = None
                rows.append(tuple(row.values()))

        conn.executemany(
            """INSERT OR REPLACE INTO financials
               (company_id, fiscal_year, revenue, ebit, da, capex, nwc,
                total_debt, cash, shares_outstanding)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        conn.commit()
    finally:
        conn.close()

    return path
