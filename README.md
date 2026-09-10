# GPTSnip

**Snip it. Paste it into ChatGPT. Keep talking.**

GPTSnip is a lightweight Windows utility for quickly sharing part of your screen with ChatGPT without breaking the flow of a conversation.

The goal is simple:

1. Trigger GPTSnip with a mouse button or hotkey.
2. Drag a box around anything on your screen.
3. Release.
4. GPTSnip captures the selected region.
5. Your existing ChatGPT window is brought to the foreground.
6. The screenshot is automatically pasted into the current message.

**GPTSnip does not send the message.**

The screenshot simply appears in the ChatGPT composer, ready for you to add text or voice context before sending it yourself.

## Why?

The normal workflow works:

> Open Snipping Tool → capture → copy → find ChatGPT → paste → continue conversation.

But when you're sharing screenshots with ChatGPT constantly, those extra steps add up.

GPTSnip reduces that workflow to:

> **Trigger → drag → release → keep talking.**

## Project Goals

GPTSnip is intentionally small and focused.

- Windows-first
- Designed specifically for ChatGPT
- Fast region selection
- Automatic clipboard capture
- Automatically focus the existing ChatGPT window
- Automatically paste the screenshot
- Never automatically send a message
- Minimal or no visible UI
- Configurable mouse button or keyboard shortcut
- Run quietly in the background

## Status

🚧 **Early development**

The first milestone is a working Windows prototype that can:

`Select region → capture → copy → focus ChatGPT → paste`

Nothing more until that works reliably.

## Non-Goals

GPTSnip is not intended to be:

- A replacement for Windows Snipping Tool
- A full screenshot manager
- An image editor
- A general-purpose screen capture application
- A ChatGPT API client

It's a shortcut between **something on your screen** and **the ChatGPT conversation you're already having**.

## Platform

Initial development targets **Windows 11**.

## License

MIT
