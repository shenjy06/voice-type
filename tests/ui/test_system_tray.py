"""Tests for voice_type.ui.system_tray — TrayIcon and HotkeyManager."""

from PySide6.QtWidgets import QSystemTrayIcon
from pynput import keyboard
from voicetype.ui.system_tray import TrayIcon, HotkeyManager


class TestTrayIcon:
    def test_init_creates_tray(self, qtbot):
        tray = TrayIcon()
        assert tray._tray is not None

    def test_init_creates_menu_actions(self, qtbot):
        tray = TrayIcon()
        ctx = tray._tray.contextMenu()
        actions = ctx.actions()
        assert len(actions) >= 10
        assert tray.auto_paste_action.text() == "Auto-paste"
        assert tray.polish_action.text() == "Polish text"

    def test_on_activated_double_click_emits(self, qtbot):
        tray = TrayIcon()
        with qtbot.waitSignal(tray.show_window_requested):
            tray._on_activated(QSystemTrayIcon.DoubleClick)

    def test_on_activated_other_reason_no_signal(self, qtbot):
        tray = TrayIcon()
        called = []
        tray.show_window_requested.connect(lambda: called.append(True))
        tray._on_activated(QSystemTrayIcon.Trigger)
        assert called == []

    def test_show_calls_tray_show(self, qtbot, mocker):
        tray = TrayIcon()
        mock_show = mocker.patch.object(tray._tray, "show")
        tray.show()
        mock_show.assert_called_once()

    def test_set_recording_true_changes_to_stop(self, qtbot):
        tray = TrayIcon()
        tray.set_recording(True)
        assert tray.record_action.text() == "Stop Recording"
        assert tray._tray.toolTip() == "Voice Type — Recording..."
        assert tray._is_recording is True

    def test_set_recording_false_changes_to_start(self, qtbot):
        tray = TrayIcon()
        tray.set_recording(True)
        tray.set_recording(False)
        assert tray.record_action.text() == "Start Recording"
        assert tray._tray.toolTip() == "Voice Type"
        assert tray._is_recording is False

    def test_show_message(self, qtbot, mocker):
        tray = TrayIcon()
        mock_msg = mocker.patch.object(tray._tray, "showMessage")
        tray.show_message("Test", "Hello")
        mock_msg.assert_called_once_with("Test", "Hello", QSystemTrayIcon.Information, 3000)

    def test_hide_calls_tray_hide(self, qtbot, mocker):
        tray = TrayIcon()
        mock_hide = mocker.patch.object(tray._tray, "hide")
        tray.hide()
        mock_hide.assert_called_once()

    def test_menu_show_window_emits_signal(self, qtbot):
        tray = TrayIcon()
        with qtbot.waitSignal(tray.show_window_requested):
            tray.show_action.trigger()

    def test_menu_settings_emits_signal(self, qtbot):
        tray = TrayIcon()
        with qtbot.waitSignal(tray.settings_requested):
            tray.settings_action.trigger()

    def test_menu_history_emits_signal(self, qtbot):
        tray = TrayIcon()
        with qtbot.waitSignal(tray.history_requested):
            tray.history_action.trigger()

    def test_menu_quit_emits_signal(self, qtbot):
        tray = TrayIcon()
        with qtbot.waitSignal(tray.quit_requested):
            tray._tray.contextMenu().actions()[-1].trigger()  # Quit

    def test_menu_record_emits_toggle(self, qtbot):
        tray = TrayIcon()
        with qtbot.waitSignal(tray.recording_toggled):
            tray.record_action.trigger()

    def test_quick_toggle_auto_paste_emits(self, qtbot):
        tray = TrayIcon()
        with qtbot.waitSignal(tray.auto_paste_toggled) as blocker:
            tray.auto_paste_action.trigger()
        assert blocker.args == [True]

    def test_quick_toggle_polish_emits(self, qtbot):
        tray = TrayIcon()
        with qtbot.waitSignal(tray.polish_toggled) as blocker:
            tray.polish_action.trigger()
        assert blocker.args == [True]

    def test_paste_mode_action_emits_mode(self, qtbot):
        tray = TrayIcon()
        with qtbot.waitSignal(tray.paste_mode_changed) as blocker:
            tray.paste_mode_actions["ctrl_shift_v"].trigger()
        assert blocker.args == ["ctrl_shift_v"]

    def test_asr_language_action_emits_language(self, qtbot):
        tray = TrayIcon()
        with qtbot.waitSignal(tray.asr_language_changed) as blocker:
            tray.asr_language_actions["en"].trigger()
        assert blocker.args == ["en"]

    def test_apply_config_checks_quick_actions(self, qtbot):
        from voicetype.config import AppConfig, AsrConfig, OutputConfig, PolishApiConfig

        tray = TrayIcon()
        cfg = AppConfig(
            asr=AsrConfig(language="en"),
            polish=PolishApiConfig(enabled=False),
            output=OutputConfig(auto_paste=False, paste_mode="ctrl_shift_v"),
        )
        tray.apply_config(cfg)

        assert tray.auto_paste_action.isChecked() is False
        assert tray.polish_action.isChecked() is False
        assert tray.paste_mode_actions["ctrl_shift_v"].isChecked() is True
        assert tray.asr_language_actions["en"].isChecked() is True


