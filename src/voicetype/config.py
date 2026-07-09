"""Configuration management — loads/saves user settings from JSON.

API keys are stored in plaintext in config.json (and in exported/profile
files unless a password is supplied). The `voicetype.crypto` module provides
portable password-based encryption (Fernet + PBKDF2) used by
``export_to``/``import_from`` for encrypted config files. The at-rest
DPAPI path documented in crypto.py is intentionally not wired into
to_dict/from_dict because the raw ctypes binding is unstable in some
environments.
"""

import copy
import json
import logging
import time
from dataclasses import dataclass, field, asdict, fields
from pathlib import Path

import voicetype.crypto as crypto

logger = logging.getLogger(__name__)

CONFIG_DIR = Path.home() / ".voice-type"
CONFIG_FILE = CONFIG_DIR / "config.json"
PROFILES_DIR = CONFIG_DIR / "profiles"
ACTIVE_PROFILE_FILE = CONFIG_DIR / "active_profile"

DEFAULT_BASE_URL = "https://api.openai.com/v1"


class EncryptedConfigError(Exception):
    """Raised when import_from meets an encrypted file but no password."""


class InvalidPasswordError(Exception):
    """Raised when import_from cannot decrypt a file with the given password."""


@dataclass
class PolishApiConfig:
    base_url: str = DEFAULT_BASE_URL
    api_key: str = ""
    model: str = "gpt-4o"
    enabled: bool = True
    style: str = "default"


@dataclass
class AsrConfig:
    base_url: str = DEFAULT_BASE_URL
    api_key: str = ""
    model: str = "whisper-1"
    language: str = "auto"
    # Streaming real-time ASR via WebSocket (OpenAI Realtime API protocol).
    # When enabled, the recorder streams PCM chunks to the streaming provider
    # and text appears live in the status bubble. Uses base_url as the
    # WebSocket endpoint.
    streaming_enabled: bool = False


@dataclass
class HotkeyConfig:
    toggle_enabled: bool = True
    toggle_hotkey: str = "right_alt"


@dataclass
class RecordingConfig:
    sample_rate: int = 16000
    # Audio preprocessing — spectral-gate noise reduction applied before
    # ASR. Off by default so existing users see no behaviour change until
    # they opt in via Settings → STT → Recording.
    denoise_enabled: bool = False
    denoise_strength: str = "medium"  # low | medium | high
    # Voice Activity Detection — auto-stop the recording after the user
    # stops speaking. Off by default for backward compatibility; opt in
    # via Settings → STT → Recording. Silence is only counted after the
    # first speech is detected, so the user can pause before talking
    # without triggering an early stop.
    vad_enabled: bool = False
    vad_silence_duration_ms: int = 1500
    # RMS level (0.0-1.0, same scale as input_level) below which audio
    # counts as silence. 0.02 matches the mic-test silent threshold.
    vad_threshold: float = 0.02


