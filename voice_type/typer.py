"""Text output — window management + clipboard paste."""

import logging
import time
import ctypes
from ctypes import wintypes

import pyperclip
from voice_type.config import AppConfig

logger = logging.getLogger(__name__)

# Windows constants
SW_RESTORE = 9
SW_SHOW = 5
WM_NULL = 0x0000

# ctypes function setup
user32 = ctypes.windll.user32


def get_foreground_window() -> int:
    """Get the handle of the current foreground window."""
    hwnd = user32.GetForegroundWindow()
    return hwnd


def set_foreground_window(hwnd: int) -> bool:
    """Attempt to bring the window with given handle to the foreground."""
    if not hwnd or hwnd == 0:
        return False
    # Check if window still exists
    if not user32.IsWindow(hwnd):
        return False
    # Try multiple approaches
    result = user32.SetForegroundWindow(hwnd)
    if not result:
        # Fallback: try ShowWindow + SetForegroundWindow
        user32.ShowWindow(hwnd, SW_RESTORE)
        result = user32.SetForegroundWindow(hwnd)
    return bool(result)


class TextTyper:
    def __init__(self, config: AppConfig):
        self.config = config

    def output_text(self, text: str, saved_hwnd: int = 0) -> bool:
        """
        Output text to the cursor position.

        Strategy: clipboard copy + Ctrl+V paste.
        Attempts to restore the saved foreground window first.

        Returns True if text was successfully pasted, False otherwise.
        """
        if not text:
            logger.warning("No text to output")
            return False

        # Try to restore the saved window
        if saved_hwnd and saved_hwnd != 0:
            logger.info("Restoring window hwnd=%s", saved_hwnd)
            if not set_foreground_window(saved_hwnd):
                logger.warning("Failed to restore saved window")

        # Small delay to ensure window focus is settled
        time.sleep(self.config.output.paste_delay_ms / 1000.0)

        # Copy to clipboard and paste
        try:
            original_clipboard = pyperclip.paste()
        except Exception:
            original_clipboard = ""

        pyperclip.copy(text)
        logger.info("Text copied to clipboard (%d chars)", len(text))

        # Send Ctrl+V via ctypes
        success = self._send_paste()

        if not success:
            # Restore original clipboard
            try:
                pyperclip.copy(original_clipboard)
            except Exception:
                pass
            logger.error("Failed to paste text")
            return False

        logger.info("Text pasted successfully")
        return True

    def _send_paste(self) -> bool:
        """Send Ctrl+V using Windows API."""
        try:
            # Use keybd_event for Ctrl+V
            VK_CONTROL = 0x11
            VK_V = 0x56
            KEYEVENTF_KEYUP = 0x0002

            # Press Ctrl
            user32.keybd_event(VK_CONTROL, 0, 0, 0)
            time.sleep(0.05)
            # Press V
            user32.keybd_event(VK_V, 0, 0, 0)
            time.sleep(0.05)
            # Release V
            user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
            time.sleep(0.05)
            # Release Ctrl
            user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
            return True
        except Exception as e:
            logger.error("Failed to send paste keystrokes: %s", e)
            return False
