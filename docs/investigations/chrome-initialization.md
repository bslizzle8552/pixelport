# Chrome cold-document initialization

Investigation: September 10, 2026. Chrome 152.0.7977.84, standard 64-bit Python
3.14.3. This records the cause of failed fresh-launch automatic targeting and the
non-authorizing initialization fix included in functional baseline `7063818`.
Current physical acceptance is in [validation](../validation.md).

## Reproduction and causal evidence

The unique visible Chrome renderer exposed MSAA document role 15, state `0x844`
(BUSY, focusable, focused), and no usable document URL. Repeated MTA and STA MSAA
reads stayed unknown. One hidden renderer did not compete with the visible root.

| Comparison in the same environment | Result |
| --- | --- |
| Pre-middle baseline `4244ea3`, raw reader | Same BUSY failure |
| Current pre-fix raw reader | Same BUSY failure |
| Baseline spawned worker, three requests | Native failure; correct tokens; about 505 ms cold, 11 ms warm |
| Current spawned worker, three requests | Native failure; correct tokens; about 580 ms cold, 11 ms warm |

The failure occurred at the BUSY gate in `read_once`, before URL parsing. Workers
and supervisors exchanged replies and shut down normally. There was no token,
result-age, or deadline loss hiding a positive identity. The failure reproduced
without a mouse hook, rejecting hook/spawn ordering as a necessary cause here.

A root-only `IAccessible2::get_states` call through `IAccessible` /
`IServiceProvider` / `QueryService` requested web accessibility data. The first
MSAA sample 120 ms later stayed unknown; the next at roughly 240 ms returned
chatgpt.com, followed by four successful samples. Foreground and clipboard sequence
were unchanged. No UIA probe was needed for that recovery.

Matching Chromium source shows minimal MSAA role/state requests enable native APIs
without requesting web document data. An initial empty document remains BUSY.
IA2 state access requests the missing data; simply extending the deadline does not.
Earlier simultaneous UIA inspection plausibly warmed the provider, but the exact
historical reason it later returned to an uninitialized state was not observed.

## Production correction and boundaries

Only an unchanged, uniquely scoped, visible document with BUSY and no other
disqualifying state can bootstrap. Interface discovery begins with IAccessible;
IDispatch remains the ordinary MSAA read path. IA2 `get_states` is vtable slot 35
and its output is a 32-bit Windows long. All retrieved references are released
on success, failure, and exception.

Bootstrap always returns unknown. A later request must pass ordinary role/state,
URL, native identity, and two matching reads 120 ms apart. Failure stays unknown.
No renderer preference, deadline, retry interval, manual priority, or eligibility
rule was relaxed. The one-second worker deadline still contains a hung provider.

## Validation and interpretation

The cold-provider regression fails against `4244ea3` at recovery and passes with
the fix. It requires initialization to remain ineligible, no additional retry sleep,
and two fresh subsequent URL reads. Tests also cover invalid state, identity changes,
unsupported initialization, redaction, correct COM discovery, and reference release.
The Chrome-fix stage passed 151 tests; the final functional baseline passes 177.

After initialization, two passive baseline launches and four patched launches
(including two on final Chrome-fix source) remembered ChatGPT without G. Real hooks
and supervised workers were active; capture was disabled in these passive runs.
Those runs are warm-provider evidence, not independent cold-Chrome acceptance.
The isolated native helper and cold-provider regression establish the narrower
initialization path. Permanently BUSY/unsupported providers continue to fail closed.

## Source references

- [Minimal versus web accessibility requests](https://github.com/chromium/chromium/blob/152.0.7977.84/content/browser/accessibility/browser_accessibility_state_impl.cc)
- [MSAA role/state, IA2 states, and document URL mapping](https://github.com/chromium/chromium/blob/152.0.7977.84/ui/accessibility/platform/ax_platform_node_win.cc)
- [Initial BUSY empty document](https://github.com/chromium/chromium/blob/152.0.7977.84/ui/accessibility/platform/browser_accessibility_manager_win.cc)
- [IAccessible2 discovery contract](https://github.com/LinuxA11y/IAccessible2/blob/master/api/Accessible2.idl)
