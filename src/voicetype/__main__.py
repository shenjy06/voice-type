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
from voicetype.typer import TextTyper
from voicetype.ui.history_dialog import HistoryDialog
from voicetype.ui.main_window import FloatingRecordingWindow, StatusBubble, Toast
from voicetype.ui.settings_dialog import SettingsDialog
from voicetype.ui.system_tray import HotkeyManager, TrayIcon
from voicetype.window_manager import get_foreground_window
from voicetype.i18n import init_language, t

logger = logging.getLogger(__name__)


class _PasteBridge(QObject):
    """Marshals a background-thread paste failure to the UI thread.

    Qt signals are the correct cross-thread mechanism here: a signal emitted
    from the paste worker thread is delivered to this object's thread (the UI
    thread) via a queued connection. ``QTimer.singleShot`` cannot be used from
    a worker thread because timers are thread-affine and the worker has no
    event loop.
    """

    paste_failed = Signal()


class _SilenceBridge(QObject):
    """Marshals the VAD silence event from the audio thread to the UI thread.

    ``AudioRecorder.on_silence`` is invoked on sounddevice's audio callback
    thread; emitting this signal from there delivers it queued to this
    object's thread (the UI thread), where stopping the recording is safe.
    Same pattern as :class:`_PasteBridge`.
    """

    silence_detected = Signal()


