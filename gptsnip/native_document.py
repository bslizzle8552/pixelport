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
from .browser import DocumentResult, STABILITY_SECONDS, document_hostname, identity_diagnostic


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
        identity_diagnostic('native renderer candidates', visible=len(visible))
        if len(visible) != 1 or visible[0][2] != pid or pid != window.pid:
            return None
        return DocumentSnapshot(window, started, thread, visible[0])
    except Exception:
        return None


def is_current(snapshot):
    return isinstance(snapshot, DocumentSnapshot) and snapshot_window(snapshot.window) == snapshot


def _guid(value):
    return (ct.c_ubyte * 16).from_buffer_copy(uuid.UUID(value).bytes_le)


def _com_method(pointer, slot, result, *arguments):
    table = ct.cast(pointer, ct.POINTER(ct.POINTER(ct.c_void_p))).contents
    return ct.WINFUNCTYPE(result, ct.c_void_p, *arguments)(table[slot])


def _release(pointer):
    if pointer.value:
        _com_method(pointer, 2, wt.ULONG)(pointer)


def _root_pointer(hwnd, interface='00020400-0000-0000-c000-000000000046'):
    # Only invoked in the isolated reader process.
    import pythoncom  # Initialize COM before retrieving native interface pointers.
    oleacc = ct.WinDLL('oleacc')
    oleacc.AccessibleObjectFromWindow.argtypes = [wt.HWND, wt.DWORD, ct.c_void_p,
                                                 ct.POINTER(ct.c_void_p)]
    oleacc.AccessibleObjectFromWindow.restype = ct.c_long
    iid = _guid(interface)
    pointer = ct.c_void_p()
    result = oleacc.AccessibleObjectFromWindow(hwnd, 0xFFFFFFFC, ct.byref(iid), ct.byref(pointer))
    if result < 0 or not pointer.value:
        _release(pointer)
        raise RuntimeError('document_unavailable')
    return pointer


def _root_dispatch(hwnd):
    import pythoncom
    pointer = _root_pointer(hwnd)
    try:
        return pythoncom.ObjectFromAddress(pointer.value, pythoncom.IID_IDispatch)
    finally:
        _release(pointer)


def _request_document_data(hwnd):
    """Ask the exact root for IA2 state, without walking content or taking identity.

    Chrome 152's MSAA role/state reads enable only kNativeAPIs, leaving a BUSY
    empty document indefinitely. IA2 get_states requests web accessibility data.
    This query is a bootstrap only: the caller rejects the current sample, and a
    later request must pass every ordinary MSAA/stability/identity check.
    """
    # Follow IA2's IAccessible -> IServiceProvider discovery contract. Keep the
    # existing IDispatch path for MSAA property reads.
    root = _root_pointer(hwnd, '618736e0-3c3d-11cf-810c-00aa00389b71')
    service, accessible = ct.c_void_p(), ct.c_void_p()
    try:
        service_iid = _guid('6d5140c1-7436-11ce-8034-00aa006009fa')
        hr = _com_method(root, 0, ct.c_long, ct.c_void_p, ct.POINTER(ct.c_void_p))(
            root, ct.byref(service_iid), ct.byref(service))
        if hr < 0 or not service.value:
            return False
        ia2_iid = _guid('e89f726e-c4f4-4c19-bb19-b647d7fa8478')
        hr = _com_method(service, 3, ct.c_long, ct.c_void_p, ct.c_void_p,
                         ct.POINTER(ct.c_void_p))(
            service, ct.byref(ia2_iid), ct.byref(ia2_iid), ct.byref(accessible))
        if hr < 0 or not accessible.value:
            return False
        # IUnknown (3) + IDispatch (4) + IAccessible (21) + IA2 get_states (7).
        # The IA2 IDL defines AccessibleStates as a 32-bit long on Windows.
        states = ct.c_long()
        hr = _com_method(accessible, 35, ct.c_long, ct.POINTER(ct.c_long))(
            accessible, ct.byref(states))
        return hr == 0
    finally:
        for pointer in (accessible, service, root):
            _release(pointer)


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
        identity_diagnostic('native document metadata',
                            role=role if isinstance(role, int) else 'invalid',
                            state=hex(state) if isinstance(state, int) else 'invalid')
        # Unavailable, invisible, or offscreen roots cannot request document data.
        if role != 15 or not isinstance(state, int) or state & (0x1 | 0x8000 | 0x10000):
            return DocumentResult(reason='wrong_role_or_unavailable')
        if state & 0x800:
            if snapshot_window(window) != before:
                return DocumentResult(reason='identity_changed_during_read')
            requested = _request_document_data(before.renderer[0])
            identity_diagnostic('native document initialization requested', available=requested)
            return DocumentResult(reason='document_initializing' if requested
                                  else 'document_initialization_unavailable')
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
