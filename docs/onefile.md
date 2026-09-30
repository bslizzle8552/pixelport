# PixelPort v0.1.0 ONEFILE candidate

**ONEFILE is physically tested and accepted by the user for v0.1.0.**
The final release uses the accepted executable and default Windows icon. This page
retains the engineering evidence; the [release record](release-v0.1.0.md) is the
current acceptance and delivery status.

## ONEDIR acceptance recorded

The user physically confirmed the actual ONEDIR executable: double-click cold
launch without Python/PowerShell or G, automatic Chrome/chatgpt.com recognition,
physical middle hold/drag/release, automatic screenshot paste remaining UNSENT,
a second complete cold launch, same-Chrome-window non-target invalidation with
clipboard-only capture, and automatic ChatGPT recovery/paste.

Remaining ONEDIR physical checks: tiny middle click; Escape cancellation and next
gesture; Ctrl+Alt+Shift+S fallback; duplicate refusal; Q quit with normal middle-click
restoration and relaunch; multi-monitor capture. Source physical evidence and
frozen automated checks do not fill those gaps. See validation.md for the record.
The existing accepted ONEDIR artifact was preserved byte-for-byte, including its
1.0-second reader deadline; it was not rebuilt in this pass.

## Build architecture and versions

The new `packaging/pixelport-onefile.spec` uses the same launcher, hidden imports
(win32timezone and win32com), standard dependency hooks, notice collection, version
metadata, default icon, console bootloader and no-UPX configuration as ONEDIR.
Analysis data and binaries are passed directly to EXE rather than COLLECT. The
wrapper selects an isolated output/work path, preserving ONEDIR.

```powershell
.\packaging\build.ps1 -Format Onefile
```

