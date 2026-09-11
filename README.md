# PixelPort

Hold your mouse wheel, drag around anything on your screen, and release.
PixelPort returns to your verified ChatGPT tab in Chrome and pastes the screenshot
into the composer without sending it.

**Windows 11 · Google Chrome · No OpenAI API key required**

## Demo

*Demo coming: capture from another application, return to Chrome, and leave the
screenshot visibly UNSENT.* Final PixelPort artwork will be added when available.

## Why PixelPort?

When you discuss something on screen with ChatGPT, repeated capturing, switching
windows, and pasting interrupt the conversation. PixelPort combines those steps:

**Hold wheel → drag region → release → screenshot in composer → add context → manually send.**

PixelPort **never automatically sends** the ChatGPT message.

## Download / installation

**v0.1.0 download coming with the first GitHub Release.** No executable or installer
is available yet. For now, use the [source setup](#development) below.

## How to use

1. Launch PixelPort. Keep its console open; you can minimize it.
2. Select the intended ChatGPT tab in Chrome and click its message composer.
   Leave Chrome foreground briefly until the console reports
   `Chrome target verified as chatgpt.com`. No manual binding is needed.
3. Switch to the application you want to capture. Hold the wheel button, drag a
   rectangle, and release. Select at least **6 × 6 physical pixels**.
4. Check the screenshot in ChatGPT, add your context, and send it yourself.

Keep the intended ChatGPT tab selected in its Chrome window and its composer
focused. PixelPort does not switch tabs, identify a specific conversation, or
locate/click the composer. Avoid switching windows during its return and paste.

## Controls

| Control | Action |
| --- | --- |
| **Hold middle mouse → drag → release** | Capture a region |
| **Escape** | Cancel selection; release the held wheel before trying again |
| **Ctrl+Alt+Shift+S** | Keyboard fallback: release keys, then left-drag a region |
| **Ctrl+Alt+Shift+G** | Advanced: manually bind the foreground target as an override |
| **Ctrl+Alt+Shift+Q** | Quit and restore normal middle-click behavior |

PixelPort owns middle-click while running, including clicks that would normally
open/close tabs, start autoscroll, or pan in another application. Wheel scrolling,
left/right clicks, side buttons, and normal pointer movement remain unaffected.
Ctrl+C in the launch console also quits. Only one instance can run per session.

## Automatic ChatGPT targeting and clipboard fallback

For automatic Chrome targeting, PixelPort verifies that the selected loaded
Chrome document is on **chatgpt.com**. It remembers that window while you work
elsewhere and checks it again during capture/paste.

If verification fails, a successfully captured screenshot **stays on the clipboard
and automatic paste does not occur**. Select the intended composer and paste it
manually. A cancelled selection produces no screenshot; a clipboard-copy error is
reported separately.

Manual G binding is an **advanced override that bypasses automatic Chrome site
verification**. Bind only your intended destination. Restart to clear it, or
rebind if its identity changes. Legacy targeting paths for other browsers remain
in the implementation, but they are **not validated support for v0.1.0**.

## Privacy

PixelPort operates locally, does not use the OpenAI API, and requires no API key.
It has no telemetry, screenshot-history database, or automatic screenshot-file
storage. Chrome document identity is inspected locally; full browsing history is
not collected. Full URLs, conversation IDs, and page/composer text are not written
to PixelPort diagnostics.

Captures replace the Windows clipboard. PixelPort requests exclusion from Windows
clipboard history/cloud sync, but other clipboard managers may retain images.
Successful automatic paste injects **Ctrl+V**; PixelPort does not press Enter or
click Send. **ChatGPT itself may upload or process a pasted attachment before you
press Send.** Pasted screenshots are not guaranteed to stay on your computer.

Optional diagnostics record local window/input metadata and can be written to a
file only when enabled. Review those files before sharing; see
[diagnostics](docs/diagnostics.md).

## Compatibility / limitations

Tested on **Windows 11 with Google Chrome and chatgpt.com, including a multi-monitor
setup**. This does not establish universal Windows, browser, mouse, or DPI support.
Other browsers, elevated applications, secure/UAC desktops, remote sessions,
exclusive full-screen applications, HDR fidelity, and every mixed-DPI arrangement
are not validated. A working physical middle button is required for the primary gesture.

Selection cancels on focus loss, changed screen bounds, or a 60-second hold.
Captures use live pixels after the overlay closes; moving content may change.
ChatGPT site verification does not pin a conversation or guarantee composer focus.

## Troubleshooting

- **No automatic paste:** select ChatGPT in Chrome, click the composer, wait for
  verification, and retry. Check the console; manually paste from the clipboard
  when fallback is reported. Clear an unintended G override by restarting.
- **Middle capture unavailable or stops responding:** use the keyboard fallback,
  then quit and relaunch. Mouse remappers and driver behavior can interfere.
- **Selection immediately cancels:** keep its overlay foreground, drag at least
  6 × 6 pixels, and avoid changing the display layout during capture.
- **Startup says a shortcut is unavailable:** close the conflicting application
  and retry. Do not launch multiple instances.

For a bug report, include PixelPort, Windows, and Chrome versions, reproduction
steps, and the console message. Omit private screen content and review diagnostic
metadata before sharing it.

## Development

The tested source runtime is standard 64-bit **CPython 3.14.3** with Tcl/Tk,
Pillow 12.3.0, and pywin32 312. Use the normal Windows Python installation with Tk.
From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m gptsnip
```

No venv activation or execution-policy change is needed. The internal Python
package remains `gptsnip` for v0.1.0 to preserve the validated imports, entry point,
and spawned worker behavior; it is an implementation detail that can migrate later.
The public product and planned executable name are **PixelPort** and **PixelPort.exe**.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
.\.venv\Scripts\python.exe -m compileall -q gptsnip tests
.\.venv\Scripts\python.exe -m pip check
git diff --check
# Quit PixelPort first; briefly registers actual hotkeys and the mouse hook.
.\.venv\Scripts\python.exe tests\native_smoke.py
```

See [technical architecture](docs/architecture.md), [validation and limitations](docs/validation.md),
and the [Chrome investigation](docs/investigations/chrome-msaa-validation.md).

## License / affiliation

[MIT License](LICENSE).

PixelPort is an independent open-source utility and is not affiliated with,
endorsed by, or sponsored by OpenAI.
