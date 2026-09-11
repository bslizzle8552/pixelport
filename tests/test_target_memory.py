"""Foreground observation through capture/paste, with all desktop effects mocked."""

from contextlib import ExitStack
import sys
import unittest
from unittest.mock import MagicMock, patch

if sys.platform == "win32":
    from gptsnip.app import App
    from gptsnip.core import Window


@unittest.skipUnless(sys.platform == "win32", "Windows target memory flow")
class TargetMemoryTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = MagicMock()
        self.app = App(self.root, reader=MagicMock(request=MagicMock(return_value=None), poll=MagicMock(return_value=None)))
        self.app.notice = MagicMock()
        self.a = Window(10, 1, "msedge.exe", "ChatGPT - Edge")
        self.b = Window(20, 2, "firefox.exe", "ChatGPT - Firefox")
        self.other = Window(30, 3, "notepad.exe", "Notes")
        self.current = self.a
        self.windows = [self.a, self.b, self.other]
        self.clock = self.mock("time.monotonic", return_value=10)
        self.foreground = self.mock("win32gui.GetForegroundWindow",
                                    side_effect=lambda: self.current.hwnd)
        self.inspect = self.mock("native.inspect_window", side_effect=lambda hwnd:
                                 next((w for w in self.windows if w.hwnd == hwnd), None))
        self.enumerate = self.mock("native.list_windows", side_effect=lambda: self.windows)
        self.mock("native.desktop_bounds", return_value=(0, 0, 100, 100))
        self.selector = self.mock("Selector")

    def mock(self, name, **kwargs):
        return self.stack.enter_context(patch(f"gptsnip.app.{name}", **kwargs))

    def observe(self, window):
        self.current = window
        self.clock.return_value += 1
        self.app.tick()

    def prepare_capture(self):
        self.mock("native.dwmapi.DwmFlush", return_value=0)
        self.mock("ImageGrab.grab").return_value.__enter__.return_value.size = (10, 20)
        self.copy = self.mock("native.copy_image", return_value=99)
        self.mock("native.keys_down", return_value=False)
        self.mock("native.win32gui.IsIconic", return_value=False)
        self.activate = self.mock("native.win32gui.SetForegroundWindow")
        self.mock("native.win32clipboard.GetClipboardSequenceNumber", return_value=99)
        self.send = self.mock("native.user32.SendInput", return_value=4)

    def test_foreground_chatgpt_remembered_and_retained_after_switch(self):
        self.observe(self.a)
        self.assertEqual(self.app.remembered, self.a)
        self.observe(self.other)
        self.assertEqual(self.app.remembered, self.a)
        self.app.begin_capture()
        self.assertEqual(self.app.target, self.a)

    def test_latest_observation_wins_and_successful_capture_only_pastes_ctrl_v(self):
        self.observe(self.a)
        self.observe(self.b)
        self.observe(self.other)
        self.prepare_capture()
        self.app.begin_capture()
        self.assertEqual(self.app.target, self.b)
        self.app.selection_complete((0, 0, 10, 20))
        delay, capture = self.root.after.call_args.args
        self.assertEqual(delay, 120)
        capture()
        self.copy.assert_called_once()
        self.activate.assert_called_once_with(self.b.hwnd)
        self.current = self.b
        _, wait_focus = self.root.after.call_args.args
        wait_focus()
        self.send.assert_called_once()
        count, events, _ = self.send.call_args.args
        self.assertEqual(count, 4)
        self.assertEqual([(e.type, e.ki.wVk, e.ki.dwFlags) for e in events],
                         [(1, 0x11, 0), (1, 0x56, 0), (1, 0x56, 2), (1, 0x11, 2)])
        self.assertFalse(self.app.busy)

    def test_codex_does_not_replace_legacy_browser_and_capture_only_pastes_to_browser(self):
        codex = Window(40, 4, "ChatGPT.exe", "ChatGPT")
        self.windows.append(codex)
        self.observe(self.a)
        self.observe(codex)
        self.assertEqual(self.app.remembered, self.a)
        self.prepare_capture()
        self.app.begin_capture()
        self.assertEqual(self.app.target, self.a)
        self.app.selection_complete((0, 0, 10, 20))
        delay, capture = self.root.after.call_args.args
        self.assertEqual(delay, 120)
        capture()
        self.copy.assert_called_once()
        self.activate.assert_called_once_with(self.a.hwnd)
        self.current = self.a
        _, wait_focus = self.root.after.call_args.args
        wait_focus()
        self.send.assert_called_once()
        count, events, _ = self.send.call_args.args
        self.assertEqual(count, 4)
        self.assertEqual([(e.type, e.ki.wVk, e.ki.dwFlags) for e in events],
                         [(1, 0x11, 0), (1, 0x56, 0), (1, 0x56, 2), (1, 0x11, 2)])
        self.assertFalse(self.app.busy)

    def test_non_browser_observation_and_discovery_always_copy_without_paste(self):
        self.prepare_capture()
        cases = [(process, title)
                 for process in ("ChatGPT.exe", "codex.exe", "notepad.exe",
                                 "Code.exe", "powershell.exe")
                 for title in ("ChatGPT", "OpenAI", "GPT")]
        for process, title in cases:
            with self.subTest(process=process, title=title):
                window = Window(40, 4, process, title)
                self.windows = [window, Window(50, 5, "chrome.exe",
                                "Easier Screenshot Sharing - Google Chrome")]
                self.observe(window)
                self.assertIsNone(self.app.remembered)
                self.app.begin_capture()
                self.assertIsNone(self.app.target)
                self.app.capture((0, 0, 10, 20))
                self.assertFalse(self.app.busy)
        self.assertEqual(self.copy.call_count, len(cases))
        self.activate.assert_not_called()
        self.send.assert_not_called()

    def test_codex_does_not_make_legacy_browser_discovery_ambiguous(self):
        self.windows = [Window(40, 4, "ChatGPT.exe", "ChatGPT"), self.a]
        self.app.begin_capture()
        self.assertIsNone(self.app.remembered)
        self.assertEqual(self.app.target, self.a)

    def test_closed_legacy_memory_does_not_redirect_to_codex_or_another_browser(self):
        self.observe(self.a)
        codex = Window(40, 4, "ChatGPT.exe", "ChatGPT")
        self.windows = [codex, self.b]
        self.observe(codex)
        self.prepare_capture()
        for _ in range(2):
            self.app.begin_capture()
            self.assertIsNone(self.app.target)
            self.app.capture((0, 0, 10, 20))
            self.assertEqual(self.app.remembered, self.a)
        self.assertEqual(self.copy.call_count, 2)
        self.activate.assert_not_called()
        self.send.assert_not_called()

    def test_closed_or_changed_memory_copies_without_redirecting(self):
        self.observe(self.a)
        self.prepare_capture()
        for changed in (None, Window(10, 1, self.a.process, "Documentation")):
            with self.subTest(changed=changed):
                self.windows = [self.b] if changed is None else [changed, self.b]
                # Multiple subsequent captures must still fail closed.
                for _ in range(2):
                    self.app.begin_capture()
                    self.assertIsNone(self.app.target)
                    self.app.capture((0, 0, 10, 20))
                    self.assertFalse(self.app.busy)
                self.assertEqual(self.app.remembered, self.a)
        self.assertEqual(self.copy.call_count, 4)
        self.activate.assert_not_called()
        self.send.assert_not_called()

    def test_changed_during_selection_blocks_activation_after_copy(self):
        self.observe(self.a)
        self.prepare_capture()
        self.app.begin_capture()
        self.windows = [self.b]
        self.app.capture((0, 0, 10, 20))
        self.copy.assert_called_once()
        self.activate.assert_not_called()
        self.send.assert_not_called()
        self.assertFalse(self.app.busy)

    def test_changed_after_activation_blocks_input(self):
        self.observe(self.a)
        self.prepare_capture()
        self.app.begin_capture()
        self.app.capture((0, 0, 10, 20))
        self.activate.assert_called_once_with(self.a.hwnd)
        self.windows = [Window(10, 1, self.a.process, "Documentation"), self.b]
        self.app.wait_focus()
        self.send.assert_not_called()
        self.assertFalse(self.app.busy)

    def test_manual_binding_overrides_later_memory_including_custom_title(self):
        custom = Window(40, 4, "chrome.exe", "My existing conversation")
        self.windows.append(custom)
        self.current = custom
        self.app.bind_target()
        self.observe(self.b)
        self.app.begin_capture()
        self.assertEqual(self.app.target, custom)

    def test_invalid_manual_binding_blocks_valid_automatic_memory(self):
        self.app.bind_target()
        self.observe(self.b)
        self.windows = [self.b]
        self.app.begin_capture()
        self.assertIsNone(self.app.target)

    def test_desktop_requires_deliberate_manual_binding_and_still_pastes_unsent(self):
        desktop = Window(40, 4, "ChatGPT.exe", "ChatGPT")
        self.windows.append(desktop)
        self.observe(desktop)
        self.assertIsNone(self.app.remembered)
        self.app.bind_target()
        self.assertEqual(self.app.bound, desktop)
        self.observe(self.a)
        self.prepare_capture()
        self.app.begin_capture()
        self.assertEqual(self.app.target, desktop)
        self.app.capture((0, 0, 10, 20))
        self.copy.assert_called_once()
        self.activate.assert_called_once_with(desktop.hwnd)
        self.current = desktop
        self.app.wait_focus()
        self.send.assert_called_once()
        count, events, _ = self.send.call_args.args
        self.assertEqual(count, 4)
        self.assertEqual([(e.type, e.ki.wVk, e.ki.dwFlags) for e in events],
                         [(1, 0x11, 0), (1, 0x56, 0), (1, 0x56, 2), (1, 0x11, 2)])

    def test_no_observation_or_candidate_copies_without_arbitrary_paste(self):
        self.windows = [self.other, Window(40, 4, "chrome.exe", "Documentation")]
        self.observe(self.other)
        self.prepare_capture()
        self.app.begin_capture()
        self.app.capture((0, 0, 10, 20))
        self.assertIsNone(self.app.remembered)
        self.copy.assert_called_once()
        self.activate.assert_not_called()
        self.send.assert_not_called()

    def test_foreground_tab_title_change_learns_without_window_switch(self):
        self.current = Window(10, 1, self.a.process, "Documentation")
        self.windows = [self.current]
        self.observe(self.current)
        self.assertIsNone(self.app.remembered)
        self.windows = [self.a]
        self.observe(self.a)
        self.assertEqual(self.app.remembered, self.a)

    def test_new_observation_recovers_invalid_memory(self):
        self.observe(self.a)
        self.windows = [self.b]
        self.observe(self.b)
        self.app.begin_capture()
        self.assertEqual(self.app.target, self.b)

    def test_observation_is_throttled_without_enumerating_windows(self):
        for timestamp in (10, 10.03, 10.06, 10.24, 10.27):
            self.clock.return_value = timestamp
            self.app.tick()
        self.assertEqual(self.inspect.call_count, 2)
        self.enumerate.assert_not_called()
        self.app.notice.assert_called_once()

    def test_capture_and_stop_suspend_observation(self):
        self.observe(self.a)
        self.app.begin_capture()
        self.observe(self.b)
        self.assertEqual(self.app.target, self.a)
        self.assertEqual(self.app.remembered, self.a)
        self.app.stopping = True
        self.app.busy = False
        self.observe(self.b)
        self.assertEqual(self.app.remembered, self.a)

    def test_foreground_race_does_not_learn_unobserved_window(self):
        self.foreground.side_effect = [self.a.hwnd, self.other.hwnd]
        self.app.tick()
        self.assertIsNone(self.app.remembered)

    def test_uninspectable_foreground_keeps_memory(self):
        self.observe(self.a)
        self.inspect.side_effect = None
        self.inspect.return_value = None
        self.observe(self.other)
        self.assertEqual(self.app.remembered, self.a)


if __name__ == "__main__":
    unittest.main()
