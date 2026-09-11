"""URL decisions and real bounded child-process transport; no desktop effects."""
import multiprocessing as mp
import time
import unittest
from unittest.mock import patch

from gptsnip.browser import BrowserReader, DocumentResult, document_hostname, is_chatgpt_url, identity_diagnostic


def echo_worker(connection):
    while True:
        token, window, _ = connection.recv()
        connection.send((token, DocumentResult('verified', 'chatgpt.com', window, time.monotonic(), '')))


def hung_worker(connection):
    connection.recv()
    time.sleep(30)


def slow_fresh_worker(connection):
    # Warm the real transport first, so this regression measures the request
    # budget independently of variable source interpreter startup on the host.
    token, window, _ = connection.recv()
    connection.send((token, DocumentResult('verified', 'chatgpt.com', window, time.monotonic(), '')))
    token, window, _ = connection.recv()
    time.sleep(1.05)
    connection.send((token, DocumentResult('verified', 'chatgpt.com', window, time.monotonic(), '')))
    time.sleep(30)


def stale_worker(connection):
    token, window, _ = connection.recv()
    connection.send((token, DocumentResult('verified', 'chatgpt.com', window, time.monotonic() - 2, '')))
    time.sleep(30)


def wrong_token_worker(connection):
    token, window, _ = connection.recv()
    connection.send((token - 1, DocumentResult('verified', 'chatgpt.com', window, time.monotonic(), '')))
    time.sleep(30)


class URLTests(unittest.TestCase):
    def test_exact_https_origin_and_paths(self):
        for url in ('https://chatgpt.com', 'https://chatgpt.com/',
                    'https://chatgpt.com/c/example?x=1#fragment',
                    'HTTPS://CHATGPT.COM:443/c/example', 'https://chatgpt.com/a%20b'):
            with self.subTest(url=url):
                self.assertTrue(is_chatgpt_url(url))
                self.assertEqual(document_hostname(url), 'chatgpt.com')

    def test_reject_lookalikes_credentials_schemes_ports_and_malformed_values(self):
        for url in ('http://chatgpt.com', 'https://fakechatgpt.com',
                    'https://chatgpt.com.example.com', 'https://chatgpt-example.com',
                    'https://www.chatgpt.com', 'https://chatgpt.com.',
                    'https://user:password@chatgpt.com', 'https://@chatgpt.com',
                    'https://chatgpt.com@evil.example', 'https://evil.example@chatgpt.com',
                    'https://chatgpt.com\\@evil.example', 'https://chatgpt.com:444',
                    'https://chatgpt.com:', 'https://chatgpt.com:bad',
                    'https://chatgpt.com:99999', 'https://[chatgpt.com',
                    'https://chatgpt%2ecom', 'https://chаtgpt.com',
                    ' https://chatgpt.com', 'https://chatgpt.com\n',
                    'https://chatgpt.com/a b', 'https://chatgpt.com/%xy',
                    'javascript:https://chatgpt.com', 'file://chatgpt.com',
                    'https:chatgpt.com', '//chatgpt.com', '', None, 1):
            with self.subTest(url=url):
                self.assertFalse(is_chatgpt_url(url))

    def test_github_is_verified_as_a_different_hostname(self):
        self.assertEqual(document_hostname('https://github.com/example'), 'github.com')
        self.assertFalse(is_chatgpt_url('https://github.com/example'))


class DiagnosticTests(unittest.TestCase):
    def test_trace_is_opt_in_and_stops_after_twelve_requests(self):
        with patch.dict('os.environ', {'GPTSNIP_IDENTITY_DIAGNOSTICS': '0'}), patch('builtins.print') as output:
            identity_diagnostic('request admitted', 1)
            output.assert_not_called()
        with patch.dict('os.environ', {'GPTSNIP_IDENTITY_DIAGNOSTICS': '1'}), patch('builtins.print') as output:
            for token in range(1, 100):
                identity_diagnostic('request admitted', token)
            self.assertEqual(output.call_count, 12)


