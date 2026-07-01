"""Windows window management — foreground control via ctypes."""

import time
import ctypes

# Windows constants
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
        return False
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
        return False

    # Strategy 1: AttachThreadInput + SetForegroundWindow
    attached = False
    try:
        attached = _attach_thread_input(hwnd)
        time.sleep(0.01)
        result = user32.SetForegroundWindow(hwnd)
        if result:
            return True
    except Exception:
        pass
    finally:
        if attached:
            _detach_thread_input(hwnd)

    # Strategy 2: Alt tap + SetForegroundWindow
    if _tap_alt():
        time.sleep(0.02)
        result = user32.SetForegroundWindow(hwnd)
        if result:
            return True

    # Strategy 3: BringWindowToTop + Alt tap + SetForegroundWindow
    # NOTE: Do NOT use ShowWindow(SW_RESTORE) here — it un-maximizes a
    # maximized window, which the user sees as the target window shrinking
    # from full-screen to windowed mode right as text is pasted.
    # BringWindowToTop raises the window without changing its show state
    # (minimized/maximized/restored).
    try:
        user32.BringWindowToTop(hwnd)
    except Exception:
        pass
    if _tap_alt():
        time.sleep(0.02)
        result = user32.SetForegroundWindow(hwnd)
        if result:
            return True

    return False
