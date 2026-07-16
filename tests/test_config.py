"""Tests for voice_type.config — dataclasses, serialization, migration, persistence."""

import json
from pathlib import Path

import pytest

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
    EncryptedConfigError,
    InvalidPasswordError,
    list_profiles,
    save_profile,
    load_profile,
    delete_profile,
    get_active_profile,
    set_active_profile,
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
        assert cfg.denoise_enabled is False
        assert cfg.denoise_strength == "medium"

    def test_hotkey_config_defaults(self):
        cfg = HotkeyConfig()
        assert cfg.toggle_enabled is True
        assert cfg.toggle_hotkey == "right_alt"

    def test_output_config_defaults(self):
        cfg = OutputConfig()
        assert cfg.paste_delay_ms == 120
        assert cfg.auto_paste is True
        assert cfg.paste_mode == "auto"
        assert cfg.continuous_mode is False

    def test_glossary_entry_defaults(self):
        cfg = GlossaryEntry()
        assert cfg.source == ""
        assert cfg.replacement == ""

    def test_window_config_defaults(self):
        cfg = WindowConfig()
        assert cfg.show_on_start is True
        assert cfg.always_on_top is True
        # Default theme is dark (preserves the pre-theme-switch look for
        # existing users; "light"/"system" are opt-in via Settings).
        assert cfg.theme_mode == "dark"

    def test_window_config_theme_mode_loads_from_dict(self):
        """theme_mode round-trips through from_dict (forward/backward compat)."""
        cfg = AppConfig.from_dict({"window": {"theme_mode": "light"}})
        assert cfg.window.theme_mode == "light"
        # An old config without theme_mode defaults to dark.
        cfg_old = AppConfig.from_dict({"window": {"always_on_top": False}})
        assert cfg_old.window.theme_mode == "dark"


class TestAppConfigDefaults:
    def test_app_config_defaults(self):
        cfg = AppConfig()
        assert cfg.polish.base_url == "https://api.openai.com/v1"
        assert cfg.asr.model == "whisper-1"
        assert cfg.recording.sample_rate == 16000
        assert cfg.recording.denoise_enabled is False
        assert cfg.output.auto_paste is True
        assert cfg.window.show_on_start is True

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

    def test_to_dict_round_trip_with_denoise(self):
        cfg = AppConfig(
            recording=RecordingConfig(
                sample_rate=48000,
                denoise_enabled=True,
                denoise_strength="high",
            ),
        )
        restored = AppConfig.from_dict(cfg.to_dict())
        assert restored.recording.sample_rate == 48000
        assert restored.recording.denoise_enabled is True
        assert restored.recording.denoise_strength == "high"


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

    def test_from_dict_loads_denoise_settings(self):
        """Denoise fields are read from the recording section."""
        data = {
            "recording": {
                "sample_rate": 44100,
                "denoise_enabled": True,
                "denoise_strength": "low",
            },
        }
        cfg = AppConfig.from_dict(data)
        assert cfg.recording.sample_rate == 44100
        assert cfg.recording.denoise_enabled is True
        assert cfg.recording.denoise_strength == "low"

    def test_from_dict_missing_denoise_uses_defaults(self):
        """Old configs without denoise fields get safe defaults."""
        data = {"recording": {"sample_rate": 16000}}
        cfg = AppConfig.from_dict(data)
        assert cfg.recording.denoise_enabled is False
        assert cfg.recording.denoise_strength == "medium"

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

    def test_from_dict_continuous_mode(self):
        """continuous_mode round-trips through from_dict."""
        cfg = AppConfig.from_dict({"output": {"continuous_mode": True}})
        assert cfg.output.continuous_mode is True

    def test_from_dict_missing_continuous_mode_uses_default(self):
        """Old configs without continuous_mode get the safe default (off)."""
        cfg = AppConfig.from_dict({"output": {"auto_paste": True}})
        assert cfg.output.continuous_mode is False


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


