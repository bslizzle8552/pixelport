# Chrome UIA and MSAA investigation

Historical observations from September 10, 2026, on Chrome 152.0.7977.84.
The initial passive study compared two separate Chrome windows, one on chatgpt.com
and one on github.com. It established native URL access without changing focus or
using browser automation, but did not establish same-window active-tab safety.
That later gate is recorded in [MSAA validation](chrome-msaa-validation.md).

No browser flags, extensions, COM registration, or dependencies were added.
The UIA experiment used Windows' existing .NET assemblies; the native experiment
used ctypes, oleacc, and existing pywin32. Root properties were inspected without
walking page content. Full URLs were reduced to host/scheme/shape in saved results;
raw scripts and traces are not part of the public tree.

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
This initial investigation did not observe a Chrome-composer foreground interval;
the later same-window validation covers that separate gate.

Do not put the raw tree walk into PixelPort's 250 ms Tk timer. Even the faster native
reader needs a worker and a deadline: one small median does not bound a hung
provider. Microsoft recommends separating UIA calls from the UI thread using an
MTA thread. A bounded worker process is worth evaluating for stronger isolation.
[Microsoft threading guidance](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-threading)

## Decision and limits

The editable omnibox is weaker evidence than the loaded document URL. Empty UIA
values, duplicate frame nodes, and multiple document placeholders rule out generic
first-match or positional selection. MSAA's unique native renderer and document
root were selected for further testing, not accepted from steady-state observations
alone. Background-tab exclusion, same-window switching, uncommitted address edits,
loading/ambiguity, stale replies, and provider failures required later validation.

Production uses a supervised process because a fast median cannot bound a hung
provider. UIA is retained here as investigation evidence, not a runtime dependency.
Other browsers and alternative Chrome provider configurations were not validated.
The later [cold-provider investigation](chrome-initialization.md) explains why
additional accessibility clients can mask initialization failures.

References: [AccessibleObjectFromWindow](https://learn.microsoft.com/en-us/windows/win32/api/oleacc/nf-oleacc-accessibleobjectfromwindow),
[pywin32 ObjectFromAddress](https://mhammond.github.io/pywin32/pythoncom__ObjectFromAddress_meth.html).
