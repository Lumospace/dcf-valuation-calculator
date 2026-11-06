"""DCF 引擎测试：用可手算的基准案例校验公式与边界条件。"""

import unittest

from dcf.model import DCFInputs, fade_schedule, project, run_dcf, terminal_value


def base_inputs(**overrides) -> DCFInputs:
    """三年期基准案例，全部数字可手算复核。

    base_revenue=1000, growth=10%, margin=20%, tax=25%,
    D&A=5%, capex=6%, NWC=10%, WACC=10%, g=2%, net_debt=100, shares=50
    """
    params = dict(
        base_revenue=1000.0,
        revenue_growth=[0.10, 0.10, 0.10],
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


class TestProjection(unittest.TestCase):
    def test_revenue_compounds_at_given_growth(self):
        frame = project(base_inputs())
        self.assertEqual(len(frame), 3)
        self.assertAlmostEqual(frame["revenue"].iloc[0], 1100.0, places=6)
        self.assertAlmostEqual(frame["revenue"].iloc[1], 1210.0, places=6)
        self.assertAlmostEqual(frame["revenue"].iloc[2], 1331.0, places=6)

    def test_fcff_formula(self):
        frame = project(base_inputs())
        # Y1: EBIT=220, NOPAT=165, D&A=55, capex=66, ΔNWC=10 → FCFF=144
        self.assertAlmostEqual(frame["fcff"].iloc[0], 144.0, places=6)
        self.assertAlmostEqual(frame["fcff"].iloc[1], 158.4, places=6)
        self.assertAlmostEqual(frame["fcff"].iloc[2], 174.24, places=6)

    def test_end_year_discount_factors(self):
        frame = project(base_inputs())
        self.assertAlmostEqual(frame["discount_factor"].iloc[0], 1 / 1.1, places=9)
        self.assertAlmostEqual(frame["discount_factor"].iloc[2], 1 / 1.1**3, places=9)


class TestTerminalValue(unittest.TestCase):
    def test_gordon_growth(self):
        # 174.24 × 1.02 / (0.10 - 0.02) = 2221.56
        self.assertAlmostEqual(terminal_value(174.24, 0.10, 0.02), 2221.56, places=6)

    def test_wacc_equal_growth_is_rejected(self):
        with self.assertRaises(ValueError):
            terminal_value(100.0, 0.05, 0.05)

    def test_exit_multiple_method(self):
        result = run_dcf(base_inputs(terminal_method="exit_multiple", exit_multiple=8.0))
        # 末年 EBITDA = 266.2 + 66.55 = 332.75，×8 = 2662
        self.assertAlmostEqual(result.terminal_value, 332.75 * 8.0, places=6)


class TestValuation(unittest.TestCase):
    def test_full_valuation_chain(self):
        result = run_dcf(base_inputs())
        self.assertAlmostEqual(result.pv_fcff, 392.7272727, places=4)
        self.assertAlmostEqual(result.pv_terminal, 1669.0909091, places=4)
        self.assertAlmostEqual(result.enterprise_value, 2061.8181818, places=4)
        self.assertAlmostEqual(result.equity_value, 1961.8181818, places=4)
        self.assertAlmostEqual(result.value_per_share, 39.2363636, places=4)

    def test_equity_bridge(self):
        result = run_dcf(base_inputs())
        self.assertAlmostEqual(
            result.equity_value, result.enterprise_value - result.inputs.net_debt, places=6
        )

    def test_midyear_discounting_increases_value(self):
        end_year = run_dcf(base_inputs(midyear=False))
        mid_year = run_dcf(base_inputs(midyear=True))
        self.assertGreater(mid_year.enterprise_value, end_year.enterprise_value)
        self.assertAlmostEqual(
            mid_year.projection["discount_factor"].iloc[0], 1 / 1.1**0.5, places=9
        )


class TestBoundaries(unittest.TestCase):
    def test_wacc_below_growth_rejected(self):
        with self.assertRaises(ValueError):
            run_dcf(base_inputs(wacc=0.01, terminal_growth=0.02))

    def test_growth_length_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            run_dcf(base_inputs(revenue_growth=[0.1, 0.1]))

    def test_non_positive_shares_rejected(self):
        with self.assertRaises(ValueError):
            run_dcf(base_inputs(shares_outstanding=0.0))

    def test_growth_below_minus_100pct_rejected(self):
        with self.assertRaises(ValueError):
            run_dcf(base_inputs(revenue_growth=[-1.5, 0.1, 0.1]))

    def test_high_terminal_share_triggers_warning(self):
        result = run_dcf(base_inputs(terminal_growth=0.05, wacc=0.09))
        self.assertTrue(any("终值" in w for w in result.warnings))
        self.assertGreater(result.tv_share_of_ev, 0.85)

    def test_negative_equity_triggers_warning(self):
        result = run_dcf(base_inputs(net_debt=5000.0))
        self.assertLess(result.equity_value, 0)
        self.assertTrue(any("股权价值为负" in w for w in result.warnings))


class TestFadeSchedule(unittest.TestCase):
    def test_linear_fade(self):
        values = fade_schedule(0.2, 0.02, 5)
        self.assertAlmostEqual(values[0], 0.2)
        self.assertAlmostEqual(values[-1], 0.02)
        self.assertAlmostEqual(values[2], (0.2 + 0.02) / 2, places=9)

    def test_single_year(self):
        self.assertEqual(len(fade_schedule(0.1, 0.05, 1)), 1)


class TestExitMultiple(unittest.TestCase):
    def test_terminal_value_uses_last_year_ebitda(self):
        inputs = base_inputs(terminal_method="exit_multiple", exit_multiple=8.0)
        result = run_dcf(inputs)
        last = result.projection.iloc[-1]
        ebitda = last["ebit"] + last["da"]
        self.assertAlmostEqual(result.terminal_value, ebitda * 8.0, places=6)
        self.assertAlmostEqual(result.pv_terminal, ebitda * 8.0 * last["discount_factor"], places=6)

    def test_allows_growth_above_wacc(self):
        inputs = base_inputs(terminal_method="exit_multiple", exit_multiple=8.0, terminal_growth=0.12)
        run_dcf(inputs)

    def test_gordon_still_rejects_growth_above_wacc(self):
        with self.assertRaises(ValueError):
            run_dcf(base_inputs(terminal_growth=0.12))


if __name__ == "__main__":
    unittest.main()
