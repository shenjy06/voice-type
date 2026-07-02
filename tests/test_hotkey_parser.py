"""Tests for voicetype.hotkey_parser."""

import pytest
from pynput import keyboard

from voicetype.hotkey_parser import (
    HotkeyBinding,
    SUPPORTED_HOTKEYS,
    binding_to_string,
    is_supported,
    key_to_string,
)


class TestHotkeyBinding:
    def test_right_alt_binding(self):
        binding = HotkeyBinding.from_string("right_alt")
        assert binding.kind == "right_alt"
        assert binding.key is None

    @pytest.mark.parametrize("name, expected_attr", [
        ("f1", "f1"),
        ("f12", "f12"),
        ("alt_r", "alt_r"),
        ("space", "space"),
    ])
    def test_named_key_binding(self, name, expected_attr):
        binding = HotkeyBinding.from_string(name)
        assert binding.kind == "key"
        assert binding.key == getattr(keyboard.Key, expected_attr)

    def test_character_key_binding(self):
        binding = HotkeyBinding.from_string("a")
        assert binding.kind == "key"
        assert binding.key == keyboard.KeyCode(char="a")

    def test_vk_key_binding(self):
        binding = HotkeyBinding.from_string("vk:65")
        assert binding.kind == "key"
        assert binding.key == keyboard.KeyCode(vk=65)

    def test_unknown_string_falls_back_to_right_alt(self):
        binding = HotkeyBinding.from_string("ctrl+shift+x")
        assert binding.kind == "right_alt"

    def test_empty_string_falls_back_to_right_alt(self):
        binding = HotkeyBinding.from_string("")
        assert binding.kind == "right_alt"

    def test_none_string_falls_back_to_right_alt(self):
        binding = HotkeyBinding.from_string(None)
        assert binding.kind == "right_alt"

    def test_case_insensitive(self):
        binding = HotkeyBinding.from_string("F9")
        assert binding.kind == "key"
        assert binding.key == keyboard.Key.f9


class TestBindingToString:
    def test_right_alt(self):
        assert binding_to_string(HotkeyBinding.right_alt()) == "right_alt"

    def test_named_key(self):
        binding = HotkeyBinding(kind="key", key=keyboard.Key.f9)
        assert binding_to_string(binding) == "f9"

    def test_character_key(self):
        binding = HotkeyBinding(kind="key", key=keyboard.KeyCode(char="a"))
        assert binding_to_string(binding) == "a"

    def test_vk_key(self):
        binding = HotkeyBinding(kind="key", key=keyboard.KeyCode(vk=65))
        assert binding_to_string(binding) == "vk:65"


class TestKeyToString:
    def test_right_alt_maps_to_special_value(self):
        assert key_to_string(keyboard.Key.alt_r) == "right_alt"
        assert key_to_string(keyboard.Key.alt_gr) == "right_alt"

    def test_named_key(self):
        assert key_to_string(keyboard.Key.f9) == "f9"

    def test_character_keycode(self):
        assert key_to_string(keyboard.KeyCode(char="a")) == "a"

    def test_vk_keycode(self):
        assert key_to_string(keyboard.KeyCode(vk=65)) == "vk:65"


class TestSupportedHotkeys:
    def test_supported_list_contains_defaults(self):
        assert "right_alt" in SUPPORTED_HOTKEYS

    def test_is_supported_right_alt(self):
        assert is_supported("right_alt") is True

    def test_is_supported_named_key(self):
        assert is_supported("f5") is True

    def test_is_supported_character(self):
        assert is_supported("a") is True

    def test_is_supported_vk(self):
        assert is_supported("vk:65") is True

    def test_is_supported_unknown(self):
        assert is_supported("ctrl+x combo") is False

    def test_is_supported_case_insensitive(self):
        assert is_supported("Right_Alt") is True
        assert is_supported("F2") is True
