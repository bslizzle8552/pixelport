"""External onedir acceptance probe; never bundled and never captures or pastes.

Run with a known existing Chrome HWND: python packaging/frozen_smoke.py --chrome-hwnd N
It passively observes that already-selected window, launches the real EXE hidden,
reads existing opt-in metadata, and posts Q only to PixelPort's own hotkey window.
Duplicate refusal is a separate final run with identity timing disabled.
Do not perform middle gestures while this short probe is running.
"""

import argparse
import ctypes as ct
from ctypes import wintypes as wt
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time

import win32api
import win32clipboard
import win32con
import win32event
import win32gui
import win32process


kernel32 = ct.WinDLL("kernel32", use_last_error=True)
kernel32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ct.POINTER(wt.DWORD)]
kernel32.QueryFullProcessImageNameW.restype = wt.BOOL


class ProcessEntry(ct.Structure):
    _fields_ = [('size', wt.DWORD), ('usage', wt.DWORD), ('pid', wt.DWORD),
                ('heap', ct.c_size_t), ('module', wt.DWORD), ('threads', wt.DWORD),
                ('parent', wt.DWORD), ('priority', wt.LONG), ('flags', wt.DWORD),
                ('exe', wt.WCHAR * 260)]


def process_parents():
    """Native snapshot for distinguishing ONEFILE bootloader/app/worker processes."""
    kernel32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wt.HANDLE
    kernel32.Process32FirstW.argtypes = [wt.HANDLE, ct.POINTER(ProcessEntry)]
    kernel32.Process32NextW.argtypes = [wt.HANDLE, ct.POINTER(ProcessEntry)]
    kernel32.CloseHandle.argtypes = [wt.HANDLE]
    handle = kernel32.CreateToolhelp32Snapshot(2, 0)
    if handle == ct.c_void_p(-1).value:
        raise ct.WinError(ct.get_last_error())
    entry = ProcessEntry(size=ct.sizeof(ProcessEntry))
    result = {}
    try:
        more = kernel32.Process32FirstW(handle, ct.byref(entry))
        while more:
            result[entry.pid] = entry.parent
            more = kernel32.Process32NextW(handle, ct.byref(entry))
    finally:
        kernel32.CloseHandle(handle)
    return result


def owns_hotkey(hwnd, root_pid, onefile=False):
    pid = win32process.GetWindowThreadProcessId(hwnd)[1]
    if pid == root_pid:
        return True
    return onefile and process_parents().get(pid) == root_pid and pid in processes()

def processes():
    found = {}
    for pid in win32process.EnumProcesses():
        if not pid:
            continue
        try:
            handle = win32api.OpenProcess(0x1000, False, pid)
            try:
                buffer, size = ct.create_unicode_buffer(32768), wt.DWORD(32768)
                if not kernel32.QueryFullProcessImageNameW(int(handle), 0, buffer, ct.byref(size)):
                    raise ct.WinError(ct.get_last_error())
                path = buffer.value
                if Path(path).name.lower() == 'pixelport.exe':
                    found[pid] = path
            finally:
                handle.Close()
        except (win32api.error, OSError):
            pass
    return found


