# GPTSnip middle-mouse capture handoff

## Result and validation boundary

Implemented the continuous **hold middle button → drag → release to capture**
gesture. The existing keyboard fallback, manual G binding, browser identity,
clipboard, foreground activation, and unsent Ctrl+V flow remain in place.
This accepted implementation is prepared for the user-requested commit
`feat: add middle-mouse capture gesture`. No push, packaging, or follow-on feature
is included.

The starting workspace was clean at commit
`4244ea3 feat: add verified automatic ChatGPT browser targeting`.
The complete baseline suite passed **91 tests before any edits**. The final suite
passes **145 tests: all original 91 plus 54 new mouse regressions**, with no skips
on this Windows runtime. Compilation and dependency consistency also pass.

The real Windows lifecycle smoke passed: native `WH_MOUSE_LL` installation,
hook-thread message-loop operation and exit, unhooking, all three hotkey
registrations, Q dispatch, second-instance rejection, and hotkey reuse after exit.
The smoke deliberately disables capture admission and does not capture pixels,
change the clipboard, switch foreground, or inject mouse/keyboard input.

**Physical Windows acceptance passed, as reported by the user after testing this
middle-mouse build.** The user confirmed:

- Hold middle button, drag, and release captures; the overlay tracks the gesture.
- The screenshot automatically returns to the verified ChatGPT Chrome conversation
  and remains **UNSENT**.
- Multiple captures can be added to the same composer before sending, and unwanted
  attachments can still be removed normally.
- Capture works across the user's multi-monitor setup.
- Escape cancels selection cleanly.
- Keyboard capture, automatic `chatgpt.com` targeting, and fail-closed clipboard
  behavior remain functional.

These are user-reported physical results, separate from automated test evidence.
They do not assert that every optional case in the checklist below was exercised.

## Input architecture and suppression

- `gptsnip/mouse.py` uses ctypes with pointer-sized Win32 signatures, a retained
  `HOOKPROC`, `SetWindowsHookExW(WH_MOUSE_LL, ..., 0)`, and a dedicated native
  message-loop thread. `GetMessageW` services the hook and a 250 ms hold watchdog.
- The callback returns nonzero for middle-button down and up. No synthetic mouse
  events are sent or replayed. Wheel rotation, left/right/side buttons, and cursor
  movement are forwarded through `CallNextHookEx`. Middle-click is owned even when
  a capture is busy or a gesture is too small. A pre-install held interaction is
  passed through until its up, balancing the down already delivered to an app.
- The callback performs no Tk, screenshot, clipboard, MSAA/COM, console logging,
  blocking queue operations, or worker-process work. Idle mouse movement takes
  the pass-through path without allocating a coordinate snapshot.
- One immutable latest sample carries a gesture serial, original physical press
  coordinate, current/release coordinate, and release/cancel flags. Mouse movement
  replaces that sample; it cannot grow a queue. The hook is the single producer;
  Tk publishes an admission flag and acknowledged serial. This uses normal
  CPython's object-reference publication; free-threaded builds are untested.
- Tk reads the mailbox on the existing 30 ms timer and only redraws changed
  samples. A release cannot be overwritten by a rapid second gesture before Tk
  acknowledges it. New gestures during capture/paste are intentionally ignored.
- The existing translucent `Selector` starts immediately at the original press
  point and takes hook-driven movement/release. Its keyboard path retains left
  drag. The first existing fresh Chrome check runs while the overlay is visible;
  a release before its reply waits with the exact final rectangle retained. The
  same `selection_complete → capture → activation → paste` path follows. All
  three fresh Chrome checks remain required. No targeting interaction bug was
  found requiring any change to the browser identity architecture.

