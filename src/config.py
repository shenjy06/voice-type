"""Configuration management — loads/saves user settings from JSON."""

import json
from dataclasses import dataclass, field, asdict
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
        rec_data = data.get("recording", {})
        # Migrate old hotkey fields: if start_hotkey_modifiers exists in recording,
        # the user had hotkeys configured — preserve them by enabling the toggle
        if "start_hotkey_modifiers" in rec_data or "hotkey_modifiers" in rec_data:
            hotkey_data = {"toggle_enabled": True}
        else:
            hotkey_data = data.get("hotkey", {})
        glossary_entries = []
        for item in data.get("glossary", []):
            if isinstance(item, dict):
                glossary_entries.append(
                    GlossaryEntry(
                        source=str(item.get("source", "")),
                        replacement=str(item.get("replacement", "")),
                    )
                )
        return cls(
            language=data.get("language", "auto"),
            polish=PolishApiConfig(**data.get("polish", data.get("api", {}))),
            asr=AsrConfig(**data.get("asr", {})),
            recording=RecordingConfig(sample_rate=rec_data.get("sample_rate", 16000)),
            output=OutputConfig(**data.get("output", {})),
            glossary=glossary_entries,
            window=WindowConfig(**data.get("window", {})),
            hotkey=HotkeyConfig(**hotkey_data),
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
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
