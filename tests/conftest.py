import pytest
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
