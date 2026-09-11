"""Chrome native metadata and document-root reads; no input or content traversal."""

import ctypes as ct
from ctypes import wintypes as wt
from dataclasses import dataclass
import time
import uuid

import win32api
import win32gui
import win32process

from . import windows as native
from .browser import DocumentResult, STABILITY_SECONDS, document_hostname


@dataclass(frozen=True)
class DocumentSnapshot:
    window: object
    process_started: float
    thread: int
    renderer: tuple


def snapshot_window(window):
    """Only cheap Win32 metadata. Safe for reply validation on the UI thread."""
    try:
        if (window.process.lower() != 'chrome.exe'
                or native.inspect_window(window.hwnd) != window
                or win32gui.GetAncestor(window.hwnd, 2) != window.hwnd
                or win32gui.IsIconic(window.hwnd)):
            return None
        thread, pid = win32process.GetWindowThreadProcessId(window.hwnd)
        process = win32api.OpenProcess(0x1000, False, pid)
        try:
            started = win32process.GetProcessTimes(process)['CreationTime'].timestamp()
        finally:
            process.Close()
        visible = []

        def collect(child, _):
            if (win32gui.GetClassName(child) == 'Chrome_RenderWidgetHostHWND'
                    and win32gui.GetAncestor(child, 2) == window.hwnd
                    and win32gui.IsWindowVisible(child)):
                child_thread, child_pid = win32process.GetWindowThreadProcessId(child)
                visible.append((child, child_thread, child_pid, window.hwnd))
            return True

        win32gui.EnumChildWindows(window.hwnd, collect, None)
        if len(visible) != 1 or visible[0][2] != pid or pid != window.pid:
            return None
        return DocumentSnapshot(window, started, thread, visible[0])
    except Exception:
        return None


def is_current(snapshot):
    return isinstance(snapshot, DocumentSnapshot) and snapshot_window(snapshot.window) == snapshot


def _root_dispatch(hwnd):
    # Only invoked in the isolated reader process.
    import pythoncom
    oleacc = ct.WinDLL('oleacc')
    oleacc.AccessibleObjectFromWindow.argtypes = [wt.HWND, wt.DWORD, ct.c_void_p,
                                                 ct.POINTER(ct.c_void_p)]
    oleacc.AccessibleObjectFromWindow.restype = ct.c_long
    iid = (ct.c_ubyte * 16).from_buffer_copy(uuid.UUID(str(pythoncom.IID_IDispatch)).bytes_le)
    pointer = ct.c_void_p()
    result = oleacc.AccessibleObjectFromWindow(hwnd, 0xFFFFFFFC, ct.byref(iid), ct.byref(pointer))
    if result < 0 or not pointer.value:
        raise RuntimeError('document_unavailable')
    try:
        return pythoncom.ObjectFromAddress(pointer.value, pythoncom.IID_IDispatch)
    finally:
        table = ct.cast(pointer, ct.POINTER(ct.POINTER(ct.c_void_p))).contents
        ct.WINFUNCTYPE(wt.ULONG, ct.c_void_p)(table[2])(pointer)


def _property(root, name):
    import pythoncom
    return root.Invoke(root.GetIDsOfNames(name), 0, pythoncom.DISPATCH_PROPERTYGET, True, 0)


def read_once(window):
    before = snapshot_window(window)
    if before is None:
        return DocumentResult(reason='missing_ambiguous_or_stale_window')
    try:
        root = _root_dispatch(before.renderer[0])
        role, state = _property(root, 'accRole'), _property(root, 'accState')
        # Unavailable, busy, invisible, or offscreen cannot establish identity.
        if role != 15 or not isinstance(state, int) or state & (0x1 | 0x800 | 0x8000 | 0x10000):
            return DocumentResult(reason='wrong_role_or_unavailable')
        host = document_hostname(_property(root, 'accValue'))
        # The full value and parsed URL never reach a result, IPC, or diagnostic.
        if not host:
            return DocumentResult(reason='invalid_or_missing_url')
        if snapshot_window(window) != before:
            return DocumentResult(reason='identity_changed_during_read')
        return DocumentResult('verified', host, before, time.monotonic(), '')
    except Exception:
        return DocumentResult(reason='provider_error')


def read_stable(window):
    first = read_once(window)
    if first.status != 'verified':
        return first
    time.sleep(STABILITY_SECONDS)
    second = read_once(window)
    if (second.status != 'verified' or second.host != first.host
            or second.snapshot != first.snapshot):
        return DocumentResult(reason='unstable_document')
    return second
