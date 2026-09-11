# Chrome active-document validation and implementation

September 10, 2026. Repository: GPTSnip.

## Decision and scope

**The required native identity gate passed; Chrome-only integration is implemented.**
The evidence supports the active loaded document method in the exercised states.
It does not establish an atomic browser-tab-and-paste operation or universal Chrome
accessibility behavior. Optional states not exercised are listed explicitly below.

The previous [UIA investigation](UIA_INVESTIGATION.md) remains a historical record.
Its separate-window steady-state evidence alone did not authorize implementation.
This pass first read the repository documentation, targeting code, and tests, ran
the original 48-test suite, and then performed the user-assisted same-window matrix.
Production targeting was changed only after evaluating the A–E evidence and the
observed ambiguity rejection. No commit, push, dependency installation, mouse
trigger, packaging, or unrelated feature work occurred.

## Real-machine state matrix

Installed Chrome version was rechecked: **152.0.7977.84**. The shared Chrome
top-level window and process identity remained the same. ChatGPT and GitHub
had distinct renderer identities that were stable per tab during the observed
switches. Machine-specific HWND/PID values are omitted.

| Test | Observed result | Assessment |
| --- | --- | --- |
| A: ChatGPT selected, composer focused | A measured 32.961-second interval contained 327 native reads, all `chatgpt.com`, one visible renderer, role 15. Scoped UIA focus metadata identified an Edit with the focused ProseMirror class in Chrome; the omnibox was not focused. Native foreground/focus and clipboard sequence did not change across these reads. | Pass |
| B: GitHub selected, ChatGPT background, same HWND | Initial measured interval: 112 reads over 11.296 seconds, all `github.com`. UIA selected-tab runtime IDs independently showed the GitHub tab selected and ChatGPT unselected. One visible GitHub renderer, role 15; no background ChatGPT identity appeared. The user confirmed B complete. | Pass, hard gate |
| C: Switch back to ChatGPT | One sample returned unknown because renderer identity changed during the read. The next sample returned `chatgpt.com` on the original ChatGPT renderer and remained stable. The user confirmed C complete. | Pass |
| D: Repeated switches | Four additional switches were observed in the requested alternating sequence. The visible renderer tracked the selected tab. A changing-identity sample and a zero-visible-renderer sample were rejected. Later user tab switches were also recorded; no accepted background-tab mismatch was found in comparable intervals. A second separate D sequence was requested but is not claimed as independently confirmed. | Pass for observed repeated switching |
| E: Uncommitted omnibox `https://chatgpt.com` while GitHub selected | The draft did not become an accepted document identity. There were two distinct focused-draft intervals, separated by a brief actual ChatGPT-tab visit. In 296 native samples bracketed by consistent GitHub-selected/draft-present UIA observations, 173 rejected multiple visible renderers and 123 returned `github.com`; zero returned `chatgpt.com`. Defocused-draft reads also returned GitHub. UIA later showed the draft cancelled. The user confirmed E complete. | Pass; no spoof |
| F: Multiple Chrome windows | Only one Chrome top-level window remained. No replacement window was requested or created. Every renderer was scoped through `GetAncestor(..., GA_ROOT)` to the exact requested HWND. Reading the old, now-closed Chrome HWND returned unknown. A mismatched Codex PID/HWND request also returned unknown. | Exact-HWND scoping checked; two-window live repetition not performed |
| G: Failure states | Four changed-identity reads, one zero-visible-renderer read, 282 multiple-visible-renderer reads, and one invalid/missing document URL read returned unknown. Closed/invalid top-level HWND reads rejected. Minimize/restore was requested but no minimized interval was recorded. No controlled reload, provider outage, or deliberate renderer closure was induced. | Observed failures reject; remaining cases tested with mocks/isolated test workers |

The UIA comparison read only the scoped browser-frame omnibox value, selected-tab
runtime IDs, and minimal focus properties. It did not read tab names or traverse
document content. The production reader does not depend on UIA or the omnibox.

### Transition interpretation

The native probe ran at a nominal 100 ms interval. The UIA comparison ran at roughly
230–250 ms including lookup overhead. **3,577 accepted native samples** falling
between consecutive consistent ChatGPT/GitHub selected-tab observations agreed
with that selected tab. There were **zero mismatches** in those comparable samples.
This comparison excludes tab-switch boundaries and the unlabelled third tab; it
does not claim independent ground truth for every native sample.

For C, the interval from the last accepted GitHub sample to the first accepted
ChatGPT sample was about **202 ms**, including one rejected intermediate read.
The rejected read itself took about 76 ms. During D, a zero-candidate sample was
followed by accepted ChatGPT about **103 ms** later. These are polling/read bounds,
not exact click-to-update latency: the user's clicks were not instrumented.
There was no observed indefinitely stale hostname. An omnibox popup sustained two
visible renderers for about 25 seconds in one interval; this was sustained ambiguity,
not a reason to choose a candidate or accept a stale cache.