class TestExportImport:
    """export_to / import_from / update_from — config file portability."""

    def _sample_config(self) -> AppConfig:
        return AppConfig(
            language="zh",
            polish=PolishApiConfig(api_key="sk-polish", model="gpt-4o-mini", enabled=False),
            asr=AsrConfig(api_key="sk-asr", model="whisper-1", language="en"),
            recording=RecordingConfig(sample_rate=48000, denoise_enabled=True),
            output=OutputConfig(paste_delay_ms=300, auto_paste=False),
            glossary=[GlossaryEntry(source="派森", replacement="Python")],
            window=WindowConfig(show_on_start=False),
            hotkey=HotkeyConfig(toggle_enabled=False, toggle_hotkey="f9"),
        )

    def test_export_to_writes_valid_json(self, tmp_path):
        cfg = self._sample_config()
        out = tmp_path / "exported.json"
        cfg.export_to(out)
        assert out.exists()
        with open(out, encoding="utf-8") as f:
            data = json.load(f)
        assert data["polish"]["api_key"] == "sk-polish"
        assert data["asr"]["language"] == "en"
        assert data["glossary"] == [{"source": "派森", "replacement": "Python"}]

    def test_export_to_creates_parent_dirs(self, tmp_path):
        cfg = AppConfig()
        out = tmp_path / "nested" / "deep" / "config.json"
        cfg.export_to(out)
        assert out.exists()

    def test_import_from_round_trips_export_to(self, tmp_path):
        cfg = self._sample_config()
        out = tmp_path / "exported.json"
        cfg.export_to(out)
        loaded = AppConfig.import_from(out)
        assert loaded.language == "zh"
        assert loaded.polish.api_key == "sk-polish"
        assert loaded.polish.model == "gpt-4o-mini"
        assert loaded.polish.enabled is False
        assert loaded.asr.language == "en"
        assert loaded.recording.sample_rate == 48000
        assert loaded.recording.denoise_enabled is True
        assert loaded.output.auto_paste is False
        assert loaded.glossary == [GlossaryEntry(source="派森", replacement="Python")]
        assert loaded.window.show_on_start is False
        assert loaded.hotkey.toggle_hotkey == "f9"

    def test_import_from_accepts_legacy_config(self, tmp_path):
        """An exported file from an older version (no streaming field) loads."""
        out = tmp_path / "legacy.json"
        out.write_text(
            json.dumps({"asr": {"model": "whisper-1"}, "polish": {}}),
            encoding="utf-8",
        )
        cfg = AppConfig.import_from(out)
        assert cfg.asr.model == "whisper-1"

    def test_import_from_raises_on_malformed_json(self, tmp_path):
        out = tmp_path / "bad.json"
        out.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            AppConfig.import_from(out)

    def test_import_from_raises_on_missing_file(self, tmp_path):
        with pytest.raises(OSError):
            AppConfig.import_from(tmp_path / "nonexistent.json")

    def test_update_from_preserves_identity(self):
        """update_from mutates the existing object rather than replacing it."""
        original = AppConfig()
        target = original  # capture the reference
        other = self._sample_config()
        original.update_from(other)
        # Same object — external references still valid
        assert target is original
        # Fields copied
        assert original.language == "zh"
        assert original.polish.api_key == "sk-polish"
        assert original.recording.sample_rate == 48000
        assert original.hotkey.toggle_hotkey == "f9"

    def test_update_from_does_not_share_mutable_subobjects(self):
        """update_from copies field values; mutating source shouldn't leak back."""
        original = AppConfig()
        other = AppConfig(glossary=[GlossaryEntry(source="x", replacement="y")])
        original.update_from(other)
        # Mutate the source's glossary after the update
        other.glossary.append(GlossaryEntry(source="z", replacement="w"))
        assert len(original.glossary) == 1  # no aliasing


class TestIsDefault:
    """AppConfig.is_default() — used to warn before importing an empty config."""

    def test_default_config_is_default(self):
        assert AppConfig().is_default()

    def test_with_asr_key_is_not_default(self):
        cfg = AppConfig(asr=AsrConfig(api_key="sk-test"))
        assert not cfg.is_default()

    def test_with_polish_key_is_not_default(self):
        cfg = AppConfig(polish=PolishApiConfig(api_key="sk-test"))
        assert not cfg.is_default()

    def test_with_changed_model_is_not_default(self):
        cfg = AppConfig(asr=AsrConfig(model="custom-model"))
        assert not cfg.is_default()

    def test_with_glossary_is_not_default(self):
        cfg = AppConfig(glossary=[GlossaryEntry(source="x", replacement="y")])
        assert not cfg.is_default()

    def test_with_denoise_enabled_is_not_default(self):
        cfg = AppConfig(recording=RecordingConfig(denoise_enabled=True))
        assert not cfg.is_default()


