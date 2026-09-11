# PixelPort v0.1.0 validation

The final feature-frozen functional baseline is commit `7063818` (September 11,
2026). Public naming, documentation, version metadata, and dependency/ignore hygiene
were prepared afterward without changing capture, targeting, or paste decisions.
No executable has been packaged; source acceptance is not frozen-build acceptance.

## Physical acceptance of the functional baseline

Manually confirmed on Windows 11 with Chrome and chatgpt.com, including a
multi-monitor setup:

- Automatic Chrome/ChatGPT verification without G binding.
- Two complete fresh quit/relaunch cycles.
- Immediate physical hold-middle → drag → release after launch, with no
  PowerShell click/focus ritual.
- Automatic paste into the ChatGPT composer, remaining UNSENT.
- Multiple consecutive captures and multi-monitor captures.
- Escape cancellation and keyboard capture fallback.
- Fail-closed clipboard behavior was physically validated previously: GitHub in
  the selected Chrome window blocked automatic paste and retained the image;
  returning to ChatGPT restored automatic targeting.

These results are the operator's acceptance report, not a new physical capture
performed during the branding cleanup. Raw acceptance JSONL and transcripts are
local artifacts excluded from the public working tree. The branding pass did not
repeat physical captures or independently recreate every cold Chrome provider state.

## Source validation after release preparation

Environment: Windows, standard x64 CPython 3.14.3, Pillow 12.3.0, pywin32 312.
Commands run from the repository root on September 11, 2026:

| Check | Result |
| --- | --- |
| `.\.venv\Scripts\python.exe -m unittest discover -s tests -q` | 177 passed, 3.721 seconds; no failures/errors/skips |
| `.\.venv\Scripts\python.exe -m compileall -q gptsnip tests` | Passed |
| `.\.venv\Scripts\python.exe -m pip check` | No broken requirements |
| `git diff --check` | Passed |
| `.\.venv\Scripts\python.exe tests/native_smoke.py` | Passed; startup identifies PixelPort v0.1.0 |

All existing functional tests remain unchanged. The smoke script's status text was
updated for branding and to clarify possible Tk foreground effects; its assertions
and exercised lifecycle remain intact.

The suite covers URL parsing, exact renderer/window identity, cold-provider
initialization, bounded reader failures, stale tokens/generations, target memory,
manual override, all three fresh Chrome checks, clipboard-only fallback, physical
and injected event handling, selection geometry, cancellation, native activation
boundaries, and Ctrl+V-only input. Native capture/input effects are mocked in unit
flow tests; multiprocessing tests exercise real isolated worker lifecycle.

Native smoke temporarily registers three real hotkeys and the mouse hook, disables
capture admission, dispatches quit, verifies duplicate-instance rejection, and
checks unhook/thread exit and cleanup. It performs no screenshot, clipboard write,
or SendInput. Tk startup can affect foreground. It does not prove real selector
attachment, physical gesture accuracy, or browser paste.

## Investigation evidence

- [UIA/MSAA exploration](investigations/chrome-uia.md): native property availability,
  scoped selection, and the editable-address-bar limitation.
- [Chrome selected-document validation](investigations/chrome-msaa-validation.md):
  same-window ChatGPT/GitHub switching, address drafts, ambiguity rejection, and
  measured reader performance.
- [Cold-provider initialization](investigations/chrome-initialization.md): reproduced
  BUSY failure and non-authorizing IA2 bootstrap.
- [Middle foreground acquisition](investigations/middle-foreground.md): local-focus
  versus global-foreground evidence, scoped correction, and recording lessons.

## Dependency boundary

Source requirements use `Pillow>=12.3.0,<13`, matching the tested installed minimum,
and retain `pywin32>=311,<400` on Windows. No dependencies were added or installed
for the cleanup. The old Pillow range admitted 12.1.0, before the
[12.1.1 security fix](https://pillow.readthedocs.io/en/stable/releasenotes/12.1.1.html);
[12.2.0](https://pillow.readthedocs.io/en/stable/releasenotes/12.2.0.html) includes
further security corrections. This is dependency hygiene, not evidence of an
exploitable PSD/FITS/PDF loading path in PixelPort's screen capture workflow.
Exact build-tool/dependency pins belong to the later packaging pass.

## Limits and the packaging gate

Supported claims remain Windows 11, Chrome, and chatgpt.com on the exercised setup.
Other browsers' legacy heuristics and manual binding still execute but are outside
the validated automatic Chrome claim. Site identity does not pin a conversation
or locate a composer. Last-instant tab/focus changes remain possible after checks.

Live two-window repetition of the later MSAA matrix, a held minimized interval,
controlled reload/provider outage, every Chrome configuration, mixed-DPI layout,
HDR/protected content, elevated/secure desktops, remote sessions, full-screen games,
remapped mice, free-threaded Python, and hung foreign input queues are not fully
validated. Bounds changes do not detect every display topology/scaling change.

The next dedicated pass must validate a frozen worker entry point and dependency
collection, then rerun automated/native checks and physical acceptance against the
actual downloadable executable on Windows 11 without a Python installation.
The current source entry point does not implement a frozen packaging launcher or
early `multiprocessing.freeze_support()`; add and verify these as packaging work.
Keep the existing deadlines and fail-closed checks. The planned executable name is
`PixelPort.exe`. No package, installer, archive, tag, or GitHub Release exists from
this preparation pass.
