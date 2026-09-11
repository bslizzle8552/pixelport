# Isolated frozen BrowserReader timing

September 11, 2026. Historical ONEDIR timing pass; the artifact remains unchanged.
The later [ONEFILE pass](onefile.md) records physical ONEDIR results and the
subsequently approved 1.5-second default for new frozen builds.

**Historical ONEDIR timing evidence. The later ONEFILE release is physically accepted;
see [release record](release-v0.1.0.md).** Five
isolated cold process launches and 55 warm reads completed within the existing
1,000 ms deadline. No production, launcher, spec, or deadline change was needed.
No rebuild was performed. No physical capture or paste was performed.

## Conditions

Used the actual `dist/PixelPort/PixelPort.exe`. Each launch followed a process
inventory showing no PixelPort process, a one-second quiet interval, and a second
inventory. Each process ended with Q posted only to its own hotkey window. Hook
thread exit and absence of all PixelPort processes were checked afterward. These
are cold application/worker launches, not cold OS boots or cleared filesystem
caches. Chrome stayed running with its current selected document.

No duplicate instance overlapped any timing cycle. No browser navigation, tab
change, focus call, keyboard injection, screenshot, clipboard write or paste was
performed. The foreground Chrome document was a non-ChatGPT host for every read;
its name is intentionally omitted. Native verification of a non-target document
counts as reader completion, not as eligibility for automatic paste.

Opt-in diagnostics are capped at 12 requests per launch. The external harness
records stdout arrival with perf_counter; figures are approximate log-observation
timings, not profiler measurements. Every admitted request and any failed sample
is retained in ignored local evidence. No failed or unknown result occurred in
these 60 measured requests.

## Five isolated cold launches

All values are milliseconds. Admission is relative to process launch. Bootstrap
is worker-start log to worker-receipt log. Native phase is worker receipt to native
result, including first-use native/COM setup and the unchanged 120 ms stability
wait. Total-to-app includes polling/delivery.

| Cycle | Launch to banner | Admission | Bootstrap | Native phase | Admission to native result | Admission to App | Decision / eligibility |
|---|---:|---:|---:|---:|---:|---:|---|
| 1 | 706.6 | 746.2 | 211.3 | 242.7 | 475.7 | 500.8 | Pass / non-target |
| 2 | 577.0 | 616.3 | 219.2 | 227.5 | 472.2 | 484.1 | Pass / non-target |
| 3 | 512.5 | 558.5 | 207.5 | 216.0 | 445.5 | 470.3 | Pass / non-target |
| 4 | 528.7 | 581.7 | 279.9 | 224.7 | 541.8 | 554.5 | Pass / non-target |
| 5 | 561.3 | 597.8 | 260.0 | 242.8 | 529.3 | 547.0 | Pass / non-target |

Cold admission-to-App: **minimum 470.284, median 500.750, maximum 554.499 ms**.
Worst observed margin under the 1,000 ms limit: about **445.5 ms**.
Cold admission-to-native-result: min 445.478, median 475.666, max 541.819 ms.
Bootstrap: min 207.545, median 219.194, max 279.907 ms. Admission to worker receipt,
including process creation/supervisor handoff: min 229.475, median 244.717,
max 317.112 ms. Cold native phase: min 216.003, median 227.468, max 242.766 ms.

## Warm distribution

55 subsequent requests across the same five runs, 11 per already-running worker:

| Measurement (ms) | Min | Median | p95 | Max |
|---|---:|---:|---:|---:|
| Admission to App | 139.325 | 157.540 | 159.332 | 172.247 |
| Admission to native result | 127.677 | 129.332 | 131.496 | 134.134 |
| Native phase | 127.434 | 128.991 | 131.172 | 133.792 |

p95 uses nearest rank. All 55 warm results were verified non-target; zero eligible
ChatGPT, zero unknown, zero deadline failures. The warm native phase is dominated
by the required 120 ms stability interval, not frozen process creation.

## Stage visibility and interpretation

The unchanged candidate logs request admission, supervisor admission, worker
start, worker receipt, the first native snapshot, native completion, application
poll/delivery, and App consumption. Native-read entry occurs immediately after
worker receipt and its deadline check; no distinct read-entry timestamp is emitted.
Supervisor receipt is not independently logged: for successful requests it is
bounded between native-result emission and application poll/delivery. The local
per-request ledger retains those endpoints. No exact unobserved timestamp is
invented, and no rebuild solely to add those two timestamp points was justified.

