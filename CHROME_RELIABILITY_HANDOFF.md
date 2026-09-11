# Automatic Chrome identity reliability — September 10, 2026

**Root cause reproduced; narrow fix implemented. Physical acceptance is pending.**
No commit, push, packaging, release cleanup, or browser settings changes were made.
GPTSnip and the diagnostic application instances are stopped.

## 1. Confirmed cause and raw-reader evidence

Chrome exposed an uninitialized accessibility document. Its unique visible
`Chrome_RenderWidgetHostHWND` returned document role 15, MSAA state `0x844`
(BUSY, focusable, focused), and no usable document URL. Repeated standalone
MSAA reads returned `unknown / wrong_role_or_unavailable`. Both MTA and STA
probes failed identically. The current renderer was visible, correctly scoped
to the foreground Chrome window and its PID, and the window was not minimized.
There was one additional hidden renderer, which did not compete for selection.
Chrome remained version **152.0.7977.84**, matching the previous validation.

The existing reader queried only MSAA role/state/value. In the matching Chromium
source, role/state use `OnMinimalPropertiesUsed`, enabling `kNativeAPIs` without
requesting web document data. Chrome's initial empty document is explicitly BUSY.
Waiting or increasing the deadline does not supply the missing request.

A bounded diagnostic requested `IAccessible2::get_states` on that same document
root through `IAccessible -> IServiceProvider -> QueryService`. This reads one
integer; it does not traverse content or perform an action. The first MSAA sample
120 ms later remained unknown. The next sample, approximately 240 ms after the
query, returned `chatgpt.com`; the next four samples also verified it. Foreground
and clipboard sequence were unchanged. No UIA probe was needed for this recovery.

The earlier validation ran UIA inspection alongside MSAA. Those additional reads
are a plausible explanation for its initialized provider state, **not a directly
replayed historical cause**. The current failure and native-query recovery were
directly observed.

## 2. Baseline comparison and failure stage

An isolated detached worktree at `4244ea3` was created under the user's Temp
directory. The working checkout was preserved.

| Check in the same current Chrome environment | Result |
| --- | --- |
| Current committed reader, raw, before initialization | Unknown: wrong role or unavailable state |
| `4244ea3` reader, raw, before initialization | Same failure |
| Current reader through spawned worker, three requests | Same native failure; correct tokens; about 580 ms cold and 11 ms warm |
| `4244ea3` through spawned worker, three requests | Same native failure; correct tokens; about 505 ms cold and 11 ms warm |
| Old baseline App after native initialization, two fresh passive launches | Automatically remembered ChatGPT, no G |
| Patched App after initialization, four fresh passive launches, including two on final source | Automatically remembered ChatGPT, no G, real mouse hook running |

Both pre-initialization transports had live supervisors, healthy request/reply
exchange, no deadline failure, and clean supervisor shutdown. The failed identity
was produced **inside `read_once`, at its BUSY-state gate**, before reading a URL.
It was not a positive identity lost to stale tokens, generations, or result age.
App correctly refuses that unknown result, so fresh-launch memory stays empty.

The actual previously running process was not instrumented retrospectively.
Its internal history cannot be claimed from these reproductions. The baseline
App itself was run after provider initialization; its raw reader and real worker
were both tested before initialization.

## 3. Mouse-hook / multiprocessing assessment

The middle-mouse diff adds hook startup before the first lazy BrowserReader
request and mouse polling before identity polling. It also changes capture
generation and selector timing during gestures. It does not change reader
startup code, spawn context, mutex name, deadlines, or idle request admission.

The failure reproduced without GPTSnip's hook in a standalone process and in the
pre-middle-mouse worker. After native initialization, App instances with the real
hook successfully spawned, read, polled, and remembered Chrome. Thus hook/spawn
ordering is **not a necessary cause of this reproduced failure**. There is no
evidence it contributed here; unrelated rare scheduling failures are not ruled
out universally. Runtime: Python **3.14.3**, 64-bit Windows.

## 4. Code changes

- `gptsnip/native_document.py`: for a unique, unchanged, visible document root
  that reports BUSY without other disqualifying state flags, request IA2 root
  state once. Release all native interfaces and return unknown. Later ordinary
  requests must still obtain two matching, non-BUSY MSAA URL reads. Initialization
  failure stays unknown. Explicit COM initialization and pointer-sized COM calls
  remain inside the isolated reader process in application operation.
- `gptsnip/browser.py`: opt-in diagnostic events for request admission, supervisor
  receipt, worker start, native metadata/results, transport rejection/delivery.
- `gptsnip/app.py`: diagnostic events for foreground observation, application
  result checks/rejections, and remembering the automatic Chrome target. The
  identity predicate is expressed as explicit checks with the same acceptance rule.
- `tests/test_native_document.py`, `tests/test_browser.py`: regressions below.

Diagnostics require `GPTSNIP_IDENTITY_DIAGNOSTICS=1` and stop after the first
12 admitted requests per reader/launch. They print only hostnames, native IDs,
numeric role/state, and fixed stage/reason labels. No URL paths, conversation IDs,
page/composer text, window titles, or provider exception text is printed.

