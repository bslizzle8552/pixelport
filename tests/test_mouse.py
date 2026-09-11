"""Native input is mocked: these tests never operate the user's mouse/clipboard."""

from contextlib import ExitStack
import ctypes as ct
import sys
import unittest
from unittest.mock import MagicMock, patch

if sys.platform == "win32":
    from gptsnip import mouse
    from gptsnip.app import App
    from gptsnip.browser import DocumentResult
    from gptsnip.core import Window
    from gptsnip.native_document import DocumentSnapshot
    from gptsnip.selector import Selector
    from test_chrome_targeting import FakeReader


@unittest.skipUnless(sys.platform == "win32", "Windows mouse input")
class MouseStateTests(unittest.TestCase):
    def setUp(self):
        self.state = mouse.MouseState()

    def down(self, point=(-100, 20)):
        self.assertTrue(self.state.event(mouse.WM_MBUTTONDOWN, point))

    def test_down_retains_exact_physical_origin(self):
        self.down()
        self.assertEqual(self.state.gesture.start, (-100, 20))
        self.assertTrue(self.state.held)

    def test_move_coalesces_without_suppressing_cursor(self):
        self.down()
        for x in range(10000):
            self.assertFalse(self.state.event(mouse.WM_MOUSEMOVE, (x, 30)))
        self.assertEqual(self.state.gesture.point, (9999, 30))
        self.assertEqual(self.state.gesture.serial, 1)

    def test_up_records_exact_final_point_and_suppresses(self):
        self.down()
        self.assertTrue(self.state.event(mouse.WM_MBUTTONUP, (30, -20)))
        self.assertTrue(self.state.gesture.released)
        self.assertEqual(self.state.gesture.point, (30, -20))
        self.assertFalse(self.state.held)

    def test_duplicate_down_does_not_reset_anchor(self):
        self.down()
        self.down((999, 999))
        self.assertEqual(self.state.gesture.start, (-100, 20))
        self.assertEqual(self.state.serial, 1)

    def test_rapid_second_click_cannot_replace_unconsumed_release(self):
        self.down()
        self.state.event(mouse.WM_MBUTTONUP, (20, 50))
        first = self.state.gesture
        self.down((50, 60))
        self.state.event(mouse.WM_MBUTTONUP, (80, 90))
        self.assertIs(self.state.gesture, first)

    def test_cancel_ack_ignores_movement_and_release_until_new_press(self):
        self.down()
        self.state.acknowledged = 1
        first = self.state.gesture
        self.state.event(mouse.WM_MOUSEMOVE, (20, 40))
        self.down()
        self.state.event(mouse.WM_MBUTTONUP, (30, 40))
        self.assertIs(self.state.gesture, first)
        self.down((40, 50))
        self.assertEqual(self.state.gesture.serial, 2)

    def test_disabled_admission_still_suppresses_middle_pair(self):
        self.state.accepting = False
        self.down()
        self.state.accepting = True
        self.state.event(mouse.WM_MOUSEMOVE, (20, 40))
        self.assertTrue(self.state.event(mouse.WM_MBUTTONUP, (20, 40)))
        self.assertIsNone(self.state.gesture)
        self.down()
        self.assertIsNotNone(self.state.gesture)

    def test_other_buttons_wheels_and_idle_movement_pass_through(self):
        for message in (0x200, 0x201, 0x202, 0x203, 0x204, 0x205, 0x206,
                        0x20A, 0x20B, 0x20C, 0x20D, 0x20E):
            with self.subTest(message=message):
                self.assertFalse(self.state.event(message, (10, 20)))
                self.assertIsNone(self.state.gesture)

    def test_injected_middle_cannot_start_or_end_physical_gesture(self):
        self.assertTrue(self.state.event(mouse.WM_MBUTTONDOWN, (1, 1), injected=True))
        self.assertIsNone(self.state.gesture)
        self.down()
        self.state.event(mouse.WM_MBUTTONUP, (20, 40), injected=True)
        self.assertFalse(self.state.gesture.released)
        self.assertTrue(self.state.held)

    def test_preexisting_down_is_balanced_by_passthrough_up(self):
        self.state.preexisting_hold = True
        self.assertFalse(self.state.event(mouse.WM_MBUTTONUP, (1, 2)))
        self.assertIsNone(self.state.gesture)
        self.down()
        self.assertIsNotNone(self.state.gesture)

    def test_missing_up_timeout_cancels_and_rearms_next_down(self):
        self.down()
        with patch("gptsnip.mouse.time.monotonic", return_value=self.state.held_since + 60):
            self.state.expire()
        self.assertTrue(self.state.gesture.cancelled)
        self.assertFalse(self.state.held)
        self.state.acknowledged = 1
        self.down()
        self.assertEqual(self.state.serial, 2)

    def test_valid_hold_does_not_expire_early(self):
        self.down()
        with patch("gptsnip.mouse.time.monotonic", return_value=self.state.held_since + 59):
            self.state.expire()
        self.assertTrue(self.state.held)
        self.assertFalse(self.state.gesture.cancelled)


