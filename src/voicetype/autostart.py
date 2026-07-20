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
        command = _get_autostart_command()
        if not command:
            logger.warning("Cannot determine exe path for auto-start")
            return
        with _open_key(writable=True) as key:
            winreg.SetValueEx(key, _APP_NAME, 0, winreg.REG_SZ, command)
        logger.info("Auto-start enabled: %s", command)
    else:
        try:
            with _open_key(writable=True) as key:
                winreg.DeleteValue(key, _APP_NAME)
            logger.info("Auto-start disabled")
        except FileNotFoundError:
            pass


def _get_autostart_command() -> str:
    """Return the registry command line used to launch the app at logon.

    Frozen (PyInstaller) builds launch the exe directly. In script mode the
    previous code registered a bare ``python.exe`` path — which starts an
    interactive interpreter and immediately exits, so auto-start silently
    did nothing. Register ``pythonw.exe -m voicetype`` instead (windowless
    interpreter + module entry point), falling back to ``python.exe`` when
    ``pythonw.exe`` is unavailable.
    """
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = pythonw if pythonw.exists() else Path(sys.executable)
    return f'"{exe}" -m voicetype'