"""Chrome memory/capture integration; pixels, clipboard, focus and input are mocked."""
from contextlib import ExitStack
from dataclasses import replace
import sys
import unittest
from unittest.mock import MagicMock, patch

if sys.platform == 'win32':
    from gptsnip.app import App
    from gptsnip.browser import DocumentResult
    from gptsnip.core import Window, choose_target
    from gptsnip.native_document import DocumentSnapshot


class FakeReader:
    def __init__(self):
        self.serial = 0
        self.pending = None
        self.reply = None
        self.calls = []

    def request(self, window):
        if self.pending:
            return None
        self.serial += 1
        self.pending = (self.serial, window)
        self.calls.append(window)
        return self.serial

    def poll(self):
        reply, self.reply = self.reply, None
        if reply:
            self.pending = None
        return reply

    def close(self):
        pass


@unittest.skipUnless(sys.platform == 'win32', 'Windows capture integration')
class ChromeTargetingTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.reader = FakeReader()
        self.root = MagicMock()
        self.app = App(self.root, reader=self.reader)
        self.app.notice = MagicMock()
        self.a = Window(10, 1, 'chrome.exe', 'Easier Screenshot Sharing - Google Chrome')
        self.b = Window(20, 2, 'chrome.exe', 'ChatGPT - Google Chrome')
        self.codex = Window(30, 3, 'ChatGPT.exe', 'ChatGPT')
        self.windows = [self.a, self.b, self.codex]
        self.foreground = self.a
        self.snapshots = {w.hwnd: DocumentSnapshot(w, 1.0, 8, (w.hwnd + 100, 8, w.pid, w.hwnd))
                          for w in (self.a, self.b)}
        self.clock = self.mock('time.monotonic', return_value=100.0)
        self.mock('win32gui.GetForegroundWindow', side_effect=lambda: self.foreground.hwnd)
        self.mock('native.inspect_window', side_effect=lambda hwnd: next((w for w in self.windows if w.hwnd == hwnd), None))
        self.mock('native.list_windows', side_effect=lambda: self.windows)
        self.mock('native_document.is_current', side_effect=lambda snap: self.snapshots.get(snap.window.hwnd) == snap)
        self.mock('native.desktop_bounds', return_value=(0, 0, 100, 100))
        self.selector = self.mock('Selector')
        self.mock('native.dwmapi.DwmFlush', return_value=0)
        self.mock('ImageGrab.grab').return_value.__enter__.return_value.size = (10, 20)
        self.copy = self.mock('native.copy_image', return_value=99)
        self.mock('native.keys_down', return_value=False)
        self.mock('native.win32gui.IsIconic', return_value=False)
        self.activate = self.mock('native.win32gui.SetForegroundWindow')
        self.mock('native.win32clipboard.GetClipboardSequenceNumber', return_value=99)
        self.send = self.mock('native.user32.SendInput', return_value=4)

    def mock(self, name, **kwargs):
        return self.stack.enter_context(patch('gptsnip.app.' + name, **kwargs))

    def result(self, window, host='chatgpt.com'):
        return DocumentResult('verified', host, self.snapshots[window.hwnd], self.clock.return_value, '')

    def deliver(self, host='chatgpt.com', result=None):
        self.assertIsNotNone(self.reader.pending)
        token, window = self.reader.pending
        self.reader.reply = token, result if result is not None else self.result(window, host)
        self.app.poll_identity()

    def observe(self, window, host='chatgpt.com', result=None):
        self.foreground = window
        self.clock.return_value += 1
        self.app.observe_foreground()
        if window.process.lower() == 'chrome.exe':
            self.deliver(host, result)

    def select(self):
        self.app.begin_capture()
        self.assertIsNone(self.app.target)
        self.selector.assert_not_called()
        self.deliver()
        self.assertEqual(self.app.target, self.a)

    def test_arbitrary_title_is_learned_only_after_verified_active_document(self):
        self.app.observe_foreground()
        self.assertIsNone(self.app.remembered)
        self.deliver()
        self.assertEqual(self.app.remembered, self.a)
        self.assertIsNotNone(self.app.chrome_memory)
        self.assertFalse(self.a.recognized, 'title-only Chrome eligibility must stay disabled')

    def test_chrome_title_cannot_enable_unverified_discovery(self):
        self.assertIsNone(choose_target([self.b, self.codex]))
        self.app.begin_capture()
        self.assertIsNone(self.app.target)
        self.app.capture((0, 0, 10, 20))
        self.copy.assert_called_once()
        self.activate.assert_not_called()
        self.send.assert_not_called()

    def test_background_chatgpt_active_github_is_not_eligible(self):
        self.observe(self.b, 'github.com')
        self.assertIsNone(self.app.remembered)

    def test_same_hwnd_github_invalidates_memory_and_blocks_later_capture(self):
        self.observe(self.a)
        self.observe(self.a, 'github.com')
        self.observe(self.codex)
        for _ in range(2):
            self.app.begin_capture()
            self.assertIsNone(self.app.target)
            self.app.capture((0, 0, 10, 20))
        self.assertEqual(self.app.remembered, self.a)
        self.assertTrue(self.app.memory_blocked)
        self.assertEqual(self.copy.call_count, 2)
        self.activate.assert_not_called()
        self.send.assert_not_called()

    def test_switching_back_to_chatgpt_recovers_blocked_memory(self):
        self.observe(self.a)
        self.observe(self.a, 'github.com')
        self.observe(self.a)
        self.assertFalse(self.app.memory_blocked)
        self.select()

    def test_other_application_preserves_chrome_memory(self):
        self.observe(self.a)
        self.observe(self.codex)
        self.assertEqual(self.app.remembered, self.a)
        self.select()

    def test_separate_windows_do_not_invalidate_or_migrate_memory(self):
        self.observe(self.a)
        self.observe(self.b, 'github.com')
        self.assertEqual(self.app.remembered, self.a)
        self.assertFalse(self.app.memory_blocked)
        self.app.begin_capture()
        self.deliver(result=self.result(self.b))
        self.assertIsNone(self.app.target)

    def test_unknown_or_timeout_invalidates_same_window(self):
        self.observe(self.a)
        self.observe(self.a, result=DocumentResult(reason='timeout'))
        self.assertTrue(self.app.memory_blocked)
        self.app.begin_capture()
        self.assertIsNone(self.app.target)

    def test_stale_evidence_cannot_learn_target(self):
        self.app.observe_foreground()
        self.deliver(result=replace(self.result(self.a), sampled_at=90))
        self.assertIsNone(self.app.remembered)

    def test_changed_renderer_or_reused_process_rejects_reply(self):
        for field in ('renderer', 'process_started'):
            self.clock.return_value += 1
            self.app.observe_foreground()
            old = self.result(self.a)
            snap = self.snapshots[self.a.hwnd]
            self.snapshots[self.a.hwnd] = replace(snap, **{field: (999, 8, 1, 10) if field == 'renderer' else 2.0})
            self.deliver(result=old)
            self.assertIsNone(self.app.remembered)

    def test_foreground_switch_during_idle_request_cannot_learn_background_window(self):
        self.app.observe_foreground()
        self.foreground = self.codex
        self.deliver()
        self.assertIsNone(self.app.remembered)

    def test_idle_request_cannot_satisfy_new_capture_revalidation(self):
        self.observe(self.a)
        self.clock.return_value += 1
        self.app.observe_foreground()
        self.app.begin_capture()
        self.deliver()  # Old idle response drains; a new required request starts.
        self.assertIsNone(self.app.target)
        self.assertIsNotNone(self.reader.pending)
        self.deliver()
        self.assertEqual(self.app.target, self.a)

    def test_capture_selection_requires_fresh_success_or_copies_only(self):
        self.observe(self.a)
        self.app.begin_capture()
        self.deliver('github.com')
        self.assertIsNone(self.app.target)
        self.app.capture((0, 0, 10, 20))
        self.copy.assert_called_once()
        self.activate.assert_not_called()

    def test_pre_activation_url_failure_blocks_activation_and_input(self):
        self.observe(self.a)
        self.select()
        self.app.capture((0, 0, 10, 20))
        self.copy.assert_called_once()
        self.activate.assert_not_called()
        self.deliver('github.com')
        self.activate.assert_not_called()
        self.send.assert_not_called()
        self.assertFalse(self.app.busy)

    def test_pre_paste_url_failure_blocks_input_after_activation(self):
        self.observe(self.a)
        self.select()
        self.app.capture((0, 0, 10, 20))
        self.deliver()
        self.activate.assert_called_once_with(self.a.hwnd)
        self.app.wait_focus()
        self.deliver(result=DocumentResult(reason='timeout'))
        self.send.assert_not_called()
        self.assertFalse(self.app.busy)

    def test_success_requires_three_fresh_checks_and_only_injects_ctrl_v(self):
        self.observe(self.a)
        self.observe(self.codex)
        self.select()
        self.app.capture((0, 0, 10, 20))
        self.deliver()  # Before activation.
        self.foreground = self.a
        self.app.wait_focus()
        self.send.assert_not_called()
        self.deliver()  # Immediately before paste.
        self.assertEqual(len(self.reader.calls), 4)  # Idle + three capture checks.
        count, events, _ = self.send.call_args.args
        self.assertEqual(count, 4)
        self.assertEqual([(e.type, e.ki.wVk, e.ki.dwFlags) for e in events],
                         [(1, 0x11, 0), (1, 0x56, 0), (1, 0x56, 2), (1, 0x11, 2)])

    def test_lost_focus_after_url_verification_still_blocks_native_input(self):
        self.observe(self.a)
        self.select()
        self.app.capture((0, 0, 10, 20))
        self.deliver()
        self.app.wait_focus()
        self.foreground = self.codex
        self.deliver()
        self.send.assert_not_called()

    def test_manual_g_binding_keeps_existing_override_without_url_calls(self):
        for window in (self.a, self.codex):
            self.foreground = window
            self.app.bind_target()
            self.app.begin_capture()
            self.assertEqual(self.app.target, window)
            self.assertIsNone(self.app.target_document)
            self.app.capture((0, 0, 10, 20))
            self.app.wait_focus()
        self.assertEqual(self.send.call_count, 2)
        self.assertEqual(self.reader.calls, [])

    def test_stop_prevents_late_verification_from_starting_selector(self):
        self.observe(self.a)
        self.app.begin_capture()
        self.app.stop()
        self.deliver()
        self.selector.assert_not_called()
        self.activate.assert_not_called()

    def test_verification_flow_has_deadline_even_if_reader_never_replies(self):
        self.observe(self.a)
        self.app.begin_capture()
        self.clock.return_value += 2
        self.app.poll_identity()
        self.assertIsNone(self.app.target)
        self.selector.assert_called_once()
        self.activate.assert_not_called()

    def test_reply_after_flow_deadline_cannot_reopen_capture_target(self):
        self.observe(self.a)
        self.app.begin_capture()
        self.clock.return_value += 2
        self.deliver()  # A fresh-looking reply still cannot extend the flow deadline.
        self.assertIsNone(self.app.target)
        self.selector.assert_called_once()

    def test_idle_native_requests_are_rate_limited_and_bounded(self):
        self.app.observe_foreground()
        for _ in range(10):
            self.clock.return_value += .03
            self.app.observe_foreground()
        self.assertEqual(len(self.reader.calls), 1)
        self.deliver()
        self.app.observe_foreground()
        self.assertEqual(len(self.reader.calls), 1)
        self.clock.return_value += .5
        self.app.observe_foreground()
        self.assertEqual(len(self.reader.calls), 2)


if __name__ == '__main__':
    unittest.main()
