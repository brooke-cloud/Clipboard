import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QCoreApplication

from clipboard_app.settings import AppSettings, SettingsStore, stylesheet


class SettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def test_round_trip_and_restart_load(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            first = SettingsStore(path)
            expected = AppSettings(18, "custom", "#abc123", "Alt+F12", False)
            first.save(expected)
            actual = SettingsStore(path).load()
            self.assertEqual(expected, actual)

    def test_stylesheet_uses_font_and_background(self):
        css = stylesheet(AppSettings(font_size=17, theme="custom", custom_color="#123456"))
        self.assertIn("font-size: 17px", css)
        self.assertIn("background: #123456", css)

    def test_always_on_top_round_trip(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            value = AppSettings(always_on_top=True)
            SettingsStore(path).save(value)
            self.assertTrue(SettingsStore(path).load().always_on_top)


if __name__ == "__main__":
    unittest.main()
