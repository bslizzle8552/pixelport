"""Diagnostics must preserve decisions, redact content, and bound output."""

from contextlib import ExitStack
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

if sys.platform == "win32":
    from gptsnip import middle_diagnostics as diagnostics
    from gptsnip.app import App
    from gptsnip.core import Window
    from gptsnip.native_document import DocumentSnapshot


@unittest.skipUnless(sys.platform == "win32", "Win32 focus diagnostics")
class DiagnosticTests(unittest.TestCase):
    def enabled_trace(self):
        with patch.dict("os.environ", GPTSNIP_MIDDLE_DIAGNOSTICS="1"):
            return diagnostics.MiddleDiagnostics()

    def test_disabled_trace_does_no_native_reads_or_output(self):
        with patch.dict("os.environ", GPTSNIP_MIDDLE_DIAGNOSTICS="0"):
            trace = diagnostics.MiddleDiagnostics()
        with patch.object(trace, "snapshot") as snapshot, \
                patch.object(diagnostics.win32gui, "GetForegroundWindow") as foreground, \
                patch("builtins.print") as output:
            trace.emit(None, "test")
            trace.poll(None)
        snapshot.assert_not_called()
        foreground.assert_not_called()
        output.assert_not_called()

    def test_unavailable_state_cannot_raise_into_capture_flow(self):
        trace = self.enabled_trace()
        with patch.object(trace, "snapshot", side_effect=OSError("unavailable")), \
                patch.object(diagnostics.win32gui, "GetForegroundWindow", return_value=42):
            trace.emit(None, "test")
            trace.poll(None)

    def test_output_and_native_sampling_stop_at_limit(self):
        trace = self.enabled_trace()
        trace.LIMIT = 3
        with patch.object(trace, "snapshot", return_value={}) as snapshot, \
                patch("builtins.print") as output:
            for _ in range(10):
                trace.emit(None, "test")
            trace.poll(None)
        self.assertEqual(snapshot.call_count, 3)
        self.assertEqual(output.call_count, 4)  # Three records and one limit notice.

    def test_direct_file_retains_all_records_even_when_console_output_fails(self):
        trace = self.enabled_trace()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "middle.jsonl"
            trace.file_path = str(path)
            with patch.object(trace, "snapshot", return_value={"generation": 1}), \
                    patch("builtins.print", side_effect=OSError("console unavailable")):
                trace.emit(None, "startup ready")
                trace.emit(None, "selector foreground mismatch", compared_foreground=42,
                           expected_foreground=77)
                trace.emit(None, "Ctrl+V issued")
            records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([record["event"] for record in records],
                         ["startup ready", "selector foreground mismatch", "Ctrl+V issued"])
        self.assertEqual(records[1]["compared_foreground"], 42)
        self.assertEqual(records[1]["expected_foreground"], 77)

    def test_direct_file_appends_without_overwriting_evidence_and_is_bounded(self):
        trace = self.enabled_trace()
        trace.LIMIT = 2
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "middle.jsonl"
            path.write_text('{"event":"previous evidence"}\n', encoding="utf-8")
            trace.file_path = str(path)
            with patch.object(trace, "snapshot", return_value={}), patch("builtins.print"):
                for _ in range(5):
                    trace.emit(None, "new record")
            records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([record["event"] for record in records],
                         ["previous evidence", "new record", "new record",
                          "trace limit reached; relaunch for more"])

    def test_unwritable_file_warns_once_and_falls_back_to_console(self):
        trace = self.enabled_trace()
        trace.file_path = "unavailable.jsonl"
        with patch("builtins.open", side_effect=PermissionError), \
                patch("builtins.print") as output:
            trace.write("first")
            trace.write("second")
        lines = [call.args[0] for call in output.call_args_list]
        self.assertEqual(sum("file recording failed" in line for line in lines), 1)
        self.assertTrue(any('"event":"first"' in line for line in lines))
        self.assertTrue(any('"event":"second"' in line for line in lines))

    def test_disabled_trace_does_not_create_configured_file(self):
        with patch.dict("os.environ", GPTSNIP_MIDDLE_DIAGNOSTICS="0",
                        GPTSNIP_MIDDLE_DIAGNOSTIC_FILE="unused.jsonl"):
            trace = diagnostics.MiddleDiagnostics()
        with patch("builtins.open") as opened:
            trace.emit(None, "test")
            trace.poll(None)
        opened.assert_not_called()

    def test_foreground_transition_carries_last_sample_before_click(self):
        trace = self.enabled_trace()
        initial = {"ms": 0, "foreground": {"hwnd": 1}}
        before = {"ms": 260, "foreground": {"hwnd": 1}, "generation": 2}
        after = {"ms": 280, "foreground": {"hwnd": 2}, "generation": 2}
        with patch.object(diagnostics.time, "monotonic", side_effect=[0, .26, .28]), \
                patch.object(diagnostics.win32gui, "GetForegroundWindow", side_effect=[1, 1, 2]), \
                patch.object(trace, "snapshot", side_effect=[initial, before, after]), \
                patch.object(trace, "write") as output:
            for _ in range(3):
                trace.poll(None)
        self.assertEqual(output.call_count, 2)
        self.assertEqual(output.call_args.kwargs, {"previous": before, "state": after})

    def test_snapshot_uses_allowlisted_identity_without_title_or_document_repr(self):
        app = App(MagicMock(), reader=MagicMock())
        window = Window(10, 20, "chrome.exe", "PRIVATE TITLE AND CONVERSATION")
        app.remembered = app.bound = app.target = window
        document = DocumentSnapshot(window, 1.0, 8, (110, 8, 20, 10))
        app.chrome_memory = app.target_document = document
        app.identity_pending = (1, "required", window, 3, document, None)
        app.verification = (window, document, None, 3, 1000)
        with ExitStack() as stack:
            stack.enter_context(patch.object(diagnostics, "window_state", return_value={"hwnd": 10}))
            stack.enter_context(patch.object(diagnostics, "gui_state", return_value={}))
            stack.enter_context(patch.object(diagnostics.win32gui, "GetForegroundWindow", return_value=10))
            title_read = stack.enter_context(patch.object(diagnostics.win32gui, "GetWindowText"))
            stack.enter_context(patch.object(diagnostics.kernel32, "GetConsoleWindow", return_value=0))
            stack.enter_context(patch.object(diagnostics.kernel32, "GetCurrentThreadId", return_value=5))
            stack.enter_context(patch.object(diagnostics.user32, "GetAsyncKeyState", return_value=0))
            stack.enter_context(patch.object(diagnostics.native, "desktop_bounds", return_value=(0, 0, 100, 100)))
            app.root.winfo_id.return_value = 7
            app.root.state.return_value = "withdrawn"
            app.root.focus_get.return_value = None
            app.root.grab_current.return_value = None
            value = self.enabled_trace().snapshot(app)
        text = json.dumps(value)
        self.assertNotIn("PRIVATE", text)
        self.assertNotIn("DocumentSnapshot", text)
        self.assertEqual(value["remembered"], {"hwnd": 10, "pid": 20, "process": "chrome.exe"})
        self.assertTrue(value["chrome_memory_present"])
        title_read.assert_not_called()


if __name__ == "__main__":
    unittest.main()