### Passive scope and privacy

The 15-minute native run recorded **8,933** samples: **8,645 verified document
identities** and **288 unknowns**. Verified means the URL/root was readable, not
that the site was eligible. The user also selected another site during the run;
those results were not treated as ChatGPT or folded into the labelled A–E proof.

Clipboard sequence stayed unchanged for the entire native run. Foreground remained
unchanged within every individual read. One C transition changed native focus from
unavailable to the Chrome top-level HWND during a rejected read; steady held A/B
intervals had no focus change. The probe contains no input or activation calls,
so no focus change is attributed to an injected action.

There were no screenshots, clipboard writes, pastes, key injection, window
activation, browser automation, extension, DevTools, page-identifying network
requests, or conversation modifications by the probes. The user performed the
browser actions. Public Microsoft documentation was consulted separately.

Full URL values were immediately reduced to host/scheme validity inside probe
memory. Saved evidence has no URL paths, queries, conversation IDs, page text,
composer text, or tab titles. Scratch scripts and redacted evidence were retained
locally outside the repository. Sampling processes stopped. Session-specific
probe scripts, logs, raw evidence, and local paths are excluded from version control.

## Production architecture

The native path is:

```text
exact Chrome window/process snapshot
  -> unique visible Chrome_RenderWidgetHostHWND scoped to that HWND
  -> AccessibleObjectFromWindow(OBJID_CLIENT, IID_IDispatch)
  -> accRole(CHILDID_SELF) == ROLE_SYSTEM_DOCUMENT (15)
  -> accState rejects unavailable/busy/invisible/offscreen
  -> accValue(CHILDID_SELF), parsed and immediately reduced to hostname
  -> unchanged window/process/renderer snapshot
  -> second matching read 120 ms later
```

The URL parser accepts HTTPS with hostname exactly `chatgpt.com` for eligibility.
Other valid HTTPS hosts can be positively identified as non-targets. Default HTTPS
or explicit port 443 is accepted; credentials, malformed escapes, whitespace,
backslashes, unsupported schemes/ports, subdomains, and lookalikes do not qualify.
Only redacted results cross the process boundary. No document-content walk occurs.

One supervisor thread owns one spawned child process and bounded request/result
queues. Tk performs no accessibility calls, process creation, IPC waits, joins,
or termination. It only submits/polls local queues and checks cheap Win32 metadata.
A plain worker thread was not chosen because a hung COM call cannot be reliably
terminated within that thread. A disposable child process permits termination
without freezing the GUI or creating accumulating replacement threads.

| Control | Value/behavior |
| --- | --- |
| Cheap idle foreground metadata | Existing 250 ms interval |
| Idle Chrome request admission | No more often than every 750 ms; foreground Chrome only |
| Stable document evidence | Two matching reads separated by 120 ms |
| Request deadline | 1 second, including process startup and accessibility |
| Maximum reply age | 300 ms, checked by transport and application |
| Required capture verification flow | 1.5 seconds including any old idle work draining |
| Failure recovery | Terminate child outside Tk; two-second cooldown; never create another child while the previous one remains alive |
| Outstanding work | At most one admitted request; one supervisor and one child |
| Identity binding | HWND, PID, executable, process creation time, native thread, renderer HWND/PID/thread/root, and existing exact title snapshot |
| Stale replies | Request token, capture generation, deadlines, and current native identity must all agree |

Chrome cannot qualify from a title alone. Foreground verified ChatGPT is remembered;
the same window becoming non-ChatGPT or unknown blocks that memory. Switching to
another application preserves it. Blocked memory is retained rather than allowing
discovery to redirect a later capture. A fresh positive foreground observation
restores eligibility. Title equality is an additional staleness check after learning;
no particular title text is required for admission.

Three fresh verifications protect each automatic Chrome capture: before fixing its
target, after copying but before activation, and immediately before Ctrl+V. The
captured target's renderer/process identity must still match. Failed checks retain
the copied screenshot and prevent the corresponding activation/input step.

Manual G binding retains its existing priority and explicit URL-check override.
Codex/ChatGPT.exe never qualify automatically. Edge/Firefox/Brave/Vivaldi/Opera keep
their prior title heuristic; no URL-based support was enabled for them. Unobserved
Chrome windows are not discovered by title, so Chrome must be visited while GPTSnip
runs. This avoids adding expensive background-window URL scans.

## Tests and measured performance

