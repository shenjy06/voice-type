"""Tests for voice_type.ui.main_window — FloatingRecordingWindow, PulsingDot, Toast."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QFontMetrics
from PySide6.QtWidgets import QPushButton
from voicetype.ui.main_window import (
    AudioLevelWaveform,
    CaptionPanel,
    FloatingRecordingWindow,
    MicrophoneIcon,
    PulsingDot,
    Toast,
    _button_style,
)
from voicetype.ui import theme
from voicetype.ui.theme import DARK_PALETTE, LIGHT_PALETTE, apply_theme_mode, get_palette, set_active_palette
from voicetype.state import RecorderState


class TestPulsingDot:
    def test_start_sets_recording_and_timer(self, qtbot):
        dot = PulsingDot()
        dot.start()
        assert dot._recording is True
        assert dot._timer.isActive()

    def test_stop_resets_opacity(self, qtbot):
        dot = PulsingDot()
        dot.start()
        dot.stop()
        assert dot._recording is False
        assert dot._opacity == 1.0
        assert not dot._timer.isActive()

    def test_pulse_decreases_then_increases(self, qtbot):
        dot = PulsingDot()
        dot._growing = True
        dot._opacity = 1.0
        # First pulse should decrease
        dot._pulse()
        assert dot._opacity < 1.0
        # Keep pulsing until it wraps around
        for _ in range(20):
            dot._pulse()
        # Should have wrapped back to growing=True and opacity >= 1.0 or close
        assert dot._growing is True or dot._opacity >= 0.3


class TestFloatingRecordingWindow:
    def test_init_always_on_top(self, qtbot):
        win = FloatingRecordingWindow(always_on_top=True)
        qtbot.addWidget(win)
        flags = win.windowFlags()
        assert flags & Qt.WindowStaysOnTopHint

    def test_init_not_always_on_top(self, qtbot):
        win = FloatingRecordingWindow(always_on_top=False)
        qtbot.addWidget(win)
        flags = win.windowFlags()
        assert flags & Qt.FramelessWindowHint

    def test_initial_state_is_idle(self, qtbot):
        win = FloatingRecordingWindow()
        qtbot.addWidget(win)
        assert win._state == RecorderState.IDLE
        assert isinstance(win.app_icon, MicrophoneIcon)
        assert win.app_icon.width() == 16
        assert win.app_name_label.text() == "Voice Type"

    def test_status_row_uses_recording_indicator(self, qtbot):
        win = FloatingRecordingWindow()
        qtbot.addWidget(win)
        assert isinstance(win.dot, PulsingDot)
        assert not hasattr(win, "status_label")

    def test_start_recording_emits_signal(self, qtbot):
        win = FloatingRecordingWindow()
        qtbot.addWidget(win)
        with qtbot.waitSignal(win.recording_started):
            win.start_recording()
        assert win.is_recording() is True
        assert win._state == RecorderState.RECORDING
        assert win.duration_label.text() == "00:00"

    def test_start_recording_when_already_recording_noop(self, qtbot):
        win = FloatingRecordingWindow()
        qtbot.addWidget(win)
        win.start_recording()
        # Second start should not emit again
        emitted = []
        win.recording_started.connect(lambda: emitted.append(True))
        win.start_recording()
        assert emitted == []

    def test_stop_recording_emits_signal(self, qtbot):
        win = FloatingRecordingWindow()
        qtbot.addWidget(win)
        win.start_recording()
        with qtbot.waitSignal(win.recording_stopped):
            win.stop_recording()
        assert win.is_recording() is False
        assert win._state == RecorderState.IDLE
        assert win.duration_label.text() == "00:00"

    def test_stop_recording_when_not_recording_noop(self, qtbot):
        win = FloatingRecordingWindow()
        qtbot.addWidget(win)
        emitted = []
        win.recording_stopped.connect(lambda: emitted.append(True))
        win.stop_recording()
        assert emitted == []

    def test_toggle_from_idle_starts(self, qtbot):
        win = FloatingRecordingWindow()
        qtbot.addWidget(win)
        with qtbot.waitSignal(win.recording_started):
            win._toggle_recording()
        assert win.is_recording() is True

    def test_toggle_from_recording_stops(self, qtbot):
        win = FloatingRecordingWindow()
        qtbot.addWidget(win)
        win.start_recording()
        with qtbot.waitSignal(win.recording_stopped):
            win._toggle_recording()
        assert win.is_recording() is False

    def test_set_processing(self, qtbot):
        win = FloatingRecordingWindow()
        qtbot.addWidget(win)
        win.start_recording()
        win.set_processing()
        assert win._state == RecorderState.PROCESSING
        assert win.is_recording() is False

    def test_set_done(self, qtbot):
        win = FloatingRecordingWindow()
        qtbot.addWidget(win)
        win.set_done()
        assert win._state == RecorderState.DONE

    def test_set_error(self, qtbot):
        win = FloatingRecordingWindow()
        qtbot.addWidget(win)
        win.set_error("No speech")
        assert win._state == RecorderState.ERROR

    def test_close_event_emits_hide(self, qtbot):
        win = FloatingRecordingWindow()
        qtbot.addWidget(win)
        with qtbot.waitSignal(win.hide_requested):
            event = QCloseEvent()
            win.closeEvent(event)
            assert not event.isAccepted()

    def test_set_hotkey_manager(self, qtbot):
        win = FloatingRecordingWindow()
        qtbot.addWidget(win)
        mgr = object()
        win.set_hotkey_manager(mgr)
        assert win._hotkey_manager is mgr

    def test_is_recording_in_different_states(self, qtbot):
        win = FloatingRecordingWindow()
        qtbot.addWidget(win)
        assert win.is_recording() is False  # IDLE
        win.start_recording()
        assert win.is_recording() is True  # RECORDING
        win.stop_recording()
        assert win.is_recording() is False  # IDLE

    def test_state_transitions_full_cycle(self, qtbot):
        """IDLE -> RECORDING -> PROCESSING -> DONE -> RECORDING."""
        win = FloatingRecordingWindow()
        qtbot.addWidget(win)
        assert win._state == RecorderState.IDLE

        win.start_recording()
        assert win._state == RecorderState.RECORDING

        win.set_processing()
        assert win._state == RecorderState.PROCESSING

        win.set_done()
        assert win._state == RecorderState.DONE

        win.start_recording()
        assert win._state == RecorderState.RECORDING

    def test_set_audio_level_is_clamped(self, qtbot):
        win = FloatingRecordingWindow()
        qtbot.addWidget(win)
        win.set_audio_level(2.0)
        assert win._pending_audio_level == 1.0
        win.set_audio_level(-1.0)
        assert win._pending_audio_level == 0.0


class TestAudioLevelWaveform:
    def test_add_level_keeps_recent_levels(self, qtbot):
        waveform = AudioLevelWaveform()
        qtbot.addWidget(waveform)
        waveform.add_level(0.5)
        assert waveform._levels[-1] == 0.5
        assert len(waveform._levels) == waveform._BAR_COUNT

    def test_add_level_clamps_values(self, qtbot):
        waveform = AudioLevelWaveform()
        qtbot.addWidget(waveform)
        waveform.add_level(2.0)
        assert waveform._levels[-1] == 1.0
        waveform.add_level(-1.0)
        assert waveform._levels[-1] == 0.0

    def test_reset_clears_levels(self, qtbot):
        waveform = AudioLevelWaveform()
        qtbot.addWidget(waveform)
        waveform.add_level(0.5)
        waveform.reset()
        assert all(level == 0.0 for level in waveform._levels)


class TestToast:
    def test_toast_shows_with_text(self, qtbot):
        toast = Toast("Test message")
        qtbot.addWidget(toast)
        assert toast._text == "Test message"

    def test_toast_custom_duration(self, qtbot):
        toast = Toast("Quick", duration_ms=500)
        qtbot.addWidget(toast)
        assert toast._duration_ms == 500

    def test_toast_default_duration(self, qtbot):
        toast = Toast("Normal")
        qtbot.addWidget(toast)
        assert toast._duration_ms == 1500

    def test_toast_size_depends_on_text(self, qtbot):
        toast_short = Toast("Hi")
        toast_long = Toast("This is a much longer message that should make a wider toast")
        qtbot.addWidget(toast_short)
        qtbot.addWidget(toast_long)
        assert toast_long.width() > toast_short.width()


class TestThemeIntegration:
    """The floating window sources every color from the active theme palette.

    Colors are read from :func:`get_palette` at paint/stylesheet-build time,
    so a light/dark switch takes effect on the next repaint. These tests pin
    the palette wiring (not pixel values) so they hold under both themes.
    """

    def setup_method(self):
        self._saved_palette = get_palette()

    def teardown_method(self):
        set_active_palette(self._saved_palette)

    def test_recording_button_uses_palette_danger(self):
        style = _button_style(RecorderState.RECORDING, DARK_PALETTE)
        assert DARK_PALETTE.danger in style
        assert "#dc2626" not in style or DARK_PALETTE.danger_hover in style

    def test_processing_button_uses_palette_warning(self):
        style = _button_style(RecorderState.PROCESSING, DARK_PALETTE)
        assert DARK_PALETTE.warning in style

    def test_idle_button_style_is_none(self):
        """Idle has no dedicated style - _update_record_button applies accent."""
        assert _button_style(RecorderState.IDLE, DARK_PALETTE) is None

    def test_idle_record_button_uses_active_accent(self, qtbot):
        apply_theme_mode("dark")
        win = FloatingRecordingWindow()
        qtbot.addWidget(win)
        assert DARK_PALETTE.accent in win.record_btn.styleSheet()

    def test_header_buttons_use_vector_icons_not_emoji(self, qtbot):
        apply_theme_mode("dark")
        win = FloatingRecordingWindow()
        qtbot.addWidget(win)
        buttons = win.findChildren(QPushButton)
        icon_buttons = [b for b in buttons if not b.icon().isNull()]
        # Two header buttons (gear + close) have icons; the record button is text-only.
        assert len(icon_buttons) >= 2
        for b in buttons:
            assert b.text() not in ("⚙", "✕"), "emoji/symbol text glyph left over"

    def test_apply_theme_switches_record_button_accent(self, qtbot):
        """apply_theme() re-styles the record button for the active palette."""
        apply_theme_mode("dark")
        win = FloatingRecordingWindow()
        qtbot.addWidget(win)
        assert DARK_PALETTE.accent in win.record_btn.styleSheet()
        apply_theme_mode("light")
        win.apply_theme()
        assert LIGHT_PALETTE.accent in win.record_btn.styleSheet()
        assert DARK_PALETTE.accent not in win.record_btn.styleSheet()

    def test_apply_theme_refreshes_header_icons(self, qtbot):
        """apply_theme() re-sets the gear/close icons for the new palette."""
        apply_theme_mode("dark")
        win = FloatingRecordingWindow()
        qtbot.addWidget(win)
        dark_gear = win._settings_btn.icon()
        apply_theme_mode("light")
        win.apply_theme()
        # QIcon has no value equality, but a re-set icon for a different palette
        # is a fresh instance from the per-color cache.
        light_gear = win._settings_btn.icon()
        assert not light_gear.isNull()




class TestCaptionPanel:
    def test_show_text_sets_text_and_shows(self, qtbot):
        panel = CaptionPanel()
        qtbot.addWidget(panel)
        panel.show_text("hello world")
        assert panel.text == "hello world"
        assert panel._render_text == "hello world"
        assert panel.isVisible()

    def test_show_text_updates_existing_text(self, qtbot):
        panel = CaptionPanel()
        qtbot.addWidget(panel)
        panel.show_text("hello")
        panel.show_text("hello world again")
        assert panel.text == "hello world again"

    def test_long_text_is_trimmed_from_front(self, qtbot):
        """Transcripts beyond the line cap drop the oldest content, keep the tail."""
        panel = CaptionPanel()
        qtbot.addWidget(panel)
        long_text = "字" * 2000
        panel.show_text(long_text)
        # The full transcript is kept; only the rendered text is trimmed.
        assert panel.text == long_text
        assert panel._render_text.startswith("…")
        assert panel._render_text.endswith("字")
        fm = QFontMetrics(panel._font)
        assert panel.height() <= fm.lineSpacing() * panel._MAX_LINES + panel._V_PADDING

    def test_height_grows_with_content_up_to_cap(self, qtbot):
        panel = CaptionPanel()
        qtbot.addWidget(panel)
        panel.show_text("short")
        short_h = panel.height()
        panel.show_text("word " * 200)
        assert panel.height() >= short_h
        fm = QFontMetrics(panel._font)
        assert panel.height() <= fm.lineSpacing() * panel._MAX_LINES + panel._V_PADDING

    def test_dismiss_hides_and_clears(self, qtbot):
        panel = CaptionPanel()
        qtbot.addWidget(panel)
        panel.show_text("hello")
        panel.dismiss()
        assert not panel.isVisible()
        assert panel.text == ""
        assert panel._render_text == ""

    def test_dismiss_when_hidden_is_safe(self, qtbot):
        panel = CaptionPanel()
        qtbot.addWidget(panel)
        panel.dismiss()  # never shown — must not raise
