"""Small, platform-independent selection and targeting rules."""

from dataclasses import dataclass
from io import BytesIO
import re

BROWSERS = frozenset({"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe",
                      "vivaldi.exe", "opera.exe"})


@dataclass(frozen=True)
class Window:
    hwnd: int
    pid: int
    process: str
    title: str

    @property
    def supported(self):
        # Preserve the existing manual-binding/inspection allowlist. Automatic
        # eligibility is the stricter, browser-only rule in recognized below.
        return self.process.lower() in BROWSERS | {"chatgpt.exe"}

    @property
    def recognized(self):
        # Chrome requires fresh native document evidence at the application layer.
        # Preserve the other browsers' existing heuristic; desktop never qualifies.
        return self.process.lower() in BROWSERS - {'chrome.exe'} and (
            re.search(r"\bChatGPT\b", self.title, re.IGNORECASE) is not None
        )


def choose_target(windows, remembered=None, bound=None):
    # Retain invalid snapshots: forgetting them would allow discovery to silently
    # redirect a later capture to a different conversation.
    if bound is not None:
        return next((w for w in windows if w == bound), None)
    if remembered is not None:
        return next((w for w in windows if w == remembered and w.recognized), None)
    candidates = [w for w in windows if w.recognized]
    # Without an observed target, multiple candidates are ambiguous.
    return candidates[0] if len(candidates) == 1 else None


def selection_box(start, end, bounds):
    """Physical screen coordinates, including negative origins; right/bottom exclusive."""
    left, top, right, bottom = bounds
    x1, x2 = sorted((max(left, min(right, start[0])),
                     max(left, min(right, end[0]))))
    y1, y2 = sorted((max(top, min(bottom, start[1])),
                     max(top, min(bottom, end[1]))))
    return (x1, y1, x2, y2) if x2 > x1 and y2 > y1 else None


def image_dib(image):
    """CF_DIB is BMP data without its 14-byte file header (24-bit, lossless RGB)."""
    stream = BytesIO()
    image.convert("RGB").save(stream, "BMP")
    return stream.getvalue()[14:]
