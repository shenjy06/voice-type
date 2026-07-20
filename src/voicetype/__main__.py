"""Voice Type — entry point and application orchestrator.

The :class:`Application` class wires together UI components and two
controllers:

    * :class:`RecordingController`  — owns the recording state machine
    * :class:`ProcessingController` — runs ASR + LLM polishing off the UI thread

Application keeps the public attribute surface (`audio_recorder`, `window`,
`tray`, etc.) that existing tests depend on; controllers collaborate by
duck-typed interfaces rather than mutating each other's state directly.
"""

# --- Compatibility shims (must run before any third-party imports) ---------
# `openai` still imports `pydantic.v1.typing` on first load, which emits a
# UserWarning on Python 3.14+. Suppress that one harmless warning specifically
# so it doesn't pollute test output and user logs. Re-enable once upstream
# removes the pydantic.v1 import path.
import warnings

warnings.filterwarnings(
    "ignore",
    message=r"Core Pydantic V1 functionality isn't compatible with Python 3\.14 or greater\.",
    category=UserWarning,
)

import logging
import os
import sys
import threading
import time
import weakref

import ctypes
import pyperclip
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject, QTimer, Signal

from voicetype._logging import setup_logging
from voicetype.audio import AudioRecorder, cleanup_stale_audio
from voicetype.config import AppConfig
from voicetype.context import get_cursor_context
from voicetype.hotkey_parser import HotkeyBinding
from voicetype.history import HistoryStore
from voicetype.processing_controller import ProcessingController
from voicetype.recording_controller import RecordingController
from voicetype.streaming_asr import StreamingTranscriber
from voicetype.typer import TextTyper
from voicetype.ui.history_dialog import HistoryDialog
from voicetype.ui.main_window import CaptionPanel, FloatingRecordingWindow, StatusBubble, Toast
from voicetype.ui.settings_dialog import SettingsDialog
from voicetype.ui.system_tray import HotkeyManager, TrayIcon
from voicetype.ui.theme import apply_theme_mode
from voicetype.i18n import init_language, t
from voicetype.window_manager import get_foreground_window

logger = logging.getLogger(__name__)


class _PasteBridge(QObject):
    """Marshals a background-thread paste/copy result to the UI thread.

    Qt signals are the correct cross-thread mechanism here: a signal emitted
    from the output worker thread is delivered to this object's thread (the
    UI thread) via a queued connection. ``QTimer.singleShot`` cannot be used
    from a worker thread because timers are thread-affine and the worker has
    no event loop.
    """

    paste_finished = Signal(bool)  # True = pasted/copied OK, False = failed
    paste_continue_ready = Signal(bool)  # per-operation: only connected for continuous sessions


class _SilenceBridge(QObject):
    """Marshals the VAD silence event from the audio thread to the UI thread.

    ``AudioRecorder.on_silence`` is invoked on sounddevice's audio callback
    thread; emitting this signal from there delivers it queued to this
    object's thread (the UI thread), where stopping the recording is safe.
    Same pattern as :class:`_PasteBridge`.
    """

    silence_detected = Signal()


class _StreamingTextBridge(QObject):
    """Marshals streaming transcript text from the WebSocket recv thread to the UI thread.

    ``StreamingTranscriber`` invokes ``on_text_update`` / ``on_error`` on its
    background recv thread; emitting these signals delivers them queued to the
    UI thread so we can update the status bubble safely.
    """

    text_updated = Signal(str)
    stream_error = Signal(str)


