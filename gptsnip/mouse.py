"""Native middle-button ownership; the hook never calls Tk or capture code."""

import ctypes as ct
from ctypes import wintypes as wt
from dataclasses import dataclass, replace
import threading
import time

WH_MOUSE_LL = 14
WM_MOUSEMOVE = 0x0200
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
WM_TIMER = 0x0113
WM_QUIT = 0x0012
HOLD_TIMEOUT = 60.0


@dataclass(frozen=True)
class Gesture:
    serial: int
    start: tuple
    point: tuple
    released: bool = False
    cancelled: bool = False


class MouseState:
    """One immutable latest sample, not a movement queue.

    The hook thread alone writes gesture/held. Tk writes accepting/acknowledged.
    CPython reference assignment publishes complete snapshots without waiting on
    a UI lock. One outstanding gesture prevents rapid clicks replacing a release.
    """

    def __init__(self):
        self.gesture = None
        self.accepting = True
        self.acknowledged = 0
        self.held = False
        self.held_since = 0
        self.serial = 0
        self.preexisting_hold = False

    def event(self, message, point, injected=False):
        if injected:
            # Other software's synthetic clicks cannot start/end a physical drag.
            return message in (WM_MBUTTONDOWN, WM_MBUTTONUP) and not self.preexisting_hold
        if self.preexisting_hold:
            if message == WM_MBUTTONUP:
                self.preexisting_hold = False
            return False  # Balance a down delivered before GPTSnip installed.
        if message == WM_MBUTTONDOWN:
            if not self.held:
                self.held = True
                self.held_since = time.monotonic()
                if (self.accepting and
                        (self.gesture is None or self.gesture.serial <= self.acknowledged)):
                    self.serial += 1
                    self.gesture = Gesture(self.serial, point, point)
            return True
        if message in (WM_MOUSEMOVE, WM_MBUTTONUP):
            current = self.gesture
            if (self.held and current is not None and not current.released
                    and not current.cancelled and current.serial > self.acknowledged):
                self.gesture = replace(current, point=point,
                                       released=message == WM_MBUTTONUP)
            if message == WM_MBUTTONUP:
                self.held = False
                return True
        return False

    def expire(self):
        # No cursor polling, no inferred release/capture, no synthetic input.
        # A bounded hold also recovers from a lost up on a desktop transition.
        if self.held and time.monotonic() - self.held_since >= HOLD_TIMEOUT:
            self.held = False
            current = self.gesture
            if current is not None and current.serial > self.acknowledged:
                self.gesture = replace(current, cancelled=True)


class MSLLHOOKSTRUCT(ct.Structure):
    _fields_ = [("pt", wt.POINT), ("mouseData", wt.DWORD), ("flags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ct.c_size_t)]


HOOKPROC = ct.WINFUNCTYPE(ct.c_ssize_t, ct.c_int, wt.WPARAM, wt.LPARAM)
user32 = ct.WinDLL("user32", use_last_error=True)
kernel32 = ct.WinDLL("kernel32", use_last_error=True)
user32.SetWindowsHookExW.argtypes = [ct.c_int, HOOKPROC, wt.HINSTANCE, wt.DWORD]
user32.SetWindowsHookExW.restype = wt.HANDLE
user32.CallNextHookEx.argtypes = [wt.HANDLE, ct.c_int, wt.WPARAM, wt.LPARAM]
user32.CallNextHookEx.restype = ct.c_ssize_t
user32.UnhookWindowsHookEx.argtypes = [wt.HANDLE]
user32.UnhookWindowsHookEx.restype = wt.BOOL
user32.GetMessageW.argtypes = [ct.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
user32.GetMessageW.restype = ct.c_int
user32.PeekMessageW.argtypes = [ct.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT, wt.UINT]
user32.PostThreadMessageW.argtypes = [wt.DWORD, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.SetTimer.argtypes = [wt.HWND, ct.c_size_t, wt.UINT, wt.LPVOID]
user32.SetTimer.restype = ct.c_size_t
user32.KillTimer.argtypes = [wt.HWND, ct.c_size_t]
user32.GetAsyncKeyState.argtypes = [ct.c_int]
user32.GetAsyncKeyState.restype = wt.SHORT
kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
kernel32.GetModuleHandleW.restype = wt.HMODULE
kernel32.GetCurrentThreadId.restype = wt.DWORD


class MouseHook:
    def __init__(self):
        self.state = MouseState()
        self.error = None
        self._ready = threading.Event()
        self._stop = threading.Event()
        self._thread = None
        self._thread_id = None
        self._hook = None
        self._callback = HOOKPROC(self._dispatch)  # Retain until unhook/thread exit.

    def _dispatch(self, code, message, address):
        if code >= 0 and message in (WM_MOUSEMOVE, WM_MBUTTONDOWN, WM_MBUTTONUP):
            try:
                # Ordinary movement does not allocate even a coordinate tuple.
                if message != WM_MOUSEMOVE or self.state.held:
                    data = ct.cast(address, ct.POINTER(MSLLHOOKSTRUCT)).contents
                    if self.state.event(message, (data.pt.x, data.pt.y), bool(data.flags & 3)):
                        return 1
            except Exception:
                self.error = "Mouse hook callback failed."
                self.state.accepting = False
                if message in (WM_MBUTTONDOWN, WM_MBUTTONUP):
                    return 1
        return user32.CallNextHookEx(None, code, message, address)

    def start(self):
        self._thread = threading.Thread(target=self._run, name="GPTSnipMouse", daemon=True)
        self._thread.start()
        if not self._ready.wait(2) or self.error:
            self.close()
            raise RuntimeError(self.error or "Mouse hook startup timed out.")

    def _run(self):
        timer = 0
        try:
            self._thread_id = kernel32.GetCurrentThreadId()
            msg = wt.MSG()
            user32.PeekMessageW(ct.byref(msg), None, 0, 0, 0)  # Create thread queue.
            self.state.preexisting_hold = bool(user32.GetAsyncKeyState(4) & 0x8000)
            self._hook = user32.SetWindowsHookExW(
                WH_MOUSE_LL, self._callback, kernel32.GetModuleHandleW(None), 0)
            if not self._hook:
                raise ct.WinError(ct.get_last_error())
            timer = user32.SetTimer(None, 0, 250, None)
            if not timer:
                raise ct.WinError(ct.get_last_error())
            self._ready.set()
            while not self._stop.is_set():
                result = user32.GetMessageW(ct.byref(msg), None, 0, 0)
                if result == -1:
                    raise ct.WinError(ct.get_last_error())
                if result == 0:
                    break
                if msg.message == WM_TIMER:
                    self.state.expire()
        except Exception as exc:
            self.error = str(exc)
        finally:
            self.state.accepting = False
            if timer:
                user32.KillTimer(None, timer)
            if self._hook:
                if not user32.UnhookWindowsHookEx(self._hook):
                    self.error = "Windows could not remove the mouse hook."
                self._hook = None
            self._thread_id = None  # Never post WM_QUIT to a recycled thread ID.
            self._ready.set()

    def close(self):
        self.state.accepting = False
        self._stop.set()
        thread_id = self._thread_id
        if thread_id:
            user32.PostThreadMessageW(thread_id, WM_QUIT, 0, 0)
        if self._thread:
            self._thread.join(2)
            if self._thread.is_alive():
                self.error = "Mouse hook thread did not stop within two seconds."
