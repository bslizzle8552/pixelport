# GPTSnip V0

A small Windows 11 utility: global hotkey → drag a rectangle → clipboard image →
focus your existing ChatGPT web browser window → Ctrl+V → stop. **GPTSnip never sends the message.**

Chrome automatic targeting now verifies the active loaded document at exactly
`https://chatgpt.com`. Its title can be anything, including
`Easier Screenshot Sharing - Google Chrome`. Codex and ChatGPT desktop remain
excluded automatically. Manual G binding remains an explicit override.

The native reader passed the real same-window tab/draft validation gate. The
complete suite passes **91 tests**. The user confirmed all three real capture cases:
ChatGPT browser paste, GitHub clipboard-only fallback, and ChatGPT recovery after
switching back. See [HANDOFF.md](HANDOFF.md) and [MSAA_VALIDATION.md](MSAA_VALIDATION.md).

## Install and run

Use Windows 11 and Python 3.11 or newer with Tcl/Tk installed (included in the
normal python.org Windows installer). Tested runtime: Python 3.14.3, Pillow 12.3.0,
pywin32 312. Run in PowerShell as your normal user:

```powershell
cd path\to\gptsnip
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m gptsnip
```

No virtual-environment activation or execution-policy change is needed. Keep the
console running; it shows status and errors. Failed captures/pastes also play the
Windows notification sound if system sounds are enabled.

| Shortcut | Action |
| --- | --- |
| **Ctrl+Alt+Shift+S** | Select a region and attempt to paste |
| **Escape** | Cancel while selecting; no clipboard change or paste |
| **Ctrl+Alt+Shift+G** | Optionally bind the foreground ChatGPT window as an override |
| **Ctrl+Alt+Shift+Q** | Quit and release hotkeys |

Ctrl+C in the launch console also quits. A second instance exits immediately.
If a shortcut is already registered elsewhere, startup fails with a console
explanation and releases any shortcuts registered so far.

## Prepare the destination

1. With GPTSnip running, open the **existing ChatGPT conversation** in Chrome.
2. Click inside its message composer, so normal Ctrl+V would paste there. Use the
   conversation normally, or leave it foreground for at least half a second.
3. Leave Chrome foreground for about two seconds. Expect
   `Chrome target verified as chatgpt.com` in the console. **No G binding or
   ChatGPT title marker is needed.** G remains an explicit override.
4. Switch to the application you want to capture. Press **Ctrl+Alt+Shift+S**,
   release the keys, drag a rectangle, and release the mouse.
5. Check the attachment, add your context, and send it yourself.

Chrome identity comes from the loaded document, so conversation-only titles work.
Switching the same window to GitHub blocks its remembered automatic target once
observed. Switching back to ChatGPT permits verification again. Switching to
another application preserves Chrome memory; every capture still rechecks it.

Keep ChatGPT as the **selected tab in its browser window** when paste happens.
GPTSnip does not switch tabs. It also
does not locate or click the composer: the browser must retain the composer focus
you established in step 2. If a menu, dialog, address bar, or another input takes
focus inside that window, manually return to the composer and paste.

## Chrome document verification

The reader requires exactly one visible `Chrome_RenderWidgetHostHWND` under the
requested top-level HWND, a document-role MSAA root, and a parsed HTTPS document
URL with hostname exactly `chatgpt.com`. Omnibox drafts and titles are not the URL
source. Credentials, subdomains, lookalikes, malformed URLs, and ports other than
default HTTPS or explicit 443 do not qualify.

The 250 ms UI timer reads cheap foreground metadata. Idle Chrome accessibility
requests start no more often than every 750 ms. One supervisor thread manages at
most one child process and one outstanding request. Requests have a one-second
deadline and require two matching reads 120 ms apart. Replies older than 300 ms,
or belonging to another request/window/process/renderer, are rejected. Timed-out
workers are terminated outside Tk; retries have a two-second cooldown. No
accessibility API runs on Tk's UI thread.

Chrome is reverified before fixing the capture target, after copying and before
activation, and immediately before Ctrl+V. Each required verification has a
1.5-second flow deadline, including pending idle work. Idle evidence cannot satisfy
these checks. Unknown, ambiguous, minimized, inaccessible, busy, changed, and stale
states block automatic paste. Copied images remain available for manual paste.

Only hostname, outcome, and window/process/renderer identity cross the worker
boundary. Full URLs are discarded in the reader; paths, queries, conversation IDs,
and page/composer text are not logged. Titles remain only in memory for the existing
snapshot checks. There are no new dependencies, extensions, browser automation,
DevTools, or page-identifying network requests.

## Target selection and safe fallback

- An explicit manual binding takes priority. It remembers window handle, process ID,
  executable name, and title **only in memory**. If any changes, automatic paste
  stops; it never silently falls back to another conversation. Rebind with G.
  Restart GPTSnip to clear a binding. The existing G admission rule is unchanged:
  supported browsers and `ChatGPT.exe` may be deliberately bound, without a title
  marker. This explicit desktop override is separate from automatic eligibility;
  arbitrary other executables are still not bindable.
- Otherwise, use the most recently observed ChatGPT browser window. Chrome requires
  the native verification above. Edge, Firefox, Brave, Vivaldi, and Opera retain
  their existing standalone, case-insensitive `ChatGPT` title heuristic. Their URL
  readers were not validated or enabled. Codex, `ChatGPT.exe`, VS Code, terminals, and all
  other non-browser processes are ineligible regardless of title or product name.
  Codex on the inspected machine actually runs as `ChatGPT.exe`; its window class
  also resembles Chrome's. Neither executable branding nor window class grants
  automatic eligibility.
