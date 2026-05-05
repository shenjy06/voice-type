"""Windows window management — foreground control via ctypes."""

import logging
import time
import ctypes

logger = logging.getLogger(__name__)

# Windows constants
SW_RESTORE = 9
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002

user32 = ctypes.windll.user32

# Map keyboard virtual key codes
VK_MENU = 0x12  # Alt key


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
    """Attach our input thread to the target window's thread."""
    our_tid = user32.GetCurrentThreadId()
    target_tid = user32.GetWindowThreadProcessId(target_hwnd, None)
    if our_tid != target_tid:
        user32.AttachThreadInput(target_tid, our_tid, True)


def _detach_thread_input(target_hwnd: int):
    """Detach input threads after use."""
    our_tid = user32.GetCurrentThreadId()
    target_tid = user32.GetWindowThreadProcessId(target_hwnd, None)
    if our_tid != target_tid:
        user32.AttachThreadInput(target_tid, our_tid, False)


def get_foreground_window() -> int:
    """Get the handle of the current foreground window."""
    return user32.GetForegroundWindow()


def set_foreground_window(hwnd: int) -> bool:
    """Attempt to bring the window with given handle to the foreground."""
    if not hwnd or hwnd == 0:
        return False
    if not user32.IsWindow(hwnd):
        logger.warning("Saved window no longer exists (hwnd=%s)", hwnd)
        return False

    # Strategy 1: AttachThreadInput + SetForegroundWindow
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