@dataclass
class OutputConfig:
    paste_delay_ms: int = 120
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
            recording=RecordingConfig(**_filtered(RecordingConfig, rec_data)),
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
            config = cls.from_dict(data)
            logger.info("Config loaded from %s", CONFIG_FILE)
            return config
        logger.info("No config file found — using defaults")
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
        new_dict = self.to_dict()
        # Skip serialization entirely if dict content unchanged.
        if getattr(AppConfig, "_last_saved_dict", None) == new_dict:
            logger.debug("Config unchanged — skipping save")
            return
        start = time.monotonic()
        new_json = json.dumps(new_dict, indent=2, ensure_ascii=False)
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, encoding="utf-8") as f:
                    existing = f.read()
                if existing == new_json:
                    AppConfig._last_saved_dict = new_dict
                    logger.debug("Config on disk matches — skipping write")
                    return  # no changes — skip write
            except (OSError, json.JSONDecodeError) as e:
                logger.warning("Could not read existing config: %s", e)
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        tmp_path = CONFIG_FILE.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(new_json)
        tmp_path.replace(CONFIG_FILE)
        AppConfig._last_saved_dict = new_dict
        elapsed = (time.monotonic() - start) * 1000
        logger.debug("Config saved in %.1f ms", elapsed)

    def export_to(self, path: Path, password: str | None = None) -> None:
        """Export this config to a JSON file at ``path``.

        Unlike :meth:`save`, this always writes (no change detection) and
        targets an arbitrary user-chosen location — for backup, migration,
        or sharing. The format is identical to ``config.json`` so an
        exported file can be re-imported on another machine.

        If ``password`` is provided, the file is encrypted with a portable
        (password-derived) envelope so API keys aren't stored in plaintext.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        if password:
            plaintext = json.dumps(self.to_dict(), ensure_ascii=False)
            envelope = crypto.encrypt_with_password(plaintext, password)
            content = json.dumps(envelope, ensure_ascii=False)
        else:
            content = json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
        # Atomic write (tmp + replace) so a mid-write failure can't leave a
        # half-written export behind, mirroring save().
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(content)
        tmp_path.replace(path)

    @classmethod
    def import_from(cls, path: Path, password: str | None = None) -> "AppConfig":
        """Load a config from a JSON file at ``path``.

        Raises ``OSError`` on read failure or ``json.JSONDecodeError`` on
        malformed JSON; the caller is expected to surface both as a single
        "invalid config file" message. ``from_dict`` handles the rest
        (unknown keys dropped, missing fields defaulted) so an exported
        file from an older or newer version still loads.

        If the file is password-encrypted, ``password`` must be supplied:
        raising :class:`EncryptedConfigError` when it's missing and
        :class:`InvalidPasswordError` when it doesn't decrypt. The caller
        typically catches the former, prompts for a password, and retries.
        """
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if crypto.is_encrypted_envelope(data):
            if password is None:
                raise EncryptedConfigError(str(path))
            plaintext = crypto.decrypt_with_password(data, password)
            if plaintext is None:
                raise InvalidPasswordError(str(path))
            data = json.loads(plaintext)
        return cls.from_dict(data)

    def is_default(self) -> bool:
        """Return True if this config is essentially a default/empty one.

        A config counts as default when no API keys have been set and no
        substantial settings differ from AppConfig() defaults. This is
        used by the import dialog to warn before overwriting current
        settings with an effectively blank configuration.
        """
        if self.is_configured():
            return False
        default = AppConfig()
        return (
            self.language == default.language
            and self.polish == default.polish
            and self.asr == default.asr
            and self.recording == default.recording
            and self.output == default.output
            and self.glossary == default.glossary
            and self.window == default.window
            and self.hotkey == default.hotkey
        )

    def summary(self) -> str:
        """Return a short human-readable summary suitable for a preview dialog.

        Omits API keys (security) and shows model names, enabled features,
        and glossary count.
        """
        parts = []
        # STT
        parts.append(f"STT: {self.asr.model} ({self.asr.language})"
                     + (" +streaming" if self.asr.streaming_enabled else ""))
        # Polish
        if self.polish.enabled:
            parts.append(f"Polish: {self.polish.model} [{self.polish.style}]")
        else:
            parts.append("Polish: disabled")
        # Recording extras
        extras = []
        if self.recording.denoise_enabled:
            extras.append(f"denoise({self.recording.denoise_strength})")
        if self.recording.vad_enabled:
            extras.append(f"VAD({self.recording.vad_silence_duration_ms}ms)")
        if extras:
            parts.append("Recording: " + ", ".join(extras))
        # Output
        parts.append(f"Output: paste={self.output.paste_mode}"
                     + (" auto" if self.output.auto_paste else ""))
        # Glossary
        if self.glossary:
            parts.append(f"Glossary: {len(self.glossary)} terms")
        # Window
        parts.append(f"Window: top={self.window.always_on_top}"
                     + f" startup={self.window.auto_start}")
        return "\n".join(parts)

    def update_from(self, other: "AppConfig") -> None:
        """Copy all fields from ``other`` in place, preserving object identity.

        Needed because external code (Application) holds a reference to the
        existing AppConfig instance; replacing ``self.config`` with a new
        object would break that link. Mirrors how ``_apply_save`` mutates
        fields rather than replacing the instance. Values are deep-copied so
        mutable sub-objects (the glossary list, sub-config dataclasses) are
        not shared between the two instances.
        """
        for f in fields(self):
            setattr(self, f.name, copy.deepcopy(getattr(other, f.name)))


# ---- named config profiles ------------------------------------------------
# Profiles are named snapshots stored separately from the active config.json.
# Switching a profile copies its content into the active config (see
# settings_dialog), so startup loading stays a single-file operation.


def _validate_profile_name(name: str) -> None:
    """Raise ``ValueError`` if ``name`` could escape the profiles directory.

    A profile name is used directly as a filename, so path separators and
    ``..`` are rejected to prevent traversal. Unicode, interior spaces, and
    punctuation are all allowed - the goal is only security, not style.
    """
    stripped = name.strip()
    if not stripped:
        raise ValueError("profile name is empty")
    if stripped in (".", ".."):
        raise ValueError(f"invalid profile name: {stripped!r}")
    if "\\" in stripped or "/" in stripped:
        raise ValueError(
            f"profile name must not contain path separators: {stripped!r}"
        )
    if stripped != name:
        raise ValueError("profile name must not have surrounding whitespace")


def list_profiles() -> list[str]:
    """Return sorted profile names available on disk (empty if none)."""
    if not PROFILES_DIR.exists():
        return []
    return sorted(p.stem for p in PROFILES_DIR.glob("*.json"))


def save_profile(name: str, config: "AppConfig") -> None:
    """Persist ``config`` as a named profile (plaintext JSON)."""
    _validate_profile_name(name)
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    config.export_to(PROFILES_DIR / f"{name}.json")


def load_profile(name: str) -> "AppConfig":
    """Load a named profile. Raises OSError/JSONDecodeError on failure."""
    _validate_profile_name(name)
    return AppConfig.import_from(PROFILES_DIR / f"{name}.json")


def delete_profile(name: str) -> None:
    """Delete a named profile file if it exists, clearing the active marker."""
    _validate_profile_name(name)
    (PROFILES_DIR / f"{name}.json").unlink(missing_ok=True)
    if get_active_profile() == name:
        set_active_profile(None)


def get_active_profile() -> str | None:
    """Return the active profile name, or None for the default config."""
    if ACTIVE_PROFILE_FILE.exists():
        name = ACTIVE_PROFILE_FILE.read_text(encoding="utf-8").strip()
        return name or None
    return None


def set_active_profile(name: str | None) -> None:
    """Record (or clear, when None) the active profile name."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if name is None:
        ACTIVE_PROFILE_FILE.unlink(missing_ok=True)
    else:
        ACTIVE_PROFILE_FILE.write_text(name, encoding="utf-8")
