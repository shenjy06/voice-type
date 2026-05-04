import pytest
from voice_type.config import AppConfig


@pytest.fixture
def tmp_config_path(tmp_path, monkeypatch):
    """Redirect CONFIG_DIR/CONFIG_FILE to a temporary directory and return the config dir path."""
    import voice_type.config as config_mod
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