@unittest.skipUnless(sys.platform == "win32", "Windows hook ABI/lifecycle")
class HookTests(unittest.TestCase):
    def setUp(self):
        self.hook = mouse.MouseHook()

    def dispatch(self, message, code=0):
        data = mouse.MSLLHOOKSTRUCT(pt=mouse.wt.POINT(-40, 50))
        return self.hook._dispatch(code, message, ct.addressof(data))

    def test_middle_down_and_up_return_nonzero_without_calling_next(self):
        with patch.object(mouse.user32, "CallNextHookEx") as next_hook:
            self.assertEqual(self.dispatch(mouse.WM_MBUTTONDOWN), 1)
            self.assertEqual(self.dispatch(mouse.WM_MBUTTONUP), 1)
        next_hook.assert_not_called()
        self.assertEqual(self.hook.state.gesture.start, (-40, 50))

    def test_negative_code_and_other_events_always_call_next(self):
        with patch.object(mouse.user32, "CallNextHookEx", return_value=73) as next_hook:
            self.assertEqual(self.dispatch(mouse.WM_MBUTTONDOWN, -1), 73)
            for msg in (0x201, 0x204, 0x20A, 0x20B, 0x20C, 0x20E, mouse.WM_MOUSEMOVE):
                self.assertEqual(self.dispatch(msg), 73)
        self.assertEqual(next_hook.call_count, 8)
        self.assertIsNone(self.hook.state.gesture)

    def test_callback_exception_fails_closed_and_reports_outside_callback(self):
        with patch.object(self.hook.state, "event", side_effect=ValueError):
            self.assertEqual(self.dispatch(mouse.WM_MBUTTONDOWN), 1)
        self.assertIsNotNone(self.hook.error)
        self.assertFalse(self.hook.state.accepting)

    def run_mock_thread(self, hook_handle=123, timer=456, get_message=0):
        stack = ExitStack()
        self.addCleanup(stack.close)
        mocks = {}
        for name, value in (("PeekMessageW", 0), ("GetAsyncKeyState", 0),
                            ("SetWindowsHookExW", hook_handle), ("SetTimer", timer),
                            ("GetMessageW", get_message), ("KillTimer", 1),
                            ("UnhookWindowsHookEx", 1)):
            mocks[name] = stack.enter_context(patch.object(mouse.user32, name, return_value=value))
        self.hook._run()
        return mocks

    def test_install_pump_and_cleanup_retain_callback(self):
        callback = self.hook._callback
        calls = self.run_mock_thread()
        self.assertIsNone(self.hook.error)
        self.assertIs(self.hook._callback, callback)
        self.assertEqual(calls["SetWindowsHookExW"].call_args.args[0], 14)
        calls["UnhookWindowsHookEx"].assert_called_once_with(123)
        calls["KillTimer"].assert_called_once_with(None, 456)

    def test_install_failure_sets_ready_and_has_no_unhook(self):
        calls = self.run_mock_thread(hook_handle=0)
        self.assertIsNotNone(self.hook.error)
        self.assertTrue(self.hook._ready.is_set())
        calls["UnhookWindowsHookEx"].assert_not_called()

    def test_timer_failure_still_unhooks(self):
        calls = self.run_mock_thread(timer=0)
        self.assertIsNotNone(self.hook.error)
        calls["UnhookWindowsHookEx"].assert_called_once_with(123)

    def test_message_loop_error_still_unhooks(self):
        calls = self.run_mock_thread(get_message=-1)
        self.assertIsNotNone(self.hook.error)
        calls["UnhookWindowsHookEx"].assert_called_once_with(123)

    def test_close_posts_quit_and_joins_without_mouse_injection(self):
        self.hook._thread_id = 99
        self.hook._thread = MagicMock()
        self.hook._thread.is_alive.return_value = False
        with patch.object(mouse.user32, "PostThreadMessageW") as post:
            self.hook.close()
        post.assert_called_once_with(99, mouse.WM_QUIT, 0, 0)
        self.hook._thread.join.assert_called_once_with(2)
        self.assertFalse(self.hook.state.accepting)


