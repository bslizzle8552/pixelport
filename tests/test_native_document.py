"""Native document boundary with controlled Win32/COM states; no actual COM calls."""
from contextlib import ExitStack
from datetime import datetime, timezone
import sys
import unittest
from unittest.mock import MagicMock, patch

if sys.platform == 'win32':
    from gptsnip import native_document as doc
    from gptsnip.browser import DocumentResult
    from gptsnip.core import Window


@unittest.skipUnless(sys.platform == 'win32', 'Windows native metadata')
class DocumentTests(unittest.TestCase):
    def setUp(self):
        self.window = Window(10, 1, 'chrome.exe', 'Easier Screenshot Sharing - Google Chrome')
        self.snapshot = doc.DocumentSnapshot(self.window, 1.0, 8, (100, 8, 1, 10))
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.snap = self.stack.enter_context(patch.object(doc, 'snapshot_window', return_value=self.snapshot))
        self.root = self.stack.enter_context(patch.object(doc, '_root_dispatch', return_value=object()))
        self.values = {'accRole': 15, 'accState': 0, 'accValue': 'https://chatgpt.com/c/private-example'}
        self.prop = self.stack.enter_context(patch.object(doc, '_property', side_effect=lambda _, key: self.values[key]))

    def test_unique_document_returns_only_host_and_identity(self):
        result = doc.read_once(self.window)
        self.assertTrue(result.eligible)
        self.assertEqual(result.snapshot, self.snapshot)
        self.assertNotIn('private-example', repr(result))
        self.assertEqual([c.args[1] for c in self.prop.call_args_list], ['accRole', 'accState', 'accValue'])

    def test_zero_multiple_or_stale_candidates_never_call_com(self):
        self.snap.return_value = None
        self.assertFalse(doc.read_once(self.window).eligible)
        self.root.assert_not_called()

    def test_wrong_role_and_unavailable_states_reject_without_reading_value(self):
        for role, flags in ((42, 0), (15, 1), (15, 0x800), (15, 0x8000), (15, 0x10000)):
            with self.subTest(role=role, flags=flags):
                self.values.update(accRole=role, accState=flags)
                self.prop.reset_mock()
                self.assertFalse(doc.read_once(self.window).eligible)
                self.assertNotIn('accValue', [c.args[1] for c in self.prop.call_args_list])

    def test_inaccessible_com_object_fails_closed_without_exception_text(self):
        self.root.side_effect = RuntimeError('https://chatgpt.com/c/private-example')
        result = doc.read_once(self.window)
        self.assertFalse(result.eligible)
        self.assertNotIn('private-example', repr(result))

    def test_renderer_changes_during_read_discard_hostname(self):
        self.snap.side_effect = [self.snapshot, None]
        result = doc.read_once(self.window)
        self.assertEqual(result.reason, 'identity_changed_during_read')
        self.assertIsNone(result.host)

    def test_missing_or_invalid_document_value_is_unknown(self):
        for value in ('', None, 'http://chatgpt.com', 'https://user@chatgpt.com'):
            self.values['accValue'] = value
            self.assertEqual(doc.read_once(self.window).status, 'unknown')

    def test_active_github_is_not_eligible_even_with_chatgpt_background(self):
        self.values['accValue'] = 'https://github.com/example'
        result = doc.read_once(self.window)
        self.assertEqual(result.status, 'verified')
        self.assertEqual(result.host, 'github.com')
        self.assertFalse(result.eligible)

    def test_two_reads_must_agree_on_host_and_renderer(self):
        a = DocumentResult('verified', 'chatgpt.com', self.snapshot, 10, '')
        other = doc.DocumentSnapshot(self.window, 1, 8, (200, 8, 1, 10))
        for b in (DocumentResult(), DocumentResult('verified', 'github.com', self.snapshot, 11, ''),
                  DocumentResult('verified', 'chatgpt.com', other, 11, '')):
            with patch.object(doc, 'read_once', side_effect=[a, b]), patch.object(doc.time, 'sleep'):
                self.assertFalse(doc.read_stable(self.window).eligible)
        with patch.object(doc, 'read_once', side_effect=[a, a]), patch.object(doc.time, 'sleep'):
            self.assertTrue(doc.read_stable(self.window).eligible)


@unittest.skipUnless(sys.platform == 'win32', 'Windows native metadata')
class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.window = Window(10, 1, 'chrome.exe', 'Any title')
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        def mock(name, **kwargs):
            return self.stack.enter_context(patch('gptsnip.native_document.' + name, **kwargs))
        self.inspect = mock('native.inspect_window', return_value=self.window)
        self.iconic = mock('win32gui.IsIconic', return_value=False)
        self.ancestor = mock('win32gui.GetAncestor', return_value=10)
        mock('win32process.GetWindowThreadProcessId', return_value=(8, 1))
        mock('win32api.OpenProcess', return_value=MagicMock())
        mock('win32process.GetProcessTimes', return_value={'CreationTime': datetime(2026, 1, 1, tzinfo=timezone.utc)})
        mock('win32gui.GetClassName', return_value='Chrome_RenderWidgetHostHWND')
        self.visible = mock('win32gui.IsWindowVisible', return_value=True)
        self.children = [100]
        mock('win32gui.EnumChildWindows', side_effect=lambda hwnd, fn, arg: [fn(h, arg) for h in self.children])

    def test_unique_visible_renderer_is_bound_to_exact_window_process(self):
        result = doc.snapshot_window(self.window)
        self.assertEqual(result.renderer, (100, 8, 1, 10))
        self.assertEqual(result.window, self.window)

    def test_zero_or_multiple_visible_renderers_are_rejected(self):
        for children in ([], [100, 200]):
            self.children = children
            self.assertIsNone(doc.snapshot_window(self.window))

    def test_hidden_background_renderer_does_not_compete(self):
        self.children = [100, 200]
        self.visible.side_effect = lambda hwnd: hwnd == 100
        self.assertEqual(doc.snapshot_window(self.window).renderer[0], 100)

    def test_renderer_from_other_top_level_window_is_not_used(self):
        self.ancestor.side_effect = lambda hwnd, _: 10 if hwnd == 10 else 20
        self.assertIsNone(doc.snapshot_window(self.window))

    def test_minimized_closed_changed_window_and_desktop_are_rejected(self):
        self.iconic.return_value = True
        self.assertIsNone(doc.snapshot_window(self.window))
        self.iconic.return_value = False
        for current in (None, Window(10, 2, 'chrome.exe', 'Any title'),
                        Window(10, 1, 'chrome.exe', 'Changed title')):
            self.inspect.return_value = current
            self.assertIsNone(doc.snapshot_window(self.window))
        self.assertIsNone(doc.snapshot_window(Window(10, 1, 'ChatGPT.exe', 'ChatGPT')))


if __name__ == '__main__':
    unittest.main()