class Application:
    """Top-level orchestrator — owns the Qt event loop, wires UI components to
    controllers, and manages the lifecycle of audio recording, ASR/polish
    processing, text output, hotkeys, and system tray integration.

    Public attributes (also used by tests):
        config, audio_recorder, window, tray, typer, history_store,
        hotkey_manager
    """

    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("Voice Type")
        self.app.setQuitOnLastWindowClosed(False)

        # Clean up stale audio files from previous sessions on a background
        # thread — a glob + stat sweep is not time-critical and shouldn't add
        # latency to startup on the UI thread.
        threading.Thread(target=cleanup_stale_audio, daemon=True).start()

        self.config = AppConfig.load()
        init_language(self.config.language)
        # Apply the configured UI theme (dark/light/system) before any window
        # or dialog is constructed so they pick up the right palette at build
        # time. FloatingRecordingWindow/Toast/StatusBubble read the palette in
        # paintEvent, so they re-skin on the next repaint after a switch.
        apply_theme_mode(self.config.window.theme_mode)
        self.audio_recorder = AudioRecorder(
            self.config.recording.sample_rate,
            denoise_enabled=self.config.recording.denoise_enabled,
            denoise_strength=self.config.recording.denoise_strength,
            vad_enabled=self.config.recording.vad_enabled,
            vad_silence_duration_ms=self.config.recording.vad_silence_duration_ms,
            vad_threshold=self.config.recording.vad_threshold,
            streaming_enabled=self.config.asr.streaming_enabled,
            device=self.config.recording.device,
        )
        self.typer = TextTyper(self.config)
        self.history_store = HistoryStore()
        self._quitting = False
        # Track paste threads so we can join them at quit, preventing
        # ctypes calls from daemon threads after Qt objects are destroyed.
        self._paste_threads: list[threading.Thread] = []
        # Retry state: when a processing cycle fails, the audio file path +
        # cursor context are retained here so the user can retry from the
        # tray menu without re-recording. Cleared on new recording / retry
        # success / quit.
        self._retry_audio_path: str | None = None
        self._retry_context: tuple[str, str] = ("", "")
        # Continuous dictation session state. ``_continuous_active`` is True
        # while a continuous session is in progress (between the first
        # recording and a cancel/error/quit). The per-operation continue
        # signal (paste_continue_ready) avoids the shared-state bug where
        # a history paste completing before a processing-done paste could
        # mistakenly restart recording.
        self._continuous_active = False
        logger.info("Application initialized (configured=%s)", self.config.is_configured())

        # Audio-level sync timer — owned at Application level so it can be
        # stopped at quit even if the controller has been torn down.
        self._audio_level_timer = QTimer()
        self._audio_level_timer.setInterval(100)
        self._audio_level_timer.timeout.connect(self._sync_audio_level)

        # Polish elapsed-time timer — starts when polish begins, ticks every
        # second so the status bubble shows "润色中... (5s)" during long operations.
        self._polish_start = 0.0
        self._polish_timer = QTimer()
        self._polish_timer.setInterval(1000)
        self._polish_timer.timeout.connect(self._update_polish_elapsed)

        # Keep weak references to active toasts so they aren't GC'd mid-animation.
        # Weak refs avoid the destroyed-signal race: if a toast is GC'd before
        # its destroyed signal fires, the WeakSet silently drops the dead ref
        # instead of crashing on a wild pointer.
        self._toasts = weakref.WeakSet()

        # Bridge for marshaling background-thread paste failures to the UI
        # thread (created here so it lives on the UI/main thread).
        self._paste_bridge = _PasteBridge()
        self._paste_bridge.paste_finished.connect(self._on_paste_finished)
        self._paste_bridge.paste_continue_ready.connect(self._on_continue_ready)

        # Bridge for marshaling VAD silence detection from the audio thread to
        # the UI thread. The recorder invokes ``on_silence`` on its callback
        # thread; the signal is delivered queued here so we can stop the
        # recording on the UI thread (same path as the user pressing stop).
        self._silence_bridge = _SilenceBridge()
        self._silence_bridge.silence_detected.connect(self._on_silence_detected)
        self.audio_recorder.on_silence = self._silence_bridge.silence_detected.emit

        # Bridge for marshaling streaming transcript text from the WebSocket
        # recv thread to the UI thread (so the status bubble can update live).
        self._streaming_bridge = _StreamingTextBridge()
        self._streaming_bridge.text_updated.connect(self._on_streaming_text)
        self._streaming_bridge.stream_error.connect(self._on_streaming_error)
        # Active streaming transcriber for the current recording cycle, or
        # None when streaming is disabled / not yet started / already finished.
        self._streaming_transcriber: StreamingTranscriber | None = None

        self._init_ui()
        self._init_controllers()

        # Check config on first launch — show settings if no API key is set
        if not self.config.is_configured():
            self._show_settings()

        self._init_hotkey()
        self._warmup_api_connections()

    def _warmup_api_connections(self) -> None:
        """Pre-establish TLS connections to ASR/Polish APIs on a background thread.

        The first API call in a session pays a TLS handshake cost (~200-500ms).
        Calling ``warmup()`` at startup makes a lightweight ``models.list()``
        request so the SDK's httpx connection pool is ready before the first
        recording. Best-effort: failures are swallowed silently — see
        Transcriber.warmup / TextPolisher.warmup.
        """
        from voicetype.processing import get_transcriber, get_polisher

        def _warmup():
            # Skip ASR warmup when the base URL is a WebSocket endpoint — the
            # openai SDK's models.list() is a REST call that 404s on wss://.
            asr_url = self.config.asr.base_url
            if self.config.asr.api_key and not asr_url.startswith(("ws://", "wss://")):
                try:
                    get_transcriber(self.config).warmup()
                except Exception as e:
                    logger.debug("ASR warmup skipped: %s", e)
            if self.config.polish.api_key:
                try:
                    get_polisher(self.config).warmup()
                except Exception as e:
                    logger.debug("Polish warmup skipped: %s", e)

        threading.Thread(target=_warmup, daemon=True).start()

    # ---- init --------------------------------------------------------------

    def _init_ui(self):
        # Floating window
        self.window = FloatingRecordingWindow(self.config.window.always_on_top)
        self.window.recording_started.connect(self._on_recording_started)
        self.window.recording_stopped.connect(self._on_recording_stopped)
        self.window.settings_requested.connect(self._show_settings)
        self.window.hide_requested.connect(self.window.hide)

        # System tray
        self.tray = TrayIcon()
        self.tray.show_window_requested.connect(self._show_window)
        self.tray.history_requested.connect(self._show_history)
        self.tray.settings_requested.connect(self._show_settings)
        self.tray.recording_toggled.connect(self._toggle_recording)
        self.tray.retry_requested.connect(self._retry_processing)
        self.tray.auto_paste_toggled.connect(self._set_auto_paste)
        self.tray.polish_toggled.connect(self._set_polish_enabled)
        self.tray.paste_mode_changed.connect(self._set_paste_mode)
        self.tray.asr_language_changed.connect(self._set_asr_language)
        self.tray.continuous_mode_toggled.connect(self._set_continuous_mode)
        self.tray.quit_requested.connect(self._quit)
        self.tray.apply_config(self.config)
        self.tray.show()

        # Settings dialog (lazy)
        self._settings_dialog = None
        self._history_dialog = None
        # Foreground window captured BEFORE the history dialog opens, so a
        # paste from history targets the user's real edit window instead of
        # the (modal) history dialog itself.
        self._history_target_hwnd = 0

        # Status bubble (persistent Bubble during recording/processing)
        self._status_bubble = StatusBubble()
        # Live caption panel for streaming ASR — shows the full transcript
        # (the bubble only shows a one-line truncated preview).
        self._caption_panel = CaptionPanel()

        if self.config.window.show_on_start:
            self._show_window()

    def _init_controllers(self):
        self._recording_controller = RecordingController(
            recorder=self.audio_recorder,
            ui=self.window,
            tray=self.tray,
            bubble=self._status_bubble,
            level_timer=self._audio_level_timer,
            context_provider=self._capture_cursor_context,
        )
        self._processing_controller = ProcessingController(
            config=self.config,
            on_done=self._on_processing_done,
            on_error=self._on_processing_error,
            parent=self.app,
        )
        self._processing_controller.progress.connect(self._on_processing_progress)

    def _init_hotkey(self):
        binding = HotkeyBinding.from_string(self.config.hotkey.toggle_hotkey)
        self.hotkey_manager = HotkeyManager(self.window, binding=binding)
        self.hotkey_manager.toggle_recording.connect(self._toggle_recording)
        self.hotkey_manager.cancel_recording.connect(self._cancel_recording)
        self.window.set_hotkey_manager(self.hotkey_manager)
        if self.config.hotkey.toggle_enabled:
            self.hotkey_manager.start()

    # ---- recording event handlers (delegate to RecordingController) --------

    def _toggle_recording(self):
        self._recording_controller.toggle()

    def _cancel_recording(self):
        # Cancel ends any active continuous session — the user explicitly
        # wants to stop, so don't auto-restart after the current cycle.
        self._continuous_active = False
        self._caption_panel.dismiss()
        self._recording_controller.cancel()

    def _on_recording_started(self):
        logger.debug("Recording started event received")
        # Starting fresh — abandon any retained retry audio from a previous
        # failed cycle so its file doesn't leak.
        self._abandon_retry_state()
        # Entering a continuous session if the user enabled it. Auto-continued
        # recordings also flow through here, but _continuous_active is already
        # True in that case (idempotent set).
        if self.config.output.continuous_mode:
            self._continuous_active = True
        # Sync streaming flag from config and start the streaming ASR client
        # before the recorder begins capturing, so no PCM chunks are lost.
        streaming = self.config.asr.streaming_enabled
        self.audio_recorder.streaming_enabled = streaming
        if streaming:
            if not self._start_streaming():
                # Streaming start failed — degrade to non-streaming so the
                # recording still works (frames are saved, transcribed later).
                self.audio_recorder.streaming_enabled = False
                self._show_toast(t("msg.streaming_fallback"))
        self._recording_controller.on_recording_started()
        # Override the bubble text to indicate live transcription.
        if self._streaming_transcriber is not None:
            self._status_bubble.show_status(t("status.streaming"))
            # Show the caption panel with a placeholder until the first
            # transcript fragment arrives.
            self._caption_panel.show_text(t("caption.listening"))
        else:
            self._caption_panel.dismiss()

    def _on_recording_stopped(self):
        if not self._recording_controller.stop_recording_event():
            return  # cancelled; UI already reset to idle
        context_before, context_after = self._recording_controller.cursor_context
        logger.debug(
            "Recording stopped — context: before=%d chars, after=%d chars",
            len(context_before),
            len(context_after),
        )
        if self._streaming_transcriber is not None:
            # Streaming mode: hand the transcriber to the worker, which will
            # finalize() it to collect the transcript. No recorder needed.
            self._processing_controller.start(
                context_before=context_before,
                context_after=context_after,
                streaming_transcriber=self._streaming_transcriber,
            )
        else:
            self._processing_controller.start(
                self.audio_recorder, context_before, context_after
            )

    def _capture_cursor_context(self, hwnd: int = 0) -> tuple[str, str]:
        """Capture text around the cursor for context-aware polishing.

        Returns empty strings when polishing is disabled (so the polisher
        falls back to standalone mode) or when capture fails for any reason —
        context is a best-effort enhancement, never a hard dependency.
        """
        if not self.config.polish.enabled:
            return ("", "")
        try:
            return get_cursor_context(hwnd)
        except Exception:
            return ("", "")

    # ---- processing progress + result handlers ----------------------------

    def _on_processing_progress(self, stage: str):
        """Update the status bubble with the current processing stage.

        When the polish stage begins, start the elapsed-time timer so the
        bubble shows "润色中... (5s)" during long LLM calls.
        """
        self._status_bubble.show_status(stage)
        if stage == t("status.polishing"):
            self._polish_start = time.monotonic()
            if not self._polish_timer.isActive():
                self._polish_timer.start()

    def _update_polish_elapsed(self):
        """Tick the polish elapsed-time display every second."""
        elapsed = int(time.monotonic() - self._polish_start)
        self._status_bubble.show_status(
            t("status.polishing") + f" ({elapsed}s)"
        )

    def _stop_polish_timer(self):
        """Stop the polish elapsed timer (called when processing finishes/fails)."""
        if self._polish_timer.isActive():
            self._polish_timer.stop()

    def _on_processing_done(self, refined_text: str):
        self._stop_polish_timer()
        self._caption_panel.dismiss()
        self._recording_controller.reset_after_processing()
        self._cleanup_streaming()
        # Success — the worker has already deleted the audio file. Clear
        # retry state and disable the tray menu entry.
        if self._retry_audio_path is not None:
            self._retry_audio_path = None
            self._retry_context = ("", "")
            self.tray.set_retry_available(False)

        if refined_text:
            logger.info("Processing done: %d chars", len(refined_text))
            self.history_store.add(refined_text)
            self._output_text_async(
                refined_text,
                self._recording_controller.saved_hwnd,
                continue_session=self._continuous_active,
            )
        elif self._continuous_active and not self._quitting:
            # Empty transcript: nothing to paste, but keep the continuous
            # session going so the user can re-dictate immediately.
            self._toggle_recording()

    def _output_text_async(self, text: str, hwnd: int, continue_session: bool = False) -> None:
        """Output text on a background thread — paste (auto_paste on) or copy
        to clipboard (auto_paste off) — so the pre-paste delay and keystroke
        sequence never block the UI thread.

        Unifies the paste and copy-only paths so both report completion via
        ``paste_finished``. When ``continue_session`` is True, also emits
        ``paste_continue_ready`` so the continuous-dictation loop restarts
        recording after the output lands. Window focus and keyboard injection
        are OS-level and thread-agnostic — the foreground restriction is
        handled via ``AttachThreadInput`` inside ``set_foreground_window``.

        Threads are tracked in ``_paste_threads`` so ``_quit`` can join them
        before Qt objects are destroyed, preventing a daemon-thread ctypes
        call from running against a torn-down window.
        """
        # Prune finished threads so the list doesn't grow unbounded.
        self._paste_threads = [t for t in self._paste_threads if t.is_alive()]

        def _work():
            if self.config.output.auto_paste:
                success = self.typer.output_text(text, hwnd)
            else:
                try:
                    pyperclip.copy(text)
                    success = True
                except Exception:
                    success = False
            self._paste_bridge.paste_finished.emit(success)
            if continue_session:
                self._paste_bridge.paste_continue_ready.emit(success)

        t = threading.Thread(target=_work, daemon=True)
        self._paste_threads.append(t)
        t.start()

    def _on_paste_finished(self, success: bool):
        """Handle paste/copy completion (invoked on the UI thread via signal).

        On failure, surface the paste-failed toast. Continuous-dictation
        restart is handled by the per-operation ``paste_continue_ready``
        signal (see ``_on_continue_ready``), which is only connected for
        processing-done outputs — history pastes never trigger a restart.
        """
        if not success:
            self._show_toast(t("msg.paste_failed_copied"))

    def _on_continue_ready(self, success: bool):
        """Handle per-operation continue signal (invoked on the UI thread).

        Only connected for processing-done outputs where ``continue_session``
        was True, so history pastes never reach this handler. On success,
        restart recording if the session is still active.
        """
        if success and self._continuous_active and not self._quitting:
            self._toggle_recording()

    def _on_silence_detected(self):
        """Handle VAD auto-stop (invoked on the UI thread via signal).

        Equivalent to the user pressing the toggle hotkey to stop: drives the
        UI through stop_recording, which emits recording_stopped and starts
        processing. Guarded so a stale signal that arrives after the user
        already stopped manually is a no-op.
        """
        if not self._recording_controller.is_recording:
            return
        logger.debug("VAD silence detected — auto-stopping recording")
        self._recording_controller.stop()

    def _on_processing_error(self, error_msg: str):
        self._stop_polish_timer()
        self._caption_panel.dismiss()
        logger.error("Processing error: %s", error_msg)
        self._cleanup_streaming()
        # A failure breaks the continuous loop — don't auto-restart on a
        # broken cycle. The user can retry, which doesn't resume the session.
        self._continuous_active = False
        # Retain the audio file for retry. On a normal-flow failure the
        # recorder still holds the path — take ownership so it survives
        # (cancel_during_processing no longer calls recorder.cleanup()).
        # On a retry-flow failure the recorder has nothing to take (the
        # path is already in _retry_audio_path); take returns None and the
        # existing retry state is preserved unchanged. On a streaming-flow
        # failure there is no audio file at all (streaming doesn't save).
        audio_path = self.audio_recorder.take_audio_path()
        if audio_path is not None:
            self._retry_audio_path = str(audio_path)
            self._retry_context = self._recording_controller.cursor_context
        self._recording_controller.cancel_during_processing(error_msg)
        retryable = self._retry_audio_path is not None
        self.tray.set_retry_available(retryable)
        hint = t("msg.error_retry_hint") if retryable else t("msg.error_format")
        # Use str.replace as a safe substitute for format_map — if the
        # translated string accidentally omits the ``{msg}`` placeholder,
        # the replacement is a no-op instead of a KeyError.
        formatted = hint.replace("{msg}", error_msg)
        self.tray.show_message(t("app.name"), formatted)

    def _retry_processing(self):
        """Re-run the last failed processing cycle using its retained audio.

        Reuses the saved audio file + cursor context so the user doesn't
        have to re-record. No-op if no retry state exists, or if a cycle is
        already running, or if a new recording is in progress.
        """
        if self._retry_audio_path is None:
            return
        if not os.path.exists(self._retry_audio_path):
            logger.warning("Retained audio file no longer exists: %s", self._retry_audio_path)
            self._abandon_retry_state()
            self._show_toast(t("msg.retry_unavailable"))
            return
        if self._processing_controller.is_running():
            return
        if self._recording_controller.is_recording:
            return
        logger.info("Retrying processing with retained audio: %s", self._retry_audio_path)
        context_before, context_after = self._retry_context
        # Drive the UI into PROCESSING — mirrors the transition the normal
        # stop path performs so the bubble + window reflect the retry.
        self.window.set_processing()
        self._status_bubble.show_status(t("status.processing"))
        self.tray.set_retry_available(False)
        self._processing_controller.start(
            audio_path=self._retry_audio_path,
            context_before=context_before,
            context_after=context_after,
        )

    def _abandon_retry_state(self):
        """Delete the retained retry audio file (if any) and clear the state.

        Called when the user starts a new recording (the old failed audio is
        no longer wanted) and at application quit (don't leak the file).
        """
        if self._retry_audio_path is None:
            return
        try:
            os.remove(self._retry_audio_path)
        except OSError:
            pass
        self._retry_audio_path = None
        self._retry_context = ("", "")
        self.tray.set_retry_available(False)

    # ---- streaming ASR -----------------------------------------------------

    def _start_streaming(self) -> bool:
        """Create and start a StreamingTranscriber for this recording cycle.

        Returns True on success. On failure the caller falls back to
        non-streaming mode.
        """
        asr = self.config.asr
        self._streaming_transcriber = StreamingTranscriber(
            api_key=asr.api_key,
            model=asr.model,
            base_url=asr.base_url,
            language=asr.language,
            sample_rate=self.config.recording.sample_rate,
            on_text_update=self._streaming_bridge.text_updated.emit,
            on_error=self._streaming_bridge.stream_error.emit,
        )
        if not self._streaming_transcriber.start():
            self._streaming_transcriber = None
            return False
        self.audio_recorder.on_audio_chunk = self._streaming_transcriber.send_audio
        return True

    def _on_streaming_text(self, text: str):
        """Update the caption panel and status bubble with the live transcript."""
        if not text:
            return
        logger.debug("Streaming text -> caption/bubble: %d chars: %r", len(text), text[:50])
        # Full transcript goes to the caption panel; the bubble keeps the
        # one-line truncated preview.
        self._caption_panel.show_text(text)
        display = text if len(text) <= 40 else text[:39] + "…"
        self._status_bubble.show_status(display)

    def _on_streaming_error(self, msg: str):
        """Log a streaming error (finalize will surface the empty result)."""
        logger.error("Streaming ASR error: %s", msg)

    def _cleanup_streaming(self):
        """Clear streaming state after a cycle completes (success or failure).

        The WebSocket itself is closed by ``StreamingTranscriber.finalize()``
        on the worker thread; here we just drop our references so the next
        cycle starts clean.
        """
        self._streaming_transcriber = None
        self.audio_recorder.on_audio_chunk = None

    # ---- dialogs & toast ---------------------------------------------------

    def _show_settings(self):
        if self._settings_dialog is None:
            self._settings_dialog = SettingsDialog(self.config, self.window)
            self._settings_dialog.settings_saved.connect(self._on_settings_saved)
            # Live theme preview: when the user changes the theme combo (or
            # Cancel restores it), re-skin the floating window + tray to match.
            self._settings_dialog.theme_changed.connect(self._on_theme_changed)
        self._settings_dialog.exec()

    def _on_theme_changed(self, mode: str):
        """Re-apply the active palette to the floating window and tray.

        The SettingsDialog already switched the global palette and re-skinned
        itself; this refreshes the persistent surfaces (floating window, tray,
        cached history dialog) which read the palette at paint/icon-build time.
        """
        self.window.apply_theme()
        self.tray.apply_theme()
        if self._history_dialog is not None:
            self._history_dialog.apply_theme()

    def _show_history(self):
        # Capture the target window BEFORE the (modal) dialog takes the
        # foreground, so a paste from history restores focus to where the
        # user actually wants the text — not back to the history dialog.
        self._history_target_hwnd = get_foreground_window()
        if self._history_dialog is None:
            self._history_dialog = HistoryDialog(self.history_store, self.window)
            self._history_dialog.paste_requested.connect(self._paste_history_text)
        else:
            self._history_dialog.reload()
        self._history_dialog.exec()

    def _paste_history_text(self, text: str):
        # Close the history dialog first so set_foreground_window can bring
        # the real target back to the front; otherwise the modal dialog would
        # be the foreground window and the paste would land inside it.
        if self._history_dialog is not None:
            self._history_dialog.accept()
        target_hwnd = self._history_target_hwnd or get_foreground_window()
        self._output_text_async(text, target_hwnd)

    def _show_toast(self, message: str):
        toast = Toast(message, parent=self.window)
        self._toasts.add(toast)
        toast.show()

    def _on_settings_saved(self):
        """Reload config and update hotkeys."""
        logger.info("Settings saved — reloading config and caches")
        init_language(self.config.language)
        self.hotkey_manager.stop()
        binding = HotkeyBinding.from_string(self.config.hotkey.toggle_hotkey)
        self.hotkey_manager.set_binding(binding)
        if self.config.hotkey.toggle_enabled:
            self.hotkey_manager.start()
        self.audio_recorder.sample_rate = self.config.recording.sample_rate
        self.audio_recorder.denoise_enabled = self.config.recording.denoise_enabled
        self.audio_recorder.denoise_strength = self.config.recording.denoise_strength
        self.audio_recorder.vad_enabled = self.config.recording.vad_enabled
        self.audio_recorder.vad_silence_duration_ms = self.config.recording.vad_silence_duration_ms
        self.audio_recorder.vad_threshold = self.config.recording.vad_threshold
        self.audio_recorder.streaming_enabled = self.config.asr.streaming_enabled
        self.audio_recorder.device = self.config.recording.device
        self.window.retranslate()
        self.tray.retranslate()
        self.tray.apply_config(self.config)
        if self._history_dialog is not None:
            self._history_dialog.retranslate()
        # API keys / base URLs / models may have changed — drop cached API
        # clients so the next cycle rebuilds them with fresh settings.
        from voicetype.processing import invalidate_clients
        invalidate_clients()
        # Glossary may have changed — drop cached compiled regex.
        from voicetype.glossary import invalidate_glossary_cache
        invalidate_glossary_cache()
        self._settings_dialog = None
        self._show_toast(t("msg.settings_saved"))

    # ---- window / quit / sync ---------------------------------------------

    def _show_window(self):
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def _quit(self):
        if self._quitting:
            return
        self._quitting = True
        logger.info("Application quitting")
        self._continuous_active = False
        self.hotkey_manager.stop()
        self._audio_level_timer.stop()
        self._polish_timer.stop()
        # Wait for any in-flight paste thread to finish before we tear down
        # Qt objects. Each paste has a bounded timeout (window_manager retries
        # cap at ~2.5 s), so a short join is sufficient; pasted is True after
        # TextTyper sets clipboard (early exit before window focus retries).
        for t in self._paste_threads:
            t.join(timeout=3.0)
        self._flush_config_save()
        self._abandon_retry_state()
        self.audio_recorder.stop()
        self.audio_recorder.cleanup()
        self._processing_controller.shutdown()
        self.history_store.shutdown()
        self._caption_panel.dismiss()
        self.tray.hide()
        self.window.close()
        # Give Qt's event loop a brief window to flush the quit. If the
        # tray icon (or anything else) keeps the process alive past this,
        # force-exit so the process does not hang after the window is gone.
        # Use sys.exit (not os._exit) so atexit handlers, finally blocks and
        # buffered I/O (config / history writes) still get a chance to flush.
        QTimer.singleShot(3000, lambda: sys.exit(0))
        self.app.quit()

    def _sync_audio_level(self):
        """Copy recorder level into the UI on the Qt thread."""
        self.window.refresh_recording_indicators(self.audio_recorder.input_level)

    # ---- quick settings ----------------------------------------------------

    def _save_quick_settings(self):
        # Update in-memory state and the live UI immediately (cheap), but
        # debounce the disk write so rapid tray toggles coalesce into a
        # single config.json write instead of one per click.
        self.tray.apply_config(self.config)
        self.typer.config = self.config
        self._schedule_config_save()

    def _schedule_config_save(self):
        """Coalesce rapid config changes into a single delayed disk write."""
        timer = getattr(self, "_config_save_timer", None)
        if timer is None:
            timer = QTimer()
            timer.setSingleShot(True)
            timer.setInterval(500)
            timer.timeout.connect(self.config.save)
            self._config_save_timer = timer
        timer.start()

    def _flush_config_save(self):
        """Write config now if a debounced save is pending (call at quit)."""
        timer = getattr(self, "_config_save_timer", None)
        if timer is not None and timer.isActive():
            timer.stop()
            self.config.save()

    def _set_auto_paste(self, enabled: bool):
        self.config.output.auto_paste = enabled
        self._save_quick_settings()

    def _set_polish_enabled(self, enabled: bool):
        self.config.polish.enabled = enabled
        self._save_quick_settings()

    def _set_paste_mode(self, mode: str):
        self.config.output.paste_mode = mode
        self._save_quick_settings()

    def _set_asr_language(self, language: str):
        self.config.asr.language = language
        self._save_quick_settings()

    def _set_continuous_mode(self, enabled: bool):
        self.config.output.continuous_mode = enabled
        if not enabled:
            # Turning off continuous mode ends any active session - the
            # current cycle finishes but no new recording auto-starts.
            self._continuous_active = False
        self._save_quick_settings()

    # ---- entry point -------------------------------------------------------

    def run(self):
        sys.exit(self.app.exec())


