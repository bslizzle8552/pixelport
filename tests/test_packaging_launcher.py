"""Packaging launcher boundaries; never starts native UI or a worker."""

from pathlib import Path
import runpy
import unittest
from unittest.mock import MagicMock, patch

from gptsnip import __main__ as entry

LAUNCHER = Path(__file__).resolve().parents[1] / "packaging/launcher.py"


class LauncherTests(unittest.TestCase):
    def test_worker_diverts_before_any_application_start(self):
        with patch("multiprocessing.freeze_support", side_effect=SystemExit(0)) as divert, \
                patch.object(entry, "main") as main:
            with self.assertRaises(SystemExit) as stopped:
                runpy.run_path(str(LAUNCHER), run_name="__main__")
        self.assertEqual(stopped.exception.code, 0)
        divert.assert_called_once_with()
        main.assert_not_called()

    def test_normal_launch_calls_freeze_support_before_main(self):
        events = []
        with patch("multiprocessing.freeze_support", side_effect=lambda: events.append("freeze")), \
                patch.object(entry, "main", side_effect=lambda: events.append("main") or 0), \
                patch("builtins.input") as pause:
            with self.assertRaises(SystemExit) as stopped:
                runpy.run_path(str(LAUNCHER), run_name="__main__")
        self.assertEqual(stopped.exception.code, 0)
        self.assertEqual(events, ["freeze", "main"])
        pause.assert_not_called()

    def test_interactive_failure_remains_readable_after_app_returns(self):
        with patch("multiprocessing.freeze_support"), patch.object(entry, "main", return_value=1), \
                patch("sys.stdin", MagicMock(isatty=lambda: True)), patch("builtins.input") as pause:
            with self.assertRaises(SystemExit) as stopped:
                runpy.run_path(str(LAUNCHER), run_name="__main__")
        self.assertEqual(stopped.exception.code, 1)
        pause.assert_called_once()

    def test_redirected_startup_exception_reports_and_exits_without_waiting(self):
        with patch("multiprocessing.freeze_support"), \
                patch.object(entry, "main", side_effect=ImportError("test dependency")), \
                patch("sys.stdin", MagicMock(isatty=lambda: False)), \
                patch("traceback.print_exc") as report, patch("builtins.input") as pause:
            with self.assertRaises(SystemExit) as stopped:
                runpy.run_path(str(LAUNCHER), run_name="__main__")
        self.assertEqual(stopped.exception.code, 1)
        report.assert_called_once()
        pause.assert_not_called()
