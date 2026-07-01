"""Tests for voice_type.config — dataclasses, serialization, migration, persistence."""

import json
from voicetype.config import (
    AppConfig,
    AsrConfig,
    OutputConfig,
    PolishApiConfig,
    RecordingConfig,
    WindowConfig,
    HotkeyConfig,
    GlossaryEntry,
    DEFAULT_BASE_URL,
)


class TestDefaultConfigs:
    def test_polish_api_config_defaults(self):
        cfg = PolishApiConfig()
        assert cfg.base_url == "https://api.openai.com/v1"
        assert cfg.api_key == ""
        assert cfg.model == "gpt-4o"
        assert cfg.enabled is True

    def test_asr_config_defaults(self):
        cfg = AsrConfig()
        assert cfg.base_url == "https://api.openai.com/v1"
        assert cfg.api_key == ""
        assert cfg.model == "whisper-1"
        assert cfg.language == "auto"

    def test_recording_config_defaults(self):
        cfg = RecordingConfig()
        assert cfg.sample_rate == 16000

    def test_hotkey_config_defaults(self):
        cfg = HotkeyConfig()
        assert cfg.toggle_enabled is True
        assert cfg.toggle_hotkey == "right_shift"

    def test_output_config_defaults(self):
        cfg = OutputConfig()
        assert cfg.paste_delay_ms == 300
        assert cfg.auto_paste is True
        assert cfg.paste_mode == "auto"

    def test_glossary_entry_defaults(self):
        cfg = GlossaryEntry()
        assert cfg.source == ""
        assert cfg.replacement == ""

    def test_window_config_defaults(self):
        cfg = WindowConfig()
        assert cfg.show_on_start is True
        assert cfg.always_on_top is True


class TestAppConfigDefaults:
    def test_app_config_defaults(self):
        cfg = AppConfig()
        assert cfg.polish.base_url == "https://api.openai.com/v1"
        assert cfg.asr.model == "whisper-1"
        assert cfg.recording.sample_rate == 16000
        assert cfg.output.auto_paste is True
        assert cfg.window.show_on_start is True

    def test_api_property_returns_polish(self):
        cfg = AppConfig()
        assert cfg.api is cfg.polish

    def test_is_configured_returns_false_for_defaults(self):
        cfg = AppConfig()
        assert cfg.is_configured() is False

    def test_is_configured_returns_true_for_asr_key(self):
        cfg = AppConfig(asr=AsrConfig(api_key="sk-stt"))
        assert cfg.is_configured() is True

    def test_is_configured_returns_true_for_polish_key(self):
        cfg = AppConfig(polish=PolishApiConfig(api_key="sk-polish"))
        assert cfg.is_configured() is True

    def test_is_configured_returns_true_for_both_keys(self):
        cfg = AppConfig(
            asr=AsrConfig(api_key="sk-stt"),
            polish=PolishApiConfig(api_key="sk-polish"),
        )
        assert cfg.is_configured() is True


class TestAppConfigToDict:
    def test_to_dict_contains_all_sections(self):
        cfg = AppConfig()
        d = cfg.to_dict()
        assert "polish" in d
        assert "asr" in d
        assert "recording" in d
        assert "output" in d
        assert "glossary" in d
        assert "window" in d

    def test_to_dict_round_trip(self):
        cfg = AppConfig(
            polish=PolishApiConfig(api_key="sk-test", model="gpt-4o-mini"),
            asr=AsrConfig(model="whisper-1", language="zh"),
            recording=RecordingConfig(sample_rate=48000),
            output=OutputConfig(paste_delay_ms=500, auto_paste=False),
            glossary=[GlossaryEntry(source="派森", replacement="Python")],
            window=WindowConfig(show_on_start=False),
        )
        restored = AppConfig.from_dict(cfg.to_dict())
        assert restored.polish.api_key == "sk-test"
        assert restored.polish.model == "gpt-4o-mini"
        assert restored.polish.enabled is True
        assert restored.asr.language == "zh"
        assert restored.recording.sample_rate == 48000
        assert restored.output.paste_delay_ms == 500
        assert restored.output.auto_paste is False
        assert restored.output.paste_mode == "auto"
        assert restored.glossary[0].source == "派森"
        assert restored.glossary[0].replacement == "Python"
        assert restored.window.show_on_start is False


