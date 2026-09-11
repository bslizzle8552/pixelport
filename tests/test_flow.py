import sys
import unittest
from unittest.mock import MagicMock, patch

if sys.platform == "win32":
    from gptsnip.app import App
    from gptsnip.core import Window


@unittest.skipUnless(sys.platform == "win32", "Windows application flow")
class FlowTests(unittest.TestCase):
    def setUp(self):
        self.root = MagicMock()
        self.app = App(self.root)
        self.app.notice = MagicMock()
        self.app.busy = True
        self.app.bounds = (0, 0, 100, 100)
        self.app.target = Window(1, 1, "chrome.exe", "ChatGPT")

    def test_escape_never_schedules_capture(self):
        self.app.selection_complete(None)
        self.assertFalse(self.app.busy)
        self.root.after.assert_not_called()

    def test_capture_deferred_until_selector_removed(self):
        self.app.selection_complete((1, 2, 30, 40))
        self.assertIsNone(self.app.selector)
        self.assertGreaterEqual(self.root.after.call_args.args[0], 100)

    def test_no_target_still_copies_but_never_focuses(self):
        self.app.target = None
        with patch("gptsnip.app.native.desktop_bounds", return_value=self.app.bounds), \
                patch("gptsnip.app.native.dwmapi.DwmFlush", return_value=0), \
                patch("gptsnip.app.ImageGrab.grab") as grab, \
                patch("gptsnip.app.native.copy_image", return_value=99) as copy, \
                patch("gptsnip.app.native.request_foreground") as focus:
            grab.return_value.__enter__.return_value.size = (10, 20)
            self.app.capture((0, 0, 10, 20))
            copy.assert_called_once()
            focus.assert_not_called()
            self.assertFalse(self.app.busy)

    def test_monitor_layout_change_blocks_capture(self):
        with patch("gptsnip.app.native.desktop_bounds", return_value=(-100, 0, 100, 100)), \
                patch("gptsnip.app.ImageGrab.grab") as grab:
            self.app.capture((0, 0, 10, 20))
            grab.assert_not_called()
            self.assertFalse(self.app.busy)

    def test_focus_refusal_never_pastes(self):
        self.app.deadline = 0
        with patch("gptsnip.app.win32gui.GetForegroundWindow", return_value=42), \
                patch("gptsnip.app.native.paste") as paste:
            self.app.wait_focus()
            paste.assert_not_called()
            self.assertFalse(self.app.busy)

    def test_stop_blocks_pending_capture(self):
        self.app.stop()
        with patch("gptsnip.app.ImageGrab.grab") as grab:
            self.app.capture((0, 0, 10, 20))
            grab.assert_not_called()


if __name__ == "__main__":
    unittest.main()