def run(exe, chrome, cycle, output):
    assert not processes(), 'Quit every PixelPort EXE before frozen smoke'
    assert win32gui.IsWindow(chrome), 'Chrome HWND no longer exists'
    clipboard = win32clipboard.GetClipboardSequenceNumber()
    trace = output / f'cycle-{cycle}.jsonl'
    assert not trace.exists(), 'Use a fresh output directory to preserve evidence'
    environment = os.environ.copy()
    for key in list(environment):
        if key.startswith(('PYTHON', 'GPTSNIP_', '_PYI')) or key in ('TCL_LIBRARY', 'TK_LIBRARY'):
            environment.pop(key)
    environment['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
    environment.update(GPTSNIP_IDENTITY_DIAGNOSTICS='1', GPTSNIP_MIDDLE_DIAGNOSTICS='1',
                       GPTSNIP_MIDDLE_DIAGNOSTIC_FILE=str(trace))
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    started = time.perf_counter()
    app = subprocess.Popen([str(exe)], cwd=output, env=environment,
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace',
                           startupinfo=startup, creationflags=subprocess.CREATE_NEW_CONSOLE)
    lines = []
    def consume():
        for line in app.stdout:
            lines.append((time.perf_counter() - started, line.rstrip()))
    reader = threading.Thread(target=consume, daemon=True)
    reader.start()
    hwnd = None
    hook_handle = None
    tracked = set()
    try:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            candidate = win32gui.FindWindow('GPTSnipV0Hotkeys', None)
            if candidate and win32process.GetWindowThreadProcessId(candidate)[1] == app.pid:
                hwnd = candidate
            if any('PixelPort v0.1.0 ready.' in line for _, line in lines) and hwnd:
                break
            assert app.poll() is None, 'Frozen startup exited: ' + repr(lines)
            time.sleep(.03)
        else:
            raise AssertionError('No frozen startup banner/hotkey window')
        assert trace.exists(), 'No native startup trace'
        records = [json.loads(line) for line in trace.read_text(encoding='utf-8').splitlines()]
        ready = next(r for r in records if r['event'] == 'startup ready')
        hook = ready['state']['hook']
        assert hook['installed'] and not hook['error_present'] and hook['thread']
        hook_handle = win32api.OpenThread(0x100000, False, hook['thread'])
        # No activation or navigation: the user selects Chrome; App remains authoritative.
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            current = processes()
            assert app.pid in current, 'Cannot inspect the launched process'
            tracked.update(current)
            assert len(current) <= 2, 'Unexpected recursive/extra frozen process'
            text = '\n'.join(line for _, line in lines)
            assert 'Traceback' not in text and 'could not run' not in text, text
            assert 'timeout' not in text and 'deadline' not in text, 'Frozen reader deadline failed: ' + text
            if text.count('transport delivered result') >= 4:
                break
            time.sleep(.05)
        else:
            raise AssertionError('Insufficient frozen reader replies: ' + repr(lines))
        text = '\n'.join(line for _, line in lines)
        assert text.count('PixelPort v0.1.0 ready.') == 1
        assert text.count('browser worker started') == 1, 'Expected exactly one worker'
        assert 'worker received request' in text and 'native result' in text
        assert 'automatic Chrome target remembered' in text, 'Selected document did not verify as ChatGPT'
        assert 'Ctrl+V issued' not in text and 'capture started' not in text
        assert win32clipboard.GetClipboardSequenceNumber() == clipboard
        workers = [int(re.search(r'pid=(\d+)', line)[1]) for _, line in lines if 'browser worker started' in line]
        assert len(workers) == 1 and workers[0] != app.pid
        tracked.update(workers)
        child_windows = []
        win32gui.EnumWindows(lambda w, _: child_windows.append(w)
                             if win32process.GetWindowThreadProcessId(w)[1] == workers[0] else None, None)
        assert not child_windows, 'Worker unexpectedly created windows'
        request_times = {}
        latencies = []
        for stamp, line in lines:
            token = re.search(r'token=(\d+)', line)
            if not token:
                continue
            token = int(token[1])
            if 'request admitted' in line:
                request_times[token] = stamp
            if 'transport delivered result' in line and token in request_times:
                latencies.append(round((stamp-request_times[token])*1000, 2))
        summary = dict(cycle=cycle, startup_ms=round(next(t for t,l in lines if 'ready.' in l)*1000, 2),
                       request_roundtrip_ms=latencies, one_worker=True,
                       hook_installed=True, child_windows=0, clipboard_unchanged=True)
    finally:
        if hwnd and win32gui.IsWindow(hwnd):
            win32gui.PostMessage(hwnd, win32con.WM_HOTKEY, 3, 0)
        try:
            app.wait(timeout=8)
        except subprocess.TimeoutExpired:
            app.terminate()
            app.wait(timeout=5)
            raise AssertionError('Frozen application required forced termination')
        finally:
            reader.join(3)
            (output / f'cycle-{cycle}.log').write_text('\n'.join(f'{t:.6f} {l}' for t,l in lines)+'\n', encoding='utf-8')
    assert app.returncode == 0, 'Q shutdown failed'
    assert hook_handle is not None
    try:
        assert win32event.WaitForSingleObject(hook_handle, 2000) == win32con.WAIT_OBJECT_0
    finally:
        hook_handle.Close()
    assert not processes(), 'Orphan PixelPort worker remains'
    assert win32clipboard.GetClipboardSequenceNumber() == clipboard
    assert not any('could not remove' in line or 'did not stop' in line for _,line in lines)
    for identifier,key in ((1,'S'),(2,'G'),(3,'Q')):
        win32gui.RegisterHotKey(None, identifier, 0x4000 | win32con.MOD_CONTROL | win32con.MOD_ALT | win32con.MOD_SHIFT, ord(key))
        win32gui.UnregisterHotKey(None, identifier)
    summary.update(q_exit_code=app.returncode, hook_thread_exited=True, no_orphans=True, hotkeys_released=True)
    return summary


def duplicate_only(exe, output, onefile=False):
    """After all measured cycles: no reader timing or opt-in diagnostics here."""
    assert not processes(), 'Existing instance before separate duplicate check'
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(('GPTSNIP_', 'PYTHON', '_PYI')) or key in ('TCL_LIBRARY', 'TK_LIBRARY'):
            env.pop(key)
    env['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
    if onefile:
        temp = output / 'extraction-temp'
        temp.mkdir(exist_ok=False)
        env['TEMP'] = env['TMP'] = str(temp)
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    sequence = win32clipboard.GetClipboardSequenceNumber()
    log = output / 'duplicate-only.log'
    assert not log.exists(), 'Use fresh output'
    hwnd = None
    with log.open('w', encoding='utf-8') as stream:
        app = subprocess.Popen([str(exe)], cwd=output, env=env, stdin=subprocess.DEVNULL,
                               stdout=stream, stderr=subprocess.STDOUT, startupinfo=startup,
                               creationflags=subprocess.CREATE_NO_WINDOW if onefile else subprocess.CREATE_NEW_CONSOLE)
        try:
            end = time.monotonic() + 8
            while time.monotonic() < end:
                candidate = win32gui.FindWindow('GPTSnipV0Hotkeys', None)
                if candidate and owns_hotkey(candidate, app.pid, onefile):
                    hwnd = candidate
                if hwnd and 'v0.1.0 ready.' in log.read_text(encoding='utf-8'):
                    break
                assert app.poll() is None, 'Original failed startup'
                time.sleep(.05)
            else:
                raise AssertionError('Original startup did not complete')
            time.sleep(2)  # Startup settles; no BrowserReader timings are collected.
            duplicate = subprocess.run([str(exe)], cwd=output, env=env,
                                       stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                       timeout=8, startupinfo=startup,
                                       creationflags=subprocess.CREATE_NO_WINDOW if onefile else subprocess.CREATE_NEW_CONSOLE)
            assert duplicate.returncode == 1 and 'PixelPort is already running' in duplicate.stdout
            assert 'ready.' not in duplicate.stdout and app.poll() is None
        finally:
            if hwnd and win32gui.IsWindow(hwnd):
                win32gui.PostMessage(hwnd, win32con.WM_HOTKEY, 3, 0)
            try:
                app.wait(timeout=8)
            except subprocess.TimeoutExpired:
                app.terminate()
                app.wait(timeout=5)
                raise AssertionError('Duplicate test original required forced termination')
    assert app.returncode == 0 and not processes()
    assert win32clipboard.GetClipboardSequenceNumber() == sequence
    if onefile:
        assert not list(temp.glob('_MEI*')), 'ONEFILE extraction directory not cleaned'
    return dict(duplicate_refused=True, original_q_exit_code=0, no_orphans=True,
                clipboard_unchanged=True, reader_timing_disabled=True,
                extraction_cleaned=True if onefile else None,
                residual_temp_entries=[p.name for p in temp.iterdir()] if onefile else [])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chrome-hwnd', type=int, required=True)
    parser.add_argument('--exe', type=Path, default=Path('dist/PixelPort/PixelPort.exe'))
    parser.add_argument('--output', type=Path, default=Path('build/frozen-smoke'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    result = [run(args.exe.resolve(), args.chrome_hwnd, n, args.output.resolve()) for n in (1,2)]
    result = dict(cycles=result, duplicate=duplicate_only(args.exe.resolve(), args.output.resolve()))
    (args.output/'summary.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
