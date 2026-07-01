"""Configuration management — loads/saves user settings from JSON.

The `voicetype.crypto` module is available for at-rest encryption of API keys
but is intentionally NOT wired into to_dict/from_dict here because the
raw ctypes DPAPI binding is unstable in some environments. To enable
encryption, plug crypto.encrypt/decrypt into to_dict/from_dict and run
integration tests in your target environment first.
"""

import json
from dataclasses import dataclass, field, asdict, fields
from pathlib import Path

CONFIG_DIR = Path.home() / ".voice-type"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_BASE_URL = "https://api.openai.com/v1"


@dataclass
class PolishApiConfig:
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "gpt-4o"
    enabled: bool = True
    style: str = "default"


@dataclass
class AsrConfig:
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "whisper-1"
    language: str = "auto"


@dataclass
class HotkeyConfig:
    toggle_enabled: bool = True
    toggle_hotkey: str = "right_shift"


@dataclass
class RecordingConfig:
    sample_rate: int = 16000


@dataclass
class OutputConfig:
    paste_delay_ms: int = 300
    auto_paste: bool = True
    paste_mode: str = "auto"


@dataclass
class GlossaryEntry:
    source: str = ""
    replacement: str = ""


@dataclass
class WindowConfig:
    show_on_start: bool = True
    always_on_top: bool = True
    auto_start: bool = False


@dataclass
class AppConfig:
    language: str = "auto"
    polish: PolishApiConfig = field(default_factory=PolishApiConfig)
    asr: AsrConfig = field(default_factory=AsrConfig)
    recording: RecordingConfig = field(default_factory=RecordingConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    glossary: list[GlossaryEntry] = field(default_factory=list)
    window: WindowConfig = field(default_factory=WindowConfig)
    hotkey: HotkeyConfig = field(default_factory=HotkeyConfig)

    # Back-compat alias
    @property
    def api(self):
        return self.polish

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AppConfig":
        # Safely extract section dicts, defaulting to empty dict if not a dict
        def _safe_dict(value, default=None):
            if value is None:
                return default or {}
            if isinstance(value, dict):
                return value
            return default or {}

        def _filtered(dataclass_cls, section: dict) -> dict:
            """Keep only keys that are known fields of ``dataclass_cls``.

            This makes config loading forward/backward-compatible: a config
            file written by a newer (or older) version with extra keys won't
            crash ``__init__`` with an unexpected-keyword TypeError.
            """
            known = {f.name for f in fields(dataclass_cls)}
            return {k: v for k, v in section.items() if k in known}

        rec_data = _safe_dict(data.get("recording"))
        # Migrate old hotkey fields: if start_hotkey_modifiers exists in recording,
        # the user had hotkeys configured — preserve them by enabling the toggle
        if "start_hotkey_modifiers" in rec_data or "hotkey_modifiers" in rec_data:
            hotkey_data = {"toggle_enabled": True}
        else:
            hotkey_data = _safe_dict(data.get("hotkey"))
        glossary_entries = []
        for item in data.get("glossary", []):
            if isinstance(item, dict):
                glossary_entries.append(
                    GlossaryEntry(
                        source=str(item.get("source", "")),
                        replacement=str(item.get("replacement", "")),
                    )
                )

        # For polish, fall back to legacy "api" section if "polish" is missing
        polish_data = _safe_dict(data.get("polish", data.get("api")))

        return cls(
            language=data.get("language", "auto"),
            polish=PolishApiConfig(**_filtered(PolishApiConfig, polish_data)),
            asr=AsrConfig(**_filtered(AsrConfig, _safe_dict(data.get("asr")))),
            recording=RecordingConfig(sample_rate=rec_data.get("sample_rate", 16000)),
            output=OutputConfig(**_filtered(OutputConfig, _safe_dict(data.get("output")))),
            glossary=glossary_entries,
            window=WindowConfig(**_filtered(WindowConfig, _safe_dict(data.get("window")))),
            hotkey=HotkeyConfig(**_filtered(HotkeyConfig, hotkey_data)),
        )

    @classmethod
    def load(cls) -> "AppConfig":
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, encoding="utf-8") as f:
                data = json.load(f)
            return cls.from_dict(data)
        return cls()

    def is_configured(self) -> bool:
        """Return True if at least one API key has been set."""
        return bool(self.asr.api_key or self.polish.api_key)

    def save(self) -> None:
        """Save config to disk, but only if content has changed.

        This prevents accidental overwrites where a default AppConfig is
        serialised on top of a user's custom configuration (e.g. when the
        app starts with defaults and a code path triggers save() before
        the real config is loaded).
        """
        new_json = json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, encoding="utf-8") as f:
                    existing = f.read()
                if existing == new_json:
                    return  # no changes — skip write
            except (OSError, json.JSONDecodeError):
                pass  # file unreadable or corrupt — proceed with write
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        tmp_path = CONFIG_FILE.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(new_json)
        tmp_path.replace(CONFIG_FILE)
