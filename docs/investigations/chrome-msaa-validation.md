# Chrome MSAA validation

Historical measurements from September 10, 2026, on Chrome 152.0.7977.84.
The selected-document validation gate passed and informed the production reader.
These measurements predate the [cold-provider fix](chrome-initialization.md).
Current behavior is documented in [architecture](../architecture.md), and current
acceptance in [validation](../validation.md). HWND/PID values and raw traces are omitted.

## Real-machine state matrix

Installed Chrome version was rechecked: **152.0.7977.84**. The shared Chrome
top-level window and process identity remained the same. ChatGPT and GitHub
had distinct renderer identities that were stable per tab during the observed
switches. Machine-specific HWND/PID values are omitted.

| Test | Observed result | Assessment |
| --- | --- | --- |
| A: ChatGPT selected, composer focused | A measured 32.961-second interval contained 327 native reads, all `chatgpt.com`, one visible renderer, role 15. Scoped UIA focus metadata identified an Edit with the focused ProseMirror class in Chrome; the omnibox was not focused. Native foreground/focus and clipboard sequence did not change across these reads. | Pass |
| B: GitHub selected, ChatGPT background, same HWND | Initial measured interval: 112 reads over 11.296 seconds, all `github.com`. UIA selected-tab runtime IDs independently showed the GitHub tab selected and ChatGPT unselected. One visible GitHub renderer, role 15; no background ChatGPT identity appeared. | Pass, hard gate |
| C: Switch back to ChatGPT | One sample returned unknown because renderer identity changed during the read. The next sample returned `chatgpt.com` on the original ChatGPT renderer and remained stable. | Pass |
| D: Repeated switches | Four additional switches were observed in the requested alternating sequence. The visible renderer tracked the selected tab. A changing-identity sample and a zero-visible-renderer sample were rejected. Later user tab switches were also recorded; no accepted background-tab mismatch was found in comparable intervals. No second independent D sequence is claimed. | Pass for observed repeated switching |
| E: Uncommitted omnibox `https://chatgpt.com` while GitHub selected | The draft did not become an accepted document identity. There were two distinct focused-draft intervals, separated by a brief actual ChatGPT-tab visit. In 296 native samples bracketed by consistent GitHub-selected/draft-present UIA observations, 173 rejected multiple visible renderers and 123 returned `github.com`; zero returned `chatgpt.com`. Defocused-draft reads also returned GitHub. UIA later showed the draft cancelled. | Pass; no spoof |
| F: Multiple Chrome windows | Only one Chrome top-level window remained. No second concurrent window was exercised. Every renderer was scoped through `GetAncestor(..., GA_ROOT)` to the exact requested HWND. Reading the old, now-closed Chrome HWND returned unknown. A mismatched Codex PID/HWND request also returned unknown. | Exact-HWND scoping checked; two-window live repetition not performed |
| G: Failure states | Four changed-identity reads, one zero-visible-renderer read, 282 multiple-visible-renderer reads, and one invalid/missing document URL read returned unknown. Closed/invalid top-level HWND reads rejected. No held minimized interval was recorded. No controlled reload, provider outage, or deliberate renderer closure was induced. | Observed failures reject; remaining cases tested with mocks/isolated test workers |

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

## Measured performance

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
- Capture limits and possible attachment upload before Send are documented in
  the [README](../../README.md).

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
