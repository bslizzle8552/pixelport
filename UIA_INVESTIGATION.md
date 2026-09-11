# Passive Chrome identity investigation — September 10, 2026

> Historical investigation: this records the earlier deferred decision. The later
> same-window gate passed and Chrome integration is now implemented. Current
> behavior is in [MSAA_VALIDATION.md](MSAA_VALIDATION.md) and [HANDOFF.md](HANDOFF.md).
> Statements below about unchanged targeting describe the earlier investigation.

## Decision: keep the current targeting behavior

**Outcome B: a promising native URL reader was demonstrated, but reliability for
production integration is not yet proven.** No production code, tests, or
dependencies were changed. Browser/title recognition, manual G binding, and the
entire capture/clipboard/foreground/Ctrl+V pipeline remain intact.

This is not a finding that Chrome lacks native URL access. On this machine,
both UI Automation (UIA) and Microsoft Active Accessibility (MSAA) exposed useful
data without browser input. MSAA's document-root URL is the stronger candidate.
However, the observed state did not cover composer focus, switching between
ChatGPT and GitHub tabs in one window, or an unfinished omnibox edit. I did not
treat steady-state reads from two separate windows as proof of those transitions.

The complete existing suite still passes: **48 tests, no failures/errors/skips**.
No commit, push, packaging, mouse trigger, or other product feature was added.

## Environment and passive scope

- Windows machine and existing Chrome installation: **152.0.7977.84**.
- Python/pywin32 from the existing `.venv`; Windows PowerShell 5.1 in an MTA
  process for the .NET UIA probes.
- Two real Chrome top-level windows, both owned by the same Chrome process:

| Window | Representative title (sanitized) | Observed URL hostname |
| --- | --- | --- |
| A | `Easier Screenshot Sharing - Google Chrome` | `chatgpt.com` |
| B | `GitHub repository - Google Chrome` | `github.com` |

Machine-specific handles and process identifiers are omitted from this report.
No Edge top-level window was returned by the existing visible-window inspection.
Other Chromium browsers were not launched or tested.

No screenshots, clipboard writes, input injection, activation, navigation,
tab changes, address-bar focus, Ctrl+L, URL copying, conversation edits, browser
profile/history reads, browser debugging, DOM inspection, or networking from
GPTSnip occurred. Research fetched only public Microsoft/Chromium/pywin32
documentation and source. The diagnostic processes only read native properties.

Full URL strings were held briefly in probe memory and reduced to hostname,
scheme/shape, and length. Saved evidence contains no URL paths, conversation IDs,
queries, or page/composer text. Focus summaries omitted names and text. There was
no browsing-history collection. Native reads can cause Chrome to initialize its
accessibility provider internally; that is distinct from changing settings or
interacting with a page.

## Actual UI Automation observations

The initial bounded raw-tree inspection started at
`AutomationElement.FromHandle(the_specific_Chrome_HWND)`. It stopped at document
roots rather than traversing page content. It was capped at 180 nodes per window,
so it was a partial inspection, not a complete tree dump.

Relevant observed structure:

```text
Chrome top-level HWND
  BrowserRootView -> NonClientView -> BrowserFrameViewWin -> BrowserView
    TopContainerView -> ToolbarView -> LocationBarView -> OmniboxViewViews
    HorizontalTabStripRegionViewOld -> TabStrip -> TabContainerImpl -> Tab
```

The address control exposed:

| Property/pattern | Observed value |
| --- | --- |
| ControlType | `ControlType.Edit` |
| ClassName | `OmniboxViewViews` |
| AutomationId | `view_1012` |
| Name | `Address and search bar` |
| Parent toolbar | `ToolbarView`, AutomationId `view_1000` |
| Supported patterns | ValuePattern, TextPattern, ScrollItemPattern |
| ValuePattern.Current.IsReadOnly | `false` |
| HasKeyboardFocus | `false` in every repeated sample |
| ValuePattern.Current.Value | Scheme-elided URL; reduced immediately to hostname |

The separate roots returned `chatgpt.com` and `github.com`, respectively.
Neither address bar had to receive focus. The probe did not search the page or
the entire tree for an occurrence of `chatgpt.com`.

