"""Tests for voice_type.ui.system_tray — TrayIcon and HotkeyManager."""

from PySide6.QtWidgets import QSystemTrayIcon
from voice_type.ui.system_tray import TrayIcon, HotkeyManager, MOD_ALT, MOD_CONTROL


class TestTrayIcon:
    def test_init_creates_tray(self, qtbot):
        tray = TrayIcon()
        assert tray._tray is not None

    def test_init_creates_menu_actions(self, qtbot):
        tray = TrayIcon()
        ctx = tray._tray.contextMenu()
        actions = ctx.actions()
        # Show Window, separator, Start Recording, Settings..., separator, Quit
        assert len(actions) >= 4

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
            tray._tray.contextMenu().actions()[3].trigger()  # Settings...

    def test_menu_quit_emits_signal(self, qtbot):
        tray = TrayIcon()
        with qtbot.waitSignal(tray.quit_requested):
            tray._tray.contextMenu().actions()[-1].trigger()  # Quit

    def test_menu_record_emits_toggle(self, qtbot):
        tray = TrayIcon()
        with qtbot.waitSignal(tray.recording_toggled):
            tray.record_action.trigger()


class TestHotkeyManager:
    def test_register_increments_id(self, qtbot):
        mgr = HotkeyManager()
        mgr.register(["alt"], "s", "start")
        mgr.register(["ctrl"], "e", "stop")
        # Two registrations, IDs should be 1 and 2
        assert len(mgr._registered) == 2
        assert mgr._registered[0][0] == 1
        assert mgr._registered[1][0] == 2

    def test_register_with_none_modifier(self, qtbot):
        """'none' modifier is ignored."""
        mgr = HotkeyManager()
        mgr.register(["none"], "s", "start")
        assert mgr._registered[0][1] == 0  # mod_value is 0

    def test_register_unknown_key_skips(self, qtbot, caplog):
        """Unknown key is skipped with warning."""
        mgr = HotkeyManager()
        mgr.register(["alt"], "!", "start")
        assert len(mgr._registered) == 0
        assert "Unknown hotkey" in caplog.text

    def test_register_multiple_modifiers(self, qtbot):
        """Multiple modifiers are ORed together."""
        mgr = HotkeyManager()
        mgr.register(["alt", "ctrl"], "s", "start")
        assert mgr._registered[0][1] == (MOD_ALT | MOD_CONTROL)

    def test_handle_hotkey_start(self, qtbot):
        """handle_hotkey with start callback emits start_recording."""
        mgr = HotkeyManager()
        mgr.register(["alt"], "s", "start")
        with qtbot.waitSignal(mgr.start_recording):
            mgr.handle_hotkey(1)

    def test_handle_hotkey_stop(self, qtbot):
        """handle_hotkey with stop callback emits stop_recording."""
        mgr = HotkeyManager()
        mgr.register(["alt"], "e", "stop")
        with qtbot.waitSignal(mgr.stop_recording):
            mgr.handle_hotkey(1)

    def test_handle_hotkey_cancel(self, qtbot):
        """handle_hotkey with cancel callback emits cancel_recording."""
        mgr = HotkeyManager()
        mgr.register(["alt"], "c", "cancel")
        with qtbot.waitSignal(mgr.cancel_recording):
            mgr.handle_hotkey(1)

    def test_handle_hotkey_nonexistent_id(self, qtbot):
        """handle_hotkey with no matching ID emits nothing."""
        mgr = HotkeyManager()
        mgr.register(["alt"], "s", "start")
        emitted = []
        mgr.start_recording.connect(lambda: emitted.append("start"))
        mgr.handle_hotkey(999)
        assert emitted == []

    def test_stop_clears_registered(self, qtbot):
        """stop() clears the registered list and resets ID counter."""
        mgr = HotkeyManager()
        mgr.register(["alt"], "s", "start")
        mgr.stop()
        assert mgr._registered == []
        assert mgr._hotkey_id == 0

    def test_update_calls_stop(self, qtbot, mocker):
        """update() calls stop()."""
        mgr = HotkeyManager()
        mock_stop = mocker.patch.object(mgr, "stop")
        mgr.update()
        mock_stop.assert_called_once()
