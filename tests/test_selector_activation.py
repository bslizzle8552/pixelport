"""Native calls are mocked; these tests never activate a real window."""

from contextlib import ExitStack
import sys
import unittest
from unittest.mock import call, patch

if sys.platform == "win32":
    from gptsnip import windows as native


@unittest.skipUnless(sys.platform == "win32", "Windows selector activation")
class SelectorActivationTests(unittest.TestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(native.win32api, "GetCurrentThreadId", return_value=11))
        stack.enter_context(patch.object(native.win32api, "GetCurrentProcessId", return_value=101))
        self.threads = stack.enter_context(patch.object(
            native.win32process, "GetWindowThreadProcessId",
            side_effect=lambda hwnd: (11, 101) if hwnd == 77 else (22, 202)))
        self.foreground = stack.enter_context(patch.object(
            native.win32gui, "GetForegroundWindow", return_value=999))
        self.attach = stack.enter_context(patch.object(native.user32, "AttachThreadInput", return_value=True))
        self.activate = stack.enter_context(patch.object(
            native.win32gui, "SetForegroundWindow",
            side_effect=lambda hwnd: setattr(self.foreground, "return_value", hwnd)))
        self.inject = stack.enter_context(patch.object(native.user32, "SendInput"))

    def test_background_source_to_our_selector_detaches_before_return_without_console(self):
        self.assertTrue(native.acquire_selector_foreground(77, 999))
        self.activate.assert_called_once_with(77)
        self.assertEqual(self.attach.call_args_list, [call(11, 22, True), call(11, 22, False)])
        self.inject.assert_not_called()

    def test_already_foreground_needs_no_attachment_or_activation(self):
        self.foreground.return_value = 77
        self.assertTrue(native.acquire_selector_foreground(77, 999))
        self.attach.assert_not_called()
        self.activate.assert_not_called()

    def test_other_process_target_is_never_activated(self):
        self.assertFalse(native.acquire_selector_foreground(888, 999))
        self.attach.assert_not_called()
        self.activate.assert_not_called()

    def test_changed_or_missing_source_is_never_activated(self):
        for source in (0, 998):
            self.assertFalse(native.acquire_selector_foreground(77, source))
        self.attach.assert_not_called()
        self.activate.assert_not_called()

    def test_attach_failure_does_not_activate_or_detach_an_unowned_attachment(self):
        self.attach.return_value = False
        self.assertFalse(native.acquire_selector_foreground(77, 999))
        self.attach.assert_called_once_with(11, 22, True)
        self.activate.assert_not_called()

    def test_activation_exception_still_detaches(self):
        self.activate.side_effect = native.win32api.error(5, "SetForegroundWindow", "denied")
        self.assertFalse(native.acquire_selector_foreground(77, 999))
        self.assertEqual(self.attach.call_args_list, [call(11, 22, True), call(11, 22, False)])

    def test_source_change_during_attach_detaches_without_stealing_back(self):
        def attach(*_):
            self.foreground.return_value = 1000
            return True
        self.attach.side_effect = attach
        self.assertFalse(native.acquire_selector_foreground(77, 999))
        self.activate.assert_not_called()
        self.assertEqual(self.attach.call_args_list, [call(11, 22, True), call(11, 22, False)])

    def test_api_success_without_actual_foreground_is_not_accepted(self):
        self.activate.side_effect = None
        self.activate.return_value = True
        self.assertFalse(native.acquire_selector_foreground(77, 999))
        self.assertEqual(self.attach.call_args_list, [call(11, 22, True), call(11, 22, False)])

    def test_detach_failure_raises_instead_of_reporting_success(self):
        self.attach.side_effect = [True, False]
        with self.assertRaisesRegex(RuntimeError, "detachment failed"):
            native.acquire_selector_foreground(77, 999)

    def test_same_ui_thread_does_not_attach_to_itself(self):
        self.threads.side_effect = lambda _: (11, 101)
        self.assertTrue(native.acquire_selector_foreground(77, 999))
        self.attach.assert_not_called()
        self.activate.assert_called_once_with(77)


if __name__ == "__main__":
    unittest.main()
