import unittest

try:
    from clipboard_app.hotkey import HotkeyError, parse_hotkey
except ImportError:
    HotkeyError = ValueError
    parse_hotkey = None


@unittest.skipIf(parse_hotkey is None, "PySide6 is not installed")
class HotkeyParsingTests(unittest.TestCase):
    def test_default(self):
        self.assertEqual((0x0002 | 0x0004, ord("V")), parse_hotkey("Ctrl+Shift+V"))

    def test_function_key(self):
        self.assertEqual((0x0001, 0x7B), parse_hotkey("Alt+F12"))

    def test_rejects_unmodified_key(self):
        with self.assertRaises(HotkeyError):
            parse_hotkey("V")

    def test_rejects_unsupported_key(self):
        with self.assertRaises(HotkeyError):
            parse_hotkey("Ctrl+Space")


if __name__ == "__main__":
    unittest.main()