class TestAppConfigFromDict:
    def test_from_dict_full_config(self):
        data = {
            "polish": {"base_url": "https://example.com", "api_key": "sk-1", "model": "gpt-4", "enabled": False},
            "asr": {"base_url": "https://asr.com", "api_key": "sk-2", "model": "whisper", "language": "en"},
            "recording": {"sample_rate": 44100},
            "output": {"paste_delay_ms": 100, "auto_paste": False, "paste_mode": "ctrl_shift_v"},
            "glossary": [{"source": "派森", "replacement": "Python"}],
            "window": {"show_on_start": False, "always_on_top": False},
            "hotkey": {"toggle_enabled": False},
        }
        cfg = AppConfig.from_dict(data)
        assert cfg.polish.base_url == "https://example.com"
        assert cfg.polish.enabled is False
        assert cfg.asr.language == "en"
        assert cfg.recording.sample_rate == 44100
        assert cfg.output.auto_paste is False
        assert cfg.output.paste_mode == "ctrl_shift_v"
        assert cfg.glossary == [GlossaryEntry(source="派森", replacement="Python")]
        assert cfg.window.show_on_start is False
        assert cfg.hotkey.toggle_enabled is False

    def test_from_dict_empty_sections_use_defaults(self):
        data = {}
        cfg = AppConfig.from_dict(data)
        # All defaults should be applied
        assert cfg.polish.model == "gpt-4o"
        assert cfg.asr.model == "whisper-1"
        assert cfg.recording.sample_rate == 16000

    def test_from_dict_partial_config(self):
        data = {"asr": {"model": "custom-asr", "language": "ja"}}
        cfg = AppConfig.from_dict(data)
        assert cfg.asr.model == "custom-asr"
        assert cfg.asr.language == "ja"
        # Polish uses defaults since not specified
        assert cfg.polish.model == "gpt-4o"

    def test_from_dict_ignores_invalid_glossary_items(self):
        data = {
            "glossary": [
                {"source": "派森", "replacement": "Python"},
                "invalid",
            ]
        }
        cfg = AppConfig.from_dict(data)
        assert cfg.glossary == [GlossaryEntry(source="派森", replacement="Python")]

    def test_from_dict_ignores_legacy_hotkey_fields(self):
        """Old start/stop/cancel hotkey fields in recording section are ignored."""
        data = {
            "recording": {
                "sample_rate": 16000,
                "start_hotkey_modifiers": ["ctrl"],
                "start_hotkey_key": "q",
                "stop_hotkey_modifiers": ["alt"],
                "stop_hotkey_key": "e",
            },
        }
        cfg = AppConfig.from_dict(data)
        # Only sample_rate should be read; hotkey uses defaults
        assert cfg.recording.sample_rate == 16000
        assert cfg.hotkey.toggle_enabled is True  # default

    def test_from_dict_hotkey_config(self):
        """Hotkey config is read from the 'hotkey' section."""
        data = {
            "recording": {},
            "polish": {},
            "asr": {},
            "output": {},
            "window": {},
            "hotkey": {"toggle_enabled": False, "toggle_hotkey": "left_alt"},
        }
        cfg = AppConfig.from_dict(data)
        assert cfg.hotkey.toggle_enabled is False
        assert cfg.hotkey.toggle_hotkey == "left_alt"

    def test_from_dict_api_key_backcompat(self):
        """Config with 'api' key (instead of 'polish') maps to PolishApiConfig."""
        data = {
            "api": {"base_url": "https://old.api", "api_key": "old-key", "model": "gpt-3.5"},
            "asr": {},
            "recording": {},
            "output": {},
            "window": {},
        }
        cfg = AppConfig.from_dict(data)
        assert cfg.polish.base_url == "https://old.api"
        assert cfg.polish.api_key == "old-key"
        assert cfg.polish.model == "gpt-3.5"

    def test_from_dict_polish_takes_precedence_over_api(self):
        """When both 'polish' and 'api' exist, 'polish' is used."""
        data = {
            "polish": {"base_url": "https://polish.api", "api_key": "pk", "model": "gpt-4"},
            "api": {"base_url": "https://old.api", "api_key": "old-key", "model": "gpt-3.5"},
            "asr": {},
            "recording": {},
            "output": {},
            "window": {},
        }
        cfg = AppConfig.from_dict(data)
        assert cfg.polish.base_url == "https://polish.api"

    def test_from_dict_ignores_unknown_keys(self):
        """Unknown keys (e.g. from a newer version's config) don't crash load."""
        data = {
            "polish": {
                "base_url": "https://api", "api_key": "pk", "model": "gpt-4",
                "future_setting": True, "temperature": 0.1,
            },
            "asr": {"api_key": "sk", "base_url": "https://api", "model": "whisper-1",
                    "language": "auto", "deprecated_field": "x"},
            "output": {"auto_paste": False, "paste_mode": "auto",
                       "paste_delay_ms": 300, "unknown_output_key": 1},
            "window": {"show_on_start": True, "always_on_top": True,
                       "auto_start": False, "ghost_field": None},
            "hotkey": {"toggle_enabled": True, "toggle_hotkey": "right_shift",
                       "old_combo": "ctrl+space"},
            "recording": {"sample_rate": 16000, "legacy_format": "wav"},
            "language": "auto",
            "top_level_future_key": {"nested": True},
        }
        cfg = AppConfig.from_dict(data)
        assert cfg.polish.api_key == "pk"
        assert cfg.polish.model == "gpt-4"
        assert cfg.asr.language == "auto"
        assert cfg.output.auto_paste is False
        assert cfg.window.show_on_start is True
        assert cfg.hotkey.toggle_hotkey == "right_shift"


class TestAppConfigLoadSave:
    def test_save_creates_directory_and_writes_json(self, tmp_config_path):
        cfg = AppConfig()
        cfg.save()
        assert tmp_config_path.exists()
        config_file = tmp_config_path / "config.json"
        assert config_file.exists()
        with open(config_file, encoding="utf-8") as f:
            data = json.load(f)
        assert "polish" in data

    def test_load_reads_existing_file(self, tmp_config_path):
        config_file = tmp_config_path / "config.json"
        config_file.parent.mkdir(parents=True)
        config_file.write_text(
            '{"asr": {"model": "custom-model"}, "polish": {}, "recording": {}, "output": {}, "window": {}}',
            encoding="utf-8",
        )
        cfg = AppConfig.load()
        assert cfg.asr.model == "custom-model"

    def test_load_returns_defaults_when_file_missing(self, tmp_config_path, monkeypatch):
        import voicetype.config as config_mod
        # Point to a non-existent file
        monkeypatch.setattr(config_mod, "CONFIG_FILE", tmp_config_path / "nonexistent" / "config.json")
        cfg = AppConfig.load()
        assert cfg.asr.model == "whisper-1"

    def test_save_and_load_round_trip(self, tmp_config_path):
        cfg = AppConfig(polish=PolishApiConfig(api_key="round-trip"))
        cfg.save()
        loaded = AppConfig.load()
        assert loaded.polish.api_key == "round-trip"


class TestDefaultBaseUrl:
    def test_default_base_url_value(self):
        assert DEFAULT_BASE_URL == "https://api.openai.com/v1"
