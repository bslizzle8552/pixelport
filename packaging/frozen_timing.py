"""Passive existing-EXE timing: no focus, navigation, capture, paste, or duplicates.

Leave an existing Chrome window foreground. Logs stay in an ignored fresh build
directory. Timestamped stdout is approximate; supervisor receipt is not logged by
the existing candidate. A Q message goes only to this launch's own hotkey HWND.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time

import win32api
import win32clipboard
import win32con
import win32event
import win32gui
import win32process

from frozen_smoke import processes, process_parents, owns_hotkey


def summarize(lines):
    requests = {}
    for stamp, line in lines:
        match = re.search(r'identity: token=(\d+) (.*)', line)
        if not match:
            continue
        token, event = int(match[1]), match[2]
        row = requests.setdefault(token, {'token': token})
        for marker, field in (
            ('request admitted', 'admission'),
            ('supervisor received request', 'supervisor_admission'),
            ('browser worker started', 'worker_started'),
            ('worker received request', 'worker_received'),
            ('native renderer candidates', 'first_native_snapshot'),
            ('native result', 'native_complete'),
            ('transport delivered result', 'app_poll'),
            ('result rejected: deadline', 'app_deadline_rejection'),
            ('App consumed result', 'app_consumed'),
        ):
            if event.startswith(marker):
                row.setdefault(field, stamp)
        if event.startswith('native result'):
            status = re.search(r'status=(\S+)', event)[1]
            host = re.search(r'host=(\S+)', event)[1]
            row['document'] = ('eligible' if host == 'chatgpt.com' else 'non-target') if status == 'verified' else 'unknown'
        if event.startswith('App consumed result'):
            row['result_status'] = re.search(r'status=(\S+)', event)[1]
            row['reason'] = event.partition('reason=')[2]
    for row in requests.values():
        for name, start, end in (
            ('request_native_ms', 'admission', 'native_complete'),
            ('request_app_ms', 'admission', 'app_consumed'),
            ('bootstrap_ms', 'worker_started', 'worker_received'),
            ('admission_to_worker_ms', 'admission', 'worker_received'),
            ('native_phase_ms', 'worker_received', 'native_complete'),
        ):
            if start in row and end in row:
                row[name] = round((row[end] - row[start]) * 1000, 3)
    return list(requests.values())


def run_cycle(exe, output, number, reads, limit, onefile=False):
    assert not processes(), 'Existing PixelPort process: stop before timing'
    time.sleep(1)
    assert not processes(), 'Orphan process appeared before launch'
    trace = output / f'cycle-{number}.jsonl'
    assert not trace.exists(), 'Use a fresh output directory'
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(('PYTHON', 'GPTSNIP_', '_PYI')) or key in ('TCL_LIBRARY', 'TK_LIBRARY'):
            env.pop(key)
    env['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
    env.update(GPTSNIP_IDENTITY_DIAGNOSTICS='1', GPTSNIP_MIDDLE_DIAGNOSTICS='1',
               GPTSNIP_MIDDLE_DIAGNOSTIC_FILE=str(trace))
    extraction = output / f'extraction-{number}'
    if onefile:
        extraction.mkdir(exist_ok=False)
        env['TEMP'] = env['TMP'] = str(extraction)
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    sequence = win32clipboard.GetClipboardSequenceNumber()
    started = time.perf_counter()
    app = subprocess.Popen([str(exe)], cwd=output, env=env, stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                           encoding='utf-8', errors='replace', startupinfo=startup,
                           creationflags=subprocess.CREATE_NO_WINDOW if onefile else subprocess.CREATE_NEW_CONSOLE)
    lines = []
    def consume():
        for line in app.stdout:
            lines.append((time.perf_counter() - started, line.rstrip()))
    thread = threading.Thread(target=consume, daemon=True)
    thread.start()
    hwnd = hook_handle = None
    peak = 0
    failure = None
    extraction_seen = {}
    module_roots = {}
    parents_seen = {}
    process_first_seen = {}
    worker_windows = set()
    try:
        while time.perf_counter() - started < limit:
            candidate = win32gui.FindWindow('GPTSnipV0Hotkeys', None)
            if candidate and owns_hotkey(candidate, app.pid, onefile):
                hwnd = candidate
            assert app.poll() is None, 'Application exited before measurement ended'
            current = processes()
            for pid in current:
                process_first_seen.setdefault(pid, round((time.perf_counter()-started)*1000, 3))
            peak = max(peak, len(current))
            assert len(current) <= (3 if onefile else 2), 'Unexpected extra process observed'
            if onefile:
                for folder in extraction.glob('_MEI*'):
                    extraction_seen.setdefault(folder.name, round((time.perf_counter()-started)*1000, 3))
                # Inspect loaded Python DLL paths after worker receipt, without touching the EXE.
                if any('native result' in line for _, line in lines):
                    parents = process_parents()
                    parents_seen.update({pid: parents.get(pid) for pid in current})
                    for pid in current:
                        if pid == app.pid or pid in module_roots:
                            continue
                        handle = win32api.OpenProcess(0x410, False, pid)
                        try:
                            for module in win32process.EnumProcessModules(handle):
                                path = Path(win32process.GetModuleFileNameEx(handle, module))
                                if path.name.lower() == 'python314.dll':
                                    module_roots[pid] = path.parent.name
                        finally:
                            handle.Close()
                    workers = [int(re.search(r'pid=(\d+)', line)[1]) for _, line in lines if 'browser worker started' in line]
                    win32gui.EnumWindows(lambda w, _: worker_windows.add(w)
                                         if win32process.GetWindowThreadProcessId(w)[1] in workers else None, None)
            if hook_handle is None and trace.exists():
                records = [json.loads(line) for line in trace.read_text(encoding='utf-8').splitlines()]
                for record in records:
                    if record['event'] == 'startup ready':
                        hook = record['state']['hook']
                        assert hook['installed'] and not hook['error_present']
                        hook_handle = win32api.OpenThread(0x100000, False, hook['thread'])
            if sum('App consumed result' in line for _, line in lines) >= reads:
                break
            time.sleep(.05)
    except Exception as exc:
        failure = type(exc).__name__ + ': ' + str(exc)
    finally:
        if hwnd and win32gui.IsWindow(hwnd):
            win32gui.PostMessage(hwnd, win32con.WM_HOTKEY, 3, 0)
        try:
            app.wait(timeout=8)
        except subprocess.TimeoutExpired:
            app.terminate()
            app.wait(timeout=5)
            failure = 'Forced termination required'
        thread.join(3)
        (output / f'cycle-{number}.log').write_text(
            '\n'.join(f'{stamp:.6f} {line}' for stamp, line in lines) + '\n', encoding='utf-8')
    hook_exited = False
    if hook_handle is not None:
        hook_exited = win32event.WaitForSingleObject(hook_handle, 2000) == win32con.WAIT_OBJECT_0
        hook_handle.Close()
    remaining = processes()
    text = '\n'.join(line for _, line in lines)
    rows = summarize(lines)
    result = dict(cycle=number, startup_ms=next((round(t*1000, 3) for t,l in lines if 'v0.1.0 ready.' in l), None),
                  requests=rows, failure=failure, q_exit_code=app.returncode,
                  hook_thread_exited=hook_exited, no_orphans=not remaining,
                  peak_processes=peak, clipboard_unchanged=sequence == win32clipboard.GetClipboardSequenceNumber(),
                  one_app_banner=text.count('v0.1.0 ready.') == 1,
                  worker_starts=text.count('browser worker started'),
                  chatgpt_remembered='automatic Chrome target remembered' in text,
                  traceback='Traceback' in text,
                  capture_or_paste=any(s in text for s in ('Ctrl+V issued', 'capture started')))
    if onefile:
        # Hotkey window is gone after clean shutdown; derive roles from the recorded parent tree.
        app_pids = [pid for pid, parent in parents_seen.items() if parent == app.pid]
        worker_pids = [pid for pid, parent in parents_seen.items() if parent in app_pids]
        result.update(extraction_first_seen_ms=extraction_seen,
                      extraction_cleaned=not list(extraction.glob('_MEI*')),
                      residual_temp_entries=[p.name for p in extraction.iterdir()],
                      python_dll_roots=module_roots, process_parents=parents_seen,
                      process_first_seen_ms=process_first_seen,
                      bootloader_pid=app.pid, app_pids=app_pids, worker_pids=worker_pids,
                      child_windows=len(worker_windows),
                      shared_extraction=len(module_roots) == 2 and len(set(module_roots.values())) == 1
                      and set(module_roots.values()) == set(extraction_seen))
    hotkeys_released = True
    for identifier, key in ((1, 'S'), (2, 'G'), (3, 'Q')):
        try:
            win32gui.RegisterHotKey(None, identifier, 0x4000 | win32con.MOD_CONTROL | win32con.MOD_ALT | win32con.MOD_SHIFT, ord(key))
            win32gui.UnregisterHotKey(None, identifier)
        except win32api.error:
            hotkeys_released = False
    result['hotkeys_released'] = hotkeys_released
    (output / f'cycle-{number}-summary.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    assert not remaining, 'Orphan remains; stop further cycles'
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, default=Path('dist/PixelPort/PixelPort.exe'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cycles', type=int, default=5)
    parser.add_argument('--reads', type=int, default=12, choices=range(1, 13))
    parser.add_argument('--limit', type=float, default=30)
    parser.add_argument('--onefile', action='store_true', help='Expect bootloader parent + app + one worker; observe extraction')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    exe = args.exe.resolve()
    results = []
    for number in range(1, args.cycles+1):
        row = run_cycle(exe, args.output.resolve(), number, args.reads, args.limit, args.onefile)
        results.append(row)
        print(json.dumps({k: v for k, v in row.items() if k != 'requests'}), flush=True)
        if row['failure'] or row['q_exit_code'] or not row['hook_thread_exited']:
            break
    (args.output/'summary.json').write_text(json.dumps(
        dict(exe_sha256=hashlib.sha256(exe.read_bytes()).hexdigest(), cycles=results), indent=2)+'\n', encoding='utf-8')