The original suite passed 48 tests before changes. The current complete suite
passes **91 tests, zero failures/errors/skips** (1.583 seconds in the final run).
Compilation, dependency consistency, and the native lifecycle smoke test passed.
The lifecycle test exercises hotkeys/duplicate protection without capture or input.

Added coverage includes strict URL parsing; wrong/missing/ambiguous document roots;
COM errors; unavailable/busy state; renderer/process/window reuse; real isolated
worker timeout and cleanup; stale worker tokens/timestamps; same-window GitHub
invalidation and ChatGPT recovery; window isolation; no title-only Chrome discovery;
manual binding; all three capture verifications; late flow replies; clipboard-only
failure; cancellation; foreground loss; and exact Ctrl-down/V-down/V-up/Ctrl-up.
Existing title-target tests now exercise the unchanged non-Chrome legacy path;
new Chrome tests require explicit document evidence. Screenshot/clipboard/input
effects in integration tests are mocked.

| Measurement | Result |
| --- | --- |
| Initial raw native read | 95.31 ms |
| Warm raw verified-read median over full probe | 3.53 ms |
| Raw verified-read p95 / maximum | 5.76 ms / 198.85 ms |
| Production worker cold round trip, including spawn and stability delay | 678.63 ms |
| Production worker warm round trips, 9 samples | 134.52–137.25 ms; about 136 ms |
| Production read-only smoke | 10/10 `chatgpt.com`, eligible, exact current identity; matching request tokens |
| Production smoke foreground/clipboard | Unchanged before/after; supervisor stopped |

These are wall-clock measurements on this machine, not CPU/idle-impact benchmarks
or universal maximum latencies. The 120 ms stability interval is intentional. Slow
or hanging providers fail closed at the deadline rather than extending the UI wait.

## Real capture acceptance

All three requested capture cases were completed and confirmed by the user:

1. Fresh launch, no G, ChatGPT selected: **“it did, pasted into chatgpt prompt in
   browser.”**
2. Same Chrome window switched to GitHub: **“it did not paste, was retained on the
   clipboard, was able to manually paste it.”**
3. Same window switched back to ChatGPT: **“recovery complete”**, responding to the
   request to confirm restored Chrome paste, unsent behavior, and no Codex paste.

These establish user-confirmed acceptance of the three real capture cases. No
screenshot was captured or inspected by the agent to assert the result. This does
not fill the separate untested native-state gaps listed in the state matrix.

The exact full acceptance procedure is in [HANDOFF.md](HANDOFF.md). Keep every
attachment unsent while checking it; sending remains the user's action.

SHA-256 comparison to the start-of-pass baseline also confirmed eight files stayed
byte-for-byte unchanged: `gptsnip/windows.py`, `gptsnip/selector.py`,
`gptsnip/__main__.py`, `gptsnip/__init__.py`, `requirements.txt`,
`tests/test_windows.py`, `tests/test_flow.py`, and `tests/native_smoke.py`.
The final Git whitespace check and direct check of untracked source/document files
passed. Changes are enumerated in HANDOFF. No commit or push was made.

## Limitations and extension decision

- Chrome 152.0.7977.84 on this machine is the validated URL-reader scope. Other
  versions, other browsers, split view/side panels, and all possible provider
  configurations are not claimed as validated.
- The same-window matrix passed, but two-window live repetition, a held minimized
  interval, controlled loading/reload, and a real provider outage were not performed.
  Mocks/isolated test workers establish rejection behavior, not those live states.
- Native checks and SendInput are not atomic. A last-instant tab or same-renderer
  navigation can happen after the final URL read. Keep hands off during return/paste.
- Host identity does not pin a conversation ID, and composer focus is still the
  user's responsibility. No page text/DOM inspection or composer click was added.
- Extra visible renderers deliberately cause clipboard-only behavior, even when
  one may belong to an innocuous popup. Cold/slow reads can also time out safely.
- Existing capture limits (HDR, protected content, mixed DPI, display changes) and
  ChatGPT's possible attachment upload before Send remain documented in README.

**A browser extension is not necessary for this validated Chrome workflow.** Native
MSAA supplies the required loaded-document identity with no added dependencies.
If future Chrome behavior invalidates unique active-renderer selection, the next
architecture to evaluate remains an extension with explicit active-tab/window
identity and an authenticated local companion; it is not implemented here.

References: Microsoft's [AccessibleObjectFromWindow contract](https://learn.microsoft.com/en-us/windows/win32/api/oleacc/nf-oleacc-accessibleobjectfromwindow)
permits IDispatch retrieval and documents accessibility errors during user actions.
Microsoft's [UIA threading guidance](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-threading)
describes related accessibility/UI-thread hazards; the killable worker-process
design here is an implementation choice for bounded MSAA failures.
