"""界面冒烟测试：三种终值模式与非法参数下页面不应崩溃。"""

import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP_PATH = str(Path(__file__).resolve().parents[1] / "app.py")


def widget(elements, key):
    return next(element for element in elements if element.key == key)


class TestAppSmoke(unittest.TestCase):
    def setUp(self):
        self.at = AppTest.from_file(APP_PATH, default_timeout=30)
        self.at.run()

    def test_initial_state_renders(self):
        self.assertEqual(len(self.at.exception), 0)
        self.assertEqual(len(self.at.metric), 4)
        self.assertEqual(len(self.at.tabs), 4)

    def test_manual_input_mode(self):
        widget(self.at.radio, "source").set_value("手动输入").run()
        self.assertEqual(len(self.at.exception), 0)
        self.assertEqual(len(self.at.metric), 4)

    def test_exit_multiple_mode_renders(self):
        widget(self.at.radio, "tm_C001").set_value("退出倍数法").run()
        self.assertEqual(len(self.at.exception), 0)
        self.assertEqual(len(self.at.metric), 4)
        self.assertEqual(len(self.at.tabs), 4)

    def test_invalid_growth_keeps_page_usable(self):
        widget(self.at.slider, "wacc_C001").set_value(4.0).run()
        widget(self.at.slider, "tg_C001").set_value(5.0).run()
        self.assertEqual(len(self.at.exception), 0)
        self.assertEqual(len(self.at.metric), 4)
        self.assertGreater(len(self.at.error), 0)

    def test_reset_button(self):
        widget(self.at.slider, "wacc_C001").set_value(12.0).run()
        button = next(item for item in self.at.button if item.label == "恢复样本假设")
        button.click().run()
        self.assertEqual(len(self.at.exception), 0)


if __name__ == "__main__":
    unittest.main()
