"""Parse configurable hotkey strings into pynput key bindings."""

from dataclasses import dataclass
from typing import Literal

from pynput import keyboard


@dataclass(frozen=True)
class HotkeyBinding:
    """A normalized hotkey binding.

    ``kind="right_alt"`` preserves the original tap-to-toggle / Right Alt+C
    cancel behavior. ``kind="key"`` means a single physical key press toggles
    recording.
    """

    kind: Literal["right_alt", "key"]
    key: keyboard.Key | keyboard.KeyCode | None = None

    @classmethod
    def right_alt(cls) -> "HotkeyBinding":
        return cls(kind="right_alt")

    @classmethod
    def from_string(cls, hotkey: str) -> "HotkeyBinding":
        """Parse a hotkey string, falling back to Right Alt on unknown input."""
        normalized = (hotkey or "").strip().lower()
        if normalized == "right_alt":
            return cls.right_alt()

        # Virtual-key representation, e.g. "vk:65"
        if normalized.startswith("vk:"):
            vk_part = normalized[3:]
            if vk_part.isdigit():
                return cls(kind="key", key=keyboard.KeyCode(vk=int(vk_part)))

        # Named Key enum values (f1..f12, alt_r, ctrl, etc.)
        key = getattr(keyboard.Key, normalized, None)
        if key is not None:
            return cls(kind="key", key=key)

        # Single character, e.g. "a", "1", " "
        if len(normalized) == 1:
            return cls(kind="key", key=keyboard.KeyCode(char=normalized))

        return cls.right_alt()


def binding_to_string(binding: HotkeyBinding) -> str:
    """Serialize a binding back to a config-friendly string."""
    if binding.kind == "right_alt":
        return "right_alt"

    key = binding.key
    if key is None:
        return "right_alt"

    if isinstance(key, keyboard.Key):
        return key.name

    if isinstance(key, keyboard.KeyCode):
        if key.char is not None:
            return key.char
        if key.vk is not None:
            return f"vk:{key.vk}"

    return "right_alt"


def key_to_string(key) -> str:
    """Serialize a captured pynput key to a config-friendly string.

    Right Alt and AltGr are mapped to the special ``right_alt`` value so the
    application keeps the original tap-vs-combo cancel behavior.
    """
    if key in (keyboard.Key.alt_r, keyboard.Key.alt_gr):
        return "right_alt"

    if isinstance(key, keyboard.Key):
        return key.name

    if isinstance(key, keyboard.KeyCode):
        if key.char is not None:
            return key.char
        if key.vk is not None:
            return f"vk:{key.vk}"

    return "right_alt"


SUPPORTED_HOTKEYS: list[str] = ["right_alt"]


def is_supported(hotkey: str) -> bool:
    """Return whether *hotkey* can be parsed into a usable binding."""
    binding = HotkeyBinding.from_string(hotkey)
    return binding.kind != "right_alt" or hotkey.strip().lower() == "right_alt"
