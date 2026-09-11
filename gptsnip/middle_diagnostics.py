"""Opt-in, bounded, read-only focus trace. Never read titles or browser content."""

import ctypes as ct
from ctypes import wintypes as wt
import json
import ntpath
import os
import time

import win32api
import win32gui
import win32process

from . import windows as native

user32 = ct.WinDLL("user32", use_last_error=True)
kernel32 = ct.WinDLL("kernel32", use_last_error=True)


class GUIThreadInfo(ct.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("flags", wt.DWORD),
                ("hwndActive", wt.HWND), ("hwndFocus", wt.HWND),
                ("hwndCapture", wt.HWND), ("hwndMenuOwner", wt.HWND),
                ("hwndMoveSize", wt.HWND), ("hwndCaret", wt.HWND),
                ("rcCaret", wt.RECT)]


user32.GetGUIThreadInfo.argtypes = [wt.DWORD, ct.POINTER(GUIThreadInfo)]
user32.GetGUIThreadInfo.restype = wt.BOOL
user32.GetAsyncKeyState.argtypes = [ct.c_int]
user32.GetAsyncKeyState.restype = wt.SHORT
kernel32.GetConsoleWindow.restype = wt.HWND
kernel32.GetCurrentThreadId.restype = wt.DWORD


def gui_state(thread):
    info = GUIThreadInfo(cbSize=ct.sizeof(GUIThreadInfo))
    if not user32.GetGUIThreadInfo(thread, ct.byref(info)):
        return {"unavailable": ct.get_last_error()}
    return {"flags": info.flags, "active": info.hwndActive, "focus": info.hwndFocus,
            "capture": info.hwndCapture}


def window_state(hwnd):
    result = {"hwnd": hwnd or 0}
    if not hwnd:
        return result
    try:
        thread, pid = win32process.GetWindowThreadProcessId(hwnd)
        result.update(thread=thread, pid=pid, window_class=win32gui.GetClassName(hwnd))
        process = win32api.OpenProcess(0x1000, False, pid)
        try:
            name, size = ct.create_unicode_buffer(32768), wt.DWORD(32768)
            if native.kernel32.QueryFullProcessImageNameW(int(process), 0, name, ct.byref(size)):
                result["process"] = ntpath.basename(name.value)
        finally:
            process.Close()
    except Exception as exc:
        result["unavailable"] = type(exc).__name__
    return result


def target_state(window):
    # Explicit allowlist: Window also contains a potentially sensitive title.
    if window is None:
        return None
    return {"hwnd": window.hwnd, "pid": window.pid, "process": window.process}