@unittest.skipUnless(sys.platform == "win32", "Windows selection")
class SelectorTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.window = self.stack.enter_context(patch("gptsnip.selector.tk.Toplevel")).return_value
        self.canvas = self.stack.enter_context(patch("gptsnip.selector.tk.Canvas")).return_value
        self.stack.enter_context(patch("gptsnip.selector.win32gui.GetAncestor", return_value=77))
        self.stack.enter_context(patch("gptsnip.selector.win32gui.SetWindowPos"))
        self.foreground = self.stack.enter_context(patch("gptsnip.selector.win32gui.GetForegroundWindow", return_value=77))
        self.cursor = self.stack.enter_context(patch("gptsnip.selector.win32api.GetCursorPos", return_value=(999, 999)))
        self.complete = MagicMock()
        self.selector = Selector(MagicMock(), (-200, -200, 2000, 2000), self.complete,
                                 middle_start=(-100, -50))

    def test_middle_anchor_does_not_query_later_cursor_or_bind_left_drag(self):
        self.assertEqual(self.selector.start, (-100, -50))
        self.cursor.assert_not_called()
        self.canvas.bind.assert_not_called()

    def test_drag_renders_normalized_rectangle_relative_to_negative_origin(self):
        self.selector.move_to((-150, -150))
        self.canvas.coords.assert_called_once_with(self.selector.rectangle, 50, 50, 100, 150)

    def test_middle_release_completes_without_extra_click(self):
        self.selector.middle_release((-50, 0))
        self.complete.assert_called_once_with((-100, -50, -50, 0))
        self.window.destroy.assert_called_once()

    def test_reverse_drag_in_all_directions(self):
        for point, box in (((-120, -80), (-120, -80, -100, -50)),
                           ((-80, -80), (-100, -80, -80, -50)),
                           ((-120, -20), (-120, -50, -100, -20)),
                           ((-80, -20), (-100, -50, -80, -20))):
            self.assertEqual(self.selector.middle_box(point), box)

    def test_both_dimensions_must_reach_six_physical_pixels(self):
        for point in ((-100, -50), (-99, -49), (-95, 100), (100, -45)):
            self.assertIsNone(self.selector.middle_box(point))
        self.assertEqual(self.selector.middle_box((-94, -44)), (-100, -50, -94, -44))

    def test_returning_to_anchor_clears_old_rectangle(self):
        self.selector.move_to((-50, 0))
        self.selector.move_to((-100, -50))
        self.assertEqual(self.canvas.coords.call_args.args[1:], (0, 0, 0, 0))

    def test_escape_finishes_once_and_later_release_does_nothing(self):
        escape = next(call.args[1] for call in self.window.bind.call_args_list if call.args[0] == "<Escape>")
        escape(None)
        self.selector.middle_release((100, 100))
        self.complete.assert_called_once_with(None)

        self.assertEqual(self.selector.cancel_reason, "Escape")

    def test_lost_focus_on_release_cancels(self):
        self.foreground.return_value = 999
        self.selector.middle_release((100, 100))
        self.complete.assert_called_once_with(None)
        self.assertEqual(self.selector.cancel_reason,
                         "foreground differs from selector: middle release check")

    def test_focus_out_reason_identifies_deferred_check(self):
        self.foreground.return_value = 999
        self.selector.check_focus("Tk FocusOut idle check")
        self.assertEqual(self.selector.cancel_reason,
                         "foreground differs from selector: Tk FocusOut idle check")
        self.complete.assert_called_once_with(None)

    def test_focus_mismatch_trace_retains_exact_compared_handles_before_destroy(self):
        events = []
        self.selector.diagnostic = lambda event, **fields: events.append(
            (event, fields, self.selector.closed))
        self.foreground.return_value = 999
        self.selector.check_focus()
        self.assertEqual(events[0][1]["compared_foreground"], 999)
        self.assertEqual(events[0][1]["expected_foreground"], 77)
        self.assertFalse(events[1][2])
        self.assertEqual(events[1][1]["reason"],
                         "foreground differs from selector: periodic mouse health check")

    def test_observed_ownership_is_sticky_and_never_reacquired_after_loss(self):
        self.foreground.return_value = 999
        with patch("gptsnip.selector.acquire_selector_foreground") as acquire:
            self.selector.observe_foreground_ownership()
            self.selector.establish_foreground()
            self.selector.check_focus()
        self.assertTrue(self.selector.foreground_established)
        acquire.assert_not_called()
        self.complete.assert_called_once_with(None)

    def test_keyboard_selector_retains_left_button_bindings_and_cursor(self):
        self.canvas.reset_mock()
        selector = Selector(MagicMock(), (0, 0, 2000, 2000), self.complete)
        self.assertEqual([call.args[0] for call in self.canvas.bind.call_args_list],
                         ["<ButtonPress-1>", "<B1-Motion>", "<ButtonRelease-1>"])
        selector.press(None)
        self.cursor.return_value = (1000, 1000)  # Original keyboard path permits 1px.
        selector.release(None)
        self.complete.assert_called_once_with((999, 999, 1000, 1000))