- Memory retains one window handle, process ID, executable name, and exact title
  for this run only. Chrome also retains process creation time and renderer identity.
  Switching to another application does not erase memory; actively observing another
  eligible ChatGPT window replaces it. Chrome tab changes in the same foreground
  HWND are checked periodically. No background-tab inspection occurs.
- If the remembered window disappears, its identity/title changes, or its active
  Chrome document becomes another site or unknown, fail closed
  and retain the old snapshot, so even a later capture cannot silently redirect
  to another conversation. Actively revisit a recognizable ChatGPT window to learn
  it again, or bind the intended window with G. A stale manual binding must be
  explicitly rebound or cleared by restarting; automatic learning cannot clear it.
- Discovery is allowed only when there is no manual binding and no remembered
  target. Unobserved Chrome cannot be discovered by title: visit the intended tab
  while GPTSnip runs. For the other supported browsers it accepts **exactly one**
  title-recognized candidate among the inspected
  visible, non-cloaked top-level windows.
  Zero or multiple candidates produce clipboard-only fallback. This avoids choosing
  an arbitrary conversation from enumeration order.
- The chosen target is fixed when capture begins. Its identity/title is checked
  again before activation and paste. Held keys/buttons, changed clipboard contents,
  or a different foreground window block paste. Foreground activation has a bounded
  wait; GPTSnip does not bypass Windows focus or privilege restrictions.
- If no unchanged target is found, the screenshot remains on the clipboard. A
  sound and console message explain that you should return to ChatGPT and Ctrl+V.
  Clipboard contention itself can prevent copying; that error explicitly says so.

Automatic-memory notices include the process name, PID, and HWND. Each capture
reports whether selection used manual binding, automatic memory, or discovery,
and the selected process/PID/HWND or a clipboard-only result. Conversation titles
are not printed by these notices. These are console diagnostics, not a stored log.

Other browsers' window titles are a heuristic, **not proof of a site's identity**.
A non-ChatGPT page titled “ChatGPT” can match those legacy rules. Binding is your declaration that the
selected window/tab is ChatGPT; do not bind an unrelated page. The native Chrome
method identifies the active site, not a permanently fixed conversation. Focus checking and SendInput are
also not atomic: avoid clicking/switching windows during the brief return/paste.
The ChatGPT tab must have been active/observable while GPTSnip runs for it to be
learned. Brief visits shorter than the sampling/verification interval can be missed. Observation
pauses during capture/paste. Exact-title validation can reject a legitimate title
change after switching away; revisit ChatGPT or use the clipboard manually.
GPTSnip cannot inspect or switch arbitrary background Chrome tabs, inspect the DOM,
navigate, reload, or open a conversation. Popup/split-view states with additional
visible renderers deliberately block automatic paste. Chrome 152.0.7977.84 is the
tested browser. Real minimized-window acceptance is unverified; minimized Chrome
is rejected by implementation and mocked tests. Same-renderer navigation can occur
after the final check, and composer focus must still be established by the user.

## Capture and clipboard behavior

- Translucent desktop overlay, crosshair, visible rectangle, and Escape cancel.
  Losing overlay focus cancels. Repeated triggers during capture/paste are ignored.
- Per-monitor DPI awareness is enabled before UI creation. Win32 physical cursor
  coordinates and virtual-screen bounds support monitors left/above the primary.
  The overlay is placed with SetWindowPos, avoiding Tk's negative-offset geometry.
- The overlay is destroyed, the event loop waits 120 ms, and DwmFlush runs before
  Pillow obtains the **final live pixels**. Moving content may change during that
  interval. Capture is cancelled if the overall desktop bounds change.
- The selected rectangle uses inclusive left/top and exclusive right/bottom edges.
  Empty selections cancel. Areas between monitors may contain black pixels.
- Image data is published as lossless, 24-bit RGB **CF_DIB**, not a file path or
  encoded text. No screenshot files are created. Capturing replaces the clipboard.
- HDR color fidelity, protected video, secure desktops/UAC, full-screen games,
  display changes during selection, and mixed-DPI interactive accuracy are not
  proven. Use standard SDR desktop applications for initial acceptance testing.

## Privacy and message safety

GPTSnip has no API integration, browser automation, telemetry, networking, screenshot
history, or persistent image storage. Only Ctrl-down, V-down, V-up, Ctrl-up are
injected. No Enter, Send click, or submission action is implemented.

**Unsent does not mean unuploaded.** ChatGPT controls what happens when an image is
pasted and may upload attachments before you send the message. GPTSnip cannot
guarantee that network transmission waits for Send. The utility itself does not
transmit the image. Normal dependency installation downloads Python packages.

The current screenshot remains in the Windows clipboard until replaced. GPTSnip
sets Windows clipboard flags requesting exclusion from clipboard history/cloud
sync; third-party clipboard managers may still retain clipboard contents.

## Validation

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q gptsnip tests
.\.venv\Scripts\python.exe -m pip check
```

Optional native lifecycle smoke test (quit GPTSnip first):

```powershell
.\.venv\Scripts\python.exe tests\native_smoke.py
```

This briefly registers the actual hotkeys, tests native message dispatch and the
duplicate-instance guard, then verifies hotkey cleanup. It does not capture the
screen, alter the clipboard, focus another application, or inject keyboard input.

Implementation references: Microsoft's [foreground-window restrictions](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setforegroundwindow),
[SendInput behavior](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput),
[clipboard formats](https://learn.microsoft.com/en-us/windows/win32/dataxchg/clipboard-formats),
and Pillow's [ImageGrab coordinates](https://pillow.readthedocs.io/en/stable/reference/ImageGrab.html).
