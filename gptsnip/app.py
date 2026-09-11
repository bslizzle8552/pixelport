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

from . import __version__
from .core import choose_target
from .browser import BrowserReader, MAX_RESULT_AGE, identity_diagnostic
from . import native_document
from .selector import Selector
from .mouse import MouseHook
from .middle_diagnostics import MiddleDiagnostics
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
        self.mouse_hook = None
        self.middle_id = None
        self.middle_box = None
        self.middle_target_ready = False
        self.next_mouse_health = 0
        self.last_mouse_sample = None
        self.middle_diagnostics = MiddleDiagnostics()
        self.instance = win32api.GetModuleHandle(None)
        self.root.report_callback_exception = self.callback_error

    def start(self):
        cls = win32gui.WNDCLASS()
        cls.hInstance = self.instance
        cls.lpszClassName = "GPTSnipV0Hotkeys"
        cls.lpfnWndProc = self.window_proc
        self.class_atom = win32gui.RegisterClass(cls)
        self.hwnd = win32gui.CreateWindow(self.class_atom, "PixelPort", 0,
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
        self.start_mouse()
        self.trace_middle("startup ready")
        print(f"PixelPort v{__version__} ready. Hold wheel + drag + release: capture | Ctrl+Alt+Shift+S: keyboard capture "
              "| Ctrl+Alt+Shift+G: manual override | Ctrl+Alt+Shift+Q: quit", flush=True)
        print("Click your ChatGPT web composer in Chrome; verified chatgpt.com is remembered automatically. "
              "Keep that tab active in its window. Ctrl+Alt+Shift+G is an optional override.", flush=True)
        self.root.after(30, self.tick)

    def start_mouse(self):
        hook = None
        try:
            hook = MouseHook()
            hook.start()
        except Exception as exc:
            if hook is not None:
                hook.close()
            self.notice(f"Middle-mouse trigger unavailable; keyboard capture remains active. {exc}")
        else:
            self.mouse_hook = hook
            self.notice("Middle-click belongs to PixelPort while running; wheel scrolling is unchanged.")

    def reset_middle(self):
        if self.mouse_hook and self.middle_id is not None:
            self.mouse_hook.state.acknowledged = self.middle_id
        self.middle_id = None
        self.middle_box = None
        self.middle_target_ready = False

    def trace_middle(self, event, selector=None, **fields):
        self.middle_diagnostics.emit(self, event, selector, **fields)

    def cancel_selection(self, reason):
        if self.selector:
            self.selector.finish(None, reason)
        else:
            self.selection_complete(None, reason)

    def poll_mouse(self):
        hook = self.mouse_hook
        if hook is None:
            return
        if hook.error:
            if self.middle_id is not None:
                self.cancel_selection("mouse hook runtime error")
            hook.close()
            self.mouse_hook = None
            self.notice(f"Middle-mouse trigger unavailable; keyboard capture remains active. {hook.error}")
            return
        state = hook.state
        gesture = state.gesture
        if gesture is not None and gesture.serial > state.acknowledged:
            if self.middle_id is None:
                if self.busy or gesture.cancelled:
                    self.trace_middle("gesture not admitted", reason=(
                        "another capture is busy" if self.busy else "gesture expired before admission"))
                    state.acknowledged = gesture.serial
                else:
                    self.begin_capture(gesture)
            if (self.middle_id == gesture.serial and self.selector
                    and gesture is not self.last_mouse_sample):
                self.last_mouse_sample = gesture
                if gesture.cancelled:
                    self.cancel_selection("60-second hold limit or missing release")
                elif native.desktop_bounds() != self.bounds:
                    self.cancel_selection("display layout changed: gesture sample")
                else:
                    self.selector.move_to(gesture.point)
                    if gesture.released:
                        self.trace_middle("physical middle release consumed")
                        if self.selector.middle_box(gesture.point) is None:
                            self.notice("Middle-mouse capture ignored: drag below threshold (6 pixels per dimension).")
                        self.selector.middle_release(gesture.point)
            # Focus/display loss also cancels a stationary held gesture.
        if self.middle_id is not None and self.selector and time.monotonic() >= self.next_mouse_health:
            self.next_mouse_health = time.monotonic() + 0.25
            if native.desktop_bounds() != self.bounds:
                self.cancel_selection("display layout changed: periodic mouse health check")
            else:
                self.selector.check_focus()
        state.accepting = not self.busy and not self.stopping

    def window_proc(self, hwnd, message, wparam, lparam):
        if message == win32con.WM_HOTKEY:
            # The native callback never performs UI work reentrantly.
            self.actions.append(wparam)
            return 0
        return win32gui.DefWindowProc(hwnd, message, wparam, lparam)

    def notice(self, text, error=False):
        print(f"PixelPort: {text}", flush=True)
        if error:
            win32api.MessageBeep(win32con.MB_ICONEXCLAMATION)

    def callback_error(self, kind, error, traceback):
        self.trace_middle("Tk callback exception", error_type=kind.__name__)
        self.generation += 1
        self.verification = None
        self.busy = False
        if self.selector:
            self.selector.finish(None, "Tk callback exception: " + kind.__name__)
            self.selector = None
        elif self.middle_id is not None:
            self.notice("Middle-mouse capture cancelled: Tk callback exception: " + kind.__name__ + ".")
        self.reset_middle()
        self.notice(str(error), error=True)

    def tick(self):
        if self.stopping:
            return
        now = time.monotonic()
        self.middle_diagnostics.poll(self)
        try:
            self.poll_mouse()
        except Exception as exc:
            self.fail(exc)
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
                    identity_diagnostic('Chrome foreground candidate observed', token,
                                        hwnd=hex(hwnd), pid=foreground.pid)
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

    def checked_identity(self, window, result, expected=None, token=None):
        try:
            if result.status != 'verified' or result.snapshot is None:
                reason = 'unverified document'
            elif result.snapshot.window != window:
                reason = 'window identity changed'
            elif not 0 <= time.monotonic() - result.sampled_at <= MAX_RESULT_AGE:
                reason = 'stale sample'
            elif expected is not None and result.snapshot != expected:
                reason = 'capture identity changed'
            elif not native_document.is_current(result.snapshot):
                reason = 'native identity changed'
            else:
                return result
        except Exception:
            reason = 'identity check unavailable'
        identity_diagnostic('result rejected: ' + reason, token)
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
            self.trace_middle("Chrome verification reply", token=token, kind=kind,
                              status=result.status, eligible=result.eligible,
                              request_generation=generation)
            identity_diagnostic('App consumed result', token, kind=kind,
                                status=result.status, reason=result.reason)
            if token == pending:
                self.identity_pending = None
                if generation == self.generation:
                    checked = self.checked_identity(window, result, expected, token)
                    identity_diagnostic('App identity check', token, accepted=checked is not None,
                                        eligible=bool(checked and checked.eligible))
                    if kind == 'idle' and not self.busy:
                        if checked is None or not checked.eligible:
                            self.invalidate_automatic(window)
                        elif win32gui.GetForegroundWindow() == window.hwnd:
                            changed = (self.remembered != window or self.memory_blocked
                                       or self.chrome_memory != checked.snapshot)
                            self.remembered, self.chrome_memory = window, checked.snapshot
                            self.memory_blocked = False
                            identity_diagnostic('automatic Chrome target remembered', token, host=checked.host)
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
                else:
                    identity_diagnostic('result rejected: capture generation changed', token)
            else:
                identity_diagnostic('result rejected: stale App token', token)
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

    def begin_capture(self, gesture=None):
        if self.busy or self.stopping:
            if gesture is not None:
                self.trace_middle("gesture not admitted", reason="busy or stopping")
            return
        if gesture is not None:
            self.trace_middle("middle admission before overlay")
        self.busy = True
        if self.mouse_hook:
            self.mouse_hook.state.accepting = False
        self.generation += 1
        self.target = self.target_document = None
        if gesture is not None:
            self.middle_id = gesture.serial
            self.middle_box = None
            self.middle_target_ready = False
            self.bounds = native.desktop_bounds()
            self.selector = Selector(self.root, self.bounds, self.selection_complete,
                                     middle_start=gesture.start,
                                     diagnostic=(self.trace_middle if self.middle_diagnostics.enabled else None))
            self.trace_middle("middle selector constructed")
            self.notice("Middle-mouse capture started.")
            self.selector.establish_foreground()
            if self.selector is None:
                return  # Acquisition cancelled; do not start target resolution.
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
        self.trace_middle("capture target resolved", verified=bool(result and result.eligible))
        if self.target is not None:
            self.notice(f"Target selected via {self.target_source}: process={self.target.process}, "
                        f"PID={self.target.pid}, HWND={self.target.hwnd:#x}.")
        else:
            self.notice(f"No valid target via {self.target_source}; capture will stay on the clipboard. "
                        "Automatic target unavailable: browser identity could not be verified.")
        if self.middle_id is not None:
            # Show the held-button overlay immediately; preserve the existing
            # first fresh target check before allowing capture/paste to proceed.
            self.middle_target_ready = True
            if self.middle_box is not None:
                self.selection_complete(self.middle_box)
        else:
            self.bounds = native.desktop_bounds()
            self.selector = Selector(self.root, self.bounds, self.selection_complete)

    def selection_complete(self, box, reason=None):
        reason = reason or (self.selector.cancel_reason if self.selector else None)
        if box is None or self.stopping:
            reason = reason or ("application stopping" if self.stopping else "selection cancelled by caller")
        self.trace_middle("selection completion", box=box, reason=reason)
        self.selector = None
        if box is None or self.stopping:
            self.generation += 1
            self.verification = None
            self.busy = False
            self.notice(f"Middle-mouse capture cancelled: {reason}."
                        if self.middle_id is not None else "Capture cancelled.")
            self.reset_middle()
            return
        if self.middle_id is not None:
            if not self.middle_target_ready:
                self.middle_box = box
                return
            self.reset_middle()
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
            self.notice("Ctrl+V issued. Check the composer; PixelPort never sends the message.")
            self.trace_middle("Ctrl+V issued")
        except Exception as exc:
            self.fail(exc)

    def fail(self, error):
        self.trace_middle("capture flow failure", error_type=type(error).__name__)
        self.generation += 1
        self.verification = None
        self.busy = False
        if self.middle_id is not None:
            if self.selector:
                self.selector.finish(None, "capture flow failure: " + type(error).__name__)
            else:
                self.notice("Middle-mouse capture cancelled: capture flow failure: "
                            + type(error).__name__ + ".")
            self.reset_middle()
        self.notice(str(error), True)

    def stop(self):
        self.stopping = True
        self.generation += 1
        self.verification = None
        if self.mouse_hook:
            self.mouse_hook.close()
        self.reader.close()
        if self.selector:
            self.selector.finish(None, "application quit")
        self.root.quit()

    def close(self):
        self.stopping = True
        if self.mouse_hook:
            self.mouse_hook.close()
            if self.mouse_hook.error:
                self.notice(self.mouse_hook.error)
        if self.selector:
            self.selector.finish(None, "application cleanup")
        self.reset_middle()
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
        print("PixelPort is already running in this Windows session.")
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
        print(f"PixelPort could not run: {exc}", flush=True)
        return 1
    finally:
        if previous_signal is not None:
            signal.signal(signal.SIGINT, previous_signal)
        if app:
            app.close()
        if root:
            root.destroy()
        mutex.Close()
