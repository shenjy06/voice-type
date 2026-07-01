"""Recording controller — owns the start/stop/cancel recording state machine.

The controller depends on a small set of collaborators that are passed in:
    recorder    — voicetype.audio.AudioRecorder
    ui          — anything that exposes start_recording/stop_recording/set_done/
                  set_processing/set_error/is_recording/isVisible/set_audio_level
    tray        — anything with set_recording/show_message
    bubble      — status bubble with show_status/dismiss
    level_timer — QTimer driving the audio-level sync
    hwnd_provider — callable returning the foreground HWND before recording starts
    context_provider — callable returning (before, after) cursor context for
                  context-aware polishing; defaults to no-op empty strings.

All collaborators are duck-typed so the controller stays testable and
free of Qt widget leakage.
"""

import ctypes

from voicetype.state import RecorderState
from voicetype.window_manager import get_foreground_window

# Show window without activating (keep focus on the user's target window).
SW_SHOWNA = 4
_user32 = ctypes.windll.user32


class RecordingController:
    """State machine for the recording workflow."""

    def __init__(
        self,
        recorder,
        ui,
        tray,
        bubble,
        level_timer,
        hwnd_provider=None,
        context_provider=None,
    ):
        self._recorder = recorder
        self._ui = ui
        self._tray = tray
        self._bubble = bubble
        self._level_timer = level_timer
        self._hwnd_provider = hwnd_provider or get_foreground_window
        self._context_provider = context_provider or (lambda: ("", ""))
        self._saved_hwnd = 0
        self._cursor_context: tuple[str, str] = ("", "")
        self._cancelled = False

    # ---- public state -------------------------------------------------------

    @property
    def saved_hwnd(self) -> int:
        return self._saved_hwnd

    @property
    def cursor_context(self) -> tuple[str, str]:
        """Return the (before, after) cursor context captured this cycle."""
        return self._cursor_context

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    @property
    def is_recording(self) -> bool:
        return self._ui.is_recording()

    # ---- transitions --------------------------------------------------------

    def toggle(self) -> None:
        """Toggle the recording state from the UI button.

        Ignores the toggle when the UI is in PROCESSING state so the user
        cannot start a new recording while a previous cycle is still being
        transcribed/polished.
        """
        if self._ui.is_recording():
            self._ui.stop_recording()
        elif self._is_processing():
            pass
        else:
            self._ui.start_recording()

    def _is_processing(self) -> bool:
        """Return True when the UI window is currently in PROCESSING state.

        Prefers the UI's public ``is_processing()`` method; falls back to
        reading ``_state`` for collaborators that haven't been updated.
        """
        is_processing = getattr(self._ui, "is_processing", None)
        if callable(is_processing):
            return bool(is_processing())
        ui_state = getattr(self._ui, "_state", None)
        return ui_state == RecorderState.PROCESSING

    def on_recording_started(self) -> int:
        """Called when the UI has transitioned to RECORDING.

        Returns the HWND captured for later paste targeting. If the recorder
        fails to start, the UI is reset to idle and 0 is returned.
        """
        self._cancelled = False
        self._saved_hwnd = self._hwnd_provider()
        if not self._recorder.start():
            self._saved_hwnd = 0
            self._cursor_context = ("", "")
            self._ui.stop_recording()
            self._tray.set_recording(False)
            self._ui.set_error(self._translate("error.no_audio"))
            return 0
        # Capture cursor context AFTER the recorder is already capturing audio
        # so the user's first words are not lost. The provider is responsible
        # for gating on polish-enabled and restoring the original clipboard.
        # Runs on the UI thread because it must target the foreground window
        # while it is still focused; the floating window uses Qt.Tool and does
        # not steal focus.
        try:
            self._cursor_context = self._context_provider()
        except Exception:
            self._cursor_context = ("", "")
        self._level_timer.start()
        self._tray.set_recording(True)
        self._bubble.show_status(self._translate("status.recording"))
        return self._saved_hwnd

    def cancel(self) -> None:
        """Mark the current cycle as cancelled. If currently recording, stop it;
        if not, clear any leftover audio from a previous cycle.
        """
        self._cancelled = True
        if self._ui.is_recording():
            self._ui.stop_recording()
        else:
            self._recorder.cleanup()
            self._tray.set_recording(False)
            self._ui.set_done()

    def stop_recording_event(self) -> bool:
        """Called when the UI fires recording_stopped. Stops the capture and
        prepares the UI for processing.

        Returns True if processing should proceed, or False if the cycle was
        cancelled. Audio saving (OGG encoding) is deliberately NOT done here —
        it runs on the processing worker's background thread so the UI never
        blocks on encoding. A save failure surfaces as a processing error.
        """
        self._recorder.stop()
        self._level_timer.stop()
        self._ui.set_audio_level(0.0)
        self._tray.set_recording(False)

        if self._cancelled:
            self._cancelled = False
            self._recorder.cleanup()
            self._bubble.dismiss()
            self._ui.set_done()
            return False

        self._ui.set_processing()
        self._bubble.show_status(self._translate("status.polishing"))

        # Show the window WITHOUT stealing focus from the target window, if the
        # user already had it visible. SW_SHOWNA = show without activating.
        if self._ui.isVisible():
            _user32.ShowWindow(int(self._ui.winId()), SW_SHOWNA)

        return True

    def reset_after_processing(self) -> None:
        """Reset the recorder + UI to idle after a processing cycle."""
        self._bubble.dismiss()
        self._recorder.cleanup()
        self._ui.set_done()

    def cancel_during_processing(self, error_msg: str | None = None) -> None:
        """Reset UI + recorder after a processing failure."""
        self._bubble.dismiss()
        self._recorder.cleanup()
        if error_msg:
            self._ui.set_error(error_msg)
        self._ui.set_done()

    @staticmethod
    def _translate(key: str) -> str:
        """Translate a key. Imported lazily to avoid hard dependency at import time."""
        from voicetype.i18n import t
        return t(key)
