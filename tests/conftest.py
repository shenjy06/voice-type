import pytest


@pytest.fixture
def tmp_config_path(tmp_path, monkeypatch):
    """Redirect CONFIG_DIR/CONFIG_FILE to a temporary directory and return the config dir path."""
    import voice_type.config as config_mod
    config_dir = tmp_path / ".voice-type"
    monkeypatch.setattr(config_mod, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config_mod, "CONFIG_FILE", config_dir / "config.json")
    return config_dir
