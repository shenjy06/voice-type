"""Tests for voice_type.ui.system_tray — TrayIcon and HotkeyManager."""

import gc
import weakref

import pytest
from PySide6.QtWidgets import QSystemTrayIcon
from pynput import keyboard
from voicetype.hotkey_parser import HotkeyBinding
from voicetype.ui.system_tray import TrayIcon, HotkeyManager


@pytest.fixture(autouse=True)
def _cleanup_tray_icons(qapp):
    """Destroy QSystemTrayIcon instances created during TrayIcon tests.

    Leaked tray icons can cause the test process to exit with code 2816 on
    Windows, so we explicitly hide and schedule deletion after each test.
    """
    refs = []
    original_init = TrayIcon.__init__

    def _tracking_init(self, parent=None):
        original_init(self, parent)
        refs.append(weakref.ref(self))

    TrayIcon.__init__ = _tracking_init
    yield
    TrayIcon.__init__ = original_init

    for ref in refs:
        tray_icon = ref()
        if tray_icon is not None and tray_icon._tray is not None:
            tray_icon._tray.hide()
            tray_icon._tray.deleteLater()
    qapp.processEvents()
    gc.collect()


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

    def test_right_alt_tap_emits_toggle(self, qtbot):
        """Tapping Right Alt alone emits toggle_recording."""
        mgr = HotkeyManager()
        mgr._on_press(keyboard.Key.alt_r)
        with qtbot.waitSignal(mgr.toggle_recording):
            mgr._on_release(keyboard.Key.alt_r)

    def test_right_alt_combo_does_not_emit(self, qtbot):
        """Right Alt + another key does NOT emit toggle."""
        mgr = HotkeyManager()
        emitted = []
        mgr.toggle_recording.connect(lambda: emitted.append(True))
        from pynput.keyboard import KeyCode
        mgr._on_press(keyboard.Key.alt_r)
        mgr._on_press(KeyCode.from_char("s"))
        mgr._on_release(KeyCode.from_char("s"))
        mgr._on_release(keyboard.Key.alt_r)
        assert emitted == []

    def test_left_alt_not_treated_as_right_alt(self, qtbot):
        """Left Alt release does not trigger toggle."""
        mgr = HotkeyManager()
        emitted = []
        mgr.toggle_recording.connect(lambda: emitted.append(True))
        mgr._on_press(keyboard.Key.alt_l)
        mgr._on_release(keyboard.Key.alt_l)
        assert emitted == []

    def test_release_without_press_does_not_emit(self, qtbot):
        """Release event without prior press does nothing."""
        mgr = HotkeyManager()
        emitted = []
        mgr.toggle_recording.connect(lambda: emitted.append(True))
        mgr._on_release(keyboard.Key.alt_r)
        assert emitted == []

    def test_right_alt_c_emits_cancel(self, qtbot):
        """Right Alt+C emits cancel_recording signal."""
        from pynput.keyboard import KeyCode
        mgr = HotkeyManager()
        mgr._on_press(keyboard.Key.alt_r)
        with qtbot.waitSignal(mgr.cancel_recording):
            mgr._on_press(KeyCode.from_char("c"))

    def test_right_alt_c_does_not_emit_toggle(self, qtbot):
        """Right Alt+C should NOT also emit toggle_recording."""
        from pynput.keyboard import KeyCode
        mgr = HotkeyManager()
        toggle_emitted = []
        mgr.toggle_recording.connect(lambda: toggle_emitted.append(True))
        mgr._on_press(keyboard.Key.alt_r)
        mgr._on_press(KeyCode.from_char("c"))
        mgr._on_release(KeyCode.from_char("c"))
        mgr._on_release(keyboard.Key.alt_r)
        assert toggle_emitted == []

    def test_right_alt_uppercase_c_emits_cancel(self, qtbot):
        """Right Alt+C with uppercase C also emits cancel."""
        from pynput.keyboard import KeyCode
        mgr = HotkeyManager()
        mgr._on_press(keyboard.Key.alt_r)
        with qtbot.waitSignal(mgr.cancel_recording):
            mgr._on_press(KeyCode.from_char("C"))

    def test_left_alt_c_does_not_emit_cancel(self, qtbot):
        """Left Alt+C is not a cancel shortcut."""
        from pynput.keyboard import KeyCode
        mgr = HotkeyManager()
        emitted = []
        mgr.cancel_recording.connect(lambda: emitted.append(True))
        mgr._on_press(keyboard.Key.alt_l)
        mgr._on_press(KeyCode.from_char("c"))
        assert emitted == []

    def test_generic_alt_tap_does_not_toggle(self, qtbot):
        """A plain Key.alt tap is treated as left-alt and must NOT toggle.

        Key.alt aliases Key.alt_l in pynput. A bare Key.alt press must
        not start or stop recording so left alt behaves like any other
        modifier.
        """
        mgr = HotkeyManager()
        emitted = []
        mgr.toggle_recording.connect(lambda: emitted.append(True))
        mgr._on_press(keyboard.Key.alt)
        mgr._on_release(keyboard.Key.alt)
        assert emitted == []

    def test_generic_alt_press_clears_stale_toggle_state(self, qtbot):
        """A generic Key.alt press must clear any stale right-alt state.

        If a previous right-alt release event was somehow missed, a
        subsequent left-alt tap should still not toggle.
        """
        mgr = HotkeyManager()
        emitted = []
        mgr.toggle_recording.connect(lambda: emitted.append(True))
        mgr._last_toggle_key = "alt_r"  # simulate stale state
        mgr._on_press(keyboard.Key.alt)
        mgr._on_release(keyboard.Key.alt)
        assert emitted == []

    def test_alt_r_press_alt_release_emits_toggle(self, qtbot):
        """Press with alt_r and release with bare alt should still toggle.

        On Windows pynput may emit Key.alt_r on press and Key.alt on
        release for the same physical Right-Alt tap. The listener must
        accept alt-as-a-superset in _on_release.
        """
        mgr = HotkeyManager()
        mgr._on_press(keyboard.Key.alt_r)
        with qtbot.waitSignal(mgr.toggle_recording):
            mgr._on_release(keyboard.Key.alt)

    def test_alt_gr_tap_emits_toggle(self, qtbot):
        """Tapping AltGr alone emits toggle_recording."""
        mgr = HotkeyManager()
        mgr._on_press(keyboard.Key.alt_gr)
        with qtbot.waitSignal(mgr.toggle_recording):
            mgr._on_release(keyboard.Key.alt_gr)

    def test_alt_gr_combo_does_not_emit(self, qtbot):
        """AltGr + another key does NOT emit toggle."""
        mgr = HotkeyManager()
        emitted = []
        mgr.toggle_recording.connect(lambda: emitted.append(True))
        from pynput.keyboard import KeyCode
        mgr._on_press(keyboard.Key.alt_gr)
        mgr._on_press(KeyCode.from_char("s"))
        mgr._on_release(KeyCode.from_char("s"))
        mgr._on_release(keyboard.Key.alt_gr)
        assert emitted == []

    def test_alt_gr_c_emits_cancel(self, qtbot):
        """AltGr+C emits cancel_recording signal."""
        from pynput.keyboard import KeyCode
        mgr = HotkeyManager()
        mgr._on_press(keyboard.Key.alt_gr)
        with qtbot.waitSignal(mgr.cancel_recording):
            mgr._on_press(KeyCode.from_char("c"))

    def test_alt_gr_press_alt_release_emits_toggle(self, qtbot):
        """Press with alt_gr and release with bare alt should still toggle."""
        mgr = HotkeyManager()
        mgr._on_press(keyboard.Key.alt_gr)
        with qtbot.waitSignal(mgr.toggle_recording):
            mgr._on_release(keyboard.Key.alt)

    def test_default_binding_is_right_alt(self, qtbot):
        """HotkeyManager defaults to Right Alt binding."""
        mgr = HotkeyManager()
        assert mgr.binding.kind == "right_alt"

    def test_function_key_press_emits_toggle(self, qtbot):
        """Pressing a bound function key emits toggle_recording."""
        mgr = HotkeyManager(binding=HotkeyBinding.from_string("f9"))
        with qtbot.waitSignal(mgr.toggle_recording):
            mgr._on_press(keyboard.Key.f9)

    def test_function_key_release_does_not_emit(self, qtbot):
        """Releasing a bound function key does not emit toggle again."""
        mgr = HotkeyManager(binding=HotkeyBinding.from_string("f9"))
        emitted = []
        mgr.toggle_recording.connect(lambda: emitted.append(True))
        mgr._on_press(keyboard.Key.f9)
        mgr._on_release(keyboard.Key.f9)
        assert len(emitted) == 1

    def test_unbound_function_key_does_not_emit(self, qtbot):
        """A function key other than the bound one does not toggle."""
        mgr = HotkeyManager(binding=HotkeyBinding.from_string("f9"))
        emitted = []
        mgr.toggle_recording.connect(lambda: emitted.append(True))
        mgr._on_press(keyboard.Key.f8)
        mgr._on_release(keyboard.Key.f8)
        assert emitted == []

    def test_set_binding_while_running_raises(self, qtbot):
        """Changing binding while listener is running is not allowed."""
        mgr = HotkeyManager()
        mgr.start()
        try:
            with pytest.raises(RuntimeError):
                mgr.set_binding(HotkeyBinding.from_string("f9"))
        finally:
            mgr.stop()

    def test_character_key_press_emits_toggle(self, qtbot):
        """Pressing a bound character key emits toggle_recording."""
        from pynput.keyboard import KeyCode
        mgr = HotkeyManager(binding=HotkeyBinding.from_string("a"))
        with qtbot.waitSignal(mgr.toggle_recording):
            mgr._on_press(KeyCode(char="a"))

    def test_key_repeat_is_suppressed_until_release(self, qtbot):
        """Holding a single-key hotkey only toggles once."""
        from pynput.keyboard import KeyCode
        mgr = HotkeyManager(binding=HotkeyBinding.from_string("a"))
        emitted = []
        mgr.toggle_recording.connect(lambda: emitted.append(True))

        mgr._on_press(KeyCode(char="a"))
        mgr._on_press(KeyCode(char="a"))
        mgr._on_press(KeyCode(char="a"))
        assert len(emitted) == 1

        mgr._on_release(KeyCode(char="a"))
        mgr._on_press(KeyCode(char="a"))
        assert len(emitted) == 2
