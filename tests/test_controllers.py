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
        on_no_audio = MagicMock()
        on_save_error = MagicMock()
        result = rc.stop_recording_event(
            on_no_audio=on_no_audio,
            on_save_error=on_save_error,
        )
        assert result is None
        assert rc._cancelled is False
        d.recorder.cleanup.assert_called_once()
        d.bubble.dismiss.assert_called_once()
        d.ui.set_done.assert_called_once()
        on_no_audio.assert_not_called()
        on_save_error.assert_not_called()

    def test_stop_recording_event_saves_and_returns_path(self):
        rc, d, _ = _make_controller()
        d.recorder.save.return_value = "/tmp/audio.ogg"
        result = rc.stop_recording_event(MagicMock(), MagicMock())
        assert result == "/tmp/audio.ogg"
        d.recorder.stop.assert_called_once()
        d.level_timer.stop.assert_called_once()
        d.ui.set_audio_level.assert_called_once_with(0.0)
        d.ui.set_processing.assert_called_once()

    def test_stop_recording_event_save_failure_invokes_callback(self):
        rc, d, _ = _make_controller()
        d.recorder.save.side_effect = ValueError("no audio")
        on_save_error = MagicMock()
        result = rc.stop_recording_event(MagicMock(), on_save_error)
        assert result is None
        on_save_error.assert_called_once()

    def test_reset_after_processing(self):
        rc, d, _ = _make_controller()
        rc.reset_after_processing()
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
