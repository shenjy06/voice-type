"""Text output — clipboard paste via Ctrl+V."""

import logging
import threading
import time
import ctypes

import pyperclip
from voicetype.config import AppConfig
from voicetype.constants import (
    PASTE_MODE_AUTO,
    PASTE_MODE_CTRL_V,
    PASTE_MODE_CTRL_SHIFT_V,
    PASTE_MODE_CLIPBOARD,
)
from voicetype.window_detect import is_terminal_window
from voicetype.window_manager import set_foreground_window

logger = logging.getLogger(__name__)

KEYEVENTF_KEYUP = 0x0002
user32 = ctypes.windll.user32


class TextTyper:
    def __init__(self, config: AppConfig):
        self.config = config
        # Clipboard operations on Windows are not thread-safe; serialize
        # copy/paste so the restore thread cannot race with the main thread.
        self._clipboard_lock = threading.Lock()

    def output_text(self, text: str, saved_hwnd: int = 0) -> bool:
        """
        Output text to the cursor position.

        Strategy: clipboard copy + configured paste shortcut.
        Attempts to restore the saved foreground window first.
        Saves and restores the user's previous clipboard content.

        Returns True if text was successfully pasted, False otherwise.
        """
        if not text:
            return False

        # Try to restore the saved window
        window_restored = False
        if saved_hwnd and saved_hwnd != 0:
            window_restored = set_foreground_window(saved_hwnd)
            if not window_restored:
                logger.warning("Failed to restore foreground window (hwnd=%s)", saved_hwnd)
            else:
                logger.debug("Foreground window restored (hwnd=%s)", saved_hwnd)

        # Small delay to ensure window focus is settled
        time.sleep(self.config.output.paste_delay_ms / 1000.0)

        # Preserve the user's previous clipboard content so we can restore it.
        try:
            with self._clipboard_lock:
                original_clipboard = pyperclip.paste()
                pyperclip.copy(text)
        except Exception as e:
            logger.warning("Clipboard operation failed: %s", e, exc_info=True)
            original_clipboard = None

        paste_mode = self.config.output.paste_mode
        if paste_mode == PASTE_MODE_CLIPBOARD:
            logger.debug("Clipboard-only mode — skipping paste shortcut")
            return True

        use_terminal_paste = self._use_terminal_paste(paste_mode, saved_hwnd)
        logger.debug(
            "Sending paste: mode=%s, terminal=%s",
            paste_mode,
            use_terminal_paste,
        )

        # Send paste shortcut via ctypes
        success = self._send_paste(use_terminal_paste=use_terminal_paste)

        if not success:
            logger.error("Paste shortcut injection failed (mode=%s)", paste_mode)
            return False

        # Restore the original clipboard content if paste succeeded.
        # Delay slightly so the target app can read the new content first.
        if original_clipboard is not None and original_clipboard != text:
            self._schedule_clipboard_restore(original_clipboard)

        logger.info("Paste successful (%d chars)", len(text))
        return True

    def _schedule_clipboard_restore(self, original: str) -> None:
        """Restore the original clipboard in a background thread after a short delay."""
        def _restore():
            time.sleep(1.0)
            try:
                with self._clipboard_lock:
                    pyperclip.copy(original)
            except Exception as e:
                logger.warning("Failed to restore clipboard: %s", e)

        threading.Thread(target=_restore, daemon=True).start()

    def _send_paste(self, use_terminal_paste: bool = False) -> bool:
        """Send Ctrl+V, or Ctrl+Shift+V for terminal windows.

        Returns False if any key injection call reports failure (keybd_event
        returns nonzero on success, zero on failure — e.g. UIPI blocking), so
        a silently-dropped paste surfaces to the user as a "copied instead"
        toast instead of looking like success.
        """
        try:
            VK_CONTROL = 0x11
            VK_SHIFT = 0x10
            VK_V = 0x56

            def _send(vk: int, flags: int) -> bool:
                # keybd_event returns nonzero on success; ctypes default
                # restype is c_int, so a falsy return means injection failed.
                return bool(user32.keybd_event(vk, 0, flags, 0))

            if not _send(VK_CONTROL, 0):
                logger.debug("keybd_event: Ctrl down failed")
                return False
            time.sleep(0.05)
            if use_terminal_paste:
                if not _send(VK_SHIFT, 0):
                    logger.debug("keybd_event: Shift down failed")
                    return False
                time.sleep(0.05)
            if not _send(VK_V, 0):
                logger.debug("keybd_event: V down failed")
                return False
            time.sleep(0.05)
            if not _send(VK_V, KEYEVENTF_KEYUP):
                logger.debug("keybd_event: V up failed")
                return False
            time.sleep(0.05)
            if use_terminal_paste:
                if not _send(VK_SHIFT, KEYEVENTF_KEYUP):
                    logger.debug("keybd_event: Shift up failed")
                    return False
                time.sleep(0.05)
            if not _send(VK_CONTROL, KEYEVENTF_KEYUP):
                logger.debug("keybd_event: Ctrl up failed")
                return False
            return True
        except Exception as e:
            logger.warning("Paste key injection raised: %s", e, exc_info=True)
            return False

    def _use_terminal_paste(self, paste_mode: str, hwnd: int) -> bool:
        if paste_mode == PASTE_MODE_CTRL_SHIFT_V:
            return True
        if paste_mode == PASTE_MODE_CTRL_V:
            return False
        # AUTO (or any unrecognised mode): detect terminal windows and use
        # Ctrl+Shift+V for them so paste works in Windows Terminal / consoles.
        return self._is_terminal_window(hwnd)

    def _is_terminal_window(self, hwnd: int) -> bool:
        """Detect terminal-like targets that prefer Ctrl+Shift+V.

        Delegates to :func:`voicetype.window_detect.is_terminal_window` so the
        same detection is shared with cursor-context capture (which must SKIP
        terminals, where Ctrl+C is SIGINT). Kept as an instance method so
        callers/tests can patch it on the typer instance.
        """
        return is_terminal_window(hwnd)
