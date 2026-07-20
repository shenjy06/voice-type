"""Capture text around the cursor position using clipboard selection."""

import logging
import time
import ctypes

import pyperclip

from voicetype.window_detect import is_terminal_window

logger = logging.getLogger(__name__)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
KEYEVENTF_KEYUP = 0x0002

VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_HOME = 0x24
VK_END = 0x23
VK_LEFT = 0x25
VK_RIGHT = 0x27
VK_C = 0x43

# Max chars to capture on each side to avoid huge selections
MAX_CONTEXT_CHARS = 500


def _key_down(vk: int):
    user32.keybd_event(vk, 0, 0, 0)


def _key_up(vk: int):
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


def _clipboard_sequence_number() -> int | None:
    """Return the current clipboard sequence number, or ``None`` on failure.

    The sequence number increments each time the clipboard contents change.
    We use it to detect whether Ctrl+C actually changed the clipboard,
    instead of writing a destructive marker — the marker was a race
    condition: if the process crashed between writing the marker and
    restoring the original, the user's clipboard was permanently lost.

    ``None`` (API unavailable) means "cannot tell" — callers should fall
    back to reading the clipboard directly rather than treating the copy
    as failed.
    """
    try:
        return kernel32.GetClipboardSequenceNumber()
    except Exception:
        return None


def _send_copy() -> str:
    """Send Ctrl+C and return clipboard text, or empty string if copy failed.

    Uses the Windows clipboard sequence number instead of a destructive
    marker to detect whether Ctrl+C changed the clipboard. When the
    sequence number is unavailable (``None``), the clipboard is read
    unconditionally — a slightly weaker check, but better than wrongly
    reporting failure on systems where the API is missing.
    """
    seq_before = _clipboard_sequence_number()

    _key_down(VK_CONTROL)
    time.sleep(0.02)
    _key_down(VK_C)
    time.sleep(0.02)
    _key_up(VK_C)
    time.sleep(0.02)
    _key_up(VK_CONTROL)
    time.sleep(0.15)

    seq_after = _clipboard_sequence_number()
    if seq_before is not None and seq_after is not None and seq_before == seq_after:
        logger.debug("Ctrl+C had no effect — clipboard unchanged (unsupported editor or no selection)")
        return ""

    try:
        return pyperclip.paste() or ""
    except Exception:
        return ""


def _restore_clipboard(text: str):
    try:
        pyperclip.copy(text)
    except Exception:
        pass


def _select_to_line_start():
    """Shift+Home — select from cursor to start of line."""
    _key_down(VK_SHIFT)
    time.sleep(0.01)
    _key_down(VK_HOME)
    time.sleep(0.01)
    _key_up(VK_HOME)
    time.sleep(0.01)
    _key_up(VK_SHIFT)
    time.sleep(0.05)


def _select_to_line_end():
    """Shift+End — select from cursor to end of line."""
    _key_down(VK_SHIFT)
    time.sleep(0.01)
    _key_down(VK_END)
    time.sleep(0.01)
    _key_up(VK_END)
    time.sleep(0.01)
    _key_up(VK_SHIFT)
    time.sleep(0.05)


def _deselect_right():
    """Move cursor right to deselect."""
    _key_down(VK_RIGHT)
    time.sleep(0.01)
    _key_up(VK_RIGHT)
    time.sleep(0.02)


def _deselect_left():
    """Move cursor left to deselect."""
    _key_down(VK_LEFT)
    time.sleep(0.01)
    _key_up(VK_LEFT)
    time.sleep(0.02)


def get_cursor_context(hwnd: int = 0) -> tuple[str, str]:
    """
    Capture text before and after the cursor on the current line.

    Returns (before_text, after_text). Either may be empty.
    Uses Shift+Home/End + Ctrl+C to read text, then deselects and
    restores the original clipboard.

    ``hwnd`` is the foreground window the user was typing into. If it is a
    terminal/console/agent window, capture is skipped entirely: the
    Shift+Home/End selection model does not apply there, and Ctrl+C is SIGINT
    (not "copy"), so injecting it would interrupt CLI agents like kimi-code.
    """
    if is_terminal_window(hwnd):
        logger.info(
            "Skipping cursor context capture in terminal window (hwnd=%s)", hwnd
        )
        return "", ""

    saved_clipboard = ""
    try:
        saved_clipboard = pyperclip.paste() or ""
    except Exception:
        pass

    before = ""
    after = ""

    try:
        # Capture text before cursor (Shift+Home, Ctrl+C, then deselect)
        _select_to_line_start()
        before = _send_copy()
        _deselect_right()

        # Capture text after cursor (Shift+End, Ctrl+C, then deselect)
        _select_to_line_end()
        after = _send_copy()
        _deselect_left()
    except Exception as e:
        logger.warning("Failed to capture cursor context: %s", e)
    finally:
        _restore_clipboard(saved_clipboard)

    # Trim to reasonable length
    if len(before) > MAX_CONTEXT_CHARS:
        before = before[-MAX_CONTEXT_CHARS:]
    if len(after) > MAX_CONTEXT_CHARS:
        after = after[:MAX_CONTEXT_CHARS]

    logger.info("Cursor context: before=%d chars, after=%d chars", len(before), len(after))
    return before, after
