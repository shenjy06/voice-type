"""Text output — clipboard paste via Ctrl+V."""

import logging
import time
import ctypes

import pyperclip
from src.config import AppConfig
from src.window_manager import set_foreground_window

logger = logging.getLogger(__name__)

KEYEVENTF_KEYUP = 0x0002
user32 = ctypes.windll.user32


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
        window_restored = False
        if saved_hwnd and saved_hwnd != 0:
            logger.info("Restoring window hwnd=%s", saved_hwnd)
            window_restored = set_foreground_window(saved_hwnd)
            if not window_restored:
                logger.warning("Failed to restore saved window, will paste in active window")

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

        logger.info("Text pasted successfully, window_restored=%s", window_restored)
        return True

    def _send_paste(self) -> bool:
        """Send Ctrl+V using Windows API."""
        try:
            # Use keybd_event for Ctrl+V
            VK_CONTROL = 0x11
            VK_V = 0x56

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
