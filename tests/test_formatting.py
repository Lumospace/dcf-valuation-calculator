"""展示层数据整理测试：防止图表数据因索引对齐变成 NaN。"""

import unittest

import pandas as pd

from dcf.formatting import projection_chart_frame


class TestProjectionChartFrame(unittest.TestCase):
    def test_index_is_year_labels(self):
        projection = pd.DataFrame({"year": [1, 2, 3], "revenue": [100.0, 110.0, 121.0], "fcff": [10.0, 11.0, 12.1]})
        frame = projection_chart_frame(projection)
        self.assertEqual(frame.index.tolist(), ["Y1", "Y2", "Y3"])

    def test_values_are_not_nan(self):
        projection = pd.DataFrame({"year": [1, 2, 3], "revenue": [100.0, 110.0, 121.0], "fcff": [10.0, 11.0, 12.1]})
        frame = projection_chart_frame(projection)
        self.assertFalse(frame.isna().any().any())

    def test_units_converted_to_yi(self):
        projection = pd.DataFrame({"year": [1], "revenue": [2e8], "fcff": [5e7]})
        frame = projection_chart_frame(projection)
        self.assertAlmostEqual(frame["营业收入（亿元）"].iloc[0], 2.0)
        self.assertAlmostEqual(frame["自由现金流（亿元）"].iloc[0], 0.5)


if __name__ == "__main__":
    unittest.main()
