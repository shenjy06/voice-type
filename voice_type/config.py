"""Configuration management — loads/saves user settings from JSON."""

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

CONFIG_DIR = Path.home() / ".voice-type"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULTS = {
    "api": {
        "base_url": "https://api.openai.com/v1",
        "api_key": "",
        "model": "gpt-4o",
    },
    "asr": {
        "base_url": "https://api.openai.com/v1",
        "api_key": "",
        "model": "whisper-1",
        "language": "auto",
    },
    "polish": {
        "base_url": "https://api.openai.com/v1",
        "api_key": "",
        "model": "gpt-4o",
    },
    "recording": {
        "sample_rate": 16000,
        "start_hotkey_modifiers": ["alt"],
        "start_hotkey_key": "s",
        "stop_hotkey_modifiers": ["alt"],
        "stop_hotkey_key": "e",
    },
    "output": {
        "paste_delay_ms": 300,
        "auto_paste": True,
    },
    "window": {
        "show_on_start": True,
        "always_on_top": True,
    },
}


@dataclass
class PolishApiConfig:
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "gpt-4o"


@dataclass
class AsrConfig:
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "whisper-1"
    language: str = "auto"


@dataclass
class RecordingConfig:
    sample_rate: int = 16000
    start_hotkey_modifiers: list = field(default_factory=lambda: ["alt"])
    start_hotkey_key: str = "s"
    stop_hotkey_modifiers: list = field(default_factory=lambda: ["alt"])
    stop_hotkey_key: str = "e"
    cancel_hotkey_modifiers: list = field(default_factory=lambda: ["alt"])
    cancel_hotkey_key: str = "c"


@dataclass
class OutputConfig:
    paste_delay_ms: int = 300
    auto_paste: bool = True


@dataclass
class WindowConfig:
    show_on_start: bool = True
    always_on_top: bool = True


@dataclass
class AppConfig:
    polish: PolishApiConfig = field(default_factory=PolishApiConfig)
    asr: AsrConfig = field(default_factory=AsrConfig)
    recording: RecordingConfig = field(default_factory=RecordingConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    window: WindowConfig = field(default_factory=WindowConfig)

    # Back-compat alias
    @property
    def api(self):
        return self.polish

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AppConfig":
        rec_data = data.get("recording", {})
        # Migrate old hotkey fields to new start/stop/cancel format
        if "hotkey_modifiers" in rec_data and "hotkey_key" in rec_data:
            rec_data.setdefault("start_hotkey_modifiers", rec_data.pop("hotkey_modifiers"))
            rec_data.setdefault("start_hotkey_key", rec_data.pop("hotkey_key"))
            rec_data.setdefault("stop_hotkey_modifiers", ["alt"])
            rec_data.setdefault("stop_hotkey_key", "e")
            rec_data.setdefault("cancel_hotkey_modifiers", ["alt"])
            rec_data.setdefault("cancel_hotkey_key", "c")
        # Ensure cancel hotkey exists for configs saved before cancel was added
        rec_data.setdefault("cancel_hotkey_modifiers", ["alt"])
        rec_data.setdefault("cancel_hotkey_key", "c")
        return cls(
            polish=PolishApiConfig(**data.get("polish", data.get("api", {}))),
            asr=AsrConfig(**data.get("asr", {})),
            recording=RecordingConfig(**rec_data),
            output=OutputConfig(**data.get("output", {})),
            window=WindowConfig(**data.get("window", {})),
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


def get_default_config() -> dict:
    return DEFAULTS
