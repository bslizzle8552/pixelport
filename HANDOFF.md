# GPTSnip native Chrome identity handoff

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
