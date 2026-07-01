"""Focused tests for the RecordingController and ProcessingController."""

from unittest.mock import MagicMock

import pytest

from voicetype.recording_controller import RecordingController
from voicetype.processing_controller import ProcessingController


class _RecordingControllerDoubles:
    """Lightweight stand-ins for the duck-typed collaborators."""

    def __init__(self):
        self.recorder = MagicMock()
        self.ui = MagicMock()
        self.tray = MagicMock()
        self.bubble = MagicMock()
        self.level_timer = MagicMock()


def _make_controller(cancelled=False, saved_hwnd=0):
    d = _RecordingControllerDoubles()
    d.ui.is_processing.return_value = False  # not processing by default
    hwnd_provider = MagicMock(return_value=12345)
    rc = RecordingController(
        recorder=d.recorder,
        ui=d.ui,
        tray=d.tray,
        bubble=d.bubble,
        level_timer=d.level_timer,
        hwnd_provider=hwnd_provider,
    )
    rc._cancelled = cancelled
    rc._saved_hwnd = saved_hwnd
    return rc, d, hwnd_provider


class TestRecordingController:
    def test_toggle_dispatches_to_ui(self):
        rc, d, _ = _make_controller()
        d.ui.is_recording.return_value = False
        rc.toggle()
        d.ui.start_recording.assert_called_once()
        d.ui.stop_recording.assert_not_called()

    def test_toggle_stops_when_recording(self):
        rc, d, _ = _make_controller()
        d.ui.is_recording.return_value = True
        rc.toggle()
        d.ui.stop_recording.assert_called_once()
        d.ui.start_recording.assert_not_called()

    def test_toggle_ignored_when_processing(self):
        """Toggle must not start a new recording while processing is in progress."""
        rc, d, _ = _make_controller()
        d.ui.is_recording.return_value = False
        d.ui.is_processing.return_value = True
        rc.toggle()
        d.ui.start_recording.assert_not_called()
        d.ui.stop_recording.assert_not_called()

    def test_toggle_falls_back_to_state_when_no_is_processing(self):
        """When the UI lacks is_processing(), _state is consulted as a fallback."""
        from voicetype.state import RecorderState

        d = _RecordingControllerDoubles()
        # Build a UI double with no is_processing attribute at all.
        ui = MagicMock(spec=["is_recording", "start_recording", "stop_recording",
                             "set_audio_level", "set_processing", "set_done",
                             "set_error", "isVisible", "winId"])
        ui.is_recording.return_value = False
        ui._state = RecorderState.PROCESSING
        rc = RecordingController(
            recorder=d.recorder, ui=ui, tray=d.tray, bubble=d.bubble,
            level_timer=d.level_timer,
        )
        rc.toggle()
        ui.start_recording.assert_not_called()
        ui.stop_recording.assert_not_called()

    def test_on_recording_started_captures_hwnd_and_starts_recorder(self):
        rc, d, hwnd_provider = _make_controller()
        result = rc.on_recording_started()
        assert result == 12345
        hwnd_provider.assert_called_once()
        d.recorder.start.assert_called_once()
        d.level_timer.start.assert_called_once()
        d.tray.set_recording.assert_called_once_with(True)
        d.bubble.show_status.assert_called_once()

    def test_on_recording_started_resets_cancelled_flag(self):
        rc, d, _ = _make_controller(cancelled=True)
        rc.on_recording_started()
        assert rc._cancelled is False

    def test_on_recording_started_captures_cursor_context(self):
        """The context_provider is invoked and its result exposed."""
        d = _RecordingControllerDoubles()
        hwnd_provider = MagicMock(return_value=12345)
        context_provider = MagicMock(return_value=("hello ", " world"))
        rc = RecordingController(
            recorder=d.recorder,
            ui=d.ui,
            tray=d.tray,
            bubble=d.bubble,
            level_timer=d.level_timer,
            hwnd_provider=hwnd_provider,
            context_provider=context_provider,
        )
        rc.on_recording_started()
        context_provider.assert_called_once()
        assert rc.cursor_context == ("hello ", " world")

    def test_on_recording_started_context_capture_failure_is_safe(self):
        """A raising provider must not break the recording start."""
        d = _RecordingControllerDoubles()
        hwnd_provider = MagicMock(return_value=12345)
        context_provider = MagicMock(side_effect=RuntimeError("boom"))
        rc = RecordingController(
            recorder=d.recorder,
            ui=d.ui,
            tray=d.tray,
            bubble=d.bubble,
            level_timer=d.level_timer,
            hwnd_provider=hwnd_provider,
            context_provider=context_provider,
        )
        result = rc.on_recording_started()
        assert result == 12345
        assert rc.cursor_context == ("", "")

    def test_cursor_context_defaults_empty_without_provider(self):
        rc, d, _ = _make_controller()
        assert rc.cursor_context == ("", "")

    def test_cancel_when_recording_stops_ui(self):
        rc, d, _ = _make_controller()
        d.ui.is_recording.return_value = True
        rc.cancel()
        assert rc._cancelled is True
        d.ui.stop_recording.assert_called_once()

    def test_cancel_when_not_recording_cleans_up(self):
        rc, d, _ = _make_controller()
        d.ui.is_recording.return_value = False
        rc.cancel()
        assert rc._cancelled is True
        d.recorder.cleanup.assert_called_once()
        d.tray.set_recording.assert_called_once_with(False)
        d.ui.set_done.assert_called_once()

    def test_stop_recording_event_when_cancelled_resets(self):
        rc, d, _ = _make_controller(cancelled=True)
        rc._cancelled = True
        result = rc.stop_recording_event()
        assert result is False
        assert rc._cancelled is False
        d.recorder.cleanup.assert_called_once()
        d.bubble.dismiss.assert_called_once()
        d.ui.set_done.assert_called_once()

    def test_stop_recording_event_proceeds_without_saving(self):
        """stop_recording_event stops the stream and signals proceed; saving is
        deferred to the processing worker so the UI thread never blocks on it."""
        rc, d, _ = _make_controller()
        result = rc.stop_recording_event()
        assert result is True
        d.recorder.stop.assert_called_once()
        d.recorder.save.assert_not_called()
        d.level_timer.stop.assert_called_once()
        d.ui.set_audio_level.assert_called_once_with(0.0)
        d.ui.set_processing.assert_called_once()

    def test_reset_after_processing(self):
        rc, d, _ = _make_controller()
        rc.reset_after_processing()
        d.bubble.dismiss.assert_called_once()
        d.recorder.cleanup.assert_called_once()
        d.ui.set_done.assert_called_once()

    def test_cancel_during_processing_sets_error(self):
        rc, d, _ = _make_controller()
        rc.cancel_during_processing("api timeout")
        d.bubble.dismiss.assert_called_once()
        d.recorder.cleanup.assert_called_once()
        d.ui.set_error.assert_called_once_with("api timeout")
        d.ui.set_done.assert_called_once()


