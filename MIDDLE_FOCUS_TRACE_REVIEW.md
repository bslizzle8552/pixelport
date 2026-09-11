# Physical trace review: missing A–D records; direct recording repaired

**Superseded by the complete console attachment:** the missing A–D records were
recovered in the user's next attachment. See
[MIDDLE_FOCUS_FIX_HANDOFF.md](MIDDLE_FOCUS_FIX_HANDOFF.md) for the evidence, fix,
and two-cycle acceptance commands. No repeat of the old diagnostic is needed.

The user confirmed that A cancelled before clicking PowerShell and D pasted an
image unsent after that click. That physical report is accepted. Unfortunately,
the supplied local file does not contain the A–D diagnostic records needed to
establish the cancellation path. No selector behavior has been changed or fix
claimed. One repeat sequence with direct file recording is necessary.

## Exact evidence in the supplied file

Read `C:\dev\gptsnip\middle-focus-diagnostic.txt` directly, both before and after
the user ran `Stop-Transcript`. Before closure it contained 4,472 bytes. Closing
the transcript added the stop command and footer, bringing it to 4,617 bytes;
it did not restore the missing records. The finalized SHA-256 is:

`7801338fd2e8903ed540bd396500614f485aba779605a61d65479515ac20d5b4`

The transcript has its PowerShell 5.1 header and launch command, then immediately
starts mid-record at line 21. Lines 21–31 contain a partial foreground-transition
record around 68,299 ms. Lines 32–39 contain one complete logical record after
joining console-wrapped lines: a Chrome verification reply at 68,392 ms.

That late record says:

| Field | Observed value |
|---|---|
| Foreground HWND | `132714` |
| Foreground process / PID / thread | `WindowsTerminal.exe` / `19152` / `19608` |
| Foreground class | `CASCADIA_HOSTING_WINDOW_CLASS` |
| Foreground GUI active / focus / capture | `132714` / `328866` / `328866` |
| Console HWND | `328772` |
| Console process / PID / thread | `powershell.exe` / `4916` / `14960` |
| Console class | `PseudoConsoleWindow` |
| GPTSnip UI thread | `12360` |
| GPTSnip GUI active / focus / capture | all null |
| Tk root | `525978`, withdrawn; focus/grab both None |
| Selector | null |
| Generation / middle ID | `6` / null |
| Gesture serial / acknowledged | `4` / `4` |
| Gesture released / cancelled | true / false |
| Hook installed / held / accepting | true / false / true |
| Physical middle button down | false |
| Remembered and selected Chrome HWND / PID | `2228446` / `15708` |
| Memory blocked / Chrome evidence present | false / true |
| Reply token / status / eligible | `77` / verified / true |
| Capture and current screen bounds | both `[-1920,0,4480,1600]` |

These are **late, inactive-selection observations**, not A's cancellation state.
The visible terminal HWND and pseudo-console HWND are distinct. That distinction
is established, but it does not establish why a previous terminal click changed
selector behavior.

The file contains no startup state, admission event, selector activation event,
foreground-mismatch event, cancellation notice, selector HWND, or Ctrl+V event.
It cannot tell us whether A acquired foreground, when it lost foreground, which
HWND the check compared, which cancellation trigger fired, what changed between
A and D, or why D succeeded. It does not prove a Windows permission issue, Tk
activation issue, or message-queue initialization issue. Inferring those from
this fragment would violate the requested evidence requirement.

## Narrow change made in this pass

The prior `Start-Transcript` instructions failed to retain the native output
needed for this diagnosis. The exact shell/terminal mechanism of that loss has
not been established. The diagnostic recorder now supports an explicit
`GPTSNIP_MIDDLE_DIAGNOSTIC_FILE` path and writes complete UTF-8 JSONL records
directly from GPTSnip. Each record is appended and its file handle closed before
any console notice, so it is flushed independently of PowerShell transcription.

Existing evidence is never overwritten. Records carry the process PID and retain
the existing timestamps, reasons, and state fields. The existing 600-record limit
remains, followed by one limit marker. When writing to a file, the console shows
one recording-path notice and the ordinary application notices, rather than the
large JSON dump. An unavailable output path gets a warning and console fallback.
The recorder remains opt-in; disabled diagnostics create no file.

Files changed this pass:

- `gptsnip/middle_diagnostics.py`: direct, flushed JSONL output.
- `tests/test_middle_diagnostics.py`: four recording regression tests.
- `MIDDLE_FOCUS_DIAGNOSTIC_HANDOFF.md`: pointer to corrected instructions.
- This technical review.

Selector checks, activation calls, hook ownership, capture/paste, Chrome MSAA,
target memory, and all target safety decisions are unchanged in this pass.
The original transcript is preserved. No commit or push was performed.

## Validation

` .\.venv\Scripts\python.exe -m unittest discover -s tests -q `:
**162 tests passed in 2.589 seconds** (158 baseline plus four new tests).

The additions verify complete records survive console-output failure, append
preserves earlier evidence and stays bounded, an unwritable path warns and falls
back, and disabled diagnostics never create a configured file. These are tests
for the confirmed diagnostic-recording gap, not a fabricated regression for the
still-unconfirmed selector cause.

Native lifecycle smoke passed with direct recording enabled: startup, three
registrations, hook install/unhook/thread exit, WM_HOTKEY dispatch, duplicate
guard, and cleanup. Both generated JSONL lines were parsed successfully and the
first was `startup ready`. The smoke log is:

`C:\Users\swallace\AppData\Local\Temp\gptsnip-middle-smoke-b24de7fffb2a4b09863a72f152d1fecc.jsonl`

No physical selector acceptance or bug resolution is claimed.

## Repeat A–D once with reliable recording

Quit GPTSnip completely. In the same PowerShell/terminal used for the original
reproduction, run:

```powershell
Set-Location C:\dev\gptsnip
$env:GPTSNIP_MIDDLE_DIAGNOSTICS = '1'
$env:GPTSNIP_MIDDLE_DIAGNOSTIC_FILE = 'C:\dev\gptsnip\middle-focus-direct.jsonl'
.\.venv\Scripts\python.exe -u -m gptsnip
```

Expect one `recording JSONL to ...middle-focus-direct.jsonl` notice. Do not use
`Start-Transcript`, output redirection, or `Tee-Object` for this run.

1. Switch to ChatGPT in Chrome and allow automatic verification. Never press G.
   Do not click PowerShell after launch yet.
2. From the usual source application, middle-hold → drag → release once: A.
3. Release all buttons, click PowerShell once, then return to that same source
   application: B/C.
4. Middle-hold → drag → release again: D. Check whether it pastes unsent.
5. Quit with **Ctrl+Alt+Shift+Q** and tell Cal the sequence is done. The JSONL file
   is already local and will be read directly; no paste or upload is needed.

The two fresh-launch acceptance cycles remain pending until the missing evidence
supports a selector fix. Repeating acceptance now would test unchanged selector
behavior. After the confirmed fix, run both requested cycles without a PowerShell
click or G, then tiny-click/Escape cancellation, GitHub clipboard-only behavior,
ChatGPT recovery, and keyboard fallback.
