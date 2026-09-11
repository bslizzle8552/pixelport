"""A transient translucent selector. Coordinates always come from Win32."""

import tkinter as tk

import win32api
import win32con
import win32gui

from .core import selection_box
from .windows import acquire_selector_foreground

MIN_MIDDLE_DRAG = 6  # Physical pixels in BOTH dimensions after clipping.


class Selector:
    def __init__(self, root, bounds, complete, middle_start=None, diagnostic=None):
        self.bounds, self.complete = bounds, complete
        self.diagnostic = diagnostic
        self.cancel_reason = None
        self.lifecycle = "constructing"
        self.start = middle_start
        self.middle = middle_start is not None
        self.source_foreground = win32gui.GetForegroundWindow() if self.middle else None
        self.foreground_established = False
        self.activation_attempted = False
        self.closed = False
        self.window = tk.Toplevel(root)
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True, "-alpha", 0.35)
        self.canvas = tk.Canvas(self.window, bg="black", highlightthickness=0,
                                borderwidth=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)
        self.rectangle = self.canvas.create_rectangle(0, 0, 0, 0, outline="#00ffff", width=3)
        x, y = middle_start if self.middle else win32api.GetCursorPos()
        self.canvas.create_text(x - bounds[0], y - bounds[1] + 28,
                                text=("Hold wheel and drag · Release to capture · Esc to cancel"
                                      if self.middle else "Drag to capture · Esc to cancel"),
                                fill="white", anchor="n")
        self.window.bind("<Escape>", lambda _: self.finish(None, "Escape"))
        if not self.middle:
            self.canvas.bind("<ButtonPress-1>", self.press)
            self.canvas.bind("<B1-Motion>", self.drag)
            self.canvas.bind("<ButtonRelease-1>", self.release)
        self.window.protocol("WM_DELETE_WINDOW", lambda: self.finish(None, "selector window close"))
        self.window.update_idletasks()
        self.hwnd = win32gui.GetAncestor(self.window.winfo_id(), win32con.GA_ROOT)
        self.trace("selector before show")
        left, top, right, bottom = bounds
        # Tk's negative geometry offsets mean "from right/bottom". SetWindowPos
        # instead places the client exactly at the physical virtual-screen origin.
        self.window.geometry(f"{right-left}x{bottom-top}+0+0")
        self.window.deiconify()
        self.window.update_idletasks()
        self.observe_foreground_ownership()
        self.trace("selector after deiconify")
        win32gui.SetWindowPos(self.hwnd, win32con.HWND_TOPMOST, left, top,
                             right-left, bottom-top, win32con.SWP_SHOWWINDOW)
        self.observe_foreground_ownership()
        self.trace("selector after SetWindowPos")
        self.window.focus_force()
        self.observe_foreground_ownership()
        self.trace("selector after focus_force")
        self.window.grab_set()
        self.observe_foreground_ownership()
        self.lifecycle = "selecting"
        self.trace("selector after grab_set")
        def focus_out(_):
            self.trace("selector Tk FocusOut")
            root.after_idle(lambda: self.check_focus("Tk FocusOut idle check"))
        self.window.bind("<FocusOut>", focus_out)
        if diagnostic is not None:
            self.window.bind("<FocusIn>", lambda _: self.trace("selector Tk FocusIn"))

    def establish_foreground(self):
        """Called after App owns this selector, before admitting drag/release."""
        if self.closed or not self.middle or self.foreground_established:
            return
        foreground = win32gui.GetForegroundWindow()
        if foreground == self.hwnd:
            self.foreground_established = True
        elif foreground == self.source_foreground and not self.activation_attempted:
            self.activation_attempted = True
            self.lifecycle = "activating"
            self.trace("selector native foreground acquisition requested")
            acquire_selector_foreground(self.hwnd, self.source_foreground)
            self.foreground_established = win32gui.GetForegroundWindow() == self.hwnd
            self.trace("selector native foreground acquisition completed",
                       acquired=self.foreground_established)
        self.lifecycle = "selecting"
        # No grace period accepts a capture without actual foreground ownership.
        self.check_focus("selector activation check")

    def observe_foreground_ownership(self):
        if win32gui.GetForegroundWindow() == self.hwnd:
            self.foreground_established = True

    def trace(self, event, **fields):
        if self.diagnostic is not None:
            self.diagnostic(event, selector=self, **fields)

    def check_focus(self, trigger="periodic mouse health check"):
        if self.closed:
            return
        foreground = win32gui.GetForegroundWindow()
        if foreground == self.hwnd:
            self.foreground_established = True
            return
        if foreground != self.hwnd:
            self.trace("selector foreground mismatch", trigger=trigger,
                       compared_foreground=foreground, expected_foreground=self.hwnd)
            reason = ("selector foreground not acquired: " if self.middle and not self.foreground_established
                      else "foreground differs from selector: ")
            self.finish(None, reason + trigger)

    def press(self, _):
        self.start = win32api.GetCursorPos()

    def drag(self, _):
        self.move_to(win32api.GetCursorPos())

    def move_to(self, point):
        if self.closed:
            return
        if self.start is not None:
            box = selection_box(self.start, point, self.bounds)
            if box:
                l, t, r, b = box
                x, y = self.bounds[:2]
                self.canvas.coords(self.rectangle, l-x, t-y, r-x, b-y)
            else:
                self.canvas.coords(self.rectangle, 0, 0, 0, 0)

    def middle_release(self, point):
        if self.closed:
            return
        self.check_focus("middle release check")
        if self.closed:
            return
        box = self.middle_box(point)
        self.finish(box, "drag below threshold (6 pixels per dimension)" if box is None else None)

    def middle_box(self, point):
        box = selection_box(self.start, point, self.bounds)
        if box and box[2] - box[0] >= MIN_MIDDLE_DRAG and box[3] - box[1] >= MIN_MIDDLE_DRAG:
            return box
        return None

    def release(self, _):
        if self.start is not None:
            self.finish(selection_box(self.start, win32api.GetCursorPos(), self.bounds),
                        "empty keyboard selection")

    def finish(self, box, reason=None):
        if self.closed:
            return
        self.cancel_reason = (reason or "selection cancelled by caller") if box is None else None
        self.lifecycle = "closing"
        self.trace("selector finish", reason=self.cancel_reason, box=box)
        self.closed = True
        self.window.grab_release()
        self.window.withdraw()
        self.window.destroy()
        self.lifecycle = "destroyed"
        self.complete(box)
