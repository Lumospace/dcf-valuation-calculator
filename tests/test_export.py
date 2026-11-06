"""Excel 导出测试。"""

import unittest
from io import BytesIO

from openpyxl import load_workbook

from dcf.export import SHEET_NAMES, build_excel
from dcf.model import DCFInputs, run_dcf
from dcf.sensitivity import build_scenarios, build_sensitivity


def sample_inputs() -> DCFInputs:
    return DCFInputs(
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


class TestExcelExport(unittest.TestCase):
    def setUp(self):
        inputs = sample_inputs()
        self.result = run_dcf(inputs)
        self.sensitivity = build_sensitivity(inputs)
        self.scenarios = build_scenarios(inputs)
        self.payload = build_excel(self.result, self.sensitivity, self.scenarios)

    def test_returns_bytes(self):
        self.assertIsInstance(self.payload, bytes)
        self.assertGreater(len(self.payload), 0)

    def test_all_sheets_present(self):
        workbook = load_workbook(BytesIO(self.payload))
        self.assertEqual(workbook.sheetnames, SHEET_NAMES)
        workbook.close()

    def test_projection_rows(self):
        workbook = load_workbook(BytesIO(self.payload))
        sheet = workbook["预测明细"]
        # 表头 1 行 + 3 个预测年度
        self.assertEqual(sheet.max_row, 4)
        workbook.close()

    def test_summary_contains_enterprise_value(self):
        workbook = load_workbook(BytesIO(self.payload))
        sheet = workbook["估值结果"]
        labels = [sheet.cell(row=row, column=1).value for row in range(1, 7)]
        self.assertIn("企业价值（元）", labels)
        workbook.close()


if __name__ == "__main__":
    unittest.main()