class TestSummary:
    """AppConfig.summary() — generates a human-readable preview for the import dialog."""

    def test_summary_default_config(self):
        s = AppConfig().summary()
        assert "STT:" in s
        assert "Polish:" in s
        assert "Output:" in s
        assert "Window:" in s
        # No glossary line for empty glossary
        assert "Glossary:" not in s

    def test_summary_with_glossary(self):
        cfg = AppConfig(glossary=[GlossaryEntry(source="x", replacement="y")])
        s = cfg.summary()
        assert "Glossary: 1 terms" in s

    def test_summary_with_streaming(self):
        cfg = AppConfig(asr=AsrConfig(streaming_enabled=True))
        s = cfg.summary()
        assert "+streaming" in s

    def test_summary_with_vad_and_denoise(self):
        cfg = AppConfig(
            recording=RecordingConfig(denoise_enabled=True, denoise_strength="high",
                                      vad_enabled=True, vad_silence_duration_ms=2000),
        )
        s = cfg.summary()
        assert "denoise(high)" in s
        assert "VAD(2000ms)" in s

    def test_summary_disabled_polish(self):
        cfg = AppConfig(polish=PolishApiConfig(enabled=False))
        s = cfg.summary()
        assert "disabled" in s

    def test_summary_does_not_leak_api_keys(self):
        cfg = AppConfig(
            asr=AsrConfig(api_key="sk-secret"),
            polish=PolishApiConfig(api_key="sk-secret2"),
        )
        s = cfg.summary()
        assert "sk-secret" not in s
        assert "sk-secret2" not in s


class TestEncryptedExportImport:
    """Password-encrypted config export/import round-trips."""

    def test_encrypted_export_import_round_trip(self, tmp_path):
        cfg = AppConfig(asr=AsrConfig(api_key="sk-enc", model="whisper-1"))
        out = tmp_path / "enc.json"
        cfg.export_to(out, password="s3cret")
        # The on-disk file must not contain the plaintext key.
        raw = out.read_text(encoding="utf-8")
        assert "sk-enc" not in raw
        # Wrong password fails.
        with pytest.raises(InvalidPasswordError):
            AppConfig.import_from(out, password="wrong")
        # Correct password round-trips.
        loaded = AppConfig.import_from(out, password="s3cret")
        assert loaded.asr.api_key == "sk-enc"

    def test_encrypted_import_without_password_raises(self, tmp_path):
        cfg = AppConfig(asr=AsrConfig(api_key="sk-enc"))
        out = tmp_path / "enc.json"
        cfg.export_to(out, password="s3cret")
        with pytest.raises(EncryptedConfigError):
            AppConfig.import_from(out)

    def test_plaintext_export_still_works(self, tmp_path):
        cfg = AppConfig(asr=AsrConfig(api_key="sk-plain"))
        out = tmp_path / "plain.json"
        cfg.export_to(out)  # no password -> plaintext
        loaded = AppConfig.import_from(out)
        assert loaded.asr.api_key == "sk-plain"


class TestProfiles:
    """Named config profiles — save/list/load/delete + active tracking."""

    def _sample(self) -> AppConfig:
        return AppConfig(
            language="zh",
            asr=AsrConfig(api_key="sk-p", model="whisper-1", language="en"),
            polish=PolishApiConfig(enabled=False),
        )

    def test_save_and_list_profiles(self):
        save_profile("work", self._sample())
        save_profile("personal", AppConfig())
        assert list_profiles() == ["personal", "work"]

    def test_load_profile_round_trip(self):
        save_profile("work", self._sample())
        loaded = load_profile("work")
        assert loaded.language == "zh"
        assert loaded.asr.api_key == "sk-p"
        assert loaded.polish.enabled is False

    def test_delete_profile(self):
        save_profile("work", self._sample())
        delete_profile("work")
        assert list_profiles() == []

    def test_active_profile_get_set(self):
        assert get_active_profile() is None
        set_active_profile("work")
        assert get_active_profile() == "work"
        set_active_profile(None)
        assert get_active_profile() is None

    def test_active_profile_cleared_on_delete(self):
        save_profile("work", self._sample())
        set_active_profile("work")
        delete_profile("work")
        # Deleting the active profile clears the active marker.
        assert get_active_profile() != "work"

    def test_profile_file_is_plaintext(self, tmp_path):
        save_profile("work", self._sample())
        from voicetype import config as config_mod
        raw = (config_mod.PROFILES_DIR / "work.json").read_text(encoding="utf-8")
        assert "sk-p" in raw

class TestProfileNameValidation:
    """Profile names must not allow path traversal."""

    @pytest.mark.parametrize("bad", ["", "..", ".", "a/b", "a\\b", " work ", "../config"])
    def test_invalid_names_rejected(self, bad):
        with pytest.raises(ValueError):
            save_profile(bad, AppConfig())

    @pytest.mark.parametrize("good", ["work", "个人", "work 2", "a.b", "profile_1"])
    def test_valid_names_accepted(self, good):
        save_profile(good, AppConfig())
        assert good in list_profiles()