def _ensure_single_instance() -> bool:
    """Ensure only one VoiceType process is running.

    Uses a Windows named mutex. Returns True if this is the first instance,
    False if another instance is already running.

    When a second instance is detected, it signals a named event so the first
    instance can bring its window to the foreground.
    """
    mutex_name = "Global\\VoiceType_SingleInstance"
    kernel32 = ctypes.windll.kernel32
    # CreateMutex returns the handle on success, or NULL on failure.
    # If the mutex already exists, GetLastError returns ERROR_ALREADY_EXISTS.
    ERROR_ALREADY_EXISTS = 183
    handle = kernel32.CreateMutexW(None, False, mutex_name)
    if not handle:
        return True  # allow the app to run anyway
    last_error = kernel32.GetLastError()
    if last_error == ERROR_ALREADY_EXISTS:
        # Signal the named event so the first instance shows its window.
        event_name = "Global\\VoiceType_ShowWindow"
        event_handle = kernel32.OpenEventW(0x0002, False, event_name)  # EVENT_MODIFY_STATE
        if event_handle:
            kernel32.SetEvent(event_handle)
            kernel32.CloseHandle(event_handle)
        return False
    return True


def _start_show_window_watcher(callback) -> None:
    """Watch for the show-window signal from a second instance.

    Runs a background daemon thread that blocks on a named event. When a
    second process signals the event, ``callback`` is invoked on the Qt main
    thread. The cross-thread handoff uses a Qt signal (the correct mechanism —
    emitted on the worker thread, delivered queued to the bridge's thread)
    rather than ``QTimer.singleShot``, which is thread-affine and would not
    fire from a thread without a running event loop.
    """
    event_name = "Global\\VoiceType_ShowWindow"
    kernel32 = ctypes.windll.kernel32
    # Create an event the second instance can signal.
    event_handle = kernel32.CreateEventW(None, False, False, event_name)
    if not event_handle:
        return

    # QObject living on the calling (UI) thread; its signal is connected to the
    # callback, so emitting it from the watcher thread marshals the call via a
    # queued connection to the UI thread.
    class _Bridge(QObject):
        triggered = Signal()

    bridge = _Bridge()
    bridge.triggered.connect(callback)

    INFINITE = 0xFFFFFFFF

    def _watch():
        while True:
            result = kernel32.WaitForSingleObject(event_handle, INFINITE)
            if result == 0:  # WAIT_OBJECT_0 — event signaled
                bridge.triggered.emit()
            else:
                break

    threading.Thread(target=_watch, daemon=True).start()


def main():
    setup_logging()
    logger.info("Voice Type starting (pid=%s)", os.getpid())
    if not _ensure_single_instance():
        logger.info("Another instance is already running — exiting")
        sys.exit(0)
    app = Application()
    _start_show_window_watcher(app._show_window)
    app.run()


if __name__ == "__main__":
    main()
