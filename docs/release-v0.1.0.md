# PixelPort v0.1.0 release record

The user reports successful real-world physical testing of the ONEFILE executable
and explicitly accepts PixelPort v0.1.0. Release acceptance is complete.
The approved logo is assets/pixelport.png. The default executable icon is retained.

## Final artifacts

The accepted executable was reused without rebuilding: every bundled project module
and the launcher match current application source. README, validation documentation,
release staging and a test-only freshness assertion do not change the executable.

| File | Bytes | SHA-256 |
|---|---:|---|
| PixelPort.exe | 19842768 | `5d92b142a0f8723102254bd6b866398d93d75a97e717ec45db3e01cda70a7311` |
| PixelPort-v0.1.0-windows-x64.zip | 19634216 | `653d6d102479b9f45285af7baf43bcad739c23312caa1b42b3833a17dcbade14` |

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