The native choice follows Microsoft's
[low-level mouse hook contract](https://learn.microsoft.com/en-us/windows/win32/winmsg/lowlevelmouseproc)
and [MSLLHOOKSTRUCT coordinate contract](https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-msllhookstruct).
Raw Input alone would not provide the required application-level suppression.

## Threshold, cancellation, and cleanup

The final clipped rectangle must be **at least 6 physical pixels in each dimension**.
Zero-area, one-pixel, narrow, or returned-to-origin selections cancel. Reaching a
larger rectangle earlier does not authorize a tiny final rectangle. No screenshot,
clipboard modification, activation, paste, or send occurs for cancellation.

Escape closes the overlay and invalidates pending capture verification. The
gesture serial is acknowledged; movement, duplicate down, and the eventual up
cannot complete it. The hook continues swallowing the held button's up. After
release, a new press can start again. Lost foreground and changed virtual desktop
bounds cancel too; bounds are also checked by the unchanged final capture path.

A 60-second held-button limit, checked every 250 ms on the hook thread, cancels
and clears a missing-up latch. It never captures at the last known point. The
next physical down can start a new gesture after UI acknowledgement. There is no
continuous `GetAsyncKeyState`/cursor polling or fabricated mouse release.

Injected middle events cannot start or complete a physical gesture. Hook install
or callback-construction failure leaves the keyboard hotkeys active and prints a
specific notice. Detected runtime hook errors cancel active middle selection and
leave keyboard capture usable. Q, Ctrl+C, and application cleanup request thread
exit and unhook in the thread's `finally`; the callback stays referenced through
cleanup. Cleanup is safe to repeat and does not retain a completed thread ID for
later Q messages. A failed unhook or a join exceeding two seconds is reported.
The existing session mutex rejects a second instance before any new hook installs.

## Files changed

| File | Purpose |
| --- | --- |
| `gptsnip/mouse.py` | New native hook, bounded mailbox, suppression, watchdog, lifecycle |
| `gptsnip/app.py` | Hook startup/fallback/cleanup; mouse-driven selector admission and coordination with existing verification |
| `gptsnip/selector.py` | Reuse rendering with original middle press, explicit movement/release, 6px threshold |
| `tests/test_mouse.py` | 54 focused native/state/selector/application regression tests |
| `tests/native_smoke.py` | Real hook installation, unhook, thread-exit checks; capture disabled |
| `README.md` | Primary gesture, keyboard fallback, ownership, cancellation, validation limits |
| `HANDOFF.md` | This implementation, test evidence, launch, and acceptance checklist |

`browser.py`, `native_document.py`, `windows.py`, `core.py`, requirements, entry
point, and all seven original `test_*.py` files are unchanged. No dependencies added.

## Tests and commands

The 54 new tests cover exact start/end coordinates; coalesced motion; all drag
directions and negative origins; 6px limits; ordinary and injected input filtering;
no-output clicks/tiny drags; Escape and late release; duplicate/rapid presses;
keyboard/mouse exclusion; first-verification races; all three Chrome checks;
clipboard-only failure; Ctrl+V-only output; focus/display loss; missing-up timeout;
constructor/install/runtime failures; and hook/selector shutdown.

```powershell
Set-Location C:\dev\gptsnip
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
# Ran 145 tests. OK.
.\.venv\Scripts\python.exe -m compileall -q gptsnip tests
# Exit 0.
.\.venv\Scripts\python.exe -m pip check
# No broken requirements found.
.\.venv\Scripts\python.exe tests\native_smoke.py
# PASS: startup, hotkeys, hook lifecycle, duplicate guard, cleanup.
```

Mock tests do not prove physical suppression in another application, real overlay
tracking and mixed-DPI precision, input latency under system load, physical Escape
ordering, privilege/desktop transitions, or actual Chrome attachment/paste focus.
The native smoke proves installation and lifecycle, not those interactions.

## Exact launch and repeatable manual acceptance checklist

The confirmed physical results are recorded above. Retain this checklist for
future regression testing; optional stress/lifecycle cases are not implied passed.

Run in a normal PowerShell console and keep it open for diagnostics:

```powershell
Set-Location C:\dev\gptsnip
.\.venv\Scripts\python.exe -m gptsnip
```

1. **Normal ChatGPT capture:** Open this conversation in Chrome, click the composer,
   and leave Chrome foreground until the console reports verified `chatgpt.com`
   (allow about two seconds). Do not press G. Keep that tab selected in its window.
   Switch to a normal desktop app. Press and hold the wheel button at the first
   corner; drag at least 6px in both directions; release the wheel. Confirm the
   overlay starts at the press point and tracks the drag, no extra click is needed,
   GPTSnip returns to Chrome, and the screenshot appears **UNSENT**. Add context and
   manually send when desired. Repeat with each reverse direction and your normal
   source apps: Codex, VS Code, terminal, CAD, Explorer, and desktop.
2. **Accidental click:** Copy a recognizable text marker to the clipboard. Middle
   click without dragging, then try a tiny drag. Confirm no screenshot or attachment,
   no automatic paste, and clipboard still contains the marker (paste manually into
   a scratch editor). Confirm a subsequent normal middle drag works. Repeat a quick
   valid press/drag/release to check that early release is retained.
3. **Escape:** Hold middle, begin dragging, press Escape while still holding middle,
   and confirm the overlay disappears. Release middle. Confirm no capture, clipboard
   change, or paste. Start a new middle drag and confirm normal recovery.
4. **Fail closed and recover:** In the same Chrome window switch to GitHub and let
   GPTSnip observe the change. Middle-drag a capture. Confirm clipboard retains the
   image and neither GitHub nor another app receives an automatic paste. Switch back
   to ChatGPT, focus the composer, wait for verification, and middle-drag again.
   Confirm automatic paste recovers and remains unsent.
5. **Other mouse input:** Outside selection, verify normal wheel scrolling, left
   click, right click, cursor movement, and side buttons. Over a browser page/link
   or disposable tab, try a tiny middle click: no autoscroll, new tab, or tab close
   should occur. Middle-button panning in CAD is intentionally unavailable while
   GPTSnip owns the button.
6. **Fallback/exclusion:** Press Ctrl+Alt+Shift+S, release the keys, then left-drag.
   Confirm the existing capture path works. During keyboard selection, middle drag
   must not start a second selection. During middle selection, S must not start a
   second capture. Escape to cancel; confirm the next gesture works. G remains an
   optional manual override; no reconfiguration is required for automatic Chrome.
7. **Recovery/lifecycle:** During a middle selection, switch focus away and confirm
   cancellation; release and retry. Optionally hold middle for over 60 seconds:
   confirm cancellation without output, then release and retry. Launch a second
   instance and confirm it exits. Quit with Ctrl+Alt+Shift+Q or console Ctrl+C, both
   while idle and during a held selection; release the button. Confirm no delayed
   capture and normal middle-click behavior after exit. Relaunch successfully.

## Known limitations / stop boundary

- Physical gesture and multi-monitor operation passed on the user's Windows setup.
  Other monitor layouts, mixed-DPI configurations, and real display-layout changes
  remain unverified. Bounds-only display
  detection cannot identify every scaling/topology change with unchanged bounds.
- A gesture held longer than 60 seconds cancels. Rapid gestures while the first
  gesture is pending or capture/paste is busy are discarded, not queued.
- Secure/UAC desktops, elevated targets, remote desktop, exclusive full-screen
  applications, remapped mouse drivers, free-threaded Python, and high-load hook
  latency are not validated. Windows can silently remove a timed-out low-level
  hook without a detectable notification. Keyboard capture remains available;
  restart the utility if middle capture stops responding.
- The unchanged pipeline captures live pixels after overlay removal and at least
  120 ms repaint delay; fast-release captures can also wait for the first bounded
  verification. Moving content can change before capture. The browser must retain
  composer focus; the app neither locates the composer nor changes selected tabs.
- The hook never injects button state, so it does not create a synthetic held
  button. Crash/secure-desktop transitions and physical post-exit behavior still
  require manual validation; normal unhook/thread cleanup passed natively.

Stop here: no tray, installer, executable packaging, startup integration, settings,
configurable buttons, history, OCR, annotations, browser extension, or other feature.

---

# Prior committed baseline: native Chrome identity handoff

Current pass, September 10, 2026: the same-window native MSAA identity gate passed,
and Chrome automatic recognition is implemented. Full evidence, state-by-state
results, timings, architecture, and limitations are in
[MSAA_VALIDATION.md](MSAA_VALIDATION.md).

## Current result

- Chrome's active loaded document must be verified as HTTPS `chatgpt.com`; no
  ChatGPT title marker or G binding is required.
- Codex/ChatGPT.exe and other non-browser branded titles remain excluded from
  automatic selection. G retains the existing explicit override.
- Same-window GitHub observations block remembered Chrome; returning to ChatGPT
  permits a new positive observation. Switching to another app preserves memory.
- One supervised worker process, bounded queues/deadlines, two matching reads,
  and three fresh capture checks protect target selection and paste.
- **91 tests pass**, plus compilation, dependency consistency, and native lifecycle
  smoke. A separate production read-only smoke returned 10/10 valid ChatGPT results.
- The user confirmed all three real capture cases: positive paste into the Chrome
  ChatGPT composer, no paste with GitHub selected (image retained and manually
  pasted from clipboard), and recovery after switching back to ChatGPT. The final
  confirmation request explicitly included unsent behavior and no Codex paste.

## Phase 1 results

| Test | Result |
| --- | --- |
| A: ChatGPT composer focused | Pass: 327 stable reads across 33 seconds |
| B: GitHub active / ChatGPT background, same HWND | Pass: GitHub identified, no background ChatGPT leakage |
| C: Switch back | Pass: one changed-identity unknown, then stable ChatGPT |
| D: Repeated switching | Pass for four further observed switches; changing/zero-candidate samples rejected |
| E: Uncommitted omnibox text | Pass: unknown with multiple renderers or correct GitHub; no ChatGPT spoof |
| F: Multiple windows | One Chrome window remained; strict HWND scoping and old closed-window rejection checked; two-window live repetition not performed |
| G: Failure states | Zero/multiple renderers, mid-read changes, invalid/missing URL, and stale top-level HWND rejected. No held minimized state or controlled provider outage/reload observed |

Across 8,933 native samples, 8,645 had verified document identity and 288 rejected.
3,577 accepted samples independently bracketed by consistent selected-tab metadata
had zero mismatches. Clipboard sequence stayed unchanged throughout. No probes
captured screenshots, wrote the clipboard, activated windows, or injected input.

## Files and dependencies

| File | Change |
| --- | --- |
| `gptsnip/browser.py` | New strict parser, redacted result, bounded worker supervision |
| `gptsnip/native_document.py` | New exact native snapshot and stable MSAA document-root reader |
| `gptsnip/core.py` | Disable title-only automatic recognition for Chrome; preserve legacy browser/manual rules |
| `gptsnip/app.py` | Async observation, stale memory blocking, generation/deadline checks, fresh capture/paste verification |
| `tests/test_browser.py` | Parser and real isolated worker failure/cleanup tests |
| `tests/test_native_document.py` | Native root and scope/failure tests |
| `tests/test_chrome_targeting.py` | Chrome memory and capture/input regressions |
| `tests/test_core.py`, `tests/test_target_memory.py` | Preserve existing legacy browser coverage under the new Chrome evidence rule |
| `README.md`, `HANDOFF.md`, `UIA_INVESTIGATION.md`, `MSAA_VALIDATION.md` | Current behavior, historical status, evidence, acceptance, and limitations |

**Dependencies changed: none.** `requirements.txt` is unchanged. Selector, native
capture/clipboard/activation/Ctrl+V primitives, entry point, duplicate-instance
guard, and existing flow/native boundary/lifecycle tests remain intact. No commit,
push, mouse trigger, installer, packaging, tray, or startup integration was done.

## Exact manual end-to-end acceptance

1. Quit any older GPTSnip. Launch fresh in PowerShell:

   ```powershell
   cd path\to\gptsnip
   .\.venv\Scripts\python.exe -m gptsnip
   ```

2. **Never press G.** Select this existing ChatGPT conversation in Chrome, click
   its composer, and leave Chrome foreground for about two seconds. Expect
   `Chrome target verified as chatgpt.com` despite the arbitrary conversation title.
3. Switch to another app, such as Codex. Press **Ctrl+Alt+Shift+S**, release keys,
   select a harmless region, and release the mouse. Expect return to that Chrome
   window and an attachment in its composer, with nothing pasted into Codex.
   Confirm the message remains **unsent**; add context/send only yourself.
4. Select **GitHub in the same Chrome window** and wait two seconds. Expect the
   invalidation notice. Switch to another app and capture again. Expect no automatic
   return or paste into Chrome/Codex. Verify the image is on the clipboard, for
   example by manually pasting into Paint.
5. Select ChatGPT again, click its composer, wait two seconds for verification,
   switch to another app, and capture again. Expect automatic Chrome paste to work
   again and remain unsent.

All three real capture cases above were completed and confirmed by the user in
this pass. These are user-reported results; the agent did not capture or inspect
screenshots to assert attachment behavior. Optional native states listed earlier
remain unverified and are separate from the completed capture acceptance.

## Verification commands and remaining limits

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q gptsnip tests
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

Optional lifecycle smoke (quit GPTSnip first):
`.\.venv\Scripts\python.exe tests\native_smoke.py`.

Warm raw native reads had a 3.53 ms median; the production worker's warm request
round trips were about 136 ms including the deliberate 120 ms stability interval.
Cold production startup/read was 679 ms in one measurement. These are wall-clock
measurements, not CPU benchmarks or guaranteed maximums.

Only this Chrome version/machine was validated. Additional visible renderers,
minimized windows, timeouts, and provider errors intentionally block automatic
paste. Document identity does not prove composer focus or pin a conversation ID.
Checks and Ctrl+V are not atomic, so do not switch tabs/windows during return/paste.
Other browsers retain their old title heuristic; no URL support is claimed for them.

A browser extension is **not necessary for the validated Chrome workflow**. If
future Chrome behavior makes active-renderer selection unreliable, evaluate an
extension/local companion then. The current task stops at browser identity.

## Historical record: previous title-only safety fix

<details>
<summary>Earlier diagnosis and validation (superseded behavior)</summary>

# GPTSnip browser-only automatic targeting fix

Latest pass: see [the passive Chrome identity investigation](UIA_INVESTIGATION.md).
Native URL access was demonstrated, but the production reliability gate remains
unmet. No production code, tests, or dependencies changed in that investigation;
the safety fix and acceptance procedures below remain the current behavior.

## Result

Automatic recognition now requires an allowlisted browser process **and** a
standalone, case-insensitive `ChatGPT` word in its top-level title. Codex and the
ChatGPT desktop application cannot be learned, discovered, or selected from
automatic memory. Existing manual binding remains an explicit override.

The complete Windows test suite passes: **48 tests, zero failures/errors/skips**.
The native lifecycle smoke test also passed. The capture -> clipboard ->
foreground -> Ctrl+V implementation is unchanged. No commit, push, packaging,
middle-mouse trigger, settings, tray, or startup feature was added.

**Remaining real-world limitation:** the foreground Chrome window inspected on
this machine was titled `Easier Screenshot Sharing - Google Chrome`. That does
not contain `ChatGPT`, so it fails closed under the requested rule. This fix
prevents the wrong-window paste; it cannot positively identify that particular
conversation from its present title. G is still the manual workaround, but using
G does not count as passing automatic acceptance. No broader page-identification
mechanism or guessed conversation-title exception was added.

## Confirmed diagnosis before changing production code

Read-only Win32 inspection used GPTSnip's existing `inspect_window` and
`list_windows`, plus `QueryFullProcessImageNameW` for the full executable path and
`GetClassName` for the window class. No capture, clipboard write, foreground
activation, or keyboard injection was performed.

Snapshot taken September 10, 2026; machine-specific identifiers are omitted:

| Window | Executable | Representative title (sanitized) | Old automatic eligibility |
| --- | --- | --- | --- |
| Foreground Chrome | `chrome.exe` | `Easier Screenshot Sharing - Google Chrome` | False: no ChatGPT marker |
| Codex | `ChatGPT.exe` | `ChatGPT` | True: desktop executable exception |
| Other Chrome window | `chrome.exe` | `GitHub repository - Google Chrome` | False: no ChatGPT marker |

Executable inspection confirmed that `ChatGPT.exe` belonged to the Codex
Windows app package and `chrome.exe` belonged to Google Chrome. Machine-specific
installation paths are omitted.

Both had class `Chrome_WidgetWin_1`. The native code uses the executable basename
from the process image path, not window class, product metadata, or app display
name. The package inspection confirmed which app owned `ChatGPT.exe`. There was
no `codex.exe` basename to blacklist in this case.

The old `Window.recognized` accepted `ChatGPT.exe` **regardless of title**. Its
browser branch required the title marker. Consequently:

1. Chrome was successfully inspected while foreground. A fresh read-only `App`
   observation left `remembered` as `None`, because the observed title lacked
   `ChatGPT`. This was an eligibility rejection, not a failure to find Chrome.
2. Discovery saw Codex as its sole recognized candidate. Calling the original
   `choose_target` on those live windows, with no binding and no memory, returned
   the Codex window (`ChatGPT.exe`, title `ChatGPT`). This reproduced the wrong
   destination selection without actually pasting.
3. There is also a memory overwrite path: a recognized Codex foreground snapshot
   replaces a previously remembered recognizable Chrome snapshot. A controlled
   replay and failing-before-fix regressions reproduced this path. Remembered
   Codex then takes priority over discovery.

There is no special Codex priority or arbitrary enumeration-order tiebreaker.
The defect is the desktop executable exception, combined with the missing title
marker in this Chrome window. The user's original running-instance memory and
prior interaction sequence were not recorded, so this report does not claim
which path occurred in every historical capture. The live discovery reproduction
and the memory-overwrite behavior are independently confirmed.

## Exact rule and priorities after the fix

Automatic eligibility is:

```python
process.lower() in {
    "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe",
    "vivaldi.exe", "opera.exe",
}
and re.search(r"\bChatGPT\b", title, re.IGNORECASE) is not None
```

Candidates must also pass existing native inspection: visible window, not reported
cloaked by DWM, and readable process/title metadata. Idle observation samples the
foreground about every 250 ms and verifies foreground did not change during
inspection. It does not inspect background tabs or URLs.

Observation, remembered-target validation, and discovery all use
`Window.recognized`; the new rule covers every automatic path. A non-browser title
containing ChatGPT, OpenAI, GPT, or Codex grants no automatic eligibility.

Priority remains:

1. Exact, valid **manual binding** wins. A stale binding blocks paste.
2. Otherwise exact, still-recognized **remembered browser memory** wins. A
   stale/closed/unrecognized snapshot blocks paste and is retained; discovery
   cannot silently redirect this or a later capture.
3. With neither binding nor memory, **discovery** may select exactly one
   recognized browser. Zero or multiple candidates fail closed.

The native window list still includes `ChatGPT.exe` for existing manual binding.
`Window.supported` retains that inspection/manual allowlist; it is **not** the
automatic predicate. `recognized` rejects desktop in every automatic path. No
Codex-specific blacklist or new manual destinations were added. G still accepts
the six browsers or `ChatGPT.exe`, including custom titles; arbitrary other
executables remain outside the original manual-binding allowlist.

Capture fixes the chosen snapshot. Existing exact HWND/PID/executable/title checks
before activation and paste, clipboard sequence validation, held-input checks,
and foreground checks remain intact. Without a valid target, capture copies the
image but never requests foreground or injects input. Clipboard contention keeps
its existing explicit copy-error handling.

## Files changed

| File | Change |
| --- | --- |
| `gptsnip/core.py` | Browser-only automatic predicate; clarify manual compatibility |
| `gptsnip/app.py` | Browser-specific startup wording and target diagnostics only |
| `tests/test_core.py` | Four new tests; replace desktop-acceptance expectation |
| `tests/test_target_memory.py` | Five new observation/discovery/capture/manual regressions |
| `README.md` | New rule, real title limitation, manual compatibility, diagnostics |
| `HANDOFF.md` | Diagnosis, validation, and acceptance procedure |

The repo already had a modified README and untracked implementation, tests,
requirements, and HANDOFF. Their pre-edit contents were backed up outside the
repo for comparison. No unrelated source changes were made.

SHA-256 comparisons verified eight files remain byte-for-byte unchanged:
`gptsnip/windows.py`, `gptsnip/selector.py`, `gptsnip/__main__.py`,
`gptsnip/__init__.py`, `requirements.txt`, `tests/test_windows.py`,
`tests/test_flow.py`, and `tests/native_smoke.py`. Source-segment comparison also
verified every App function is unchanged except `start` (wording),
`observe_foreground` (notice), and `begin_capture` (notice). Capture timing,
image handling, manual binding, selection completion, focus waits, and native
Ctrl+V mechanics are intact.

Memory notices now identify process/PID/HWND. Capture selection notices identify
`manual binding`, `automatic memory`, or `discovery` and the selected
process/PID/HWND, or state clipboard-only fallback. Conversation titles are not
printed; no persistent log is created.

## Tests added

Four core tests:

- `test_automatic_eligibility_requires_allowlisted_browser_and_chatgpt_title`:
  all six browsers accept ChatGPT titles and reject missing/unrelated markers.
- `test_codex_and_chatgpt_desktop_are_never_automatic_targets`: `codex.exe` and
  case variants of `ChatGPT.exe` fail discovery and remembered-target validation,
  including when a valid Chrome alternative exists.
- `test_non_browser_brand_titles_are_never_automatic_targets`: arbitrary apps,
  VS Code, PowerShell, and executable names containing OpenAI/GPT cannot qualify
  with ChatGPT/OpenAI/GPT titles.
- `test_desktop_does_not_compete_with_browser_discovery`: Chrome is the sole
  eligible candidate regardless of desktop enumeration position.

The former desktop-acceptance test now retains only browser/title
case-insensitivity; desktop rejection is explicitly tested above.

Five Windows application-flow tests:

- `test_codex_does_not_replace_chrome_and_capture_only_pastes_to_chrome`:
  switching from remembered Chrome to the real Codex executable/title combination
  preserves Chrome; mocked capture activates Chrome and emits only Ctrl+V.
- `test_non_browser_observation_and_discovery_always_copy_without_paste`:
  15 executable/title combinations, with the actual conversation-only Chrome
  title also present, never learn/select a non-browser. Copy occurs; activation
  and SendInput do not.
- `test_codex_does_not_make_chrome_discovery_ambiguous`: desktop presence cannot
  disqualify the sole eligible Chrome browser.
- `test_closed_chrome_memory_does_not_redirect_to_codex_or_another_browser`:
  repeated captures copy only, even after observing Codex and with another valid
  browser open.
- `test_desktop_requires_deliberate_manual_binding_and_still_pastes_unsent`:
  desktop is never automatically remembered, but explicit G still overrides later
  Chrome memory and uses exactly the original Ctrl+V chord.

Existing tests retain custom-title manual Chrome binding, stale binding/memory,
metadata changes, foreground races, cancellation and capture delay, display
changes, DIB pixel round-trip, focus refusal/loss, held input, clipboard changes
and contention, and blocked/partial SendInput. Successful integration and native
paste tests assert exactly Ctrl-down, V-down, V-up, Ctrl-up; no Enter or mouse/Send
action. Partial-input cleanup only releases V/Ctrl.

## Complete validation results

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q gptsnip tests
.\.venv\Scripts\python.exe -m pip check
git diff --check
.\.venv\Scripts\python.exe tests\native_smoke.py
```

| Check | Result |
| --- | --- |
| Original suite before edits | 39 passed |
| New regressions against original production code | Failed as expected, including Codex memory/discovery and clipboard fallback |
| Final complete suite | 48 passed in 0.107 s; zero failures, errors, or skips |
| Core tests | 15 passed |
| Existing application-flow tests | 6 passed |
| Target-memory/integration tests | 19 passed |
| Native boundary/clipboard tests | 8 passed |
| Python compilation | Passed |
| Dependency consistency | `No broken requirements found.` |
| Git whitespace check | Passed; only README LF/CRLF conversion notice |
| Direct whitespace/conflict-marker check including untracked changed files | Passed |
| Protected files and App pipeline comparison | Passed, as described above |
| Native lifecycle smoke | Passed: startup, three actual hotkey registrations, WM_HOTKEY dispatch, duplicate-instance guard, cleanup |
| Post-fix live metadata selection | Codex rejected; Chrome's current title rejected; selected target `None` |

The lifecycle smoke instance exited and released its hotkeys. It did not capture,
modify the clipboard, switch foreground, or inject keys. No GPTSnip application
was left running by this pass. Unit/integration desktop effects were mocked;
these tests do not establish real browser attachment success. The post-fix
selection check used real window metadata and the current recognition rule.

## Exact manual acceptance: Chrome with Codex open

1. Quit any older GPTSnip with **Ctrl+Alt+Shift+Q** or its console Ctrl+C. A fresh
   process loads the fix and clears all bindings/memory.
2. Leave Codex open. Launch from PowerShell:

   ```powershell
   cd path\to\gptsnip
   .\.venv\Scripts\python.exe -m gptsnip
   ```

3. **Do not press Ctrl+Alt+Shift+G.** Open the intended existing ChatGPT conversation
   in Chrome and keep its tab selected. The native window title must contain a
   standalone `ChatGPT` word. If it remains `Easier Screenshot Sharing - Google
   Chrome`, expect clipboard-only fallback and record automatic recognition as
   not passed; waiting longer cannot fix a missing title marker.
4. Click the ChatGPT web composer and leave Chrome foreground for at least one
   second. The console should log `ChatGPT window remembered automatically.` with
   `Process=chrome.exe`. A background tab alone cannot be learned.
5. Switch to Codex and leave it foreground for at least one second to exercise the
   overwrite condition. There must be no automatic-memory notice for `ChatGPT.exe`.
   Keep ChatGPT selected in its separate Chrome window.
6. Press **Ctrl+Alt+Shift+S**, release all shortcut keys, drag a region, and release
   the mouse. The console should report `Target selected via automatic memory`
   with `process=chrome.exe`.
7. Confirm Chrome returns to the intended conversation, the screenshot appears
   in its composer with the expected crop, and nothing appears in Codex.
8. Confirm the message remains **unsent**. Add text and send manually only when
   ready. Avoid clicking/switching windows during the return/paste interval.
9. Repeat from another source application without binding.

## Exact manual acceptance: no eligible browser

1. Quit/relaunch GPTSnip fresh. Leave Codex open and never press G.
2. Ensure **no visible ChatGPT-titled browser window exists**, including in the
   background. Use a non-ChatGPT tab in each browser window or close those windows.
   Merely avoiding foreground observation is insufficient: discovery intentionally
   accepts a single eligible visible browser even if it was never remembered.
3. Use Codex for at least one second, press **Ctrl+Alt+Shift+S**, release all keys,
   select a region, and release the mouse.
4. Confirm the console reports no valid discovery target and then `Image copied`.
   Codex must receive no attachment/paste. GPTSnip must not activate ChatGPT desktop,
   VS Code, a terminal, or another arbitrary app for paste.
5. Verify the clipboard by manually focusing an image-capable composer/editor and
   pressing Ctrl+V yourself. The captured image should be available. Any ChatGPT
   attachment must remain unsent until you manually send it.

## Focused manual regressions

- **Closed remembered Chrome:** after learning recognizable Chrome A, keep Codex
  foreground and close A without foregrounding another valid ChatGPT browser.
  Capture twice. Both attempts must copy only; stale memory must not redirect to
  Codex or browser B. Fresh valid foreground observation may deliberately learn B.
- **Manual Chrome override:** foreground this custom-title ChatGPT conversation,
  click its composer, press G, switch to Codex, and capture. Chrome must return,
  receive the image, and leave the message unsent. This validates the original
  override, separately from automatic acceptance. Restart to clear the binding.
- **Changed target:** changing the selected target's tab/title or closing it during
  selection must block paste after copying. Stale manual binding must also block
  fallback even when automatic memory is valid.
- **Original capture/input behavior:** Escape and a zero-area click cancel;
  held keys/buttons block paste; crop/monitor coordinates remain correct; every
  successful capture remains unsent.

## Still requiring verification on this machine

The real Chrome attachment workflow with this fix has not been manually performed.
Neither positive nor clipboard-only real capture acceptance is claimed as passed.
The current conversation-only Chrome title cannot satisfy the required automatic
model; support for such titles would require a separate decision about stronger
page identification. No URL/DOM verification was added.

Browser title conventions and composer focus remain prerequisites. A browser page
falsely titled ChatGPT can match; title metadata is not proof of website identity.
Same-title tabs are indistinguishable; Windows focus checks and SendInput are not
atomic. Other browser attachment behavior and existing mixed-DPI/HDR/protected-
content limitations remain unverified here. README retains those limitations and
the fact that ChatGPT may upload a pasted image before the user sends the message.

</details>
