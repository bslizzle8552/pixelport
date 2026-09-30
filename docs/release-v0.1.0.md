# PixelPort v0.1.0 release record

The user reports successful real-world physical testing of the ONEFILE executable
and explicitly accepts PixelPort v0.1.0. Release acceptance is complete.
The approved logo is assets/pixelport.png. The September 29, 2026 release update
embeds its symbol as the Windows icon using assets/pixelport.ico.

## Final artifacts

The accepted executable was reused without rebuilding its application code. Only
Windows icon resources were updated. Every entry in the frozen archive was compared
with the original executable and verified byte-for-byte unchanged. The frozen payload
SHA-256 is `98b1b1b504fa42dbe7f3745e32ee6fa83fafd93ef408ef827eb7de2b518aa48f`.
Windows icon extraction was visually checked, and startup plus graceful quit passed.

| File | Bytes | SHA-256 |
|---|---:|---|
| PixelPort.exe | 20111568 | `5cdfe9fc8d80b0a8896f1ed12c00513edd70181a4967f5c638c76463b1668428` |
| PixelPort-v0.1.0-windows-x64.zip | 19711481 | `27eb70fd8f8a64ae76d9b657a3ba11c805c17a64d800cad131348dee173a7c40` |

Ignored local staging: `release-output/PixelPort-v0.1.0-windows-x64/`.
ZIP: `release-output/PixelPort-v0.1.0-windows-x64.zip`.

ZIP contents, at its root:

- PixelPort.exe
- LICENSE
- THIRD_PARTY_NOTICES.md
- SHA256SUMS.txt

The checksum file covers the other three files; its own checksum is not recursive.
The ZIP was reopened and every member verified against staging. The single notice
file consolidates all 16 original notice/license texts from the accepted EXE, so no
separate notice directory is needed. No screenshots, logs, traces, caches, build
junk, private machine paths or investigation artifacts are in release staging.

## Validation and safety

Final unit suite: **185 tests passed**, plus compileall, pip check, git diff --check
and native lifecycle smoke. A freshness unit assertion now uses an explicit sample
age instead of depending on source-process startup timing; real worker transport,
hung-worker cleanup and slow-fresh-result tests remain. No production behavior
changed during final release staging.

Frozen BrowserReader timeout: 1.5 seconds. Source timeout: 1.0 second. Automatic
paste requires fresh positive chatgpt.com verification and otherwise fails closed
to clipboard. Ctrl+V only: no Enter and no Send. Middle capture, keyboard fallback,
Escape cancellation and duplicate-instance protection remain intact.

The accepted build uses CPython 3.14.3 x64, PyInstaller 6.22.2, hooks-contrib 2026.7,
Pillow 12.3.0 and pywin32 312. It is a console ONEFILE executable, unsigned, with
no installer, tray UI, startup integration, telemetry or added features.
See [ONEFILE evidence](onefile.md) for build and automated timing details.

## Release notes to paste

```text
PixelPort v0.1.0 — Windows 11 screenshot-to-ChatGPT utility.

Hold the middle mouse button, drag a region, and release to paste into your verified ChatGPT tab in Chrome. Attachments remain unsent; PixelPort never presses Enter or clicks Send.

Includes automatic ChatGPT targeting, clipboard-only fallback, Escape cancellation, keyboard capture fallback, and duplicate-instance protection.

Download the Windows x64 ZIP, extract it, and double-click PixelPort.exe. No Python installation or API key required. The executable is unsigned and may take a few seconds to start.

Quit: Ctrl+Alt+Shift+Q. Physically tested and accepted for v0.1.0.
```
