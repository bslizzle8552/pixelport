# Middle-selector foreground acquisition — ready for physical acceptance

The full console attachment contains the evidence missing from the truncated
PowerShell transcript. It establishes an initial selector foreground-acquisition
failure. A narrow correction is implemented. **Physical acceptance is pending;
the issue is not yet declared resolved.**

## Evidence and exact cancellation

The complete attachment is preserved byte-for-byte as
`C:\dev\gptsnip\middle-focus-full-diagnostic.txt` (204,959 bytes, 134 valid JSON
diagnostic records). Its SHA-256 is:

`f3b9c45d172927aadd352a71fecebba17223ff23c775aa7f90b1a45e0923f5f5`

The original truncated `middle-focus-diagnostic.txt` is also preserved. The line
numbers below refer to the complete copy.

| Event | Evidence |
|---|---|
| Startup, 4 ms (line 34) | Foreground is Windows Terminal HWND `132714`. GPTSnip UI thread is `12360`. |
| Startup, 42 ms (line 37) | GPTSnip's root wrapper `198702` is observed foreground, although Tk reports its root withdrawn. Therefore this is not simply a process that has never owned foreground. |
| A admission, 17,038 ms (line 55) | Chrome HWND `2228446`, PID `15708`, thread `8852` is foreground. |
| A overlay setup (lines 56–61) | Selector HWND `198672` becomes visible. After `SetWindowPos`, GPTSnip's local active HWND is `198672` and local focus HWND is `329554`. After `focus_force`, Tk focus is `.!toplevel`; after grab, Tk grab is also `.!toplevel`. **Every recorded foreground HWND remains Chrome `2228446`.** |
| A cancellation, 17,062 ms (lines 63–65) | Exact trigger: `periodic mouse health check`. Exact compared foreground: `2228446`. Expected selector: `198672`. Reason: **`foreground differs from selector: periodic mouse health check`**. |
| Second failed attempt, 35,453 ms (lines 90–100) | Same failure, expected selector `264210`, actual Chrome foreground `2228446`. |
| PowerShell/terminal transition, 43,616–43,662 ms (lines 113–114) | Foreground changes from Chrome through HWND `0` to Windows Terminal HWND `132714`, PID `19152`, thread `19608`. GPTSnip's UI thread remains `12360`, with local active/focus null. |
| D admission, 46,467 ms (line 115) | This gesture starts from Windows Terminal, not from Chrome. |
| D activation, 46,493 ms (line 119) | After `focus_force`, foreground becomes selector `852978`, on GPTSnip thread `12360`, PID `2408`. |
| D completion (lines 128–136) | Selector stays foreground at physical release, a valid rectangle completes, and Ctrl+V is logged at 49,467 ms. |
| Subsequent Chrome-source gesture (lines 145–165) | Starts from Chrome. After `focus_force`, foreground becomes selector `591756`; release succeeds and Ctrl+V is logged at 57,648 ms. |

At A's cancellation, Chrome memory is present and unblocked; bounds remain
`[-1920,0,4480,1600]`; generation is 1; gesture 1 is held in hook state and neither
released nor cancelled there. The async physical-button snapshot is false even
though hook state retains the down. That diagnostic value is not the cancellation
predicate and must not be substituted for the hook's physical event ownership.

There is no observed interval in A where the selector owned global foreground,
and no preceding Tk FocusOut record. It fails during initial acquisition, not
after an observed loss of ownership. The snapshots cannot exclude transitions
between their sampling points.

## Confirmed cause versus remaining native uncertainty

GPTSnip treated successful Tk setup/local focus as sufficient to enter the
foreground-owned selection lifecycle. The trace proves that these can coexist
with Chrome remaining the global foreground window. The immediate health check
then cancels the newly constructed selector. There was no explicit native
acquisition fallback or distinction between never acquiring and later losing
foreground.

The terminal click changes the visible foreground process, and the next
`focus_force` succeeds at obtaining global foreground. The same GPTSnip thread
was already initialized and had previously owned its hidden root at startup.
The trace does **not** expose an internal Windows permission bit, prove which
foreground-eligibility rule changed, or prove that the click alone permanently
changes eligibility independently of the subsequent successful capture.

Microsoft documents that foreground activation is restricted and can be denied
even when listed eligibility conditions hold. That supports treating acquisition
as an operation that needs verification; it does not identify the exact rule
responsible for this run. [SetForegroundWindow documentation](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setforegroundwindow).

## Narrow correction

For a middle gesture only, save the source foreground HWND before constructing
the overlay and track whether the selector has actually been observed foreground.
After construction, before target resolution or consuming drag/release:

1. If the selector already established foreground, use the existing flow.
2. Otherwise, if the original source remains foreground, make one native
   acquisition attempt for the selector window owned by GPTSnip's current UI
   thread/process. Temporarily attach the UI input thread to the unchanged source
   thread, call `SetForegroundWindow` for the selector, and detach in `finally`.
3. Verify actual foreground after detachment. If acquisition fails, or the source
   changes during setup, cancel with `selector foreground not acquired`.
4. Once ownership has been observed, it is retained as lifecycle history. A later
   mismatch cancels with the existing foreground-loss reason; it never triggers
   a reacquisition attempt. No selection is accepted while waiting for ownership.

