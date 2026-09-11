"""A transient translucent selector. Coordinates always come from Win32."""

import tkinter as tk

import win32api
import win32con
import win32gui

from .core import selection_box


class Selector:
    def __init__(self, root, bounds, complete):
        self.bounds, self.complete = bounds, complete
        self.start = None
        self.closed = False
        self.window = tk.Toplevel(root)
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True, "-alpha", 0.35)
        self.canvas = tk.Canvas(self.window, bg="black", highlightthickness=0,
                                borderwidth=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)
        self.rectangle = self.canvas.create_rectangle(0, 0, 0, 0, outline="#00ffff", width=3)
        x, y = win32api.GetCursorPos()
        self.canvas.create_text(x - bounds[0], y - bounds[1] + 28,
                                text="Drag to capture · Esc to cancel", fill="white", anchor="n")
        self.window.bind("<Escape>", lambda _: self.finish(None))
        self.canvas.bind("<ButtonPress-1>", self.press)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<ButtonRelease-1>", self.release)
        self.window.protocol("WM_DELETE_WINDOW", lambda: self.finish(None))
        self.window.update_idletasks()
        self.hwnd = win32gui.GetAncestor(self.window.winfo_id(), win32con.GA_ROOT)
        left, top, right, bottom = bounds
        # Tk's negative geometry offsets mean "from right/bottom". SetWindowPos
        # instead places the client exactly at the physical virtual-screen origin.
        self.window.geometry(f"{right-left}x{bottom-top}+0+0")
        self.window.deiconify()
        self.window.update_idletasks()
        win32gui.SetWindowPos(self.hwnd, win32con.HWND_TOPMOST, left, top,
                             right-left, bottom-top, win32con.SWP_SHOWWINDOW)
        self.window.focus_force()
        self.window.grab_set()
        self.window.bind("<FocusOut>", lambda _: root.after_idle(self.check_focus))

    def check_focus(self):
        if not self.closed and win32gui.GetForegroundWindow() != self.hwnd:
            self.finish(None)

    def press(self, _):
        self.start = win32api.GetCursorPos()

    def drag(self, _):
        if self.start is not None:
            box = selection_box(self.start, win32api.GetCursorPos(), self.bounds)
            if box:
                l, t, r, b = box
                x, y = self.bounds[:2]
                self.canvas.coords(self.rectangle, l-x, t-y, r-x, b-y)

    def release(self, _):
        if self.start is not None:
            self.finish(selection_box(self.start, win32api.GetCursorPos(), self.bounds))

    def finish(self, box):
        if self.closed:
            return
        self.closed = True
        self.window.grab_release()
        self.window.withdraw()
        self.window.destroy()
        self.complete(box)
