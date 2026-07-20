"""Terminal-window detection shared by paste and cursor-context logic.

Both :class:`voicetype.typer.TextTyper` (choosing Ctrl+V vs Ctrl+Shift+V) and
:func:`voicetype.context.get_cursor_context` (deciding whether simulating
Shift+Home/Ctrl+C is safe) need to know whether the foreground window is a
terminal. The detection lived only in ``typer.py``, so the context capture
path injected Ctrl+C into terminals (where it is SIGINT, not "copy") and
killed CLI agents like kimi-code. This module is the single source of truth.
"""

import ctypes
import functools
import logging

logger = logging.getLogger(__name__)

user32 = ctypes.windll.user32

TERMINAL_WINDOW_CLASSES = {
    # Windows Terminal / conPTY
    "CASCADIA_HOSTING_WINDOW_CLASS",  # Windows Terminal
    "ConsoleWindowClass",  # conhost.exe, cmd.exe, PowerShell console host
    "PseudoConsoleInputSocket",  # Windows conPTY internal
    # Linux-like terminals on Windows (Git Bash, WSL, etc.)
    "mintty",  # Git Bash, MSYS2, Cygwin
    "cygwin",  # Cygwin terminal
    "xterm",  # XTerm-compatible
    "rxvt",  # RXVT
    # Modern GPU-accelerated terminals
    "Alacritty",  # Alacritty
    "wezterm-gui",  # WezTerm
    "org.wezterm.wezterm",  # WezTerm (alternative)
    "kgui",  # Kitty
    # VS Code / IDE terminals
    "Chrome_WidgetWin_1",  # VS Code (Electron) — also covers cursor, windsurf
    "Chrome_WidgetWin_0",  # VS Code alternative
    "Chrome_RenderWidgetHostHWND",  # Chromium embedded
    # JetBrains / IntelliJ
    "SunAwtFrame",  # JetBrains IntelliJ, PyCharm, etc.
    "JetWindowClass",  # JetBrains alternative
    # Other agent / IDE
    "Windows.UI.Core.CoreWindow",  # UWP apps (some agents)
    "ReBarWindow32",  # Shell window
    "HwndWrapper",  # WPF apps (some agents)
    "Notepad",  # Notepad (for debugging)
}
TERMINAL_TITLE_MARKERS = (
    # Command shells
    "command prompt",
    "powershell",
    "windows powershell",
    "cmd.exe",
    "bash",
    "zsh",
    "git bash",
    "wsl",
    # AI coding agents
    "claude",
    "codex",
    "kimi",
    "cursor",
    "windsurf",
    "continue",
    "cline",
    " aider",
    "tabnine",
    "github copilot",
    # IDEs
    "visual studio code",
    "vs code",
    "intellij",
    "pycharm",
    "webstorm",
    "jetbrains",
)

KNOWN_TERMINAL_EXES = {
    "windowsterminal.exe",
    "cmd.exe",
    "powershell.exe",
    "pwsh.exe",
    "bash.exe",
    "zsh.exe",
    "sh.exe",
    "mintty.exe",
    "alacritty.exe",
    "wezterm-gui.exe",
    "wezterm.exe",
    "code.exe",  # VS Code
    "cursor.exe",
    "windsurf.exe",
    "claude.exe",
    "codex.exe",
    "kitty.exe",
    "conhost.exe",
}


def get_window_class_name(hwnd: int) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    try:
        length = user32.GetClassNameW(hwnd, buffer, len(buffer))
    except Exception:
        return ""
    if not length:
        return ""
    return buffer.value


def get_window_title(hwnd: int) -> str:
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


def get_process_name(hwnd: int) -> str:
    """Return the executable name for the process owning ``hwnd``.

    The process lookup (OpenProcess + GetModuleFileNameEx) is cached, but
    keyed by ``(hwnd, pid)`` — NOT by hwnd alone. Windows recycles HWNDs:
    once a window is destroyed its handle can be handed to a new window of
    a different process, so a pure-HWND cache could return a stale process
    name and misdetect a terminal window.
    """
    try:
        pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return ""
    except Exception:
        return ""
    return _get_process_name_cached(hwnd, pid.value)


@functools.lru_cache(maxsize=64)
def _get_process_name_cached(hwnd: int, pid: int) -> str:
    try:
        # PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h_process = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not h_process:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(512)
            size = ctypes.wintypes.DWORD(len(buf))
            # GetModuleFileNameExW
            ctypes.windll.psapi.GetModuleFileNameExW(h_process, 0, buf, size)
            full_path = buf.value
            return full_path.split("\\")[-1] if full_path else ""
        finally:
            ctypes.windll.kernel32.CloseHandle(h_process)
    except Exception:
        return ""


def is_terminal_window(hwnd: int) -> bool:
    """Return True if ``hwnd`` looks like a terminal/console/agent window.

    Used to decide whether Ctrl+Shift+V is needed for paste AND whether
    simulating Shift+Home/Ctrl+C for cursor-context capture is safe — it is
    NOT safe in terminals, where Ctrl+C is SIGINT.
    """
    if not hwnd:
        return False

    class_name = get_window_class_name(hwnd)
    if class_name in TERMINAL_WINDOW_CLASSES:
        logger.debug("Terminal detected (class=%s, hwnd=%s)", class_name, hwnd)
        return True

    title = get_window_title(hwnd).lower()
    for marker in TERMINAL_TITLE_MARKERS:
        if marker in title:
            logger.debug(
                "Terminal detected (title=%r, marker=%r, hwnd=%s)",
                title,
                marker,
                hwnd,
            )
            return True

    # Fallback: check the process name for known executables.
    proc_name = get_process_name(hwnd)
    if proc_name:
        if proc_name.lower() in KNOWN_TERMINAL_EXES:
            logger.debug("Terminal detected (process=%s, hwnd=%s)", proc_name, hwnd)
            return True

    logger.debug(
        "Non-terminal window (class=%s, title=%r, process=%s, hwnd=%s)",
        class_name,
        title[:50],
        proc_name,
        hwnd,
    )
    return False