`ControlType.TabItem`, class `Tab`, AutomationId `view_20`, exposed
`SelectionItemPattern.Current.IsSelected`. The scoped tab container returned
one tab item per window, selected in all 25 samples. The selected tab titles did
not contain the ChatGPT marker. No simultaneously selected/unselected tab pair
was available in that observation, so background-tab exclusion was not proven.
Hidden renderer HWNDs existed, but I did not assume they represented background
tabs; they can also serve other browser UI/content.

The content frame included `ContentsWebView`/`WebView` document placeholders
without ValuePattern support, and actual `RootWebArea` document nodes with
ValuePattern/TextPattern support. Some initial RootWebArea values were empty.
Later reads returned the expected full URL for the actual document; another
RootWebArea in A remained empty. Both empty and populated nodes could report
`IsOffscreen=false`. Thus neither a generic document search nor that flag alone
is a sufficient selector. The cause of the initial empty values was not isolated;
provider initialization is a possibility, not a confirmed diagnosis.

The targeted frame-path probe used only child-scoped `FindAll` calls with
`PropertyCondition` matches and rejected missing/duplicate expected nodes. Even
this machine had two `View` children where an initial content-path probe expected
one, illustrating why positional assumptions need care. No such path was added
to production.

The .NET wrapper did not expose a `LegacyIAccessiblePattern` type in this runtime.
That was a probe API limitation, not evidence that Chrome lacks MSAA; the separate
native MSAA probe below worked.

## Stronger candidate: the native document root

Win32 `EnumChildWindows` found renderer windows with class
`Chrome_RenderWidgetHostHWND`. `GetAncestor(..., GA_ROOT)` scoped each renderer
to the requested Chrome HWND, and `IsWindowVisible` distinguished native visible
and hidden renderers. A had two renderer children, one visible; B had three, one
visible. Only the unique visible renderer was read.

`oleacc.dll!AccessibleObjectFromWindow(renderer_hwnd, OBJID_CLIENT, IID_IAccessible)`
returned `ROLE_SYSTEM_DOCUMENT` (`15`). Reading only `accValue(CHILDID_SELF)` on
that root returned a full HTTPS URL: `chatgpt.com` for A and `github.com` for B.
There was no descent into document content.

This also worked directly in Python with the **existing** pywin32 dependency:
request `IID_IDispatch`, wrap the returned pointer using
`pythoncom.ObjectFromAddress`, then perform property-get calls for `accRole` and
`accValue` with child ID `0`. The probe released the original COM reference;
pywin32 owns the additional reference acquired by its QueryInterface call.
COM use stayed in a separate, short-lived MTA process.

