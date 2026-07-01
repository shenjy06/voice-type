"""Text output — clipboard paste via Ctrl+V."""

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
from voicetype.window_manager import set_foreground_window

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

# Re-exported for backward compatibility with existing imports.
PASTE_MODE_AUTO = PASTE_MODE_AUTO
PASTE_MODE_CTRL_V = PASTE_MODE_CTRL_V
PASTE_MODE_CTRL_SHIFT_V = PASTE_MODE_CTRL_SHIFT_V
PASTE_MODE_CLIPBOARD = PASTE_MODE_CLIPBOARD


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

        # Small delay to ensure window focus is settled
        time.sleep(self.config.output.paste_delay_ms / 1000.0)

        # Preserve the user's previous clipboard content so we can restore it.
        try:
            with self._clipboard_lock:
                original_clipboard = pyperclip.paste()
                pyperclip.copy(text)
        except Exception:
            original_clipboard = None

        paste_mode = self.config.output.paste_mode
        if paste_mode == PASTE_MODE_CLIPBOARD:
            return True

        use_terminal_paste = self._use_terminal_paste(paste_mode, saved_hwnd)

        # Send paste shortcut via ctypes
        success = self._send_paste(use_terminal_paste=use_terminal_paste)

        if not success:
            return False

        # Restore the original clipboard content if paste succeeded.
        # Delay slightly so the target app can read the new content first.
        if original_clipboard is not None and original_clipboard != text:
            self._schedule_clipboard_restore(original_clipboard)

        return True

    def _schedule_clipboard_restore(self, original: str) -> None:
        """Restore the original clipboard in a background thread after a short delay."""
        def _restore():
            time.sleep(1.0)
            try:
                with self._clipboard_lock:
                    pyperclip.copy(original)
            except Exception:
                pass

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
                return False
            time.sleep(0.05)
            if use_terminal_paste:
                if not _send(VK_SHIFT, 0):
                    return False
                time.sleep(0.05)
            if not _send(VK_V, 0):
                return False
            time.sleep(0.05)
            if not _send(VK_V, KEYEVENTF_KEYUP):
                return False
            time.sleep(0.05)
            if use_terminal_paste:
                if not _send(VK_SHIFT, KEYEVENTF_KEYUP):
                    return False
                time.sleep(0.05)
            if not _send(VK_CONTROL, KEYEVENTF_KEYUP):
                return False
            return True
        except Exception:
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
        except Exception:
            return ""
        if not length:
            return ""
        return buffer.value

    def _get_window_title(self, hwnd: int) -> str:
        try:
            length = user32.GetWindowTextLengthW(hwnd)
        except Exception:
            return ""
        if not length:
            return ""

        buffer = ctypes.create_unicode_buffer(length + 1)
        try:
            user32.GetWindowTextW(hwnd, buffer, len(buffer))
        except Exception:
            return ""
        return buffer.value