No timeouts, retry intervals, eligibility rules, renderer selection rules, or
manual override priorities were relaxed. BUSY is still rejected even if a URL
would be available. The bootstrap itself can never authorize activation or paste.

`core.py`, `mouse.py`, `selector.py`, `windows.py`, `__main__.py`, and requirements
were verified unchanged against HEAD. Capture, clipboard, activation, Ctrl+V,
Escape, keyboard fallback, and the manual G path retain their existing code.

## 5. Regression and validation results

Starting complete suite: **145 passed**. Final complete suite: **151 passed** in
2.787 seconds, with no failures, errors, or skips.

The new cold-provider test makes MSAA remain BUSY until the extended state request
occurs. It **fails against `4244ea3`** at the recovery assertion and passes with
this fix. It also checks that bootstrap remains unknown, adds no retry sleep, and
requires two subsequent MSAA value reads with the original stability delay.

Other new coverage verifies BUSY cannot qualify even with a ChatGPT URL; unsupported
or failed initialization remains unknown and redacted; changed/unavailable roots
cannot bootstrap; COM interface discovery, 32-bit state output, and release on
success/failure/exception; and the opt-in diagnostic limit.

| Validation | Result |
| --- | --- |
| Full unittest suite | 151 passed |
| Compilation | Passed |
| Dependency consistency | No broken requirements |
| `git diff --check` | Passed; Git emitted only LF/CRLF notices |
| Native lifecycle smoke after final production changes | Passed |
| Actual production IA2 helper on current Chrome root | Succeeded; subsequent stable MSAA remained eligible |
| Two fresh passive launches on final source | Both remembered ChatGPT; no manual binding; foreground and clipboard unchanged |

Native smoke verified actual hotkey registration, duplicate-instance rejection,
Q dispatch, WH_MOUSE_LL installation/unhook/thread exit, and cleanup. It does not
exercise screenshot/paste. Passive App runs disabled capture and G admission while
retaining real idle observation, Tk scheduling, browser workers, and hook lifecycle.
Every diagnostic supervisor was joined and verified stopped. The final process
inventory showed no GPTSnip application or multiprocessing worker remaining.

## 6. Physical acceptance — action needed

**Not performed or claimed passed in this pass.** The historical acceptance does
not count for this fix. Chrome is currently initialized by the diagnostic query,
so the passive fresh launches above are not independent cold-Chrome trials.

From PowerShell:

```powershell
cd C:\dev\gptsnip
$env:GPTSNIP_IDENTITY_DIAGNOSTICS = '1'
.\.venv\Scripts\python.exe -m gptsnip
```

1. Do not press G. Select the existing ChatGPT conversation in Chrome, click the
   composer, and wait briefly for `Chrome target verified as chatgpt.com`.
2. Switch elsewhere, middle-drag a region, and release. Confirm Chrome returns
   and the screenshot appears **UNSENT**.
3. Quit completely with Ctrl+Alt+Shift+Q. Relaunch with the same command and repeat
   steps 1–2 without G. Report both cycles separately.
4. In the same Chrome window, select GitHub and leave it foreground briefly.
   Capture from elsewhere: it must stay on the clipboard without automatic paste.
5. Select ChatGPT again, click its composer, wait for verification, and repeat the
   capture. Confirm automatic recovery and an unsent attachment.

We also need a cold-provider recheck to demonstrate the complete patched bootstrap
path live, rather than just the isolated causal query and software regression.
If recreating that state requires restarting Chrome, preserve any unsent draft
first. No Chrome restart, flags, or accessibility setting changes were performed
by the agent. Do not treat a warm-provider physical pass as proof of every provider
startup state.

## 7. Remaining uncertainty and retained evidence

The specific time/reason Chrome lost its earlier initialized provider state was
not observed. Popup/DevTools/side-panel states were not manipulated; the observed
single-visible-renderer failure was not an ambiguity case. A permanently BUSY or
unsupported provider still fails closed. Existing non-atomic tab/paste limitations
remain. No live GitHub transition or physical paste was performed by the agent.

Scratch probe scripts, the detached baseline worktree, and two redacted final
passive-cycle logs are retained in `%TEMP%` with `gptsnip` prefixes. Existing
historical validation and release documents were left unchanged.

Matching source references used to diagnose the provider gap:

- [Chrome 152 minimal versus web accessibility requests](https://github.com/chromium/chromium/blob/152.0.7977.84/content/browser/accessibility/browser_accessibility_state_impl.cc)
- [Chrome 152 MSAA role/state, IA2 get_states, and document URL mapping](https://github.com/chromium/chromium/blob/152.0.7977.84/ui/accessibility/platform/ax_platform_node_win.cc)
- [Chrome 152 initial BUSY empty document](https://github.com/chromium/chromium/blob/152.0.7977.84/ui/accessibility/platform/browser_accessibility_manager_win.cc)
- [IAccessible2 interface discovery contract](https://github.com/LinuxA11y/IAccessible2/blob/master/api/Accessible2.idl)

Stop point: ready for user-assisted physical acceptance; **not declared resolved**.