class MiddleDiagnostics:
    LIMIT = 600

    def __init__(self):
        self.enabled = os.environ.get("GPTSNIP_MIDDLE_DIAGNOSTICS") == "1"
        self.file_path = (os.environ.get("GPTSNIP_MIDDLE_DIAGNOSTIC_FILE")
                          if self.enabled else None)
        self.file_announced = False
        self.file_error_reported = False
        self.started = time.monotonic()
        self.count = 0
        self.previous = None
        self.next_sample = 0

    def snapshot(self, app, selector=None):
        foreground = window_state(win32gui.GetForegroundWindow())
        hook = app.mouse_hook
        state = hook.state if hook else None
        gesture = state.gesture if state else None
        selector = selector if selector is not None else app.selector
        pending, verification = app.identity_pending, app.verification
        data = {
            "ms": round((time.monotonic() - self.started) * 1000),
            "foreground": foreground,
            "foreground_gui": gui_state(foreground.get("thread", 0)),
            "ui_thread": kernel32.GetCurrentThreadId(),
            "ui_gui": gui_state(kernel32.GetCurrentThreadId()),
            "console": window_state(kernel32.GetConsoleWindow()),
            "hotkey_hwnd": app.hwnd,
            "physical_middle_down": bool(user32.GetAsyncKeyState(4) & 0x8000),
            "busy": app.busy, "stopping": app.stopping, "generation": app.generation,
            "middle_id": app.middle_id, "target_ready": app.middle_target_ready,
            "selection_waiting_for_target": app.middle_box is not None,
            "bounds_at_capture": getattr(app, "bounds", None),
            "bounds_now": native.desktop_bounds(),
            "remembered": target_state(app.remembered), "bound": target_state(app.bound),
            "target": target_state(getattr(app, "target", None)),
            "memory_blocked": app.memory_blocked,
            "chrome_memory_present": app.chrome_memory is not None,
            "target_document_present": app.target_document is not None,
            "identity_pending": ({"token": pending[0], "kind": pending[1],
                                  "hwnd": pending[2].hwnd, "generation": pending[3]}
                                 if pending else None),
            "verification": ({"hwnd": verification[0].hwnd, "generation": verification[3],
                              "remaining_ms": round((verification[4] - time.monotonic()) * 1000)}
                             if verification else None),
            "hook": ({"accepting": state.accepting, "acknowledged": state.acknowledged,
                      "serial": state.serial, "held": state.held,
                      "preexisting_hold": state.preexisting_hold,
                      "thread": hook._thread_id, "installed": bool(hook._hook),
                      "error_present": bool(hook.error),
                      "gesture": ({"serial": gesture.serial, "start": gesture.start,
                                   "point": gesture.point, "released": gesture.released,
                                   "cancelled": gesture.cancelled} if gesture else None)}
                     if state else None),
            "selector": ({"hwnd": getattr(selector, "hwnd", None),
                          "lifecycle": selector.lifecycle, "closed": selector.closed,
                          "cancel_reason": selector.cancel_reason,
                          "source_foreground": selector.source_foreground,
                          "foreground_established": selector.foreground_established,
                          "activation_attempted": selector.activation_attempted,
                          "expected_foreground": getattr(selector, "hwnd", None)}
                         if selector else None),
        }
        try:
            data["tk"] = {"root_id": app.root.winfo_id(), "root_state": app.root.state(),
                          "focus": str(app.root.focus_get()),
                          "grab": str(app.root.grab_current())}
            if selector and not selector.closed:
                data["tk"]["selector_state"] = selector.window.state()
                data["tk"]["selector_viewable"] = bool(selector.window.winfo_viewable())
        except Exception as exc:
            data["tk_unavailable"] = type(exc).__name__
        return data

    def write(self, event, **fields):
        if self.count >= self.LIMIT:
            return
        self.count += 1
        self.output({"event": event, "pid": os.getpid(), **fields})
        if self.count == self.LIMIT:
            self.output({"event": "trace limit reached; relaunch for more", "pid": os.getpid()})

    def output(self, record):
        line = json.dumps(record, separators=(",", ":"))
        if self.file_path:
            try:
                # Persist complete records directly, before console output. Native
                # stdout in a PowerShell transcript may retain only a screen tail.
                # Append preserves earlier evidence; closing flushes each record.
                with open(self.file_path, "a", encoding="utf-8", newline="\n") as stream:
                    stream.write(line + "\n")
            except OSError as exc:
                if not self.file_error_reported:
                    self.file_error_reported = True
                    print("GPTSnip middle diagnostic: file recording failed ("
                          + type(exc).__name__ + "); using console output.", flush=True)
            else:
                if not self.file_announced:
                    self.file_announced = True
                    print("GPTSnip middle diagnostic: recording JSONL to " + self.file_path, flush=True)
                if record["event"] == "trace limit reached; relaunch for more":
                    print("GPTSnip middle diagnostic: trace limit reached; relaunch for more.", flush=True)
                return
        print("GPTSnip middle diagnostic: " + line, flush=True)

    def emit(self, app, event, selector=None, **fields):
        if not self.enabled or self.count >= self.LIMIT:
            return
        try:
            self.write(event, state=self.snapshot(app, selector), **fields)
        except Exception:
            # Diagnostics must never turn a capture into an application failure.
            pass

    def poll(self, app):
        if not self.enabled or self.count >= self.LIMIT:
            return
        try:
            now = time.monotonic()
            hwnd = win32gui.GetForegroundWindow()
            changed = self.previous is None or hwnd != self.previous["foreground"]["hwnd"]
            if not changed and now < self.next_sample:
                return
            current = self.snapshot(app)
            if changed:
                self.write("foreground transition (sampled)", previous=self.previous, state=current)
            self.previous = current
            self.next_sample = now + 0.25
        except Exception:
            pass
