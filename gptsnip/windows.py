"""Win32 boundary. No browser integration, networking, or filesystem image writes."""

import ctypes as ct
from ctypes import wintypes as wt
import ntpath
import time

import win32api
import win32clipboard
import win32con
import win32gui
import win32process

from .core import Window, image_dib

user32 = ct.WinDLL("user32", use_last_error=True)
kernel32 = ct.WinDLL("kernel32", use_last_error=True)
dwmapi = ct.WinDLL("dwmapi", use_last_error=True)
user32.SetProcessDpiAwarenessContext.argtypes = [wt.HANDLE]
user32.SetProcessDpiAwarenessContext.restype = wt.BOOL
user32.GetThreadDpiAwarenessContext.restype = wt.HANDLE
user32.GetAwarenessFromDpiAwarenessContext.argtypes = [wt.HANDLE]
user32.GetAwarenessFromDpiAwarenessContext.restype = ct.c_int
kernel32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR,
                                               ct.POINTER(wt.DWORD)]
kernel32.QueryFullProcessImageNameW.restype = wt.BOOL
dwmapi.DwmGetWindowAttribute.argtypes = [wt.HWND, wt.DWORD, wt.LPVOID, wt.DWORD]
dwmapi.DwmGetWindowAttribute.restype = ct.c_long
dwmapi.DwmFlush.restype = ct.c_long
user32.AttachThreadInput.argtypes = [wt.DWORD, wt.DWORD, wt.BOOL]
user32.AttachThreadInput.restype = wt.BOOL


def enable_dpi_awareness():
    # Set before creating ANY windows or reading screen coordinates. PMv2 avoids
    # Windows logical-coordinate virtualization on mixed-scale displays.
    if not user32.SetProcessDpiAwarenessContext(wt.HANDLE(-4)):
        context = user32.GetThreadDpiAwarenessContext()
        if user32.GetAwarenessFromDpiAwarenessContext(context) != 2:
            raise RuntimeError("Per-monitor DPI awareness could not be enabled.")


def desktop_bounds():
    x, y, width, height = (win32api.GetSystemMetrics(i) for i in (76, 77, 78, 79))
    return x, y, x + width, y + height


def inspect_window(hwnd):
    try:
        if not win32gui.IsWindowVisible(hwnd):
            return None
        cloaked = wt.DWORD()
        if (dwmapi.DwmGetWindowAttribute(hwnd, 14, ct.byref(cloaked), 4) == 0
                and cloaked.value):
            return None  # Includes windows on other virtual desktops.
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        process = win32api.OpenProcess(0x1000, False, pid)
        try:
            name, size = ct.create_unicode_buffer(32768), wt.DWORD(32768)
            if not kernel32.QueryFullProcessImageNameW(int(process), 0, name, ct.byref(size)):
                return None
            return Window(hwnd, pid, ntpath.basename(name.value), win32gui.GetWindowText(hwnd))
        finally:
            process.Close()
    except win32api.error:
        return None


def list_windows():
    windows = []

    def collect(hwnd, _):
        window = inspect_window(hwnd)
        if window is not None and window.supported:
            windows.append(window)
        return True

    win32gui.EnumWindows(collect, None)
    return windows


def copy_image(image, owner):
    data = image_dib(image)
    # Other applications briefly hold the clipboard open; retry for at most 0.5 s.
    for attempt in range(11):
        try:
            win32clipboard.OpenClipboard(owner)
            break
        except win32api.error:
            if attempt == 10:
                raise RuntimeError("Clipboard is busy; screenshot was not copied.") from None
            time.sleep(0.05)
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_DIB, data)
        # Ask Windows clipboard history and cloud clipboard not to retain this item.
        for name in ("CanIncludeInClipboardHistory", "CanUploadToCloudClipboard"):
            fmt = win32clipboard.RegisterClipboardFormat(name)
            win32clipboard.SetClipboardData(fmt, b"\0\0\0\0")
    finally:
        win32clipboard.CloseClipboard()
    return win32clipboard.GetClipboardSequenceNumber()


