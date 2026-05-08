"""Voice Type — Entry point and application orchestrator."""

import logging
import os
import sys
import ctypes
import pyperclip
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QThread, Signal, QObject
from src.config import AppConfig
from src.audio import AudioRecorder
from src.asr import Transcriber
from src.history import HistoryStore
from src.polisher import TextPolisher
from src.typer import TextTyper
from src.window_manager import get_foreground_window
from src.ui.main_window import FloatingRecordingWindow, Toast, StatusBubble
from src.ui.history_dialog import HistoryDialog
from src.ui.settings_dialog import SettingsDialog
from src.ui.system_tray import TrayIcon, HotkeyManager
from src.i18n import init_language, t

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

user32 = ctypes.windll.user32
SW_SHOWNA = 4  # Show window without activating


class ProcessingWorker(QObject):
    """Background worker for ASR + LLM processing."""

    started = Signal()
    finished = Signal(str)  # refined text
    error = Signal(str)

    def __init__(self, config: AppConfig, audio_path: str):
        super().__init__()
        self.config = config
        self.audio_path = audio_path

    def run(self):
        try:
            self.started.emit()
            transcriber = Transcriber(self.config)
            transcript = transcriber.transcribe(self.audio_path)
            # Delete audio file immediately after STT
            try:
                os.remove(self.audio_path)
                logger.info("Deleted temp audio: %s", self.audio_path)
            except OSError as e:
                logger.warning("Failed to delete audio: %s", e)
            if not transcript:
                self.finished.emit("")
                return
            polisher = TextPolisher(self.config)
            refined = polisher.polish(transcript)
            self.finished.emit(refined)
        except Exception as e:
            logger.exception("Processing failed")
            self.error.emit(str(e))


