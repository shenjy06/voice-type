"""Tests for voicetype.ui.hotkey_recorder."""

from PySide6.QtWidgets import QApplication
from pynput import keyboard
from voicetype.ui.hotkey_recorder import HotkeyRecorder


class TestHotkeyRecorder:
    def test_default_hotkey_is_right_alt(self, qtbot):
        rec = HotkeyRecorder()
        qtbot.addWidget(rec)
        assert rec.hotkey() == "right_alt"

    def test_set_hotkey_updates_display(self, qtbot):
        rec = HotkeyRecorder()
        qtbot.addWidget(rec)
        rec.set_hotkey("f9")
        assert rec.hotkey() == "f9"
        assert "F9" in rec._display.text()

    def test_captured_key_emits_hotkey(self, qtbot):
        rec = HotkeyRecorder()
        qtbot.addWidget(rec)
        with qtbot.waitSignal(rec.hotkey_captured, timeout=1000) as blocker:
            rec._on_capture_press(keyboard.Key.f9)
        QApplication.processEvents()
        assert blocker.args == ["f9"]
        assert rec.hotkey() == "f9"
        assert rec.is_recording() is False

    def test_escape_aborts_recording(self, qtbot):
        rec = HotkeyRecorder()
        qtbot.addWidget(rec)
        rec.set_hotkey("f5")
        with qtbot.waitSignal(rec.hotkey_captured, timeout=1000) as blocker:
            rec._on_capture_press(keyboard.Key.esc)
        assert blocker.args == ["f5"]
        assert rec.hotkey() == "f5"
        assert rec.is_recording() is False

    def test_right_alt_captured_as_special_value(self, qtbot):
        rec = HotkeyRecorder()
        qtbot.addWidget(rec)
        with qtbot.waitSignal(rec.hotkey_captured, timeout=1000) as blocker:
            rec._on_capture_press(keyboard.Key.alt_r)
        assert blocker.args == ["right_alt"]

    def test_stop_recording_while_listening(self, qtbot):
        rec = HotkeyRecorder()
        qtbot.addWidget(rec)
        rec._start_recording()
        rec.stop_recording()
        assert rec.is_recording() is False
