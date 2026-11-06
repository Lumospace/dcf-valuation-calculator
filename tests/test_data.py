"""数据层测试：SQL 检索、清洗与假设反推。"""

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from dcf.data import (
    build_inputs_from_financials,
    clean_financials,
    connect,
    derive_assumptions,
    list_companies,
    load_financials,
)
from dcf.model import run_dcf
from dcf.sample_data import generate_sample_db


class TestDataLayer(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "test.db"
        generate_sample_db(self.db_path)
        self.conn = connect(self.db_path)

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def test_company_list_query(self):
        frame = list_companies(self.conn)
        self.assertEqual(len(frame), 5)
        self.assertTrue((frame["years"] == 5).all())
        self.assertTrue((frame["latest_year"] == 2024).all())

    def test_load_financials_returns_all_years(self):
        frame = load_financials(self.conn, "C001")
        self.assertEqual(len(frame), 5)
        self.assertEqual(list(frame["fiscal_year"]), [2020, 2021, 2022, 2023, 2024])

    def test_clean_converts_units(self):
        raw = load_financials(self.conn, "C003")
        cleaned = clean_financials(raw, unit="万元")
        # C003 2020 年营业收入 205000 万元 → 2.05e9 元
        self.assertAlmostEqual(cleaned["revenue"].iloc[0], 205000 * 1e4, places=2)

    def test_clean_fills_missing_capex(self):
        raw = load_financials(self.conn, "C003")
        cleaned = clean_financials(raw, unit="万元")
        self.assertFalse(cleaned["capex"].isna().any())

    def test_clean_drops_invalid_revenue_rows(self):
        raw = load_financials(self.conn, "C001")
        broken = raw.copy()
        broken.loc[0, "revenue"] = np.nan
        cleaned = clean_financials(broken, unit="万元")
        self.assertEqual(len(cleaned), 4)

    def test_clean_removes_duplicate_years(self):
        raw = load_financials(self.conn, "C001")
        duplicated = pd.concat([raw, raw.iloc[[-1]]], ignore_index=True)
        cleaned = clean_financials(duplicated, unit="万元")
        self.assertEqual(len(cleaned), len(raw))

    def test_derive_assumptions(self):
        raw = load_financials(self.conn, "C001")
        assumptions = derive_assumptions(clean_financials(raw, unit="万元"))
        self.assertGreater(assumptions["base_revenue"], 0)
        self.assertTrue(-0.2 <= assumptions["revenue_growth"] <= 0.5)
        self.assertTrue(0 < assumptions["ebit_margin"] < 0.6)
        self.assertEqual(assumptions["net_debt"], 45000 * 1e4 - 30000 * 1e4)

    def test_build_inputs_runs_model(self):
        raw = load_financials(self.conn, "C002")
        inputs = build_inputs_from_financials(
            clean_financials(raw, unit="万元"), wacc=0.09, terminal_growth=0.02, years=5
        )
        result = run_dcf(inputs)
        self.assertGreater(result.enterprise_value, 0)
        self.assertGreater(result.value_per_share, 0)
        self.assertEqual(len(result.projection), 5)

    def test_growth_fades_to_terminal(self):
        raw = load_financials(self.conn, "C002")
        inputs = build_inputs_from_financials(
            clean_financials(raw, unit="万元"), wacc=0.09, terminal_growth=0.02, years=5
        )
        self.assertAlmostEqual(inputs.revenue_growth[-1], 0.02, places=9)


if __name__ == "__main__":
    unittest.main()
