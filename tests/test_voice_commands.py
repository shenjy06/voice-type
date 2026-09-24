"""Tests for voice-command matching."""

from voicetype.config import VoiceCommandEntry
from voicetype.voice_commands import match_voice_command


class TestMatchVoiceCommand:
    def _items(self):
        return [
            VoiceCommandEntry(phrase="换行", action="newline"),
            VoiceCommandEntry(phrase="new line", action="newline"),
            VoiceCommandEntry(phrase="回车", action="enter"),
            VoiceCommandEntry(phrase="enter", action="enter"),
            VoiceCommandEntry(phrase="撤销", action="undo"),
            VoiceCommandEntry(phrase="undo", action="undo"),
            VoiceCommandEntry(phrase="取消", action="discard"),
            VoiceCommandEntry(phrase="cancel", action="discard"),
        ]

    def test_exact_match(self):
        assert match_voice_command("换行", self._items()) == "newline"
        assert match_voice_command("取消", self._items()) == "discard"

    def test_punctuation_and_whitespace_tolerant(self):
        assert match_voice_command("换行。", self._items()) == "newline"
        assert match_voice_command("  new line! ", self._items()) == "newline"

    def test_case_insensitive_for_latin(self):
        assert match_voice_command("CANCEL", self._items()) == "discard"
        assert match_voice_command("Undo", self._items()) == "undo"

    def test_no_partial_or_longer_match(self):
        assert match_voice_command("换一行", self._items()) is None
        assert match_voice_command("请换行", self._items()) is None
        assert match_voice_command("hello world", self._items()) is None

    def test_blank_input_or_items(self):
        assert match_voice_command("", self._items()) is None
        assert match_voice_command("   ", self._items()) is None
        assert match_voice_command("取消", []) is None

    def test_skips_dirty_entries(self):
        items = [
            VoiceCommandEntry(phrase="", action="newline"),
            VoiceCommandEntry(phrase="撤销", action=""),
            VoiceCommandEntry(phrase="撤销", action="undo"),
        ]
        assert match_voice_command("撤销", items) == "undo"

    def test_unknown_action_rejected(self):
        items = [VoiceCommandEntry(phrase="爆炸", action="explode")]
        assert match_voice_command("爆炸", items) is None
