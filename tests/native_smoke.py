r"""Opt-in native lifecycle check; no screen capture, clipboard writes, or injected input.

Run from the repository: .venv\Scripts\python.exe tests\native_smoke.py
Temporarily registers the real shortcuts and middle-button hook, then releases them.
"""

from pathlib import Path
import subprocess
import sys
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import win32api
import win32con
import win32event
import win32gui
import winerror

from gptsnip.app import App, HOTKEYS
from gptsnip import windows as native


def main():
    native.enable_dpi_awareness()
    mutex = win32event.CreateMutex(None, False, "Local\\GPTSnipV0")
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        mutex.Close()
        raise RuntimeError("Quit the running GPTSnip before this smoke test.")
    root = tk.Tk()
    root.withdraw()
    app = App(root)
    try:
        duplicate = subprocess.run([sys.executable, "-m", "gptsnip"],
                                   capture_output=True, text=True, timeout=10)
        assert duplicate.returncode == 1 and "already running" in duplicate.stdout
        app.start()
        assert app.mouse_hook is not None, "Native mouse hook failed to install"
        hook = app.mouse_hook
        # Exercise ownership/lifecycle only, never admit a physical capture during
        # this automated smoke. Busy also prevents the UI timer rearming admission.
        app.busy = True
        hook.state.accepting = False
        hook.state.acknowledged = hook.state.serial
        assert hook._hook and hook._thread.is_alive()
        # Exercise native message dispatch through Tk's Windows event loop, without
        # synthesizing a real keyboard shortcut or interacting with another app.
        win32gui.PostMessage(app.hwnd, win32con.WM_HOTKEY, 3, 0)
        root.after(2000, root.quit)
        root.mainloop()
        assert app.stopping, "WM_HOTKEY did not reach the application"
        assert not hook._thread.is_alive(), "Mouse message-loop thread survived quit"
        assert hook._hook is None and hook._thread_id is None
        assert hook.error is None, hook.error
    finally:
        app.close()
        root.destroy()
        mutex.Close()
    for identifier, key in HOTKEYS.items():
        win32gui.RegisterHotKey(None, identifier, 0x4000 | win32con.MOD_CONTROL
                                | win32con.MOD_ALT | win32con.MOD_SHIFT, key)
        win32gui.UnregisterHotKey(None, identifier)
    print("PASS: native startup, three registrations, WH_MOUSE_LL install/unhook/thread exit, "
          "WM_HOTKEY dispatch, duplicate guard, cleanup.")
    print("No screenshot, clipboard write, foreground switch, or SendInput was performed.")


if __name__ == "__main__":
    main()
