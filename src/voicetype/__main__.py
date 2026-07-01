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

import os
import sys

import ctypes
import pyperclip
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

from voicetype.audio import AudioRecorder, cleanup_stale_audio
from voicetype.config import AppConfig
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

class Application:
    """Top-level orchestrator. Delegates stateful work to controllers."""

    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("Voice Type")
        self.app.setQuitOnLastWindowClosed(False)

        # Clean up stale audio files from previous sessions
        cleanup_stale_audio()

        self.config = AppConfig.load()
        init_language(self.config.language)
        self.audio_recorder = AudioRecorder(self.config.recording.sample_rate)
        self.typer = TextTyper(self.config)
        self.history_store = HistoryStore()
        self._quitting = False

        # Audio-level sync timer — owned at Application level so it can be
        # stopped at quit even if the controller has been torn down.
        self._audio_level_timer = QTimer()
        self._audio_level_timer.setInterval(100)
        self._audio_level_timer.timeout.connect(self._sync_audio_level)

        # Keep references to active toasts so they aren't GC'd mid-animation.
        # Toasts auto-remove themselves via their destroyed signal.
        self._toasts = []

        self._init_ui()
        self._init_controllers()

        # Check config on first launch — show settings if no API key is set
        if not self.config.is_configured():
            self._show_settings()

        self._init_hotkey()

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
        )
        self._processing_controller = ProcessingController(
            config=self.config,
            on_done=self._on_processing_done,
            on_error=self._on_processing_error,
            parent=self.app,
        )

    def _init_hotkey(self):
        self.hotkey_manager = HotkeyManager(self.window)
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
        self._recording_controller.on_recording_started()

    def _on_recording_stopped(self):
        audio_path = self._recording_controller.stop_recording_event(
            on_no_audio=lambda: None,  # legacy hook unused; UI surfaces error below
            on_save_error=self._on_recording_save_error,
        )
        if audio_path is None:
            return  # either cancelled or save failed; error UI was shown
        self._processing_controller.start(audio_path)

    def _on_recording_save_error(self):
        self.window.set_error(t("error.no_audio"))
        self.tray.show_message(t("error.title"), t("error.no_audio_detail"))
        self.window.show()

    # ---- processing result handlers ---------------------------------------

    def _on_processing_done(self, refined_text: str):
        self._recording_controller.reset_after_processing()

        if refined_text:
            self.history_store.add(refined_text)
            if self.config.output.auto_paste:
                pasted = self.typer.output_text(refined_text, self._recording_controller.saved_hwnd)
                if not pasted:
                    self._show_toast(t("msg.paste_failed_copied"))
            else:
                pyperclip.copy(refined_text)

    def _on_processing_error(self, error_msg: str):
        self._recording_controller.cancel_during_processing(error_msg)
        self.tray.show_message(t("app.name"), t("msg.error_format").format(msg=error_msg))

    # ---- dialogs & toast ---------------------------------------------------

    def _show_settings(self):
        if self._settings_dialog is None:
            self._settings_dialog = SettingsDialog(self.config, self.window)
            self._settings_dialog.settings_saved.connect(self._on_settings_saved)
        self._settings_dialog.exec()

    def _show_history(self):
        if self._history_dialog is None:
            self._history_dialog = HistoryDialog(self.history_store, self.window)
            self._history_dialog.paste_requested.connect(self._paste_history_text)
        else:
            self._history_dialog.reload()
        self._history_dialog.exec()

    def _paste_history_text(self, text: str):
        if self.config.output.auto_paste:
            pasted = self.typer.output_text(text, get_foreground_window())
            if not pasted:
                self._show_toast(t("msg.paste_failed_copied"))
        else:
            pyperclip.copy(text)

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
        init_language(self.config.language)
        self.hotkey_manager.stop()
        if self.config.hotkey.toggle_enabled:
            self.hotkey_manager.start()
        self.audio_recorder.sample_rate = self.config.recording.sample_rate
        self.window.retranslate()
        self.tray.retranslate()
        self.tray.apply_config(self.config)
        if self._history_dialog is not None:
            self._history_dialog.retranslate()
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
        self.hotkey_manager.stop()
        self._audio_level_timer.stop()
        self.audio_recorder.stop()
        self.audio_recorder.cleanup()
        self._processing_controller.shutdown()
        self.tray.hide()
        self.window.close()
        # Give Qt's event loop a brief window to flush the quit. If the
        # tray icon (or anything else) keeps the process alive past this,
        # force-exit so the process does not hang after the window is gone.
        QTimer.singleShot(3000, lambda: os._exit(0))
        self.app.quit()

    def _sync_audio_level(self):
        """Copy recorder level into the UI on the Qt thread."""
        self.window.set_audio_level(self.audio_recorder.input_level)

    # ---- quick settings ----------------------------------------------------

    def _save_quick_settings(self):
        self.config.save()
        self.tray.apply_config(self.config)
        self.typer.config = self.config

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
    second process signals the event, *callback* is invoked on the Qt main
    thread via QTimer.singleShot.
    """
    import threading

    event_name = "Global\\VoiceType_ShowWindow"
    kernel32 = ctypes.windll.kernel32
    # Create an event the second instance can signal.
    event_handle = kernel32.CreateEventW(None, False, False, event_name)
    if not event_handle:
        return

    INFINITE = 0xFFFFFFFF

    def _watch():
        while True:
            result = kernel32.WaitForSingleObject(event_handle, INFINITE)
            if result == 0:  # WAIT_OBJECT_0 — event signaled
                QTimer.singleShot(0, callback)
            else:
                break

    threading.Thread(target=_watch, daemon=True).start()


def main():
    if not _ensure_single_instance():
        sys.exit(0)
    app = Application()
    _start_show_window_watcher(app._show_window)
    app.run()


if __name__ == "__main__":
    main()
