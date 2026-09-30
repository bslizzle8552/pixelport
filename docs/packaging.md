# PixelPort Windows packaging — ONEDIR history

The user has accepted the ONEFILE executable for v0.1.0. See the
[release record](release-v0.1.0.md) and [ONEFILE build](onefile.md).
This page retains the earlier ONEDIR implementation and validation history.

## Reproduce the build

Windows x64, standard CPython **3.14.3** with Tcl/Tk **8.6.15**. Install build tools
into the development environment (not runtime requirements):

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\packaging\build.ps1
```

The wrapper temporarily limits DLL search PATH to Python and Windows, runs
`python -m PyInstaller --noconfirm --clean packaging/pixelport.spec`, and restores
the caller's PATH. This prevented unrelated runtime DLL collection from development
tools. The spec enforces the interpreter and exact pinned dependency versions.

PyInstaller **6.22.2**, hooks-contrib **2026.7**, Pillow **12.3.0**, pywin32 **312**;
all build-tool pins are in requirements-build.txt. No new runtime dependencies.
Output is `dist/PixelPort/PixelPort.exe` plus `_internal` support files. The whole
folder is required. Do not distribute the small executable alone.

The console remains visible in normal use. On application startup failure, the
launcher prints the error and waits for Enter when stdin is an interactive console.
Redirected launches exit without waiting, enabling automation. A duplicate launch
also refuses startup; when double-clicked, dismiss its message with Enter. The
original instance remains protected by the unchanged single-instance mutex.

## Worker entry and collection

`packaging/launcher.py` calls `multiprocessing.freeze_support()` inside its main
guard before importing `gptsnip.__main__`. PyInstaller's standard multiprocessing
runtime hook diverts `--multiprocessing-fork` into spawn_main and the intended
`gptsnip.browser._worker`; normal app/mutex/Tk/hook startup is not reached there.
The internal gptsnip package and source entry point remain unchanged.

Standard hooks collect multiprocessing, Tcl/Tk, Pillow native extensions/plugins,
pythoncom, pywintypes, and win32 modules. Two explicit hidden imports are justified
by observed frozen-only failures:

- `win32timezone`: GetProcessTimes dynamically imports it from native pywin32 code.
  Without it, snapshot_window failed closed before the MSAA read.
- `win32com`: COM initialization dynamically imports the package. Without it, the
  root read failed closed as provider_error. Its standard hooks handle collection.

Temporary diagnostic builds established the exact ModuleNotFoundError names.
No diagnostic runtime hook or probe is included in the acceptance executable.
During the initial ONEDIR work, no timeout, reader loop, capture, selector, hook,
clipboard or paste code was altered. The later approved frozen deadline change
is recorded separately in onefile.md. Optional PIL-plugin/platform analysis warnings are not blanket hidden
imports; browser-worker and normal startup imports were exercised directly.

The spec embeds PixelPort ProductName/FileDescription, version 0.1.0, and
OriginalFilename PixelPort.exe, derived from gptsnip.__version__. CompanyName is
omitted. Both specs use `assets/pixelport.ico`, derived from the existing logo
with sizes from 16 to 256 pixels. Console mode is explicit; UPX is disabled.

Run `packaging/install-shortcut.ps1` after a ONEFILE build to create a Start menu
shortcut pointing to `dist/onefile/PixelPort.exe` in place. Find
PixelPort in Start, right-click it, and select **Pin to taskbar**. The shortcut
uses the logo explicitly; earlier executables may still have the default embedded
icon until rebuilt with the current specs.

## Local candidate and initial observed gate (historical)

September 11, 2026 candidate:

- Executable: **3,594,974 bytes**.
- Complete folder: **42,554,453 bytes**, **988 files**.
- EXE SHA-256: `3ad752ea4984abb8629522770bc0b3101cb9f2b3ddf0dbe235b34d1073638544`.
- Artifact type: unsigned Windows x64 **onedir**; not onefile.

An actual frozen launch displayed the version/controls, installed WH_MOUSE_LL,
started one intended reader child, and refused a concurrent second instance. The
worker reached a real native document read. Its cold response completed about
**1,050.36 ms after admission**, beyond the existing **1,000 ms** request deadline.
The app rejected the result and entered cooldown, retaining fail-closed behavior.
The observed document was non-ChatGPT; its host and session identifiers remain only
in ignored local diagnostics. No capture or paste was requested.

This measurement overlapped a duplicate launch. It does not isolate ordinary
standalone cold startup, nor prove that every cold request fails. Packaging work
stopped at the then-requested deadline gate. The later ONEFILE product decision
explicitly authorized a bounded 1.5-second default for new frozen builds; see onefile.md.
A subsequent authorized [isolated measurement pass](isolated-timing.md) passed
five cold launches and 55 warm reads without rebuilding or changing the deadline. Successful earlier warm unknown replies do not
count as warm successful MSAA timings. No complete cold/warm ChatGPT acceptance is
claimed for that initial run. The later isolated timing and ChatGPT follow-up
passed; see [current results](isolated-timing.md). Source tests alone cannot fill
frozen-runtime acceptance gaps.

## Validation tools and limits

`packaging/frozen_smoke.py` is an external, non-bundled harness. It starts the actual
EXE hidden for automated checks, reads opt-in diagnostics, observes the user-selected
Chrome window passively, and posts Q only to PixelPort's hotkey HWND. A separate
final launch tests duplicate refusal with identity timing disabled.
It neither selects a region nor writes/pastes clipboard contents. Avoid middle
captures while it runs. Supply a current intended Chrome HWND from local inspection;
do not publish its raw logs. A fresh output directory preserves earlier evidence.

```powershell
.\.venv\Scripts\python.exe packaging/frozen_smoke.py --chrome-hwnd <current-hwnd> --output build/frozen-smoke-next
```

The harness intentionally fails on worker timeouts, missing ChatGPT remembrance,
extra workers, missing hook evidence, or incomplete shutdown. It is not a substitute
for double-click/physical acceptance. The unchanged candidate passed the revised
two-cycle harness and its separate duplicate check after ChatGPT was selected.
Its duplicate test has been separated from both measured verification cycles.
The original contaminated result does not establish the cause of that delay.

Four launcher boundary tests add to the original 177 tests. They verify worker
diversion, ordering before application startup, interactive failure readability,
and noninteractive exception exit. They do not emulate a frozen browser acceptance.

## Distribution audit and notices

The candidate contains the Python DLL, required win32 extensions and
pythoncom/pywintypes DLLs, Pillow native components, Tcl/Tk DLLs and script libraries,
and normal standard-library dependencies. Windows system DLLs user32, kernel32,
dwmapi, and oleacc are not copied. Build PATH contamination was removed.

Archive and filesystem checks found no project tests, development docs, diagnostic
traces, transcripts, screenshots, or build-machine username/repository paths in the
candidate. Standard-library networking modules may be included through dependency
hooks; PixelPort adds no network calls, telemetry, update service, or API client.

Keep LICENSE, THIRD_PARTY_NOTICES.md, and `_internal/notices` with the distribution.
Notices are copied from the exact Python installation and installed wheel metadata;
Pillow's full wheel license includes codec notices. Tcl, OpenSSL, and zlib upstream
texts have source references in packaging/licenses/README.md. PyInstaller's license
includes its bootloader exception and Apache runtime-hook terms; the PixelPort
project retains MIT. Vendor license files remain unmodified.

The candidate is **not signed**. Defender reported antivirus/realtime protection
unavailable/disabled on this machine, with no signature timestamp; no antivirus
clean verdict is claimed. No settings were changed and no security bypass was used.
SmartScreen reputation was not tested by a downloaded-file launch. Signing status,
malware detection, and reputation warnings are distinct.

## Final acceptance

Core ONEDIR physical behavior was confirmed by the user. The later ONEFILE
executable has now passed real-world testing and is accepted for v0.1.0.
The prior provisional checklists are superseded by that explicit acceptance;
no additional release gate remains. See [release record](release-v0.1.0.md).