class TestHotkeyManager:
    def test_start_creates_listener(self, qtbot, mocker):
        mock_listener_cls = mocker.patch("voicetype.ui.system_tray.keyboard.Listener")
        mgr = HotkeyManager()
        mgr.start()
        mock_listener_cls.assert_called_once()
        mock_listener_cls.return_value.start.assert_called_once()

    def test_stop_stops_listener(self, qtbot, mocker):
        mock_listener_cls = mocker.patch("voicetype.ui.system_tray.keyboard.Listener")
        mock_listener = mock_listener_cls.return_value
        mgr = HotkeyManager()
        mgr.start()
        mgr.stop()
        mock_listener.stop.assert_called_once()
        assert mgr._listener is None

    def test_stop_without_start(self, qtbot):
        """Calling stop() without start() should not raise."""
        mgr = HotkeyManager()
        mgr.stop()  # should be safe

    def test_start_idempotent(self, qtbot, mocker):
        mock_listener_cls = mocker.patch("voicetype.ui.system_tray.keyboard.Listener")
        mgr = HotkeyManager()
        mgr.start()
        mgr.start()
        # Listener should only be created once
        mock_listener_cls.assert_called_once()

    def test_right_shift_tap_emits_toggle(self, qtbot):
        """Tapping Right Shift alone emits toggle_recording."""
        mgr = HotkeyManager()
        mgr._on_press(keyboard.Key.shift_r)
        with qtbot.waitSignal(mgr.toggle_recording):
            mgr._on_release(keyboard.Key.shift_r)

    def test_right_shift_combo_does_not_emit(self, qtbot):
        """Right Shift + another key does NOT emit toggle."""
        mgr = HotkeyManager()
        emitted = []
        mgr.toggle_recording.connect(lambda: emitted.append(True))
        from pynput.keyboard import KeyCode
        mgr._on_press(keyboard.Key.shift_r)
        mgr._on_press(KeyCode.from_char("s"))
        mgr._on_release(KeyCode.from_char("s"))
        mgr._on_release(keyboard.Key.shift_r)
        assert emitted == []

    def test_left_shift_not_treated_as_right_shift(self, qtbot):
        """Left Shift release does not trigger toggle."""
        mgr = HotkeyManager()
        emitted = []
        mgr.toggle_recording.connect(lambda: emitted.append(True))
        mgr._on_press(keyboard.Key.shift_l)
        mgr._on_release(keyboard.Key.shift_l)
        assert emitted == []

    def test_release_without_press_does_not_emit(self, qtbot):
        """Release event without prior press does nothing."""
        mgr = HotkeyManager()
        emitted = []
        mgr.toggle_recording.connect(lambda: emitted.append(True))
        mgr._on_release(keyboard.Key.shift_r)
        assert emitted == []

    def test_right_shift_c_emits_cancel(self, qtbot):
        """Right Shift+C emits cancel_recording signal."""
        from pynput.keyboard import KeyCode
        mgr = HotkeyManager()
        mgr._on_press(keyboard.Key.shift_r)
        with qtbot.waitSignal(mgr.cancel_recording):
            mgr._on_press(KeyCode.from_char("c"))

    def test_right_shift_c_does_not_emit_toggle(self, qtbot):
        """Right Shift+C should NOT also emit toggle_recording."""
        from pynput.keyboard import KeyCode
        mgr = HotkeyManager()
        toggle_emitted = []
        mgr.toggle_recording.connect(lambda: toggle_emitted.append(True))
        mgr._on_press(keyboard.Key.shift_r)
        mgr._on_press(KeyCode.from_char("c"))
        mgr._on_release(KeyCode.from_char("c"))
        mgr._on_release(keyboard.Key.shift_r)
        assert toggle_emitted == []

    def test_right_shift_uppercase_c_emits_cancel(self, qtbot):
        """Right Shift+C with uppercase C also emits cancel."""
        from pynput.keyboard import KeyCode
        mgr = HotkeyManager()
        mgr._on_press(keyboard.Key.shift_r)
        with qtbot.waitSignal(mgr.cancel_recording):
            mgr._on_press(KeyCode.from_char("C"))

    def test_alt_c_no_longer_emits_cancel(self, qtbot):
        """Alt+C is not a cancel shortcut."""
        from pynput.keyboard import KeyCode
        mgr = HotkeyManager()
        emitted = []
        mgr.cancel_recording.connect(lambda: emitted.append(True))
        mgr._on_press(keyboard.Key.alt_l)
        mgr._on_press(KeyCode.from_char("c"))
        assert emitted == []
