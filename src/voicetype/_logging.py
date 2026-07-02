"""Logging configuration for Voice Type.

Sets up a rotating file handler (for persistent debug logs) and a console
handler (for interactive sessions). Call ``setup_logging()`` once at startup
from ``main()``.
"""

import logging
import logging.handlers
import os
from pathlib import Path

from voicetype.config import CONFIG_DIR

_LOG_FORMAT = "%(asctime)s [%(levelname)-7s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Rotating log: 10 MB max, keep 2 backups. Small enough to avoid filling disk,
# large enough to capture several sessions of debug-level logging.
_LOG_FILE = CONFIG_DIR / "logs" / "voicetype.log"
_MAX_BYTES = 10 * 1024 * 1024
_BACKUP_COUNT = 2


def setup_logging(
    level: int = logging.DEBUG,
    *,
    console_level: int = logging.INFO,
    log_file: Path = _LOG_FILE,
) -> None:
    """Configure root logger with rotating file + console handlers.

    Idempotent: calling multiple times will not duplicate handlers.
    """
    root = logging.getLogger()

    # Avoid double-setup if already configured.
    if root.handlers:
        return

    root.setLevel(level)

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # Rotating file handler — captures everything at DEBUG level.
    log_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError:
        # Fallback: if log file cannot be created (e.g. permission denied),
        # continue with console-only logging rather than crashing.
        pass

    # Console handler — INFO and above so the terminal isn't flooded.
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)
