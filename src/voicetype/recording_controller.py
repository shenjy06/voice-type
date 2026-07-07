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
import threading

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
        self._context_provider = context_provider or (lambda hwnd: ("", ""))
        self._saved_hwnd = 0
        self._cursor_context: tuple[str, str] = ("", "")
        self._context_thread: threading.Thread | None = None
        self._cancelled = False

    # ---- public state -------------------------------------------------------

    @property
    def saved_hwnd(self) -> int:
        return self._saved_hwnd

    @property
    def cursor_context(self) -> tuple[str, str]:
        """Return the (before, after) cursor context captured this cycle.

        Joins the background context-capture thread (up to a short bound) so
        the value is current by the time processing begins. Recordings are
        typically far longer than the ~0.6s capture, so the thread has long
        since finished; the join is a safety net for very short taps.
        """
        thread = self._context_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
            self._context_thread = None
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
            self.stop()
        elif self._is_processing():
            pass
        else:
            self._ui.start_recording()

    def stop(self) -> None:
        """Stop an in-progress recording (manual toggle or VAD auto-stop).

        Drives the UI through stop_recording, which emits recording_stopped
        and kicks off processing. No-op when not currently recording, so a
        stale VAD signal arriving after a manual stop is safe.
        """
        if self._ui.is_recording():
            self._ui.stop_recording()

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
        # Update the UI immediately so the recording indicator, level meter,
        # and tray reflect "recording" without delay.
        self._level_timer.start()
        self._tray.set_recording(True)
        self._bubble.show_status(self._translate("status.recording"))
        # Capture cursor context on a BACKGROUND thread. The provider simulates
        # keystrokes (Shift+Home/Ctrl+C/...) with ~0.6s of sleeps and clipboard
        # I/O; running it on the UI thread froze the window for over half a
        # second at recording start. keybd_event is thread-agnostic (the app
        # already relies on this for paste), and the floating window uses
        # Qt.Tool so it never stole focus anyway. The result is collected into
        # ``_cursor_context`` and read via ``cursor_context`` at stop time,
        # which joins this thread if it's still running.
        self._cursor_context = ("", "")
        self._context_thread = threading.Thread(
            target=self._capture_context, daemon=True
        )
        self._context_thread.start()
        return self._saved_hwnd

    def _capture_context(self) -> None:
        """Run the context provider on a background thread; swallow failures."""
        try:
            self._cursor_context = self._context_provider(self._saved_hwnd)
        except Exception:
            self._cursor_context = ("", "")

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
        cancelled. Audio saving (WAV encoding) is deliberately NOT done here —
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
        """Reset UI after a processing failure.

        Does NOT clean up the recorder's audio file — on failure the file is
        retained so the caller (Application) can retry with the same audio.
        Application takes ownership of the path via ``take_audio_path()``
        before this is called, so the recorder no longer holds a reference
        to it either.
        """
        self._bubble.dismiss()
        if error_msg:
            self._ui.set_error(error_msg)
        self._ui.set_done()

    @staticmethod
    def _translate(key: str) -> str:
        """Translate a key. Imported lazily to avoid hard dependency at import time."""
        from voicetype.i18n import t
        return t(key)