class KEYBDINPUT(ct.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ct.c_size_t)]


class MOUSEINPUT(ct.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD),
                ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ct.c_size_t)]


class INPUTUNION(ct.Union):
    # Including MOUSEINPUT gives INPUT its correct ABI size on both x86 and x64.
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ct.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", INPUTUNION)]


user32.SendInput.argtypes = [wt.UINT, ct.POINTER(INPUT), ct.c_int]
user32.SendInput.restype = wt.UINT


def keyboard_event(vk, up=False):
    return INPUT(type=1, ki=KEYBDINPUT(wVk=vk, dwFlags=2 if up else 0))


def keys_down():
    # Do not turn a held capture shortcut into Ctrl+Alt+Shift+V, or release a
    # user's physically held key. Also wait for mouse buttons and ordinary keys.
    return any(win32api.GetAsyncKeyState(vk) & 0x8000 for vk in range(1, 255))


def paste(target, clipboard_sequence):
    """Fail closed; the only injected action is one Ctrl+V chord, never Enter."""
    if inspect_window(target.hwnd) != target:
        raise RuntimeError("ChatGPT target changed; image remains on the clipboard.")
    if keys_down():
        raise RuntimeError("Keys/buttons are still held; paste cancelled. Use Ctrl+V manually.")
    if win32clipboard.GetClipboardSequenceNumber() != clipboard_sequence:
        raise RuntimeError("Clipboard changed after capture; paste cancelled.")
    if win32gui.GetForegroundWindow() != target.hwnd:
        raise RuntimeError("ChatGPT lost focus; paste cancelled. Use Ctrl+V manually.")
    events = (INPUT * 4)(keyboard_event(0x11), keyboard_event(0x56),
                         keyboard_event(0x56, True), keyboard_event(0x11, True))
    sent = user32.SendInput(4, events, ct.sizeof(INPUT))
    if sent != 4:
        # If Windows accepted only part of the chord, release our injected keys.
        if sent:
            releases = (INPUT * 2)(keyboard_event(0x56, True), keyboard_event(0x11, True))
            user32.SendInput(2, releases, ct.sizeof(INPUT))
        raise RuntimeError("Windows blocked or interrupted paste; use Ctrl+V manually.")


def request_foreground(target):
    if inspect_window(target.hwnd) != target:
        raise RuntimeError("ChatGPT target changed; image remains on the clipboard.")
    if win32gui.IsIconic(target.hwnd):
        win32gui.ShowWindow(target.hwnd, win32con.SW_RESTORE)
    try:
        win32gui.SetForegroundWindow(target.hwnd)
    except win32api.error:
        pass  # The caller verifies the actual foreground window with a deadline.


def acquire_selector_foreground(hwnd, source):
    """Gesture-only acquisition for our UI window after Tk focus was insufficient.

    Share input state with the unchanged source just for the native activation
    call, then detach before returning to Tk. No console, synthetic input, sleep,
    or persistent attachment. The caller must still verify foreground ownership.
    """
    current_thread = win32api.GetCurrentThreadId()
    try:
        target_thread, target_pid = win32process.GetWindowThreadProcessId(hwnd)
        if target_thread != current_thread or target_pid != win32api.GetCurrentProcessId():
            return False
        foreground = win32gui.GetForegroundWindow()
        if foreground == hwnd:
            return True
        if not source or foreground != source:
            return False
        source_thread, _ = win32process.GetWindowThreadProcessId(source)
        if source_thread == current_thread:
            win32gui.SetForegroundWindow(hwnd)
        else:
            if not user32.AttachThreadInput(current_thread, source_thread, True):
                return False
            try:
                # Do not take foreground back if the user switched meanwhile.
                if win32gui.GetForegroundWindow() == source:
                    win32gui.SetForegroundWindow(hwnd)
            finally:
                if not user32.AttachThreadInput(current_thread, source_thread, False):
                    raise RuntimeError("Selector input-thread detachment failed.")
        return win32gui.GetForegroundWindow() == hwnd
    except win32api.error:
        return False
