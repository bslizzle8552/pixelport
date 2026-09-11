"""One UI thread, three global shortcuts, and a bounded capture/paste flow."""

from collections import deque
import signal
import time
import tkinter as tk

from PIL import ImageGrab
import win32api
import win32con
import win32event
import win32gui
import winerror

from .core import choose_target
from .browser import BrowserReader, MAX_RESULT_AGE
from . import native_document
from .selector import Selector
from . import windows as native

HOTKEYS = {1: ord("S"), 2: ord("G"), 3: ord("Q")}
OBSERVATION_SECONDS = 0.25
BROWSER_OBSERVATION_SECONDS = 0.75


class App:
    def __init__(self, root, reader=None):
        self.root = root
        self.actions = deque()
        self.registered = []
        self.remembered = None
        self.next_observation = 0
        self.next_browser_observation = 0
        self.reader = reader if reader is not None else BrowserReader()
        self.identity_pending = None
        self.verification = None
        self.generation = 0
        self.chrome_memory = None
        self.memory_blocked = False
        self.target_document = None
        self.bound = None
        self.selector = None
        self.busy = False
        self.stopping = False
        self.hwnd = None
        self.class_atom = None
        self.instance = win32api.GetModuleHandle(None)
        self.root.report_callback_exception = self.callback_error

    def start(self):
        cls = win32gui.WNDCLASS()
        cls.hInstance = self.instance
        cls.lpszClassName = "GPTSnipV0Hotkeys"
        cls.lpfnWndProc = self.window_proc
        self.class_atom = win32gui.RegisterClass(cls)
        self.hwnd = win32gui.CreateWindow(self.class_atom, "GPTSnip", 0,
                                          0, 0, 0, 0, 0, 0, self.instance, None)
        for identifier, key in HOTKEYS.items():
            try:
                win32gui.RegisterHotKey(self.hwnd, identifier,
                                        win32con.MOD_CONTROL | win32con.MOD_ALT
                                        | win32con.MOD_SHIFT | 0x4000, key)
            except win32api.error as exc:
                raise RuntimeError(f"Ctrl+Alt+Shift+{chr(key)} is unavailable; "
                                   "close the conflicting application and retry.") from exc
            self.registered.append(identifier)
        print("GPTSnip ready. Ctrl+Alt+Shift+S: capture | G: bind ChatGPT | Q: quit", flush=True)
        print("Click your ChatGPT web composer in Chrome; verified chatgpt.com is remembered automatically. "
              "Keep that tab active in its window. G is an optional override.", flush=True)
        self.root.after(30, self.tick)

    def window_proc(self, hwnd, message, wparam, lparam):
        if message == win32con.WM_HOTKEY:
            # The native callback never performs UI work reentrantly.
            self.actions.append(wparam)
            return 0
        return win32gui.DefWindowProc(hwnd, message, wparam, lparam)

    def notice(self, text, error=False):
        print(f"GPTSnip: {text}", flush=True)
        if error:
            win32api.MessageBeep(win32con.MB_ICONEXCLAMATION)

    def callback_error(self, kind, error, traceback):
        self.generation += 1
        self.verification = None
        self.busy = False
        if self.selector:
            self.selector.finish(None)
            self.selector = None
        self.notice(str(error), error=True)

    def tick(self):
        if self.stopping:
            return
        now = time.monotonic()
        self.poll_identity()
        if not self.busy and now >= self.next_observation:
            self.next_observation = now + OBSERVATION_SECONDS
            self.observe_foreground()
        while self.actions:
            action = self.actions.popleft()
            if action == 3:
                self.stop()
                return
            if self.busy:
                continue
            try:
                if action == 2:
                    self.bind_target()
                elif action == 1:
                    self.begin_capture()
            except Exception as exc:
                self.fail(exc)
        self.root.after(30, self.tick)

    def observe_foreground(self):
        # Cheap foreground metadata remains on the existing timer. Accessibility
        # requests are separately rate-limited, including changes on the same HWND.
        hwnd = win32gui.GetForegroundWindow()
        foreground = native.inspect_window(hwnd)
        if not foreground or win32gui.GetForegroundWindow() != hwnd:
            return
        if foreground.process.lower() == 'chrome.exe':
            if (self.remembered and self.remembered.hwnd == hwnd
                    and foreground != self.remembered):
                self.invalidate_automatic(foreground)
            if (time.monotonic() >= self.next_browser_observation
                    and self.identity_pending is None):
                token = self.reader.request(foreground)
                if token is not None:
                    self.identity_pending = (token, 'idle', foreground, self.generation, None, None)
                    self.next_browser_observation = time.monotonic() + BROWSER_OBSERVATION_SECONDS
        elif foreground.recognized:
            if foreground != self.remembered:
                self.remembered = foreground
                self.chrome_memory = None
                self.memory_blocked = False
                self.notice("ChatGPT window remembered automatically."
                            f" Process={foreground.process}, PID={foreground.pid}, HWND={foreground.hwnd:#x}."
                            + (" Manual binding still takes priority." if self.bound else ""))

    def invalidate_automatic(self, window):
        if (self.remembered and self.remembered.hwnd == window.hwnd
                and self.remembered.process.lower() == 'chrome.exe'):
            if not self.memory_blocked:
                self.notice("Chrome target invalidated: active document changed or could not be verified.")
            self.memory_blocked = True
            self.chrome_memory = None
            # Keep the old target snapshot: discovery must not redirect a capture.

    def checked_identity(self, window, result, expected=None):
        try:
            if (result.status == 'verified' and result.snapshot is not None
                    and result.snapshot.window == window
                    and 0 <= time.monotonic() - result.sampled_at <= MAX_RESULT_AGE
                    and (expected is None or result.snapshot == expected)
                    and native_document.is_current(result.snapshot)):
                return result
        except Exception:
            pass
        return None

    def verify(self, window, expected, complete):
        # This also allows an already-running idle request to drain without making
        # a second worker. Its reply cannot satisfy this new capture generation.
        self.verification = (window, expected, complete, self.generation, time.monotonic() + 1.5)
        self.poll_identity()

    def poll_identity(self):
        if self.stopping:
            return
        reply = self.reader.poll()
        if reply is not None and self.identity_pending is not None:
            token, result = reply
            pending, kind, window, generation, expected, complete = self.identity_pending
            if token == pending:
                self.identity_pending = None
                if generation == self.generation:
                    checked = self.checked_identity(window, result, expected)
                    if kind == 'idle' and not self.busy:
                        if checked is None or not checked.eligible:
                            self.invalidate_automatic(window)
                        elif win32gui.GetForegroundWindow() == window.hwnd:
                            changed = (self.remembered != window or self.memory_blocked
                                       or self.chrome_memory != checked.snapshot)
                            self.remembered, self.chrome_memory = window, checked.snapshot
                            self.memory_blocked = False
                            if changed:
                                self.notice("Chrome target verified as chatgpt.com."
                                            f" PID={window.pid}, HWND={window.hwnd:#x}."
                                            + (" Manual binding still takes priority." if self.bound else ""))
                    elif kind == 'required' and self.verification is not None:
                        if time.monotonic() >= self.verification[4]:
                            checked = None
                        self.verification = None
                        if checked is None or not checked.eligible:
                            self.invalidate_automatic(window)
                            complete(None)
                        else:
                            complete(checked)
        if self.verification is not None:
            window, expected, complete, generation, deadline = self.verification
            if generation != self.generation:
                self.verification = None
            elif time.monotonic() >= deadline:
                self.verification = None
                self.invalidate_automatic(window)
                complete(None)
            elif self.identity_pending is None:
                token = self.reader.request(window)
                if token is not None:
                    self.identity_pending = (token, 'required', window, generation, expected, complete)

    def bind_target(self):
        window = native.inspect_window(win32gui.GetForegroundWindow())
        if not window or not window.supported:
            self.notice("Binding requires a supported browser or ChatGPT window in front.", True)
            return
        self.bound = window
        self.notice("Target bound for this run. Rebind if its tab/title changes.")

    def begin_capture(self):
        self.busy = True
        self.generation += 1
        self.target = self.target_document = None
        windows = native.list_windows()
        self.target_source = ("manual binding" if self.bound is not None else
                              "automatic memory" if self.remembered is not None else "discovery")
        if (self.bound is None and self.remembered is not None
                and self.remembered.process.lower() == 'chrome.exe'):
            if not self.memory_blocked and self.chrome_memory is not None and self.remembered in windows:
                window = self.remembered
                self.verify(window, self.chrome_memory,
                            lambda result: self.select_target(window if result else None, result))
            else:
                self.select_target(None)
        else:
            # Unobserved Chrome windows have no document evidence and cannot be
            # discovered by title. Other browsers retain their existing rule.
            self.select_target(choose_target(windows, self.remembered, self.bound))

    def select_target(self, target, result=None):
        self.target = target
        self.target_document = result.snapshot if result else None
        if self.target is not None:
            self.notice(f"Target selected via {self.target_source}: process={self.target.process}, "
                        f"PID={self.target.pid}, HWND={self.target.hwnd:#x}.")
        else:
            self.notice(f"No valid target via {self.target_source}; capture will stay on the clipboard. "
                        "Automatic target unavailable: browser identity could not be verified.")
        self.bounds = native.desktop_bounds()
        self.selector = Selector(self.root, self.bounds, self.selection_complete)

    def selection_complete(self, box):
        self.selector = None
        if box is None or self.stopping:
            self.generation += 1
            self.verification = None
            self.busy = False
            self.notice("Capture cancelled.")
            return
        # Destroy/hide has already happened. Let the desktop repaint before the
        # final live capture; do not take pixels from the translucent selector.
        self.root.after(120, lambda: self.capture(box))

    def capture(self, box):
        if self.stopping:
            return
        try:
            if native.desktop_bounds() != self.bounds:
                raise RuntimeError("Display layout changed; please capture again.")
            if native.dwmapi.DwmFlush() < 0:
                raise RuntimeError("Desktop composition did not settle; capture cancelled.")
            with ImageGrab.grab(bbox=box, all_screens=True) as image:
                if image.size != (box[2]-box[0], box[3]-box[1]):
                    raise RuntimeError("Capture size did not match the selection.")
                self.clipboard_sequence = native.copy_image(image, self.hwnd)
            if self.target is None:
                raise RuntimeError("No unchanged ChatGPT target found. Image copied; "
                                   "return to ChatGPT and Ctrl+V manually. G binds a target.")
            self.deadline = time.monotonic() + 2
            self.wait_keys()
        except Exception as exc:
            self.fail(exc)

    def wait_keys(self):
        if self.stopping:
            return
        try:
            if native.keys_down():
                if time.monotonic() >= self.deadline:
                    raise RuntimeError("Release keys/buttons. Image copied; paste manually.")
                self.root.after(30, self.wait_keys)
                return
            if self.target_document is not None:
                self.verify(self.target, self.target_document, self.activate_verified)
            else:
                self.activate_target()
        except Exception as exc:
            self.fail(exc)

    def activate_verified(self, result):
        if result is None:
            self.fail("Automatic paste blocked: target revalidation failed. Image copied; paste manually.")
            return
        self.activate_target()

    def activate_target(self):
        try:
            native.request_foreground(self.target)
            self.deadline = time.monotonic() + 1
            self.root.after(80, self.wait_focus)
        except Exception as exc:
            self.fail(exc)

    def wait_focus(self):
        if self.stopping:
            return
        try:
            if win32gui.GetForegroundWindow() != self.target.hwnd:
                if time.monotonic() >= self.deadline:
                    raise RuntimeError("Windows refused ChatGPT focus. Image copied; paste manually.")
                self.root.after(30, self.wait_focus)
                return
            if self.target_document is not None:
                self.verify(self.target, self.target_document, self.paste_verified)
            else:
                self.paste_target()
        except Exception as exc:
            self.fail(exc)

    def paste_verified(self, result):
        if result is None:
            self.fail("Automatic paste blocked: target revalidation failed. Image copied; paste manually.")
            return
        self.paste_target()

    def paste_target(self):
        try:
            native.paste(self.target, self.clipboard_sequence)
            self.busy = False
            self.notice("Ctrl+V issued. Check the composer; GPTSnip never sends the message.")
        except Exception as exc:
            self.fail(exc)

    def fail(self, error):
        self.generation += 1
        self.verification = None
        self.busy = False
        self.notice(str(error), True)

    def stop(self):
        self.stopping = True
        self.generation += 1
        self.verification = None
        self.reader.close()
        if self.selector:
            self.selector.finish(None)
        self.root.quit()

    def close(self):
        self.reader.close()
        for identifier in self.registered:
            win32gui.UnregisterHotKey(self.hwnd, identifier)
        if self.hwnd:
            win32gui.DestroyWindow(self.hwnd)
        if self.class_atom:
            win32gui.UnregisterClass(self.class_atom, self.instance)


def run():
    mutex = win32event.CreateMutex(None, False, "Local\\GPTSnipV0")
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        mutex.Close()
        print("GPTSnip is already running in this Windows session.")
        return 1
    root = app = None
    previous_signal = None
    try:
        native.enable_dpi_awareness()
        root = tk.Tk()
        root.withdraw()
        app = App(root)
        previous_signal = signal.signal(signal.SIGINT, lambda *_: app.stop())
        app.start()
        root.mainloop()
        return 0
    except Exception as exc:
        print(f"GPTSnip could not run: {exc}", flush=True)
        return 1
    finally:
        if previous_signal is not None:
            signal.signal(signal.SIGINT, previous_signal)
        if app:
            app.close()
        if root:
            root.destroy()
        mutex.Close()
