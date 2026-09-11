"""Redacted document identities and a bounded, asynchronous MSAA worker.

Only the child process calls accessibility APIs. The single supervisor thread
owns process creation, IPC, deadlines, and termination; Tk only uses local queues.
"""

from dataclasses import dataclass
import multiprocessing as mp
import os
from queue import Empty, Full, Queue
import re
from threading import Event, Thread
import time
from urllib.parse import urlsplit

READ_TIMEOUT = 1.0
MAX_RESULT_AGE = 0.3
STABILITY_SECONDS = 0.12
RETRY_SECONDS = 2.0
_diagnostic_token = None


def identity_diagnostic(event, token=None, **fields):
    """Opt-in trace of the first 12 requests per launch; callers pass metadata only."""
    token = _diagnostic_token if token is None else token
    if (os.environ.get('GPTSNIP_IDENTITY_DIAGNOSTICS') == '1'
            and isinstance(token, int) and 1 <= token <= 12):
        print(f'PixelPort identity: token={token} {event} '
              + ' '.join(f'{key}={value}' for key, value in fields.items()), flush=True)


def document_hostname(value):
    """Return only a parsed HTTPS hostname; discard URL paths and identifiers.

No credentials, alternative ports, whitespace, backslashes, malformed escapes,
or parser normalization tricks. A hostname is not automatically an eligible site.
"""
    if (not isinstance(value, str) or not value or len(value) > 8192
            or any(ord(c) <= 32 or ord(c) == 127 for c in value)
            or '\\' in value or re.search(r'%(?![0-9a-fA-F]{2})', value)):
        return None
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        if (parsed.scheme != 'https' or not host or '@' in parsed.netloc
                or parsed.port not in (None, 443) or parsed.netloc.endswith(':')
                or not re.fullmatch(r'[a-z0-9.-]+', host)
                or any(not part or part.startswith('-') or part.endswith('-')
                       for part in host.split('.'))):
            return None
        return host
    except (ValueError, TypeError):
        return None


def is_chatgpt_url(value):
    return document_hostname(value) == 'chatgpt.com'


@dataclass(frozen=True)
class DocumentResult:
    status: str = 'unknown'
    host: str | None = None
    snapshot: object = None
    sampled_at: float = 0.0
    reason: str = 'unavailable'

    @property
    def eligible(self):
        return self.status == 'verified' and self.host == 'chatgpt.com' and self.snapshot is not None


def _worker(connection):
    # Spawned process, no Tk windows, and no COM object crosses the IPC boundary.
    import sys
    sys.coinit_flags = 0
    from .native_document import read_stable
    global _diagnostic_token
    while True:
        token, window, deadline = connection.recv()
        _diagnostic_token = token
        identity_diagnostic('worker received request')
        if time.monotonic() >= deadline:
            result = DocumentResult(reason='deadline')
        else:
            try:
                result = read_stable(window)
            except Exception:
                # Provider exception messages can contain private data.
                result = DocumentResult(reason='provider_error')
        identity_diagnostic('native result', status=result.status, host=result.host, reason=result.reason)
        connection.send((token, result))


class BrowserReader:
    """One supervisor, at most one child and one outstanding request. No UI waits."""

    def __init__(self, worker=_worker, timeout=READ_TIMEOUT, clock=time.monotonic):
        self.worker, self.timeout, self.clock = worker, timeout, clock
        self.requests, self.results = Queue(maxsize=1), Queue(maxsize=1)
        self.stopping, self.occupied = Event(), Event()
        self.thread = None
        self.pending = None
        self.serial = 0

    def request(self, window):
        if self.stopping.is_set() or self.pending or self.occupied.is_set():
            return None
        # Discard a response whose UI deadline expired before it was delivered.
        try:
            self.results.get_nowait()
        except Empty:
            pass
        self.serial += 1
        token, deadline = self.serial, self.clock() + self.timeout
        self.pending = (token, deadline)
        self.occupied.set()
        self.requests.put_nowait((token, window, deadline))
        identity_diagnostic('request admitted', token)
        if self.thread is None:
            self.thread = Thread(target=self._supervise, name='GPTSnip identity', daemon=True)
            self.thread.start()
        return token

    def poll(self):
        if not self.pending:
            return None
        token, deadline = self.pending
        if self.clock() >= deadline:
            self.pending = None
            identity_diagnostic('result rejected: deadline', token)
            return token, DocumentResult(reason='timeout')
        try:
            received, result = self.results.get_nowait()
        except Empty:
            return None
        if received != token:
            identity_diagnostic('result rejected: stale token', token)
            return None
        self.pending = None
        age = self.clock() - result.sampled_at
        if result.status == 'verified' and not 0 <= age <= MAX_RESULT_AGE:
            result = DocumentResult(reason='stale_reply')
        identity_diagnostic('transport delivered result', token, status=result.status, reason=result.reason)
        return token, result

    def close(self):
        self.stopping.set()
        self.pending = None

    def _supervise(self):
        context = mp.get_context('spawn')
        process = connection = None
        retry_at = 0.0

        def retire():
            nonlocal process, connection
            if process is not None:
                if process.is_alive():
                    process.terminate()
                process.join(0.2)
                if process.is_alive():
                    process.kill()
                    process.join(0.2)
                if process.is_alive():
                    return False  # Never start another child while this one exists.
                process.close()
                process = None
            if connection is not None:
                connection.close()
                connection = None
            return True

        try:
            while not self.stopping.is_set():
                try:
                    token, window, deadline = self.requests.get(timeout=0.05)
                except Empty:
                    continue
                result = DocumentResult(reason='worker_unavailable')
                identity_diagnostic('supervisor received request', token)
                try:
                    if self.clock() < retry_at:
                        result = DocumentResult(reason='worker_cooldown')
                    else:
                        if process is None:
                            connection, child = context.Pipe()
                            process = context.Process(target=self.worker, args=(child,), daemon=True)
                            process.start()
                            child.close()
                            identity_diagnostic('browser worker started', token, pid=process.pid)
                        connection.send((token, window, deadline))
                        while not self.stopping.is_set() and self.clock() < deadline:
                            if connection.poll(min(0.05, max(0, deadline - self.clock()))):
                                received, candidate = connection.recv()
                                if received == token and isinstance(candidate, DocumentResult):
                                    result = candidate
                                else:
                                    result = DocumentResult(reason='mismatched_worker_reply')
                                break
                        else:
                            result = DocumentResult(reason='timeout')
                        if self.clock() >= deadline or result.reason == 'mismatched_worker_reply':
                            result = DocumentResult(reason='timeout_or_stale_reply')
                            retire()
                            retry_at = self.clock() + RETRY_SECONDS
                except Exception:
                    identity_diagnostic('worker transport error', token,
                                        exitcode=process.exitcode if process is not None else None)
                    result = DocumentResult(reason='worker_error')
                    retire()
                    retry_at = self.clock() + RETRY_SECONDS
                try:
                    self.results.put_nowait((token, result))
                except Full:
                    pass  # Expired results must never block supervision or shutdown.
                self.occupied.clear()
        finally:
            retire()