class TestProcessingController:
    def test_is_running_false_when_not_started(self, mocker):
        cfg = MagicMock()
        ctl = ProcessingController(config=cfg, on_done=MagicMock(), on_error=MagicMock())
        assert ctl.is_running() is False

    def test_shutdown_is_safe_when_never_started(self):
        cfg = MagicMock()
        ctl = ProcessingController(config=cfg, on_done=MagicMock(), on_error=MagicMock())
        # Should not raise.
        ctl.shutdown()

    def test_shutdown_when_no_thread(self):
        cfg = MagicMock()
        ctl = ProcessingController(config=cfg, on_done=MagicMock(), on_error=MagicMock())
        # _thread is None — should not raise
        ctl.shutdown()
        assert ctl._thread is None

    def test_is_running_safe_after_thread_deleted(self, qtbot):
        """is_running() must not crash when the C++ QThread was deleted by deleteLater."""
        cfg = MagicMock()
        ctl = ProcessingController(config=cfg, on_done=MagicMock(), on_error=MagicMock())

        # Simulate a thread that has finished and been deleted by Qt — the
        # Python reference still exists but the C++ object is gone.
        from PySide6.QtCore import QThread

        thread = QThread()
        ctl._thread = thread
        thread.deleteLater()
        # Process the deleteLater so the C++ object is actually destroyed.
        qtbot.wait(50)

        # This used to raise RuntimeError: Internal C++ object already deleted.
        assert ctl.is_running() is False
        assert ctl._thread is None  # cleared by the safety guard