The prior ~1,050 ms sample overlapped duplicate launch. The same artifact now
passes isolated cold runs with substantial margin. This is consistent with prior
contention, but does **not establish duplication as the sole cause**: host state,
Windows load, and OS caching were not controlled as a causal experiment. No claim
is made that every future machine or OS-cold launch will meet the deadline.

The existing 1-second deadline is viable unchanged in these samples. Increasing
it or changing startup architecture is unsupported by the current evidence.

## Worker warmup evaluation (no implementation)

BrowserReader currently starts its supervisor lazily on request; the supervisor
creates its only spawned child on that request. Simply starting the thread earlier
would not create the worker because creation is inside the request-processing
branch. A future eager-worker option would require supervisor-owned creation
before requests, retaining its existing retirement/kill/join rules and refusing to
replace a surviving child. Initialization would have to happen after successful
single-instance mutex acquisition. Frozen freeze_support diversion must remain
before all application startup.

The child imports native_document and then waits in connection.recv. That import
alone performs no Chrome document read. A safely started idle child could absorb
process/bootstrap/import cost without authorizing any target; actual requests
would still need their own unchanged deadlines, two matching native reads, exact
hostname validation, freshness checks and capture checks. First-use COM/native
cost may remain on the first request. Shutdown before any request, startup failure,
close/start races, resource bounds and no-recursion would require explicit tests.

This is feasible in principle, but adds lifecycle work and an idle process to
runs that may never use Chrome. The isolated results do not justify implementing
it. No capture/target/paste or BrowserReader lifecycle code was changed.

## Automated checks at the time of this pass

All five actual frozen runs: one app banner, one intended worker, at most two
PixelPort processes, hook installed, hook thread stopped on Q, exit code 0, no
orphans, no traceback, no capture/paste event, clipboard sequence unchanged.
A **separate later run**, with identity timing disabled, passed duplicate refusal
(exit 1, no second startup banner), original survival, Q exit 0, no orphans and
unchanged clipboard. No timing was collected during duplicate launch.

`packaging/frozen_smoke.py` now observes the user-selected Chrome window passively
and runs duplicate refusal only after both measured verification cycles, in a
separate launch with identity timing disabled. `packaging/frozen_timing.py` is the
new external measurement harness; neither tool is bundled in the EXE.

Final source checks: **181 tests passed in 4.242 s**, compileall for gptsnip/tests/
packaging passed, pip check passed, git diff --check passed, native lifecycle smoke
passed. All production modules and runtime requirements remain unchanged.

## Frozen ChatGPT acceptance follow-up

After the user manually selected ChatGPT in Chrome, the unchanged candidate passed
both passive frozen verification cycles. All eight native results were eligible
ChatGPT and verified, with automatic target remembrance in each launch. There were
no deadline, import, traceback, worker-recursion, or stale-result failures.

| Cycle | Launch to banner (ms) | Cold admission to poll (ms) | Warm admission to poll (ms) |
|---|---:|---:|---|
| 1 | 672.54 | 575.34 | 155.97, 156.64, 154.17 |
| 2 | 645.43 | 515.51 | 156.20, 154.25, 156.12 |

For comparison with the earlier admission-to-App ledger, cold App-consumption
latencies were 577.146 and 516.776 ms. Bootstrap was 285.912 and 250.365 ms; native
phase was 255.655 and 233.744 ms. The poll and consumption metrics differ slightly
because the application emits its consumption diagnostic after poll returns.

Each launch had exactly one intended worker, no child windows, successful hook
installation, Q exit 0, hook-thread exit, no orphan processes, released hotkeys,
and unchanged clipboard sequence. A separate final run, with identity timing
disabled, passed duplicate refusal and original-process cleanup. No browser focus,
navigation, injected keyboard input, capture, or paste was performed.

**The ONEDIR candidate is now ready for user physical acceptance.** Physical
capture/revalidation/paste behavior remains untested in the frozen build until the
user completes the checklist. Onefile remains blocked. No rebuild or architecture
change was needed; the 1,000 ms deadline is unchanged.

## Artifact and repository

No rebuild. EXE SHA-256:
`3ad752ea4984abb8629522770bc0b3101cb9f2b3ddf0dbe235b34d1073638544`.
EXE: 3,594,974 bytes. Full onedir: 42,554,453 bytes / 988 files.
Source HEAD remains `22a4e51a3a8ea62389d8dc33ba321b7f729a9069`.
Packaging changes remain unstaged/uncommitted; raw traces, logs, caches and build
outputs remain ignored. No commit, push, tag, release, onefile, installer or branding
change was made. The candidate remains unsigned; no new Defender/SmartScreen
assessment was made during this timing pass.