@unittest.skipUnless(sys.platform == "win32", "Windows mouse capture flow")
class MouseFlowTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = MagicMock()
        self.reader = FakeReader()
        self.app = App(self.root, self.reader)
        self.app.notice = MagicMock()
        self.app.mouse_hook = MagicMock(state=mouse.MouseState(), error=None)
        self.state = self.app.mouse_hook.state
        self.window = self.mock("gptsnip.selector.tk.Toplevel").return_value
        self.canvas = self.mock("gptsnip.selector.tk.Canvas").return_value
        self.mock("gptsnip.selector.win32gui.GetAncestor", return_value=77)
        self.mock("gptsnip.selector.win32gui.SetWindowPos")
        self.foreground = self.mock("gptsnip.app.win32gui.GetForegroundWindow", return_value=77)
        self.mock("gptsnip.selector.win32api.GetCursorPos", return_value=(0, 0))
        self.bounds = self.mock("gptsnip.app.native.desktop_bounds", return_value=(0, 0, 100, 100))
        self.windows = self.mock("gptsnip.app.native.list_windows", return_value=[])
        self.inspect = self.mock("gptsnip.app.native.inspect_window", return_value=None)
        self.mock("gptsnip.app.native.dwmapi.DwmFlush", return_value=0)
        self.grab = self.mock("gptsnip.app.ImageGrab.grab")
        self.grab.return_value.__enter__.return_value.size = (20, 30)
        self.copy = self.mock("gptsnip.app.native.copy_image", return_value=99)
        self.mock("gptsnip.app.native.keys_down", return_value=False)
        self.focus = self.mock("gptsnip.app.native.request_foreground")
        self.mock("gptsnip.app.native.win32clipboard.GetClipboardSequenceNumber", return_value=99)
        self.send = self.mock("gptsnip.app.native.user32.SendInput", return_value=4)

    def mock(self, name, **kwargs):
        return self.stack.enter_context(patch(name, **kwargs))

    def down(self):
        self.state.event(mouse.WM_MBUTTONDOWN, (10, 20))
        self.app.poll_mouse()

    def up(self, point=(30, 50)):
        self.state.event(mouse.WM_MBUTTONUP, point)
        self.app.poll_mouse()

    def run_capture(self):
        captures = [call.args[1] for call in self.root.after.call_args_list if call.args[0] == 120]
        self.assertEqual(len(captures), 1)
        captures[0]()

    def assert_no_output(self):
        self.grab.assert_not_called()
        self.copy.assert_not_called()
        self.focus.assert_not_called()
        self.send.assert_not_called()
        self.assertFalse(any(call.args[0] == 120 for call in self.root.after.call_args_list))

    def chrome(self):
        self.target = Window(10, 1, "chrome.exe", "Conversation - Google Chrome")
        self.snapshot = DocumentSnapshot(self.target, 1.0, 8, (110, 8, 1, 10))
        self.app.remembered = self.target
        self.app.chrome_memory = self.snapshot
        self.windows.return_value = [self.target]
        self.inspect.return_value = self.target
        self.mock("gptsnip.app.native_document.is_current", return_value=True)

    def deliver(self, host="chatgpt.com"):
        token, _ = self.reader.pending
        self.reader.reply = token, DocumentResult("verified", host, self.snapshot,
                                                  mouse.time.monotonic(), "")
        self.app.poll_identity()

    def test_down_starts_overlay_at_anchor_move_updates_release_schedules_same_capture(self):
        self.down()
        self.assertTrue(self.app.busy)
        self.assertEqual(self.app.selector.start, (10, 20))
        self.state.event(mouse.WM_MOUSEMOVE, (20, 40))
        self.app.poll_mouse()
        self.assertEqual(self.canvas.coords.call_args.args[1:], (10, 20, 20, 40))
        self.up()
        self.assertIsNone(self.app.selector)
        self.window.destroy.assert_called_once()
        self.run_capture()
        self.grab.assert_called_once_with(bbox=(10, 20, 30, 50), all_screens=True)
        self.copy.assert_called_once()

    def test_fresh_chrome_drag_acquires_foreground_when_tk_only_sets_local_focus(self):
        # Replay A: Chrome is foreground throughout all Tk setup calls. Neither
        # a console HWND nor prior console focus is provided to the acquisition.
        self.chrome()
        self.foreground.return_value = self.target.hwnd
        def acquire(hwnd, source):
            self.assertEqual((hwnd, source), (77, self.target.hwnd))
            self.foreground.return_value = hwnd
            return True
        native_acquire = self.mock("gptsnip.selector.acquire_selector_foreground", side_effect=acquire)
        self.down()
        self.assertTrue(self.app.selector.foreground_established)
        native_acquire.assert_called_once_with(77, self.target.hwnd)
        self.deliver()
        self.up()
        self.run_capture()
        self.deliver()
        self.foreground.return_value = self.target.hwnd
        self.app.wait_focus()
        self.deliver()
        self.assertEqual(len(self.reader.calls), 3)
        self.copy.assert_called_once()
        count, events, _ = self.send.call_args.args
        self.assertEqual(count, 4)
        self.assertEqual([(event.ki.wVk, event.ki.dwFlags) for event in events],
                         [(0x11, 0), (0x56, 0), (0x56, 2), (0x11, 2)])

    def test_failed_foreground_acquisition_cancels_without_capture_or_target_resolution(self):
        self.foreground.return_value = 999
        acquire = self.mock("gptsnip.selector.acquire_selector_foreground", return_value=False)
        self.down()
        acquire.assert_called_once_with(77, 999)
        self.app.notice.assert_any_call(
            "Middle-mouse capture cancelled: selector foreground not acquired: selector activation check.")
        self.assertIsNone(self.app.selector)
        self.assertFalse(self.app.busy)
        self.windows.assert_not_called()
        self.up()
        self.assert_no_output()

    def test_source_switch_during_overlay_setup_cancels_without_acquisition(self):
        self.foreground.return_value = 999
        self.window.focus_force.side_effect = lambda: setattr(self.foreground, "return_value", 1000)
        acquire = self.mock("gptsnip.selector.acquire_selector_foreground")
        self.down()
        acquire.assert_not_called()
        self.assertIsNone(self.app.selector)
        self.assertFalse(self.app.busy)
        self.assert_no_output()

    def test_foreground_loss_after_fallback_acquisition_cancels_without_retry(self):
        self.foreground.return_value = 999
        acquire = self.mock("gptsnip.selector.acquire_selector_foreground",
                            side_effect=lambda *_: setattr(self.foreground, "return_value", 77))
        self.down()
        self.foreground.return_value = 999
        self.app.next_mouse_health = 0
        self.app.poll_mouse()
        acquire.assert_called_once()
        self.assertIsNone(self.app.selector)
        self.assert_no_output()

    def test_simple_middle_click_does_not_capture_copy_or_paste(self):
        self.down()
        self.up((10, 20))
        self.assert_no_output()
        self.assertFalse(self.app.busy)

    def test_tiny_drag_does_not_capture_copy_or_paste(self):
        self.down()
        self.up((15, 90))
        self.assert_no_output()
        self.app.notice.assert_any_call(
            "Middle-mouse capture cancelled: drag below threshold (6 pixels per dimension).")

    def test_escape_cancels_while_held_and_next_physical_gesture_works(self):
        self.down()
        escape = next(call.args[1] for call in self.window.bind.call_args_list if call.args[0] == "<Escape>")
        escape(None)
        self.up()
        self.assert_no_output()
        self.assertFalse(self.app.busy)
        self.down()
        self.up()
        self.run_capture()
        self.copy.assert_called_once()

    def test_duplicate_down_and_direct_keyboard_start_cannot_start_twice(self):
        self.down()
        first = self.app.selector
        generation = self.app.generation
        self.down()
        self.app.begin_capture()
        self.assertIs(self.app.selector, first)
        self.assertEqual(self.app.generation, generation)

    def test_keyboard_hotkey_still_starts_original_selector(self):
        self.app.actions.append(1)
        self.app.tick()
        self.assertIsNone(self.app.selector.start)
        self.assertFalse(self.app.selector.middle)
        self.assertEqual(self.canvas.bind.call_count, 3)

    def test_middle_cannot_corrupt_keyboard_capture(self):
        self.app.begin_capture()
        keyboard = self.app.selector
        self.down()
        self.up()
        self.assertIs(self.app.selector, keyboard)
        self.assertIsNone(self.app.middle_id)
        self.assert_no_output()

    def test_pending_middle_snapshot_is_ignored_if_keyboard_already_busy(self):
        self.state.event(mouse.WM_MBUTTONDOWN, (10, 20))
        self.app.begin_capture()
        self.app.poll_mouse()
        self.assertEqual(self.state.acknowledged, 1)
        self.assertFalse(self.app.selector.middle)

    def test_fast_release_before_first_ui_tick_retains_both_corners(self):
        self.state.event(mouse.WM_MBUTTONDOWN, (10, 20))
        self.state.event(mouse.WM_MBUTTONUP, (30, 50))
        self.app.poll_mouse()
        self.run_capture()
        self.grab.assert_called_once_with(bbox=(10, 20, 30, 50), all_screens=True)

    def test_stationary_hold_timeout_cancels_and_release_has_no_output(self):
        self.down()
        with patch("gptsnip.mouse.time.monotonic", return_value=self.state.held_since + 60):
            self.state.expire()
        self.app.poll_mouse()
        self.up()
        self.assert_no_output()
        self.assertFalse(self.app.busy)
        self.app.notice.assert_any_call(
            "Middle-mouse capture cancelled: 60-second hold limit or missing release.")

    def test_display_change_cancels_without_clipboard_write(self):
        self.down()
        self.bounds.return_value = (-100, 0, 100, 100)
        self.up()
        self.assert_no_output()
        self.app.notice.assert_any_call(
            "Middle-mouse capture cancelled: display layout changed: gesture sample.")

    def test_focus_loss_cancels_and_late_release_is_ignored(self):
        self.down()
        self.foreground.return_value = 999
        self.app.next_mouse_health = 0
        self.app.poll_mouse()
        self.up()
        self.assert_no_output()
        self.app.notice.assert_any_call(
            "Middle-mouse capture cancelled: foreground differs from selector: periodic mouse health check.")

    def test_hook_install_failure_reports_and_keyboard_remains_usable(self):
        self.app.mouse_hook = None
        with patch("gptsnip.app.MouseHook") as hook:
            hook.return_value.start.side_effect = OSError("install failed")
            self.app.start_mouse()
            hook.return_value.close.assert_called_once()
        self.assertIsNone(self.app.mouse_hook)
        self.assertIn("keyboard capture remains active", self.app.notice.call_args.args[0])
        self.app.begin_capture()
        self.assertFalse(self.app.selector.middle)

    def test_runtime_hook_error_cancels_mouse_but_keeps_keyboard_available(self):
        self.down()
        hook = self.app.mouse_hook
        hook.error = "callback failed"
        self.app.poll_mouse()
        hook.close.assert_called_once()
        self.assert_no_output()
        self.app.notice.assert_any_call("Middle-mouse capture cancelled: mouse hook runtime error.")
        self.app.begin_capture()
        self.assertFalse(self.app.selector.middle)

    def test_hook_constructor_failure_keeps_keyboard_capture_available(self):
        self.app.mouse_hook = None
        with patch("gptsnip.app.MouseHook", side_effect=OSError("callback unavailable")):
            self.app.start_mouse()
        self.app.begin_capture()
        self.assertFalse(self.app.selector.middle)
        self.assertIsNone(self.app.mouse_hook)

    def test_shutdown_during_drag_unhooks_and_late_release_cannot_capture(self):
        self.down()
        hook = self.app.mouse_hook
        self.app.stop()
        hook.close.assert_called_once()
        self.up()
        self.assert_no_output()
        self.root.quit.assert_called_once()

    def test_close_without_stop_cleans_hook_and_selector(self):
        self.down()
        self.app.close()
        self.app.mouse_hook.close.assert_called_once()
        self.window.destroy.assert_called_once()
        self.assert_no_output()

    def test_overlay_construction_failure_resets_mouse_admission(self):
        with patch("gptsnip.app.Selector", side_effect=RuntimeError("overlay failed")):
            self.state.event(mouse.WM_MBUTTONDOWN, (10, 20))
            self.app.tick()
        self.assertIsNone(self.app.middle_id)
        self.assertFalse(self.app.busy)
        self.assert_no_output()

    def test_mouse_success_uses_all_three_fresh_chrome_checks_and_only_ctrl_v(self):
        self.chrome()
        self.down()
        self.assertIsNotNone(self.app.selector)  # Shown BEFORE first verification reply.
        self.deliver()
        self.up()
        self.run_capture()
        self.copy.assert_called_once()
        self.focus.assert_not_called()
        self.deliver()  # Second check, before activation.
        self.focus.assert_called_once_with(self.target)
        self.foreground.return_value = self.target.hwnd
        self.app.wait_focus()
        self.send.assert_not_called()
        self.deliver()  # Third check, immediately before Ctrl+V.
        self.assertEqual(len(self.reader.calls), 3)
        count, events, _ = self.send.call_args.args
        self.assertEqual(count, 4)
        self.assertEqual([(event.type, event.ki.wVk, event.ki.dwFlags) for event in events],
                         [(1, 0x11, 0), (1, 0x56, 0), (1, 0x56, 2), (1, 0x11, 2)])

    def test_release_before_first_chrome_reply_waits_without_losing_selection(self):
        self.chrome()
        self.down()
        self.up()
        self.assertIsNone(self.app.selector)
        self.assert_no_output()
        self.deliver()
        self.run_capture()
        self.copy.assert_called_once()

    def test_escape_during_first_chrome_check_cannot_reopen_overlay_or_capture(self):
        self.chrome()
        self.down()
        self.app.selector.finish(None)
        self.up()
        self.deliver()
        self.assertIsNone(self.app.selector)
        self.assert_no_output()

    def test_changed_chrome_target_keeps_middle_capture_on_clipboard(self):
        self.chrome()
        self.down()
        self.up()
        self.deliver("github.com")
        self.run_capture()
        self.copy.assert_called_once()
        self.focus.assert_not_called()
        self.send.assert_not_called()

    def test_previously_invalidated_chrome_memory_stays_clipboard_only(self):
        self.chrome()
        self.app.memory_blocked = True
        self.down()
        self.up()
        self.run_capture()
        self.assertEqual(len(self.reader.calls), 0)
        self.copy.assert_called_once()
        self.focus.assert_not_called()
        self.send.assert_not_called()

    def test_failed_second_chrome_check_blocks_mouse_capture_activation(self):
        self.chrome()
        self.down()
        self.deliver()
        self.up()
        self.run_capture()
        self.deliver("github.com")
        self.copy.assert_called_once()
        self.focus.assert_not_called()
        self.send.assert_not_called()

    def test_failed_third_chrome_check_blocks_mouse_capture_paste(self):
        self.chrome()
        self.down()
        self.deliver()
        self.up()
        self.run_capture()
        self.deliver()
        self.foreground.return_value = self.target.hwnd
        self.app.wait_focus()
        self.deliver("github.com")
        self.copy.assert_called_once()
        self.send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
