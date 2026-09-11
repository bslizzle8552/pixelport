# Middle-mouse startup/focus diagnostic — awaiting physical reproduction

**Current status:** the later full-console attachment supplied the missing
evidence. The fix is now ready for physical acceptance; see
[MIDDLE_FOCUS_FIX_HANDOFF.md](MIDDLE_FOCUS_FIX_HANDOFF.md). The sections below
describe the earlier diagnostic stage.

**Update after the user's A–D run:** the supplied PowerShell transcript retained
only a late fragment, even after `Stop-Transcript`. See
[the trace review and corrected recording commands](MIDDLE_FOCUS_TRACE_REVIEW.md).
Use those direct JSONL commands instead of the historical transcript commands below.
The physical bug remains unconfirmed at the code-path level; no selector fix has
been made. The diagnostic recording repair passes 162 tests and native smoke.

This pass adds instrumentation only. The reported physical cancellation path,
PowerShell-induced state change, and root cause are **not yet confirmed**.
No behavioral fix has been attempted. Stop here for the user's diagnostic result.

## Run this one physical sequence

1. Quit every GPTSnip instance using **Ctrl+Alt+Shift+Q**. Keep ChatGPT open in
   Chrome with its composer selected. Use the same PowerShell/terminal and launch
   method that reproduced the problem; do not change elevation or terminal type.
2. Run this block from PowerShell. The transcript preserves the console output;
   the final two commands run after GPTSnip exits.

   ```powershell
   Set-Location C:\dev\gptsnip
   $env:GPTSNIP_MIDDLE_DIAGNOSTICS = '1'
   Start-Transcript -Path .\middle-focus-diagnostic.txt -Force
   .\.venv\Scripts\python.exe -u -m gptsnip
   Stop-Transcript
   Remove-Item Env:\GPTSNIP_MIDDLE_DIAGNOSTICS
   ```

3. Switch to Chrome and let automatic verification complete. Expect
   `GPTSnip: Chrome target verified as chatgpt.com.` Do not press G. Do not click
   PowerShell after launch yet; do not bring it forward just to read the console.
4. From the application where the failure normally occurs, hold middle, drag a
   clearly non-tiny rectangle, and release. This is **A: the first failing drag**.
5. Release all buttons. Click the PowerShell window **once**. The trace saves
   **B: the preceding sampled state** and **C: the foreground transition** without
   needing another hotkey or manual marker.
6. Switch back to the same source application used in step 4. Hold middle, drag,
   and release once. This is **D: the first post-click drag**. Confirm whether the
   image appears in ChatGPT unsent. Do not press Enter.
7. Quit GPTSnip with **Ctrl+Alt+Shift+Q**. Send
   `C:\dev\gptsnip\middle-focus-diagnostic.txt`, plus a sentence saying whether
   A cancelled and D pasted. If A unexpectedly works, report that too; do not
   treat it as proof of a fix.

Do not perform the broader acceptance matrix yet. The first trace is needed
before choosing a production change.

## What the code establishes

`Selector.check_focus()` compares the live `GetForegroundWindow()` with the
selector's top-level HWND. A mismatch cancels. It is called from:

- the deferred Tk `FocusOut` callback;
- the middle-button release handler;
- the approximately 250 ms middle-gesture health check, including stationary holds.

The selector calls `deiconify`, `SetWindowPos` with `SWP_SHOWWINDOW`, Tk
`focus_force`, and `grab_set`. Previously it did not record whether any of these
actually established foreground ownership. The expected HWND is assigned during
each selector's construction. There is no cached startup foreground baseline or
PowerShell-focus initialization in this selection code, and no `AttachThreadInput`
call in this path. Those facts do not yet establish the native activation cause.

The strongest unresolved question is whether the first overlay never acquires
foreground, or acquires it and subsequently loses it. The new trace distinguishes
the activation stages and records the exact HWNDs used by the cancellation check.

## Instrumentation

Ordinary cancellation notices now identify the actual path: foreground mismatch
with its check trigger, Escape, undersized drag, display-bounds change, hook error,
hold timeout, selector close, callback/flow failure, quit, or cleanup. There is
also a default caller-cancellation reason for direct calls without a supplied reason.
Chrome verification failure still follows the existing clipboard-only flow; it
is not relabeled as a selector cancellation.

