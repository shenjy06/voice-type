"""Tests for scene-preset process matching."""

from voicetype.config import SceneRule
from voicetype.scenes import match_scene_profile


class TestMatchSceneProfile:
    def _rules(self):
        return [
            SceneRule(match="Code.exe", profile="coding"),
            SceneRule(match="wechat", profile="chat"),
            SceneRule(match="", profile="blank"),
            SceneRule(match="notepad", profile=""),
        ]

    def test_substring_match_case_insensitive(self):
        assert match_scene_profile("Windows_Terminal.exe", [
            SceneRule(match="terminal", profile="term")
        ]) == "term"

    def test_first_match_wins(self):
        assert match_scene_profile("code.exe", self._rules()) == "coding"

    def test_no_match_returns_none(self):
        assert match_scene_profile("chrome.exe", self._rules()) is None

    def test_blank_process_name(self):
        assert match_scene_profile("", self._rules()) is None

    def test_dirty_rules_skipped(self):
        rules = [
            SceneRule(match="", profile="coding"),
            SceneRule(match="code", profile=""),
            SceneRule(match="code", profile="ok"),
        ]
        assert match_scene_profile("code.exe", rules) == "ok"
