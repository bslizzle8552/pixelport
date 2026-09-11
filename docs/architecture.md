# PixelPort architecture

PixelPort v0.1.0 is a Windows 11 region-capture utility for the validated Chrome /
chatgpt.com workflow. The functional baseline is commit `7063818`.
Public branding and version metadata do not change the capture/target/paste policy.

## Package and native compatibility

The Python package and launch command remain `gptsnip` / `python -m gptsnip`.
Renaming these would touch imports, test mocks, multiprocessing import paths, and
entry-point handling without improving the user workflow. They may migrate in a
separate compatibility change. `gptsnip.__version__` is the source of truth: `0.1.0`.

The session mutex `Local\GPTSnipV0`, hidden hotkey class `GPTSnipV0Hotkeys`, worker
thread names, and `GPTSNIP_*` diagnostic environment variables retain their existing
identities. Keeping the mutex also prevents the old and newly branded source builds
from running competing hooks in the same session. The hidden window's display name,
console notices, and diagnostic prefixes use PixelPort. The future executable is
named `PixelPort.exe`; frozen packaging is not yet implemented or validated.

## Modules

| Module | Responsibility |
| --- | --- |
| `app.py` | Tk lifecycle, hotkeys, target memory, capture coordination, verification gates |
| `mouse.py` | Native low-level hook, bounded gesture mailbox, cancellation and shutdown |
| `selector.py` | Physical-coordinate overlay and middle/keyboard selection |
| `browser.py` | Strict URL parsing, redacted replies, supervised reader process |
| `native_document.py` | Exact Chrome document identity, stable MSAA reads, IA2 initialization |
| `windows.py` | Native window/process checks, clipboard, foreground and Ctrl+V primitives |
| `core.py` | Selection/DIB conversion and existing target-selection policy |
| `middle_diagnostics.py` | Optional bounded metadata tracing |

## Gesture and selection lifecycle

A `WH_MOUSE_LL` hook runs on a dedicated `GetMessageW` thread. Its callback
classifies physical events, suppresses middle down/up, and publishes a single
immutable latest gesture sample. It performs no Tk calls, logging, screenshots,
accessibility reads, or injection. Movement is coalesced; start/release coordinates
and serial acknowledgement prevent a pending release being overwritten. Tk consumes
changed samples every 30 ms. Reference publication assumes normal CPython;
free-threaded Python is unvalidated.

Wheel rotation, other buttons, and pointer movement pass through. A middle hold
already in progress at hook installation passes through until its matching release.
Injected middle events cannot start/finish a physical capture. Busy gestures are
discarded rather than queued. A 60-second watchdog cancels missing releases; it
never fabricates a successful release. Hook errors preserve keyboard capture.

The selector starts before target verification completes. A fast release retains
its final rectangle until verification finishes. Middle capture requires a clipped
rectangle at least 6 physical pixels in both dimensions; keyboard selection retains
its existing empty-selection rule. Escape, focus loss, display-bounds changes,
hook errors, and shutdown cancel and acknowledge the gesture.

Tk local focus is insufficient proof of foreground ownership. A middle selector
records its source foreground and observed ownership. If necessary, it makes one
native acquisition attempt, only for its own UI-thread window while the source
remains foreground. Input threads are attached only around activation and detached
in `finally`. Actual foreground is verified afterward. Failure cancels; later loss
never retries acquisition. Keyboard capture does not use this fallback. See the
[foreground investigation](investigations/middle-foreground.md).

## Chrome identity and process isolation

A snapshot binds top-level HWND/PID/executable/title, process creation time, native
thread, and renderer identity. Exactly one visible `Chrome_RenderWidgetHostHWND`
must belong to the requested root and PID. The reader obtains its MSAA document
root through `AccessibleObjectFromWindow`, checks role/state, and parses `accValue`.
Only HTTPS hostname exactly `chatgpt.com`, default port or explicit 443, qualifies.
Credentials, malformed URLs, lookalikes, and subdomains fail eligibility.