`GPTSNIP_MIDDLE_DIAGNOSTICS=1` enables JSON console records for:

- admission, selector creation, before/after activation stages, Tk focus events,
  exact foreground mismatch, release, completion, and successful Ctrl+V;
- foreground HWND/process/thread/class, its GUI active/focus/capture handles,
  GPTSnip UI-thread GUI handles, console HWND, and Tk root/focus/grab state;
- hook installation/thread, physical middle-button state, gesture serial and
  coordinates, held/released/cancelled state, admission and acknowledgement;
- selector HWND/lifecycle, expected foreground, capture generation and bounds;
- remembered/bound/selected target HWND/PID/process, memory validity, document
  evidence presence, and pending verification tokens/generations/results.

No titles, document contents, full URLs, or document identity representations are
logged. Native metadata reads do not request foreground, attach input threads,
inject input, or initialize accessibility. Records stop at 600 per launch.
Routine sampling retains one previous snapshot, refreshed about every 250 ms;
foreground changes are checked on the existing UI tick (about 30 ms). This is
sampled evidence, not an atomic Windows event trace: transitions between samples
can be missed, and diagnostic output adds some timing overhead. The trace is
disabled by default. Win32 does not expose a direct foreground-permission flag
here; permission eligibility must not be asserted solely from a focus snapshot.

## Files changed in this pass

- `gptsnip/app.py`: diagnostic plumbing and reason propagation at existing paths.
- `gptsnip/selector.py`: cancellation reasons and activation/lifecycle observations.
- `gptsnip/middle_diagnostics.py`: bounded, opt-in, read-only metadata snapshots.
- `tests/test_mouse.py`: two new diagnostic tests and stronger reason assertions
  in existing cancellation tests.
- `tests/test_middle_diagnostics.py`: five tests for opt-in behavior, failure
  isolation, output bounds, before/after sampling, and redaction.
- This technical handoff.

The existing uncommitted Chrome reliability changes in `app.py`, `browser.py`,
`native_document.py`, their tests, and `CHROME_RELIABILITY_HANDOFF.md` were present
on entry and preserved. No commit, push, packaging, naming, release-doc cleanup,
or new capture feature was performed.

## Validation and limits

- Complete suite: `python -m unittest discover -s tests -q` — **158 passed**
  (151 existing tests plus 7 diagnostic tests), 2.533 seconds.
- Native lifecycle smoke: **passed**, including registrations, hook install and
  removal, hook thread exit, WM_HOTKEY dispatch, duplicate guard, and cleanup.
  It was run both with diagnostic snapshots enabled and on final code with them
  disabled. No screenshot, clipboard write, or synthetic input was requested.
- `git diff --check`: passed; Git emitted only line-ending conversion warnings.
- Diagnostic-enabled smoke successfully read native GUI/Tk state. It sampled an
  initial foreground of `ChatGPT.exe` and then a GPTSnip UI-thread `TkTopLevel`
  while the root reported `withdrawn`. Thus the smoke script's printed claim
  of "no foreground switch" should be understood as no explicit foreground-switch
  action in the smoke code; the trace did observe a foreground change. This
  separate smoke observation is not the physical middle-drag reproduction.
- No physical fresh-launch acceptance has been performed in this pass.
- A regression test for the **confirmed software cause** remains pending; these
  seven additions test instrumentation and do not establish a behavioral fix.

## After the trace confirms the cause

Implement only the narrow confirmed correction, add its regression test, and
rerun the complete suite and native smoke. Then perform **two complete quit and
fresh-launch cycles**. In each cycle: never click PowerShell after launch, never
press G, allow automatic ChatGPT verification, switch directly to another normal
application, and middle-hold → drag → release. Require an automatic unsent paste.

Also physically verify tiny middle clicks cancel, Escape cancels, GitHub active
stays clipboard-only, returning to ChatGPT recovers, keyboard capture still works,
and PowerShell focus is irrelevant. Preserve MSAA verification, automatic memory,
stale-target/GitHub blocking, all three fresh checks, clipboard fallback, Codex
exclusion, manual G override, multi-monitor coordinates, and Ctrl+V-only output.

Pending handoff answers: exact physical cancellation reason, exact state change
after PowerShell focus, confirmed root cause, implemented fix, cause regression,
and physical acceptance results. The requested stop boundary is now reached:
the user's A–D diagnostic sequence is needed.
