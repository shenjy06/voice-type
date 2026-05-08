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

TERMINAL_WINDOW_CLASSES = {
    "CASCADIA_HOSTING_WINDOW_CLASS",  # Windows Terminal
    "ConsoleWindowClass",  # conhost.exe, cmd.exe, PowerShell console host
    "mintty",
}
TERMINAL_TITLE_MARKERS = (
    "claude",
    "codex",
    "command prompt",
    "powershell",
    "windows powershell",
)

PASTE_MODE_AUTO = "auto"
PASTE_MODE_CTRL_V = "ctrl_v"
PASTE_MODE_CTRL_SHIFT_V = "ctrl_shift_v"
PASTE_MODE_CLIPBOARD = "clipboard"


class TextTyper:
    def __init__(self, config: AppConfig):
        self.config = config

    def output_text(self, text: str, saved_hwnd: int = 0) -> bool:
        """
        Output text to the cursor position.

        Strategy: clipboard copy + configured paste shortcut.
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

        pyperclip.copy(text)
        logger.info("Text copied to clipboard (%d chars)", len(text))

        paste_mode = self.config.output.paste_mode
        if paste_mode == PASTE_MODE_CLIPBOARD:
            logger.info("Paste mode is clipboard-only; skipping paste keystrokes")
            return True

        use_terminal_paste = self._use_terminal_paste(paste_mode, saved_hwnd)

        # Send paste shortcut via ctypes
        success = self._send_paste(use_terminal_paste=use_terminal_paste)

        if not success:
            logger.error("Failed to paste text; text remains on clipboard")
            return False

        logger.info("Text pasted successfully, window_restored=%s", window_restored)
        return True

    def _send_paste(self, use_terminal_paste: bool = False) -> bool:
        """Send Ctrl+V, or Ctrl+Shift+V for terminal windows."""
        try:
            VK_CONTROL = 0x11
            VK_SHIFT = 0x10
            VK_V = 0x56

            user32.keybd_event(VK_CONTROL, 0, 0, 0)
            time.sleep(0.05)
            if use_terminal_paste:
                user32.keybd_event(VK_SHIFT, 0, 0, 0)
                time.sleep(0.05)
            user32.keybd_event(VK_V, 0, 0, 0)
            time.sleep(0.05)
            user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
            time.sleep(0.05)
            if use_terminal_paste:
                user32.keybd_event(VK_SHIFT, 0, KEYEVENTF_KEYUP, 0)
                time.sleep(0.05)
            user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
            return True
        except Exception as e:
            logger.error("Failed to send paste keystrokes: %s", e)
            return False

    def _use_terminal_paste(self, paste_mode: str, hwnd: int) -> bool:
        if paste_mode == PASTE_MODE_CTRL_SHIFT_V:
            return True
        if paste_mode == PASTE_MODE_CTRL_V:
            return False
        if paste_mode != PASTE_MODE_AUTO:
            logger.warning("Unknown paste mode '%s', falling back to auto", paste_mode)
        return self._is_terminal_window(hwnd)

    def _is_terminal_window(self, hwnd: int) -> bool:
        """Detect terminal-like targets that prefer Ctrl+Shift+V."""
        if not hwnd:
            return False

        class_name = self._get_window_class_name(hwnd)
        if class_name in TERMINAL_WINDOW_CLASSES:
            return True

        title = self._get_window_title(hwnd).lower()
        return any(marker in title for marker in TERMINAL_TITLE_MARKERS)

    def _get_window_class_name(self, hwnd: int) -> str:
        buffer = ctypes.create_unicode_buffer(256)
        try:
            length = user32.GetClassNameW(hwnd, buffer, len(buffer))
        except Exception as e:
            logger.debug("Failed to get window class for hwnd=%s: %s", hwnd, e)
            return ""
        if not length:
            return ""
        return buffer.value

    def _get_window_title(self, hwnd: int) -> str:
        try:
            length = user32.GetWindowTextLengthW(hwnd)
        except Exception as e:
            logger.debug("Failed to get window title length for hwnd=%s: %s", hwnd, e)
            return ""
        if not length:
            return ""

        buffer = ctypes.create_unicode_buffer(length + 1)
        try:
            user32.GetWindowTextW(hwnd, buffer, len(buffer))
        except Exception as e:
            logger.debug("Failed to get window title for hwnd=%s: %s", hwnd, e)
            return ""
        return buffer.value
