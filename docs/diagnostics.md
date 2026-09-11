# PixelPort diagnostics

Diagnostics are disabled by default. They help distinguish failed Chrome identity
from failed selector foreground acquisition without changing capture decisions.
The `GPTSNIP_*` names remain internal compatibility settings for v0.1.0.

From the repository root in PowerShell, enable only the trace needed:

```powershell
# Chrome request/response stages; console only, first 12 request tokens.
$env:GPTSNIP_IDENTITY_DIAGNOSTICS = '1'
# Middle gesture/focus metadata; at most 600 records plus a limit marker per launch.
$env:GPTSNIP_MIDDLE_DIAGNOSTICS = '1'
$env:GPTSNIP_MIDDLE_DIAGNOSTIC_FILE = '.\middle-focus-diagnostic.jsonl'
.\.venv\Scripts\python.exe -u -m gptsnip
```

Middle diagnostics append complete UTF-8 JSONL records directly and close the file
after every record. Existing evidence is not overwritten; limits are per launch,
so a reused file can grow over multiple launches. Without a file setting, records
use the console. An unwritable path warns once and falls back to console output.
Use direct output rather than PowerShell transcripts, which previously lost native
console records. Quit with Ctrl+Alt+Shift+Q before reading the completed file.

```powershell
Remove-Item Env:GPTSNIP_IDENTITY_DIAGNOSTICS -ErrorAction SilentlyContinue
Remove-Item Env:GPTSNIP_MIDDLE_DIAGNOSTICS -ErrorAction SilentlyContinue
Remove-Item Env:GPTSNIP_MIDDLE_DIAGNOSTIC_FILE -ErrorAction SilentlyContinue
```

Chrome diagnostics show request tokens, fixed stages/reasons, hostname, and numeric
native metadata. Middle records include process names/IDs, HWND/thread/class,
foreground/local focus/grab, physical-button snapshots, gesture coordinates, screen
bounds, selector lifecycle, and verification state. Foreground changes are sampled
on the UI tick, with one previous snapshot refreshed about every 250 ms.
Sampling is not an atomic native event log; it can miss intervening transitions.

Neither mode prints titles, full URLs, conversation IDs, page/composer text, or
provider exception messages. Process names, coordinates, and window metadata can
still reveal context: review before sharing. Normal console notices already include
selected target process/PID/HWND and capture/fallback outcomes. Do not commit logs,
transcripts, or diagnostic files; repository ignore rules exclude these artifacts.
Diagnostics add timing/I/O overhead and are intended for bounded troubleshooting,
not continuous telemetry. Middle snapshot failures cannot raise into capture flow.