This is stronger evidence than editable omnibox text. In the source matching
installed Chrome **152.0.7977.84**, the document branch of
`GetValueAttributeAsBstr` returns accessibility tree data's document URL.
That supports evaluating the document-root value as the URL source rather than
an address-bar draft. It does not by itself prove renderer selection during
tab transitions. [Matching Chromium source](https://chromium.googlesource.com/chromium/src/+/152.0.7977.84/ui/accessibility/platform/ax_platform_node_win.cc#8446)

## Configuration and dependencies

No settings, flags, extensions, or debugging configuration were enabled. The
running Chrome process command line had no `--force-renderer-accessibility`,
remote-debugging option, or explicit accessibility/UIA option. Only those
presence/absence decisions were printed; the full command line was not logged.
Existing policy/profile settings were not audited.

Chrome documents native UIA support as default from version 138. That is supporting
platform context, not a substitute for the native observations above. Edge shares
Chromium work, but its current behavior on this machine remains untested.
[Chrome UIA announcement](https://developer.chrome.com/blog/windows-uia-support-update)

No Python package was installed. The UIA experiment used Windows' existing
UIAutomationClient/UIAutomationTypes assemblies. The MSAA experiment used native
oleacc, ctypes, and the existing pywin32. `comtypes` was absent and was not needed
for this read-only document-root proof.

## Measured cost

Wall-clock measurements in the probe processes; these are not CPU/idle-impact
benchmarks and do not include process startup:

| Lookup | Samples | First lookup | Warm median | Warm range |
| --- | ---: | ---: | ---: | ---: |
| Initial bounded raw UIA tree, A | 1 | 544 ms | — | — |
| Initial bounded raw UIA tree, B | 1 | 319 ms | — | — |
| Child-scoped UIA omnibox, A | 25 | 210 ms | about 15 ms | about 12–30 ms |
| Child-scoped UIA omnibox, B | 25 | 16 ms | about 13 ms | about 11–18 ms |
| Python MSAA visible document root, A | 10 | 109 ms | 3.85 ms | 2.91–4.91 ms |
| Python MSAA visible document root, B | 10 | 4.86 ms | 3.63 ms | 3.08–3.98 ms |

All 50 repeated UIA address reads returned the expected host without an exception.
All 20 Python MSAA root reads returned the expected host, one visible renderer,
and document role. UIA samples ran approximately once per second; the MSAA
experiment used ten iterations with 250 ms pauses, then exited.

Clipboard sequence stayed unchanged during these repeated samples. The foreground
window was another application throughout them. The initial probe also retained
the same foreground HWND and clipboard sequence before/after, although focus
metadata inside that foreground application changed. No input method was called.
There was **no observed Chrome-composer foreground interval**, so that specific
requirement is still unverified. A request for a brief user-controlled composer
focus interval did not yield such a sample during the investigation.

Do not put the raw tree walk into GPTSnip's 250 ms Tk timer. Even the faster native
reader needs a worker and a deadline: one small median does not bound a hung
provider. Microsoft recommends separating UIA calls from the UI thread using an
MTA thread. A bounded worker process is worth evaluating for stronger isolation.
[Microsoft threading guidance](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-threading)

## What is proven and what is missing

| Requirement | Evidence/status |
| --- | --- |
| Address bar present and readable without focusing it | Proven in these two windows |
| Conversation-only title does not prevent URL retrieval | Proven for A |
| Reads scoped to a particular HWND | Proven for these two separate windows |
| Selected tab metadata exposed | Proven for one selected item per observed window |
| Full native document URL available | Proven for visible document roots in A/B |
| Composer focus, Chrome foreground | Not observed; not proven |
| Background ChatGPT plus active GitHub in one window | Not exercised; not proven |
| Active ChatGPT plus background GitHub in one window | Not exercised; not proven |
| Same-window tab switches / same-title different sites | Not exercised; not proven |
| Uncommitted omnibox text | Not manipulated; native document source is promising but no live draft test |
| Navigation/loading/provider warm-up | Initial empty UIA values observed; transitions not characterized |
| Split view, side panel, DevTools, multiple visible documents | Not exercised; must reject ambiguity in any future reader |
| Edge/other browsers | No live acceptance evidence |
| Provider hangs, cancellation, stale worker replies | No production worker built or tested |

These gaps are why this pass does not replace the current automatic predicate.
There is no title fallback relaxation, URL substring matching, or new automatic
destination. Codex/ChatGPT.exe remain excluded automatically.

## Next architecture and exact validation steps

**Evaluate a bounded native MSAA document-root reader next**, using the successful
probe as evidence. An extension is not yet necessary based on what was found.
The next gate should be a user-controlled state matrix while the agent only reads
native metadata:

1. Keep GPTSnip stopped to avoid accidental captures during identification tests.
   Use the existing ChatGPT conversation; no G binding is needed for this probe.
2. Manually bring Chrome A forward, click its composer, and leave it for at least
   five seconds. Read its unfocused omnibox and visible document root, verify
   `chatgpt.com`, and confirm foreground/focus are unchanged by the reads.
3. In A, manually open a non-ChatGPT tab such as GitHub, leaving ChatGPT in the
   background. With GitHub selected, repeatedly read A and require `github.com`
   or an explicit unreadable result; never `chatgpt.com` from the background tab.
4. Manually switch back to ChatGPT. Require `chatgpt.com` despite arbitrary title
   and a background GitHub tab. Repeat transitions while sampling; record the
   timing of old/new/empty values and renderer identity changes.
5. With GitHub loaded, manually edit the address bar to an unsubmitted ChatGPT
   address without navigating. Compare the omnibox draft with the document-root
   host. Repeat after defocusing without navigation. The document reader must
   never treat an uncommitted address as loaded ChatGPT.
6. Keep A on ChatGPT and a separate Chrome B on GitHub. Alternate foreground
   windows manually, then close/change A. Check HWND/PID/renderer binding and
   stale-result handling; no result may migrate between windows.
7. Exercise loading, minimized/closed windows, unavailable accessibility, and
   multiple visible documents. Ambiguous/missing/changing evidence must reject.
   Repeat on Edge separately before enabling it.

These are later user-assisted tests; they were not performed or automated in this
pass. No screenshots, clipboard changes, or messages are needed to validate them.

If that gate passes, an implementation should:

- Require an explicitly supported browser, a uniquely scoped visible document,
  stable window/renderer identity, and a successfully parsed document URL.
- Initially accept exactly `https://chatgpt.com` with an appropriate HTTPS port,
  rejecting credentials, malformed values, lookalikes, and unsupported schemes.
  No legitimate subdomain was observed; do not invent a wildcard allowance.
- Discard full URLs immediately. Store only the decision and minimal in-memory
  identity evidence; do not persist paths or conversation IDs.
- Use an isolated reader with a bounded queue/deadline, rate-limit idle work, and
  reject stale/asynchronous replies. Do not rely solely on foreground-HWND changes
  because the active tab can change inside one window.
- Retain manual binding and stale-target blockers. Revalidate the selected active
  document before activation and immediately before paste; a cached idle result
  alone is insufficient. Preserve the existing exact snapshot/input checks.
- Add the requested parser, multiple-tab/window, failure, stale-memory, manual
  override, clipboard-only, and Ctrl+V-only regressions; run the full suite.

If native document selection proves unreliable, the next explicit integration to
evaluate is a narrowly scoped browser extension reporting the active tab's origin
and tab/window identity to a local companion. Browser tab APIs have explicit
active-tab state; extension permissions, lifecycle, and authenticated local
messaging would need their own review. No extension was built or installed.
[Chrome Tabs API](https://developer.chrome.com/docs/extensions/reference/api/tabs)

## Current manual use and future end-to-end acceptance

No URL-based production acceptance test is claimed as available or passed. Current
GPTSnip still needs the ChatGPT title marker or an explicit G binding for this
conversation. Existing manual acceptance remains in [HANDOFF.md](HANDOFF.md).

After a future justified implementation, the requested acceptance must start fresh
with no binding, recognize this custom-title Chrome conversation, retain it while
Codex is used, capture/return/paste only into that composer, and leave the message
unsent. The matching negative test must switch that remembered window to GitHub
and observe it before capture; stale ChatGPT memory must block automatic paste,
even if another ChatGPT window exists. Verify the screenshot remains on clipboard.
Those end-to-end actions are outside this read-only investigation.

## Changed files and verification

Only documentation changed in this pass:

- `UIA_INVESTIGATION.md`: this report.
- `README.md`: link to the investigation and unchanged-production status.
- `HANDOFF.md`: pointer to the latest investigation, preserving the safety-fix report.

All production modules, test files, and `requirements.txt` were compared with
their pre-investigation copies and remain byte-for-byte identical. No tests were
added because no production behavior was implemented. Full suite: **48 passed**.
Compilation, dependency consistency, and whitespace checks also passed.

Final validation commands (from the repository root):

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q gptsnip tests
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

The final unittest run completed in 0.303 seconds with no failures, errors, or
skips. Dependency output was `No broken requirements found.` Direct document
checks also covered untracked Markdown files that `git diff --check` omits.

Probe scripts and redacted evidence were retained locally outside the repository.
These session-specific scratch files and logs are excluded from version control.
No GPTSnip instance was launched or restarted by this historical investigation.

API references: [AutomationElement.FromHandle](https://learn.microsoft.com/en-us/dotnet/api/system.windows.automation.automationelement.fromhandle?view=windowsdesktop-10.0),
[AccessibleObjectFromWindow](https://learn.microsoft.com/en-us/windows/win32/api/oleacc/nf-oleacc-accessibleobjectfromwindow),
[pywin32 ObjectFromAddress](https://mhammond.github.io/pywin32/pythoncom__ObjectFromAddress_meth.html).