A visible, unchanged BUSY root can receive an `IAccessible2::get_states` initialization
request through `IAccessible` / `IServiceProvider`. That request always returns
unknown for the current sample. Later ordinary MSAA reads must independently pass
all gates; bootstrap never authorizes a paste. All native interface references are
released. See [Chrome initialization](investigations/chrome-initialization.md).

| Boundary | Contract |
| --- | --- |
| Idle foreground metadata | 250 ms |
| Idle Chrome request admission | At most once per 750 ms, foreground Chrome only |
| Stable read | Two matching reads 120 ms apart |
| Request deadline | 1 second including worker startup |
| Reply age | At most 300 ms |
| Required verification flow | 1.5 seconds, including draining old idle work |
| Retry after reader failure | Two-second cooldown |
| Concurrency | One supervisor, at most one child and one admitted request |

A supervisor thread owns spawn, IPC waits, and termination. Tk only submits/polls
local queues and reads cheap native metadata. A hung COM call can be retired by
terminating its process; replacements never accumulate while the old child lives.
Tokens, generation, time, and current identity checks reject stale replies.

Only outcome, hostname, and native identity cross the worker boundary. Full URL
values may transiently remain in Python memory, including parser caches; there is
no claim of immediate erasure. They are not persisted or included in diagnostic
results. Window titles remain in in-memory snapshots. No DOM/content traversal,
browser history collection, browser automation, extension, or API client is used.

## Target policy

Automatic Chrome memory is learned from verified foreground ChatGPT. Switching to
another application preserves it; observing another site or unknown Chrome state
blocks it. The old snapshot remains, preventing silent fallback discovery. A fresh
positive foreground observation can restore automatic memory.

The selected target is fixed at capture admission. Automatic Chrome requires fresh
verification before target selection, after copying and before activation, and
immediately before Ctrl+V. An idle result cannot substitute for these checks.
Unknown, ambiguous, minimized, changed, unavailable, busy, or stale state fails closed.

Manual G binding has priority and bypasses automatic document verification. A stale
binding blocks fallback until rebound or cleared by restart. Legacy title heuristics
for Edge, Firefox, Brave, Vivaldi, and Opera still exist; they are not validated
release support. `ChatGPT.exe` and non-browser applications are excluded automatically,
though the existing explicit manual override can bind `ChatGPT.exe`.

## Pixels, clipboard, and input

DPI awareness is set before UI creation. Native physical coordinates and virtual
screen bounds allow negative monitor origins; `SetWindowPos` avoids Tk geometry's
negative-offset interpretation. After overlay destruction, at least 120 ms and
`DwmFlush` precede Pillow's live all-screen capture. Moving pixels can change during
that interval. Bounds-only checks cannot detect every topology/scaling change.

The rectangle uses inclusive left/top and exclusive right/bottom edges. It is
converted to lossless 24-bit RGB `CF_DIB` and replaces the clipboard. PixelPort
requests exclusion from Windows clipboard history/cloud sync. No screenshot file
or history database is created; third-party clipboard managers can retain contents.

Copy/activation/paste validate target identity, foreground, held input, and clipboard
sequence. Failure after copying retains the image for manual paste. Clipboard
contention can itself prevent copying and is reported. Successful input is Ctrl
down, V down, V up, Ctrl up, with key-release recovery on partial injection failure.
There is no Enter or Send action. Verification and input are not atomic; a tab or
focus change after the final check remains possible. The user must select the tab
and focus the composer. ChatGPT may upload an attachment before manual submission.

## Lifecycle and support

The session mutex rejects duplicate instances before another hook is installed.
Q, Ctrl+C, and cleanup unregister hotkeys, close the reader, and request hook exit.
The hook unhooks in `finally`; failed unhook or a join over two seconds is reported.
Windows can silently remove a slow hook; restart and keyboard fallback remain the
recovery path. Foreground acquisition is synchronous and has no guaranteed bound
against a hung foreign input queue.

[Validation](validation.md) separates automated, native, and physical evidence.
[Diagnostics](diagnostics.md) describes retained opt-in support instrumentation.