class WorkerTests(unittest.TestCase):
    def frozen_reader(self, worker):
        # Only constructor policy is frozen; the test's real worker still uses
        # source Python spawn, not a fabricated frozen executable command line.
        with patch('gptsnip.browser.sys.frozen', True, create=True):
            return self.reader(worker, timeout=None)

    def reader(self, worker, timeout=1.5):
        reader = BrowserReader(worker=worker, timeout=timeout)
        def cleanup():
            reader.close()
            if reader.thread:
                reader.thread.join(3)
                self.assertFalse(reader.thread.is_alive(), 'supervisor did not stop')
        self.addCleanup(cleanup)
        return reader

    def receive(self, reader, limit=3):
        end = time.monotonic() + limit
        while time.monotonic() < end:
            result = reader.poll()
            if result is not None:
                return result
            time.sleep(0.01)
        self.fail('bounded reader did not return')

    def test_process_round_trip_and_one_outstanding_request(self):
        reader = self.reader(echo_worker)
        token = reader.request('window A')
        for _ in range(30):
            self.assertIsNone(reader.request('window B'))
        received, result = self.receive(reader)
        self.assertEqual(received, token)
        self.assertEqual(result.snapshot, 'window A')
        self.assertTrue(result.eligible)

    def test_hung_provider_times_out_without_blocking_or_leaking_children(self):
        baseline = {p.pid for p in mp.active_children()}
        reader = self.reader(hung_worker, timeout=0.3)
        token = reader.request('window A')
        received, result = self.receive(reader)
        self.assertEqual(received, token)
        self.assertFalse(result.eligible)
        self.assertIn('timeout', result.reason)
        reader.close()
        reader.thread.join(3)
        self.assertFalse(reader.thread.is_alive())
        self.assertEqual({p.pid for p in mp.active_children()}, baseline)

    def test_expired_worker_evidence_is_rejected(self):
        reader = self.reader(stale_worker)
        reader.request('window A')
        _, result = self.receive(reader)
        self.assertFalse(result.eligible)
        self.assertEqual(result.reason, 'stale_reply')

    def test_mismatched_worker_token_is_never_accepted(self):
        reader = self.reader(wrong_token_worker)
        reader.request('window A')
        _, result = self.receive(reader)
        self.assertFalse(result.eligible)

    def test_closed_reader_cannot_start_work(self):
        reader = self.reader(echo_worker)
        reader.close()
        self.assertIsNone(reader.request('window A'))
        self.assertIsNone(reader.thread)

    def test_frozen_default_has_bounded_headroom_and_source_default_is_unchanged(self):
        with patch('gptsnip.browser.sys.frozen', False, create=True):
            self.assertEqual(BrowserReader().timeout, 1.0)
        with patch('gptsnip.browser.sys.frozen', True, create=True):
            self.assertEqual(BrowserReader().timeout, 1.5)
            self.assertEqual(BrowserReader(timeout=0.25).timeout, 0.25)

    def test_frozen_budget_accepts_slow_but_fresh_positive_result(self):
        reader = self.frozen_reader(slow_fresh_worker)
        reader.request('window A')
        _, primed = self.receive(reader)
        self.assertTrue(primed.eligible)
        reader.request('window A')
        _, result = self.receive(reader)
        self.assertTrue(result.eligible)
        self.assertEqual(result.snapshot, 'window A')

    def test_frozen_budget_still_times_out_hung_worker_and_fails_closed(self):
        baseline = {p.pid for p in mp.active_children()}
        reader = self.frozen_reader(hung_worker)
        reader.request('window A')
        _, result = self.receive(reader)
        self.assertFalse(result.eligible)
        self.assertIn('timeout', result.reason)
        reader.close()
        reader.thread.join(3)
        self.assertFalse(reader.thread.is_alive())
        self.assertEqual({p.pid for p in mp.active_children()}, baseline)

    def test_frozen_headroom_does_not_extend_positive_sample_freshness(self):
        # Isolate reply freshness from variable source process startup. The real
        # worker transport and retirement paths have separate tests above.
        with patch('gptsnip.browser.sys.frozen', True, create=True):
            reader = BrowserReader(clock=lambda: 10.0)
        self.assertEqual(reader.timeout, 1.5)
        reader.pending = (1, 10.0 + reader.timeout)
        reader.results.put_nowait((1, DocumentResult(
            'verified', 'chatgpt.com', 'window A', 9.6, '')))
        _, result = reader.poll()
        self.assertFalse(result.eligible)
        self.assertEqual(result.reason, 'stale_reply')


if __name__ == '__main__':
    unittest.main()