class Application:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("Voice Type")
        self.app.setQuitOnLastWindowClosed(False)

        self.config = AppConfig.load()
        init_language(self.config.language)
        self.audio_recorder = AudioRecorder(self.config.recording.sample_rate)
        self.typer = TextTyper(self.config)
        self.history_store = HistoryStore()
        self._processing_thread = None
        self._processing_worker = None
        self._saved_hwnd = 0
        self._cancelled = False
        self._quitting = False

        self._init_ui()

        # Check config on first launch — show settings if no API key is set
        if not self.config.is_configured():
            logger.info("No API key configured, showing settings dialog")
            self._show_settings()

        self._init_hotkey()

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
        self.tray.quit_requested.connect(self._quit)
        self.tray.show()

        # Settings dialog (lazy)
        self._settings_dialog = None
        self._history_dialog = None

        # Status bubble (persistent bubble during recording/processing)
        self._status_bubble = StatusBubble()

        if self.config.window.show_on_start:
            self._show_window()

    def _init_hotkey(self):
        self.hotkey_manager = HotkeyManager(self.window)
        self.hotkey_manager.toggle_recording.connect(self._toggle_recording)
        self.hotkey_manager.cancel_recording.connect(self._cancel_recording)
        self.window.set_hotkey_manager(self.hotkey_manager)
        if self.config.hotkey.toggle_enabled:
            self.hotkey_manager.start()

    def _cancel_recording(self):
        """Cancel recording and delete audio file."""
        self._cancelled = True
        if self.window.is_recording():
            self.window.stop_recording()
        else:
            self.audio_recorder.cleanup()
            self.tray.set_recording(False)
            self.window.set_done()
        logger.info("Recording cancelled by hotkey")

    def _toggle_recording(self):
        if self.window.is_recording():
            self.window.stop_recording()
        else:
            self.window.start_recording()

    def _on_recording_started(self):
        """User started recording — save foreground window."""
        self._saved_hwnd = get_foreground_window()
        self.audio_recorder.start()
        self.tray.set_recording(True)
        logger.info("Recording started, saved hwnd=%s", self._saved_hwnd)

        # Show persistent status bubble
        self._status_bubble.show_status(t("status.recording"))

    def _on_recording_stopped(self):
        """User stopped recording — process audio and output text."""
        self.audio_recorder.stop()
        self.tray.set_recording(False)

        if self._cancelled:
            self._cancelled = False
            self.audio_recorder.cleanup()
            self._status_bubble.dismiss()
            self.window.set_done()
            logger.info("Recording cancelled, skipping processing")
            return

        self.window.set_processing()

        # Update bubble text to show processing status
        self._status_bubble.show_status(t("status.polishing"))

        # Show the window WITHOUT stealing focus from the target window.
        # Only do this if the window was already visible (user didn't hide it).
        # SW_SHOWNA = show without activating. This keeps the original
        # foreground window intact so SetForegroundWindow succeeds later.
        if self.window.isVisible():
            user32.ShowWindow(int(self.window.winId()), SW_SHOWNA)

        # Save audio and process in background thread
        try:
            audio_path = self.audio_recorder.save()
        except ValueError:
            self.window.set_error(t("error.no_audio"))
            self.tray.show_message(t("error.title"), t("error.no_audio_detail"))
            self.window.show()
            self._status_bubble.dismiss()
            return

        self._start_processing(audio_path)

    def _start_processing(self, audio_path: str):
        """Run ASR + LLM in a background thread."""
        self._processing_thread = QThread()
        self._processing_worker = ProcessingWorker(self.config, str(audio_path))
        self._processing_worker.moveToThread(self._processing_thread)

        self._processing_thread.started.connect(self._processing_worker.run)
        self._processing_worker.finished.connect(self._on_processing_done)
        self._processing_worker.error.connect(self._on_processing_error)
        self._processing_worker.finished.connect(self._processing_thread.quit)
        self._processing_worker.error.connect(self._processing_thread.quit)
        self._processing_thread.finished.connect(self._processing_worker.deleteLater)
        self._processing_thread.finished.connect(self._processing_thread.deleteLater)

        self._processing_thread.start()

    def _on_processing_done(self, refined_text: str):
        """Processing complete — output text to cursor."""
        logger.info("Processing done, refined text: %s", refined_text[:50] if refined_text else "(empty)")

        # Dismiss the status bubble
        self._status_bubble.dismiss()

        if refined_text:
            self.history_store.add(refined_text)
            if self.config.output.auto_paste:
                pasted = self.typer.output_text(refined_text, self._saved_hwnd)
                if not pasted:
                    self._show_toast(t("msg.paste_failed_copied"))
            else:
                pyperclip.copy(refined_text)

        # Cleanup temp audio and reset to idle
        self.audio_recorder.cleanup()
        self.window.set_done()

    def _on_processing_error(self, error_msg: str):
        """Processing failed."""
        self._status_bubble.dismiss()
        self.window.set_error(error_msg)
        self.tray.show_message(t("app.name"), t("msg.error_format").format(msg=error_msg))
        self.audio_recorder.cleanup()

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
        self._toast = Toast(message, parent=self.window)
        self._toast.show()

    def _on_settings_saved(self):
        """Reload config and update hotkeys."""
        init_language(self.config.language)
        self.hotkey_manager.stop()
        if self.config.hotkey.toggle_enabled:
            self.hotkey_manager.start()
        self.audio_recorder.sample_rate = self.config.recording.sample_rate
        self.window.retranslate()
        self.tray.retranslate()
        if self._history_dialog is not None:
            self._history_dialog.retranslate()
        # Invalidate cached dialog so it's recreated with new language next time
        self._settings_dialog = None
        # Show toast from main window (which is guaranteed to be alive)
        self._show_toast(t("msg.settings_saved"))

    def _show_window(self):
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def _quit(self):
        if self._quitting:
            return
        self._quitting = True
        logger.info("Quitting application")
        self.hotkey_manager.stop()
        self.audio_recorder.stop()
        self.audio_recorder.cleanup()
        try:
            if self._processing_thread and self._processing_thread.isRunning():
                self._processing_thread.quit()
                self._processing_thread.wait(1000)
        except RuntimeError:
            pass
        finally:
            self._processing_thread = None
            self._processing_worker = None
        self.tray.hide()
        self.window.close()
        self.app.quit()
        # Force exit — Qt tray icon can keep process alive after quit()
        os._exit(0)

    def run(self):
        sys.exit(self.app.exec())


def main():
    app = Application()
    app.run()


if __name__ == "__main__":
    main()