class Application:
    """Top-level orchestrator. Delegates stateful work to controllers."""

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
        self.audio_recorder = AudioRecorder(
            self.config.recording.sample_rate,
            denoise_enabled=self.config.recording.denoise_enabled,
            denoise_strength=self.config.recording.denoise_strength,
            vad_enabled=self.config.recording.vad_enabled,
            vad_silence_duration_ms=self.config.recording.vad_silence_duration_ms,
            vad_threshold=self.config.recording.vad_threshold,
        )
        self.typer = TextTyper(self.config)
        self.history_store = HistoryStore()
        self._quitting = False
        # Track paste threads so we can join them at quit, preventing
        # ctypes calls from daemon threads after Qt objects are destroyed.
        self._paste_threads: list[threading.Thread] = []
        logger.info("Application initialized (configured=%s)", self.config.is_configured())

        # Audio-level sync timer — owned at Application level so it can be
        # stopped at quit even if the controller has been torn down.
        self._audio_level_timer = QTimer()
        self._audio_level_timer.setInterval(100)
        self._audio_level_timer.timeout.connect(self._sync_audio_level)

        # Keep references to active toasts so they aren't GC'd mid-animation.
        # Toasts auto-remove themselves via their destroyed signal.
        self._toasts = []

        # Bridge for marshaling background-thread paste failures to the UI
        # thread (created here so it lives on the UI/main thread).
        self._paste_bridge = _PasteBridge()
        self._paste_bridge.paste_failed.connect(self._on_paste_failed)

        # Bridge for marshaling VAD silence detection from the audio thread to
        # the UI thread. The recorder invokes ``on_silence`` on its callback
        # thread; the signal is delivered queued here so we can stop the
        # recording on the UI thread (same path as the user pressing stop).
        self._silence_bridge = _SilenceBridge()
        self._silence_bridge.silence_detected.connect(self._on_silence_detected)
        self.audio_recorder.on_silence = self._silence_bridge.silence_detected.emit

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
            if self.config.asr.api_key:
                try:
                    get_transcriber(self.config).warmup()
                except Exception:
                    pass
            if self.config.polish.api_key:
                try:
                    get_polisher(self.config).warmup()
                except Exception:
                    pass

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
        self.tray.auto_paste_toggled.connect(self._set_auto_paste)
        self.tray.polish_toggled.connect(self._set_polish_enabled)
        self.tray.paste_mode_changed.connect(self._set_paste_mode)
        self.tray.asr_language_changed.connect(self._set_asr_language)
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
        self._recording_controller.cancel()

    def _on_recording_started(self):
        logger.debug("Recording started event received")
        self._recording_controller.on_recording_started()

    def _on_recording_stopped(self):
        if not self._recording_controller.stop_recording_event():
            return  # cancelled; UI already reset to idle
        context_before, context_after = self._recording_controller.cursor_context
        logger.debug(
            "Recording stopped — context: before=%d chars, after=%d chars",
            len(context_before),
            len(context_after),
        )
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

    # ---- processing result handlers ---------------------------------------

    def _on_processing_done(self, refined_text: str):
        self._recording_controller.reset_after_processing()

        if refined_text:
            logger.info("Processing done: %d chars", len(refined_text))
            self.history_store.add(refined_text)
            if self.config.output.auto_paste:
                self._paste_async(refined_text, self._recording_controller.saved_hwnd)
            else:
                logger.debug("Auto-paste disabled — copying to clipboard only")
                # Copy on a background thread: clipboard contention (another
                # app holding the clipboard open) can make pyperclip.copy block
                # for hundreds of ms, which would freeze the UI thread.
                threading.Thread(
                    target=pyperclip.copy, args=(refined_text,), daemon=True
                ).start()

    def _paste_async(self, text: str, hwnd: int) -> None:
        """Paste text on a background thread so the pre-paste delay and the
        keystroke sequence never block the UI thread.

        Window focus (``set_foreground_window``) and keyboard injection
        (``keybd_event``) are OS-level and thread-agnostic — the foreground
        restriction is handled via ``AttachThreadInput`` inside
        ``set_foreground_window``. A paste failure is surfaced as a toast,
        marshaled back to the UI thread via the ``_paste_bridge`` signal.

        Threads are tracked in ``_paste_threads`` so ``_quit`` can join them
        before Qt objects are destroyed, preventing a daemon-thread ctypes
        call from running against a torn-down window.
        """
        # Prune finished threads so the list doesn't grow unbounded.
        self._paste_threads = [t for t in self._paste_threads if t.is_alive()]

        def _work():
            pasted = self.typer.output_text(text, hwnd)
            if not pasted:
                self._paste_bridge.paste_failed.emit()

        t = threading.Thread(target=_work, daemon=True)
        self._paste_threads.append(t)
        t.start()

    def _on_paste_failed(self):
        """Show the paste-failed toast (invoked on the UI thread via signal)."""
        self._show_toast(t("msg.paste_failed_copied"))

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
        logger.error("Processing error: %s", error_msg)
        self._recording_controller.cancel_during_processing(error_msg)
        self.tray.show_message(t("app.name"), t("msg.error_format").format(msg=error_msg))

    # ---- dialogs & toast ---------------------------------------------------

    def _show_settings(self):
        if self._settings_dialog is None:
            self._settings_dialog = SettingsDialog(self.config, self.window)
            self._settings_dialog.settings_saved.connect(self._on_settings_saved)
        self._settings_dialog.exec()

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
        if self.config.output.auto_paste:
            self._paste_async(text, target_hwnd)
        else:
            # Background thread — see _on_processing_done for rationale.
            threading.Thread(
                target=pyperclip.copy, args=(text,), daemon=True
            ).start()

    def _show_toast(self, message: str):
        toast = Toast(message, parent=self.window)

        def _on_destroyed():
            if toast in self._toasts:
                self._toasts.remove(toast)

        toast.destroyed.connect(_on_destroyed)
        self._toasts.append(toast)
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
        self.hotkey_manager.stop()
        self._audio_level_timer.stop()
        # Wait for any in-flight paste thread to finish before we tear down
        # Qt objects. Each paste has a bounded timeout (window_manager retries
        # cap at ~2.5 s), so a short join is sufficient; pasted is True after
        # TextTyper sets clipboard (early exit before window focus retries).
        for t in self._paste_threads:
            t.join(timeout=3.0)
        self._flush_config_save()
        self.audio_recorder.stop()
        self.audio_recorder.cleanup()
        self._processing_controller.shutdown()
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
    import threading

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
