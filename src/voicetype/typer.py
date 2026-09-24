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

# Voice-command action -> key sequence. Each entry is a list of
# (virtual-key, key-up?) steps sent in order via keybd_event, mirroring the
# desktop port: newline = Shift+Enter, enter = Return, undo = Ctrl+Z,
# tab = Tab.
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_RETURN = 0x0D
VK_TAB = 0x09
VK_Z = 0x5A

_ACTION_KEY_SEQUENCES: dict[str, tuple[int, ...]] = {
    "newline": (VK_SHIFT, VK_RETURN),
    "enter": (VK_RETURN,),
    "undo": (VK_CONTROL, VK_Z),
    "tab": (VK_TAB,),
}


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

        paste_start = time.monotonic()

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
        # Save first (read-only, minimal risk), then copy (destructive). If the
        # copy fails we try to restore the original immediately, otherwise the
        # clipboard could be left in an undefined state (cleared but not set).
        try:
            with self._clipboard_lock:
                original_clipboard = pyperclip.paste()
        except Exception as e:
            logger.warning("Failed to read clipboard: %s", e, exc_info=True)
            original_clipboard = None

        try:
            with self._clipboard_lock:
                pyperclip.copy(text)
        except Exception as e:
            logger.warning("Clipboard copy failed: %s", e, exc_info=True)
            # The clipboard may have been cleared before the copy failed.
            # Try to restore the original immediately.
            if original_clipboard is not None and original_clipboard != text:
                try:
                    pyperclip.copy(original_clipboard)
                except Exception:
                    pass
            return False

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

        logger.info("Paste successful (%d chars) in %.1fms", len(text), (time.monotonic() - paste_start) * 1000)
        return True

    def send_action_key(self, action: str, saved_hwnd: int = 0) -> bool:
        """Inject a voice-command key sequence into the saved window.

        Mirrors :meth:`output_text`'s focus handling (restore the saved
        foreground window, wait for focus to settle, clear stuck modifiers)
        but sends a command keystroke instead of a paste. Unknown actions
        return False without touching the keyboard.
        """
        sequence = _ACTION_KEY_SEQUENCES.get(action)
        if not sequence:
            logger.warning("Unknown action key: %r", action)
            return False

        if saved_hwnd and saved_hwnd != 0:
            if not set_foreground_window(saved_hwnd):
                logger.warning("Failed to restore foreground window (hwnd=%s)", saved_hwnd)

        time.sleep(self.config.output.paste_delay_ms / 1000.0)

        try:
            # Release any modifiers left over from the foreground-restore
            # Alt tap so they don't turn the action into a menu shortcut.
            for vk in (0x12, VK_SHIFT, VK_CONTROL):  # 0x12 = VK_MENU (Alt)
                user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
            time.sleep(0.02)

            # Press modifiers first, then the main key; release in reverse.
            modifiers, main_key = sequence[:-1], sequence[-1]
            for vk in modifiers:
                user32.keybd_event(vk, 0, 0, 0)
                time.sleep(0.02)
            user32.keybd_event(main_key, 0, 0, 0)
            time.sleep(0.02)
            user32.keybd_event(main_key, 0, KEYEVENTF_KEYUP, 0)
            for vk in reversed(modifiers):
                time.sleep(0.02)
                user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
            logger.info("Action key sent: %s (hwnd=%s)", action, saved_hwnd)
            return True
        except Exception as e:
            logger.warning("Action key injection raised: %s", e, exc_info=True)
            return False

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

        Before sending Ctrl+V, all modifier keys are force-released and an
        Esc is tapped. The Alt-tap used by ``set_foreground_window`` to
        bypass Windows foreground restrictions leaves the target app's menu
        bar activated (visible in apps like Notepad++, where the menu bar
        highlights after Alt). If we send V while the menu bar is active,
        the V is interpreted as a menu mnemonic (e.g. "View" → Alt+V)
        instead of pasting. Releasing modifiers + Esc dismisses the menu
        so Ctrl+V lands in the editor as intended.
        """
        try:
            VK_CONTROL = 0x11
            VK_SHIFT = 0x10
            VK_V = 0x56
            VK_MENU = 0x12      # Alt
            VK_ESCAPE = 0x1B

            def _send(vk: int, flags: int) -> bool:
                # keybd_event returns nonzero on success; ctypes default
                # restype is c_int, so a falsy return means injection failed.
                return bool(user32.keybd_event(vk, 0, flags, 0))

            # Clear any stuck modifier state (Alt from the foreground-restore
            # tap, or Ctrl/Shift from a previous paste) and dismiss a menu
            # bar that Alt may have activated. These are best-effort: we
            # intentionally ignore their return values because a cleanup
            # failure should never block the actual Ctrl+V paste.
            for vk in (VK_MENU, VK_SHIFT, VK_CONTROL):
                _send(vk, KEYEVENTF_KEYUP)
            _send(VK_ESCAPE, 0)
            _send(VK_ESCAPE, KEYEVENTF_KEYUP)
            time.sleep(0.02)

            if not _send(VK_CONTROL, 0):
                logger.debug("keybd_event: Ctrl down failed")
                return False
            time.sleep(0.02)
            if use_terminal_paste:
                if not _send(VK_SHIFT, 0):
                    logger.debug("keybd_event: Shift down failed")
                    return False
                time.sleep(0.02)
            if not _send(VK_V, 0):
                logger.debug("keybd_event: V down failed")
                return False
            time.sleep(0.02)
            if not _send(VK_V, KEYEVENTF_KEYUP):
                logger.debug("keybd_event: V up failed")
                return False
            time.sleep(0.02)
            if use_terminal_paste:
                if not _send(VK_SHIFT, KEYEVENTF_KEYUP):
                    logger.debug("keybd_event: Shift up failed")
                    return False
                time.sleep(0.02)
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