Underlying command, with Python/Windows-only build PATH:

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --distpath dist/onefile --workpath build/onefile packaging/pixelport-onefile.spec
```

- CPython 3.14.3 x64; PyInstaller 6.22.2; hooks-contrib 2026.7.
- Pillow 12.3.0; pywin32 312; Tcl/Tk 8.6.15.
- Exact remaining build pins are in requirements-build.txt; runtime requirements unchanged.
- Final build elapsed: **34.561 seconds** (initial 1.0-second build: 29.308 seconds).
- Candidate: `dist/onefile/PixelPort.exe`.
- Size: **19,842,768 bytes** (about 18.92 MiB).
- SHA-256: `5d92b142a0f8723102254bd6b866398d93d75a97e717ec45db3e01cda70a7311`.
- ProductName/FileDescription PixelPort; ProductVersion/FileVersion 0.1.0;
  OriginalFilename PixelPort.exe; CompanyName omitted; default icon, no final ICO.

The executable is self-contained. Readable companion LICENSE, THIRD_PARTY_NOTICES.md
and notices are also supplied; notices are embedded in the executable. Preserve
these companions for distribution. No installer or release archive was created.

## Product decision: bounded frozen timeout

The initial ONEFILE series at 1.0 second had cold App outcomes of **982.916,
752.633, 1009.101 (timeout), 737.864 and 868.337 ms**. In the failing third launch,
a second worker-start request also timed out at 1008.188 ms before a later retry
recovered. Six cooldown responses and both timeouts remain recorded. Forty-seven
actual warm worker reads passed: median 157.019 ms, p95 168.738 ms, max 191.766 ms.
Timeout completion is censored: these failures do not reveal exactly when their
native reads would have completed. The test observed worker bootstrap of about
599–600 ms in those failed requests; repeated extraction was not observed.

The user then explicitly approved modest packaged timeout headroom and clarified
that the invariant is **no fresh positive verification -> no automatic paste**.
The narrow change sets BrowserReader's default to **1.5 seconds when sys.frozen is
true**, retaining **1.0 second for source runs** and explicit caller timeout overrides.
No eager worker, extra supervisor, prewarming, or lifecycle redesign was added.

The 300 ms positive-sample age, 120 ms two-read stability check, exact ChatGPT
hostname requirement, window/renderer identity, stale blocking, three capture
checks, capture-flow bound, clipboard-only fallback and Ctrl+V-only behavior remain
unchanged. A 1.5-second expiry returns an ineligible result and retires the worker;
it cannot authorize paste. Future frozen builds of either format use this default;
the preserved preexisting ONEDIR binary still uses its original 1.0-second value.

## Five revised isolated cold launches

Each run began with no PixelPort processes, a one-second quiet interval, and a
second process check. Each new top-level process extracted into a fresh directory.
These are cold application launches, not OS reboots or cleared filesystem caches.
Chrome was already running and the user selected ChatGPT. No duplicate launch or
build/audit/unit-test workload overlapped these measured cycles.

All times are milliseconds. App-child appearance is a sampled native process
observation, not an exact extraction-completion timestamp.

| Cycle | Launch to banner | App child first seen | Admission to App | Worker bootstrap | Native phase | Result |
|---|---:|---:|---:|---:|---:|---|
| 1 | 4512.042 | 3664.444 | 779.153 | 403.382 | 300.016 | Pass / ChatGPT |
| 2 | 4298.736 | 3383.429 | 721.160 | 394.328 | 266.761 | Pass / ChatGPT |
| 3 | 3988.029 | 3144.439 | 772.491 | 385.260 | 314.053 | Pass / ChatGPT |
| 4 | 4091.082 | 3338.056 | 751.261 | 402.913 | 291.389 | Pass / ChatGPT |
| 5 | 4161.657 | 3319.306 | 730.322 | 415.411 | 259.011 | Pass / ChatGPT |

Cold request-to-App: **min 721.160, median 751.261, max 779.153 ms**. Maximum used
about 52% of the 1,500 ms budget, leaving about **721 ms** of measured margin.
Worker-start-to-receipt bootstrap: min 385.260, median 402.913, max 415.411 ms.
Cold native phase: min 259.011, median 291.389, max 314.053 ms.

The five successful current runs all happen to fit below 1.0 second. They do not
by themselves prove a prior censored failure would have completed by 1.5 seconds.
The approved bounded headroom is retained to reduce false timeouts; no claim is
made that Windows load or every other machine will have this exact distribution.

## Warm requests

**55 warm reads**, 11 per launch: all fresh, verified, eligible ChatGPT; zero
unknown, cooldown, deadline, stale-result or provider-error replies.

| Admission to App | Minimum | Median | p95 (nearest rank) | Maximum |
|---|---:|---:|---:|---:|
| Milliseconds | 127.674 | 156.754 | 159.854 | 174.860 |

Warm native-phase median: 129.892 ms; p95: 133.531 ms; max: 135.062 ms.
These are external timestamped stdout observations; pipe/thread scheduling can
shift individual event arrival times. They are not precision profiling of the
120 ms internal sleep. All unchanged native stability logic still executes.

## Extraction and frozen worker behavior

Normal ONEFILE topology was verified as **bootloader parent -> one application ->
one BrowserReader worker**. Exactly one normal startup banner appeared. The child
entered the intended native reader, created no windows, and did not execute normal
PixelPort hook/mutex startup. Early freeze_support remains before app imports.

The application and worker loaded python314.dll from the **same** observed _MEI
directory in every revised cycle. Exactly one such directory was seen per launch;
there was no repeat extraction for the worker. The bootloader handles top-level
extraction before application startup; this time is outside the subsequently
admitted BrowserReader request budget. Application-child appearance was about
3.14–3.66 seconds after launch; the banner arrived at about 3.99–4.51 seconds.
That includes extraction/bootloader/system scheduling and is not a pure decompression
benchmark. It explains the large launch delay; it does not explain away per-request
worker bootstrap cost. The worker still spends about 0.4 seconds starting/importing.

All _MEI extraction directories were removed after Q exit. A separate pywin32
`gen_py` cache directory remained under the isolated test TEMP path. This is
reported separately; it is not a leaked _MEI extraction tree or an orphan worker.
No cache cleanup behavior was added to the product.

The first probe attempt used CREATE_NEW_CONSOLE plus hidden startup flags, and its
console later took foreground. Two launches admitted zero Chrome requests (one
ran to the observation limit, the second was stopped cleanly). Those are preserved
as **invalid timing attempts**, not successes. The passive onefile harness then
used CREATE_NO_WINDOW so it could observe Chrome without a focus call. Normal
double-click execution of the built candidate remains a visible console application.
The original harness also called any residual TEMP entry an extraction failure;
inspection showed only gen_py remained. Its check now specifically reports _MEI
cleanup and lists residual entries separately; original diagnostic files were kept.

PyInstaller's documented bootloader/process inheritance explains this topology;
see [bootloader and environment behavior](https://pyinstaller.org/en/stable/advanced-topics.html).
Runtime hook inspection confirmed the supported multiprocessing diversion. No
private PyInstaller environment state is modified inside the application.

## Automated checks and source validation

All five revised cycles passed: one application, one intended worker, no recursion,
WH_MOUSE_LL installed, automatic ChatGPT target remembrance, Q exit 0, hook-thread
exit, worker exit, no orphans, all three hotkeys released, no child windows, no
traceback/missing-import/Tk/COM errors, and unchanged clipboard sequence. No capture,
paste, browser navigation, tab change or keyboard injection was performed.

After all timing, a separate final run with identity timing disabled passed
second-instance refusal (exit 1, no second banner), original survival, clean Q,
no orphans, extraction cleanup and unchanged clipboard. Physical middle-click
restoration and real capture cancellation are still user tests.

**185 tests passed in 7.139 seconds**; compileall for gptsnip/tests/packaging, pip
check, git diff --check and native lifecycle smoke passed. Four added regressions
cover default selection/source preservation, slow fresh positive acceptance,
hung-provider fail-closed timeout/cleanup, and stale-positive rejection. The slow
positive test primes transport before its >1-second read, avoiding conflating the
request-budget assertion with unpredictable source-interpreter startup.

## Artifact and privacy audit

The final archive contains 1,000 entries, 308 Python modules and 16 license/notice
entries plus the top-level notice overview. Required Python, pywin32, COM, Pillow,
Tk/Tcl and multiprocessing resources are present. No copies of user32, kernel32,
dwmapi or oleacc were bundled. No custom diagnostic runtime hook is present.

Archive, embedded Python code and base-library checks found no machine username or
repository path leakage; no project tests/docs, diagnostic JSONL, transcripts,
screenshots, investigation files or scratch trees were included. An initial host
substring search matched suffixes inside upstream author/license domains; review
identified those as false matches, not captured browsing data. No private browser
URL, conversation ID, API key, telemetry, network call or updater was introduced.
Only gptsnip.browser changed among bundled project modules relative to the initial
ONEFILE candidate. All other production behavior and internal gptsnip naming remain.

The executable is **NotSigned**. Defender again reported antivirus/realtime false
and no signature timestamp, so no antivirus-clean verdict is available. SmartScreen
reputation was not tested. No security settings were changed or bypassed.

## Release acceptance

The user completed real-world ONEFILE testing and accepts PixelPort v0.1.0.
ONEFILE is the chosen release format. ONEDIR timing and provisional physical
checklists above are historical; they do not impose another release gate.
The approved PNG logo appears in README. The September 29, 2026 icon update embeds
the PixelPort logo in the EXE; see the release record for current checksums.

The final ZIP contains PixelPort.exe, LICENSE, consolidated THIRD_PARTY_NOTICES.md,
and SHA256SUMS.txt. Runtime dependencies and original notices are also embedded in
the EXE. No new features, installer, CI, tray UI or startup integration were added.
See [release record](release-v0.1.0.md).
