"""Windows auto-start management via registry."""

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_APP_NAME = "VoiceType"


def _open_key(writable: bool = False):
    import winreg
    access = winreg.KEY_ALL_ACCESS if writable else winreg.KEY_READ
    return winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_KEY, 0, access)


def is_auto_start_enabled() -> bool:
    try:
        with _open_key() as key:
            winreg.QueryValueEx(key, _APP_NAME)
            return True
    except (FileNotFoundError, OSError):
        return False


def set_auto_start(enabled: bool) -> None:
    import winreg
    if enabled:
        exe_path = _get_exe_path()
        if not exe_path:
            logger.warning("Cannot determine exe path for auto-start")
            return
        with _open_key(writable=True) as key:
            winreg.SetValueEx(key, _APP_NAME, 0, winreg.REG_SZ, f'"{exe_path}"')
        logger.info("Auto-start enabled: %s", exe_path)
    else:
        try:
            with _open_key(writable=True) as key:
                winreg.DeleteValue(key, _APP_NAME)
            logger.info("Auto-start disabled")
        except FileNotFoundError:
            pass


def _get_exe_path() -> str:
    if getattr(sys, "frozen", False):
        return sys.executable
    return str(Path(sys.executable).parent / "python.exe")