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
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002

# ctypes function setup
user32 = ctypes.windll.user32

# Map keyboard virtual key codes for the Alt key trick
VK_MENU = 0x12  # Alt key
VK_NULL = 0x00

# SendInput structure
class KeyboardInput(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


def _tap_alt():
    """Tap Alt key to bypass Windows foreground window restriction."""
    inputs = (KeyboardInput * 2)()
    inputs[0].type = INPUT_KEYBOARD
    inputs[0].wVk = VK_MENU
    inputs[0].dwFlags = 0
    inputs[1].type = INPUT_KEYBOARD
    inputs[1].wVk = VK_MENU
    inputs[1].dwFlags = KEYEVENTF_KEYUP
    user32.SendInput(2, inputs, ctypes.sizeof(KeyboardInput))


def _attach_thread_input(target_hwnd: int):
    """Attach our input thread to the target window's thread for reliable focus control."""
    our_tid = user32.GetCurrentThreadId()
    target_tid = user32.GetWindowThreadProcessId(target_hwnd, None)
    if our_tid != target_tid:
        user32.AttachThreadInput(target_tid, our_tid, True)


def _detach_thread_input(target_hwnd: int):
    """Detach input threads after use to avoid side effects."""
    our_tid = user32.GetCurrentThreadId()
    target_tid = user32.GetWindowThreadProcessId(target_hwnd, None)
    if our_tid != target_tid:
        user32.AttachThreadInput(target_tid, our_tid, False)


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
        logger.warning("Saved window no longer exists (hwnd=%s)", hwnd)
        return False

    # Strategy 1: AttachThreadInput + SetForegroundWindow (most reliable)
    try:
        _attach_thread_input(hwnd)
        time.sleep(0.01)
        result = user32.SetForegroundWindow(hwnd)
        _detach_thread_input(hwnd)
        if result:
            return True
    except Exception:
        pass

    # Strategy 2: Alt tap + SetForegroundWindow
    _tap_alt()
    time.sleep(0.02)
    result = user32.SetForegroundWindow(hwnd)
    if result:
        return True

    # Strategy 3: ShowWindow(RESTORE) + Alt tap + SetForegroundWindow
    user32.ShowWindow(hwnd, SW_RESTORE)
    _tap_alt()
    time.sleep(0.02)
    return bool(user32.SetForegroundWindow(hwnd))


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