The attachment is scoped to that one native call, with no Tk event-loop pumping,
sleep, console activation, synthetic input, or persistent input attachment.
The native helper refuses to activate a target outside the current UI
thread/process and reports detachment failure instead of claiming success.
Input-thread attachment shares focus/input state and is explicitly detached
afterward. [AttachThreadInput documentation](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-attachthreadinput).

All three existing foreground-check locations remain active. Chrome verification,
three fresh target checks, GitHub/stale-target blocking, automatic memory, Codex
exclusion, manual G override, clipboard fallback, screenshot timing, multi-monitor
coordinates, and the Ctrl+V-only unsent paste path remain intact. Keyboard capture
uses its existing setup and does not invoke the new acquisition fallback.

## Files changed in this fix pass

- `gptsnip/windows.py`: gesture-scoped native selector acquisition helper.
- `gptsnip/selector.py`: source snapshot, actual-ownership tracking, acquisition
  lifecycle, and distinct failure reasons.
- `gptsnip/app.py`: run acquisition after assigning the selector, before target
  resolution; stop that flow when acquisition cancels.
- `gptsnip/middle_diagnostics.py`: include ownership/source/attempt state in opt-in
  snapshots.
- `tests/test_mouse.py`: five new regression/safety tests.
- `tests/test_selector_activation.py`: ten new native-boundary tests.
- Full diagnostic evidence copy and technical handoff updates.

Existing Chrome reliability edits are preserved. No commit, push, release work,
packaging, branding, or feature work was performed.

## Validation

`.\.venv\Scripts\python.exe -m unittest discover -s tests -q`:
**177 passed in 2.630 seconds**, up from 162.

The principal regression replays A's software condition: Chrome remains
foreground throughout all Tk setup calls despite local focus. It verifies one
explicit acquisition for the selector without any console HWND/history, then
completes all three fresh Chrome checks, image copy, and exactly four injected
key events: Ctrl down, V down, V up, Ctrl up.

Other new tests cover acquisition denial, source switches, genuine loss after
acquisition without retry, sticky ownership history, scoped attach/detach,
activation exceptions, detach failure, refusal to activate another process,
same-thread behavior, and API return values without actual foreground ownership.
Existing Escape, tiny drag, hook failure, keyboard fallback, GitHub fail-closed,
automatic targeting, and unsent-input tests pass.

Native lifecycle smoke **passed**: startup, three registrations, hook
install/unhook/thread exit, WM_HOTKEY dispatch, duplicate guard, cleanup.
`git diff --check` passed with only Git line-ending warnings.

The acquisition boundary is mocked in automated tests. Native lifecycle smoke
does not perform a physical gesture or exercise actual input-thread attachment.
Windows activation restrictions and behavior with a hung source application
remain outside this validation. The native attachment/activation calls are
synchronous; there is no claim that they impose a wall-clock timeout on a hung
foreign input queue. Physical tests must establish that this correction removes
the startup ritual on the real machine.

## Two fresh-launch acceptance cycles

Do not repeat the old failed-drag/PowerShell-click diagnostic sequence. Test the
corrected behavior with **no PowerShell click after launch and no G**.

Completely quit GPTSnip using **Ctrl+Alt+Shift+Q**, then run cycle 1:

```powershell
Set-Location C:\dev\gptsnip
$env:GPTSNIP_MIDDLE_DIAGNOSTICS = '1'
$env:GPTSNIP_MIDDLE_DIAGNOSTIC_FILE = 'C:\dev\gptsnip\middle-focus-acceptance-cycle1.jsonl'
.\.venv\Scripts\python.exe -u -m gptsnip
```

Switch to ChatGPT in Chrome and allow automatic verification. Switch directly to
another normal application. Hold middle, drag, release, and require the image
to paste into ChatGPT unsent. Do not bring PowerShell forward to inspect output.
Completely quit with **Ctrl+Alt+Shift+Q**.

Run cycle 2 from the resulting PowerShell prompt:

```powershell
$env:GPTSNIP_MIDDLE_DIAGNOSTIC_FILE = 'C:\dev\gptsnip\middle-focus-acceptance-cycle2.jsonl'
.\.venv\Scripts\python.exe -u -m gptsnip
```

Repeat the same no-console/no-G sequence. Then verify:

- Tiny middle click cancels without image output.
- Escape during a held drag cancels; release middle afterward.
- Switching away during an active selector cancels without reacquiring focus.
- GitHub active in the target Chrome window produces clipboard-only output.
- Return to ChatGPT, allow verification, and confirm automatic recovery.
- **Ctrl+Alt+Shift+S** keyboard capture still works.

Quit and report both cycle results and the secondary checks. The acceptance JSONL
files are local and can be read directly. To disable diagnostics afterward:

```powershell
Remove-Item Env:\GPTSNIP_MIDDLE_DIAGNOSTICS -ErrorAction SilentlyContinue
Remove-Item Env:\GPTSNIP_MIDDLE_DIAGNOSTIC_FILE -ErrorAction SilentlyContinue
```

Stop boundary reached: implementation and automated validation are complete;
physical acceptance is the remaining work.
