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
        ("dwExtraInfo", ctypes.c_void_p),  # ULONG_PTR, pointer-sized integer
    ]


def _tap_alt() -> bool:
    """Tap Alt key to bypass Windows foreground window restriction.

    Returns True if at least one input was successfully injected.
    """
    inputs = (KeyboardInput * 2)()
    inputs[0].type = INPUT_KEYBOARD
    inputs[0].wVk = VK_MENU
    inputs[0].dwFlags = 0
    inputs[1].type = INPUT_KEYBOARD
    inputs[1].wVk = VK_MENU
    inputs[1].dwFlags = KEYEVENTF_KEYUP
    result = user32.SendInput(2, inputs, ctypes.sizeof(KeyboardInput))
    if result == 0:
        logger.warning("SendInput failed: no events injected")
        return False
    if result != 2:
        logger.debug("SendInput partially succeeded: expected 2, got %d", result)
    return True


def _attach_thread_input(target_hwnd: int) -> bool:
    """Attach our input thread to the target window's thread.

    Returns True if attachment was performed (threads were different).
    """
    our_tid = user32.GetCurrentThreadId()
    target_tid = user32.GetWindowThreadProcessId(target_hwnd, None)
    if our_tid != target_tid:
        result = user32.AttachThreadInput(target_tid, our_tid, True)
        if not result:
            logger.warning("AttachThreadInput failed")
            return False
        return True
    return False


def _detach_thread_input(target_hwnd: int) -> None:
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
    attached = False
    try:
        attached = _attach_thread_input(hwnd)
        time.sleep(0.01)
        result = user32.SetForegroundWindow(hwnd)
        if result:
            return True
    except Exception as e:
        logger.debug("Strategy 1 failed: %s", e)
    finally:
        if attached:
            _detach_thread_input(hwnd)

    # Strategy 2: Alt tap + SetForegroundWindow
    if _tap_alt():
        time.sleep(0.02)
        result = user32.SetForegroundWindow(hwnd)
        if result:
            return True

    # Strategy 3: ShowWindow(RESTORE) + Alt tap + SetForegroundWindow
    restore_result = user32.ShowWindow(hwnd, SW_RESTORE)
    if not restore_result:
        logger.debug("ShowWindow returned %d", restore_result)
    if _tap_alt():
        time.sleep(0.02)
        result = user32.SetForegroundWindow(hwnd)
        if result:
            return True

    return False
