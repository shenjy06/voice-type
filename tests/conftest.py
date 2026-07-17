import gc
import os

import pytest

# Force offscreen qt platform when running tests on a headless display (CI,
# SSH sessions, or any machine without an X server). pytest-qt picks this
# up automatically; this env var only kicks in when QT_QPA_PLATFORM has
# NOT already been set by the user.
if not os.environ.get("QT_QPA_PLATFORM"):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

from voicetype.config import AppConfig  # noqa: E402


@pytest.fixture(autouse=True)
def tmp_config_path(tmp_path, monkeypatch):
    """Redirect CONFIG_DIR/CONFIG_FILE to a temporary directory for every test.

    autouse=True is critical: settings-dialog and main-window tests call
    ``config.save()`` (via ``_save_and_close`` / ``_save_quick_settings``).
    Without this redirect those saves would overwrite the developer's real
    ``~/.voice-type/config.json`` with test data (empty API keys, "sk-test",
    …), destroying the user's config. Making it autouse guarantees every
    test — including ones that forget to ask for the fixture explicitly —
    is sandboxed. Tests that want the dir path can still request it by name.
    """
    import voicetype.config as config_mod
    config_dir = tmp_path / ".voice-type"
    monkeypatch.setattr(config_mod, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config_mod, "CONFIG_FILE", config_dir / "config.json")
    monkeypatch.setattr(config_mod, "PROFILES_DIR", config_dir / "profiles")
    monkeypatch.setattr(config_mod, "ACTIVE_PROFILE_FILE", config_dir / "active_profile")
    return config_dir


def make_config(**overrides):
    """Create an AppConfig with nested section overrides.

    Usage: make_config(asr={"model": "whisper-1", "language": "en"})
    """
    cfg = AppConfig()
    for section, values in overrides.items():
        target = getattr(cfg, section, None)
        if target is not None:
            for k, v in values.items():
                setattr(target, k, v)
    return cfg


@pytest.fixture(scope="session")
def qapp():
    """Session-scoped QApplication — shared across all test modules.

    pytest-qt defaults to one QApplication per test function.  Each new
    instance allocates ~100 MB from the OS heap, and heap fragmentation
    prevents that memory from being reclaimed after destruction — the
    process grows monotonically over 200+ tests.  A single shared instance
    eliminates this entirely.
    """
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _cleanup_qt(qapp):
    """Tear down per-test Qt + Python state to prevent monotonic memory growth.

    Three things leak between tests:
      1. Top-level widgets (StatusBubble, Toast, dialogs) — close + deleteLater.
      2. QTimer / QThread / background daemon threads — stop + wait.
      3. Python reference cycles through Qt parent-child links — gc.collect.

    Without this the shared QApplication accumulates stale objects and the
    process RSS grows without bound across 200+ tests.
    """
    yield
    # 1. Destroy top-level widgets
    for widget in qapp.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    qapp.processEvents()
    qapp.processEvents()

    # 2. Stop all QTimers (they hold lambdas / bound methods → reference cycles)
    for obj in qapp.findChildren(object):
        if hasattr(obj, 'stop') and hasattr(obj, 'interval'):
            try:
                obj.stop()
            except Exception:
                pass

    # 3. Clear Qt's internal caches (pixmap, icon, font database) — these are
    #    process-global and survive deleteLater(), so they must be purged
    #    explicitly or they accumulate across tests.
    from PySide6.QtGui import QPixmapCache
    QPixmapCache.clear()
    # QIcon has no clearCache in PySide6 — the pixmap cache is the main leak.

    # 4. Force-break Python reference cycles
    gc.collect()
    gc.collect()
