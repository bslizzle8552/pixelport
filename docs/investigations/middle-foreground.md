# Middle-selector foreground acquisition

The September 10, 2026 investigation identified a fresh-launch cancellation caused
by the selector failing to acquire global foreground. The correction is in
functional baseline `7063818`; [physical acceptance](../validation.md) passed later.

## Evidence

The complete diagnostic contained 134 valid JSON records. The following sequence
retains useful timing and state relationships without session-specific native IDs.

| Relative time | Observation |
| --- | --- |
| 4 ms | Windows Terminal foreground |
| 42 ms | PixelPort's root wrapper observed foreground although Tk root was withdrawn |
| 17,038 ms | First gesture admitted with Chrome foreground |
| Overlay setup | Selector visible; local active/focus, Tk focus, and grab point to it; global foreground remains Chrome throughout recorded stages |
| 17,062 ms | Periodic mouse health check compares Chrome with selector and cancels for foreground mismatch |
| 35,453 ms | Second attempt shows the same acquisition failure |
| 43,616–43,662 ms | Foreground moves from Chrome through a null HWND to Terminal |
| 46,467 ms | Next gesture starts from Terminal, not Chrome |
| 46,493 ms | Tk focus request now obtains selector foreground |
| 49,467 ms | Valid release completes and Ctrl+V is recorded |
| Later Chrome-source gesture | Selector acquires foreground and Ctrl+V completes at 57,648 ms |

During the failed gesture, Chrome memory was present/unblocked, screen bounds were
unchanged, and the hook retained a held, uncancelled gesture. An asynchronous
physical-button snapshot was false; it was not the cancellation predicate and
cannot replace the hook event's ownership. No recorded stage showed initial
selector foreground ownership, though sampling cannot exclude unseen transitions.

The trace proves local Tk focus can coexist with Chrome owning global foreground.
It does not expose Windows' internal permission rule or prove the terminal click
alone permanently changed eligibility. The process had already owned its hidden
root earlier, so a claim that it had never owned foreground is also unsupported.

## Correction

For middle capture, preserve the original foreground and observe actual ownership
through overlay setup. After assigning the selector to App, attempt native
activation once only if the source remains foreground and ownership was never
established. Validate the target belongs to the current process/UI thread; attach
input threads only around SetForegroundWindow and detach in `finally`. Verify the
actual foreground after detaching. Failure or source change cancels before target
resolution. No console activation, synthetic input, sleep, or Tk pumping is used.

Observed ownership is sticky lifecycle history. Genuine later foreground loss
cancels, without another acquisition attempt. The release, periodic health, and
FocusOut checks all remain. Keyboard selection does not use the fallback.
Detachment failure is reported rather than accepted as success.

Regression tests replay Chrome staying foreground through all Tk setup calls,
then require one native acquisition, three fresh Chrome checks, image copy, and
only Ctrl+V input. Other cases cover source switches, acquisition denial, later
loss without retry, another-process targets, attach/detach failure, exceptions,
and native API success without actual foreground ownership.

Input-thread activation calls are synchronous; no hard timeout against a hung
foreign input queue is claimed. Native lifecycle smoke does not exercise physical
selection or real input attachment. The later two fresh-launch physical cycles
establish the no-console-click result on the tested machine.

## Diagnostic recording lesson

An earlier PowerShell transcript retained only a late fragment: 4,472 bytes before
closure and 4,617 after. Closing the transcript did not restore startup/admission,
activation, mismatch, or paste events. The remaining late verification record could
not establish the failure mechanism. The complete console attachment supplied the
missing sequence; no cause was inferred from the truncated fragment.

The maintained diagnostic mode therefore supports direct UTF-8 JSONL append,
closing each record before console notices. Tests verify preservation despite
console failure, bounded append, warning/console fallback for file errors, and no
file creation when disabled. Raw transcripts and acceptance traces stay local.
See [diagnostics](../diagnostics.md) for current commands.

References: [SetForegroundWindow](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setforegroundwindow),
[AttachThreadInput](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-attachthreadinput).
