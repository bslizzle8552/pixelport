import ctypes
import sys
import unittest
from unittest.mock import patch

if sys.platform == "win32":
    from gptsnip import windows as native
    from gptsnip.core import Window


@unittest.skipUnless(sys.platform == "win32", "Windows boundary tests")
class PasteSafetyTests(unittest.TestCase):
    def setUp(self):
        self.target = Window(123, 42, "chrome.exe", "ChatGPT")
        self.inspect = self.start_patch("inspect_window", return_value=self.target)
        self.keys = self.start_patch("keys_down", return_value=False)
        self.sequence = self.start_patch("win32clipboard.GetClipboardSequenceNumber", return_value=99)
        self.foreground = self.start_patch("win32gui.GetForegroundWindow", return_value=123)
        self.send = self.start_patch("user32.SendInput", return_value=4)

    def start_patch(self, name, **kwargs):
        patcher = patch(f"gptsnip.windows.{name}", **kwargs)
        result = patcher.start()
        self.addCleanup(patcher.stop)
        return result

    def test_only_ctrl_v_no_enter_or_mouse(self):
        native.paste(self.target, 99)
        self.send.assert_called_once()
        count, events, size = self.send.call_args.args
        self.assertEqual(count, 4)
        self.assertEqual(size, 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)
        self.assertEqual([(e.type, e.ki.wVk, e.ki.dwFlags) for e in events],
                         [(1, 0x11, 0), (1, 0x56, 0), (1, 0x56, 2), (1, 0x11, 2)])

    def test_changed_title_or_pid_blocks_paste(self):
        for changed in (None,
                        Window(123, 42, "chrome.exe", "Different tab"),
                        Window(123, 99, "chrome.exe", "ChatGPT"),
                        Window(123, 42, "notepad.exe", "ChatGPT")):
            with self.subTest(changed=changed):
                self.inspect.return_value = changed
                with self.assertRaisesRegex(RuntimeError, "target changed"):
                    native.paste(self.target, 99)
        self.send.assert_not_called()

    def test_lost_foreground_blocks_paste(self):
        self.foreground.return_value = 456
        with self.assertRaisesRegex(RuntimeError, "lost focus"):
            native.paste(self.target, 99)
        self.send.assert_not_called()

    def test_held_keys_block_paste(self):
        self.keys.return_value = True
        with self.assertRaisesRegex(RuntimeError, "held"):
            native.paste(self.target, 99)
        self.send.assert_not_called()

    def test_clipboard_replacement_blocks_paste(self):
        self.sequence.return_value = 100
        with self.assertRaisesRegex(RuntimeError, "Clipboard changed"):
            native.paste(self.target, 99)
        self.send.assert_not_called()

    def test_uipi_failure_does_not_retry_paste(self):
        self.send.return_value = 0
        with self.assertRaisesRegex(RuntimeError, "blocked"):
            native.paste(self.target, 99)
        self.send.assert_called_once()

    def test_partial_input_releases_keys_without_retrying_paste(self):
        self.send.side_effect = [2, 2]
        with self.assertRaises(RuntimeError):
            native.paste(self.target, 99)
        count, events, _ = self.send.call_args.args
        self.assertEqual(count, 2)
        self.assertEqual([(e.ki.wVk, e.ki.dwFlags) for e in events], [(0x56, 2), (0x11, 2)])


@unittest.skipUnless(sys.platform == "win32", "Windows boundary tests")
class ClipboardTests(unittest.TestCase):
    def test_busy_clipboard_is_bounded_and_never_emptied(self):
        from PIL import Image
        with patch.object(native.win32clipboard, "OpenClipboard",
                          side_effect=native.win32api.error(5, "OpenClipboard", "busy")) as opened, \
                patch.object(native.win32clipboard, "EmptyClipboard") as emptied, \
                patch.object(native.time, "sleep"):
            with self.assertRaisesRegex(RuntimeError, "busy"):
                native.copy_image(Image.new("RGB", (1, 1)), 1)
            self.assertEqual(opened.call_count, 11)
            emptied.assert_not_called()


if __name__ == "__main__":
    unittest.main()
