"""敏感性分析与情景分析测试。"""

import unittest

import numpy as np

from dcf.model import DCFInputs, run_dcf
from dcf.sensitivity import build_scenarios, build_sensitivity


def sample_inputs(**overrides) -> DCFInputs:
    params = dict(
        base_revenue=1000.0,
        revenue_growth=[0.10, 0.09, 0.08],
        ebit_margin=[0.20, 0.20, 0.20],
        tax_rate=0.25,
        da_pct_revenue=0.05,
        capex_pct_revenue=0.06,
        nwc_pct_revenue=0.10,
        wacc=0.10,
        terminal_growth=0.02,
        net_debt=100.0,
        shares_outstanding=50.0,
        forecast_years=3,
        midyear=False,
    )
    params.update(overrides)
    return DCFInputs(**params)


class TestSensitivity(unittest.TestCase):
    def test_grid_shape(self):
        frame = build_sensitivity(sample_inputs())
        self.assertEqual(frame.shape, (5, 5))
        self.assertEqual(frame.index.name, "WACC")

    def test_center_cell_matches_base_case(self):
        inputs = sample_inputs()
        frame = build_sensitivity(inputs)
        expected = run_dcf(inputs).value_per_share
        self.assertAlmostEqual(frame.iloc[2, 2], round(expected, 2), places=2)

    def test_higher_wacc_lowers_value(self):
        frame = build_sensitivity(sample_inputs())
        for column in frame.columns:
            series = frame[column].to_numpy(dtype=float)
            self.assertTrue(np.all(np.diff(series) < 0))

    def test_higher_growth_raises_value(self):
        frame = build_sensitivity(sample_inputs())
        for row in range(frame.shape[0]):
            series = frame.iloc[row].to_numpy(dtype=float)
            self.assertTrue(np.all(np.diff(series) > 0))

    def test_invalid_combinations_become_nan(self):
        frame = build_sensitivity(
            sample_inputs(wacc=0.05, terminal_growth=0.045),
            wacc_deltas=(-0.02, 0.0),
            g_deltas=(0.0, 0.01),
        )
        # WACC 3% 与 g 5.5% 的组合不成立
        self.assertTrue(np.isnan(frame.iloc[0, 1]))

    def test_metric_switch(self):
        frame = build_sensitivity(sample_inputs(), metric="ev")
        self.assertAlmostEqual(frame.iloc[2, 2], round(run_dcf(sample_inputs()).enterprise_value, 2), places=2)

    def test_unknown_metric_rejected(self):
        with self.assertRaises(ValueError):
            build_sensitivity(sample_inputs(), metric="ebitda")


class TestScenarios(unittest.TestCase):
    def test_three_scenarios_ordered(self):
        frame = build_scenarios(sample_inputs())
        self.assertEqual(len(frame), 3)
        values = frame["每股价值"].to_numpy()
        self.assertLess(values[0], values[1])
        self.assertLess(values[1], values[2])

    def test_base_scenario_equals_original(self):
        inputs = sample_inputs()
        frame = build_scenarios(inputs)
        base_row = frame[frame["情景"] == "基准"].iloc[0]
        self.assertAlmostEqual(base_row["每股价值"], run_dcf(inputs).value_per_share, places=6)

    def test_relative_column_anchored_on_base(self):
        frame = build_scenarios(sample_inputs())
        base_relative = frame.loc[frame["情景"] == "基准", "相对基准"].iloc[0]
        self.assertAlmostEqual(base_relative, 0.0, places=9)


class TestExitMultipleSensitivity(unittest.TestCase):
    def test_columns_are_multiples(self):
        inputs = sample_inputs(terminal_method="exit_multiple", exit_multiple=8.0)
        frame = build_sensitivity(inputs)
        self.assertEqual(frame.columns.tolist(), ["6.0x", "7.0x", "8.0x", "9.0x", "10.0x"])

    def test_center_cell_matches_base_case(self):
        inputs = sample_inputs(terminal_method="exit_multiple", exit_multiple=8.0)
        frame = build_sensitivity(inputs)
        expected = run_dcf(inputs).value_per_share
        self.assertAlmostEqual(frame.iloc[2, 2], round(expected, 2), places=2)

    def test_multiples_never_below_one(self):
        inputs = sample_inputs(terminal_method="exit_multiple", exit_multiple=2.0)
        frame = build_sensitivity(inputs)
        self.assertTrue(all(column.endswith("x") for column in frame.columns))
        self.assertIn("1.0x", frame.columns)


if __name__ == "__main__":
    unittest.main()
