"""Tests for voice_type.__main__ — ProcessingWorker and Application."""


class TestProcessingWorker:
    def test_success_path(self, qtbot, mocker):
        """Successful processing emits finished with refined text."""
        from src.__main__ import ProcessingWorker

        # Mock Transcriber and TextPolisher
        mock_transcriber = mocker.patch("src.__main__.Transcriber")
        mock_transcriber.return_value.transcribe.return_value = "hello world"
        mock_polisher = mocker.patch("src.__main__.TextPolisher")
        mock_polisher.return_value.polish.return_value = "Hello, world!"
        mocker.patch("os.remove")

        cfg = mocker.MagicMock()
        worker = ProcessingWorker(cfg, "/tmp/audio.wav")

        signals = {"started": False, "finished_text": None}

        def on_started():
            signals["started"] = True

        def on_finished(text):
            signals["finished_text"] = text

        worker.started.connect(on_started)
        worker.finished.connect(on_finished)
        worker.run()

        assert signals["started"] is True
        assert signals["finished_text"] == "Hello, world!"

    def test_empty_transcript_emits_finished_empty(self, qtbot, mocker):
        """Empty transcript emits finished with empty string (no error)."""
        from src.__main__ import ProcessingWorker

        mock_transcriber = mocker.patch("src.__main__.Transcriber")
        mock_transcriber.return_value.transcribe.return_value = ""
        mocker.patch("os.remove")

        cfg = mocker.MagicMock()
        worker = ProcessingWorker(cfg, "/tmp/audio.wav")

        finished_text = None

        def on_finished(text):
            nonlocal finished_text
            finished_text = text

        worker.finished.connect(on_finished)
        worker.run()

        assert finished_text == ""

    def test_polish_disabled_returns_transcript(self, qtbot, mocker):
        """When polish is disabled, ASR text is returned directly."""
        from src.__main__ import ProcessingWorker
        from src.config import GlossaryEntry

        mock_transcriber = mocker.patch("src.__main__.Transcriber")
        mock_transcriber.return_value.transcribe.return_value = "raw 派森 text"
        mock_polisher = mocker.patch("src.__main__.TextPolisher")
        mocker.patch("os.remove")

        cfg = mocker.MagicMock()
        cfg.polish.enabled = False
        cfg.glossary = [GlossaryEntry(source="派森", replacement="Python")]
        worker = ProcessingWorker(cfg, "/tmp/audio.wav")

        finished_text = None

        def on_finished(text):
            nonlocal finished_text
            finished_text = text

        worker.finished.connect(on_finished)
        worker.run()

        assert finished_text == "raw Python text"
        mock_polisher.assert_not_called()

    def test_glossary_applied_before_polish(self, qtbot, mocker):
        from src.__main__ import ProcessingWorker
        from src.config import GlossaryEntry

        mock_transcriber = mocker.patch("src.__main__.Transcriber")
        mock_transcriber.return_value.transcribe.return_value = "学习派森"
        mock_polisher = mocker.patch("src.__main__.TextPolisher")
        mock_polisher.return_value.polish.return_value = "学习 Python"
        mocker.patch("os.remove")

        cfg = mocker.MagicMock()
        cfg.polish.enabled = True
        cfg.glossary = [GlossaryEntry(source="派森", replacement="Python")]
        worker = ProcessingWorker(cfg, "/tmp/audio.wav")

        worker.finished.connect(lambda text: None)
        worker.run()

        mock_polisher.return_value.polish.assert_called_once_with("学习Python")

    def test_exception_emits_error(self, qtbot, mocker):
        """Exception in processing emits error signal."""
        from src.__main__ import ProcessingWorker

        mock_transcriber = mocker.patch("src.__main__.Transcriber")
        mock_transcriber.return_value.transcribe.side_effect = RuntimeError("API timeout")

        cfg = mocker.MagicMock()
        worker = ProcessingWorker(cfg, "/tmp/audio.wav")

        error_msg = None

        def on_error(msg):
            nonlocal error_msg
            error_msg = msg

        worker.error.connect(on_error)
        worker.run()

        assert "API timeout" in error_msg

    def test_deletes_audio_after_stt(self, qtbot, mocker):
        """Audio file is deleted after STT."""
        from src.__main__ import ProcessingWorker

        mock_transcriber = mocker.patch("src.__main__.Transcriber")
        mock_transcriber.return_value.transcribe.return_value = "text"
        mock_polisher = mocker.patch("src.__main__.TextPolisher")
        mock_polisher.return_value.polish.return_value = "refined"
        mock_remove = mocker.patch("os.remove")

        cfg = mocker.MagicMock()
        worker = ProcessingWorker(cfg, "/tmp/test_audio.wav")

        worker.finished.connect(lambda t: None)
        worker.run()

        mock_remove.assert_called_once_with("/tmp/test_audio.wav")

    def test_audio_deletion_failure_logs_warning(self, qtbot, mocker, caplog):
        """Failed audio deletion logs a warning but continues."""
        from src.__main__ import ProcessingWorker

        mock_transcriber = mocker.patch("src.__main__.Transcriber")
        mock_transcriber.return_value.transcribe.return_value = "text"
        mock_polisher = mocker.patch("src.__main__.TextPolisher")
        mock_polisher.return_value.polish.return_value = "refined"
        mocker.patch("os.remove", side_effect=OSError("Permission denied"))

        cfg = mocker.MagicMock()
        worker = ProcessingWorker(cfg, "/tmp/audio.wav")

        worker.finished.connect(lambda t: None)
        worker.run()

        # Processing continues despite deletion failure
        assert "Failed to delete audio" in caplog.text


class TestApplication:
    def _make_application(self, qtbot, mocker, is_configured=True):
        """Create an Application with all dependencies mocked."""
        mocker.patch("src.__main__.QApplication")
        mock_config = mocker.patch("src.__main__.AppConfig")
        mock_cfg = mocker.MagicMock(
            recording=mocker.MagicMock(sample_rate=16000),
            output=mocker.MagicMock(auto_paste=True, paste_delay_ms=300, paste_mode="auto"),
            polish=mocker.MagicMock(enabled=True),
            asr=mocker.MagicMock(language="auto"),
            window=mocker.MagicMock(show_on_start=False, always_on_top=True),
            hotkey=mocker.MagicMock(toggle_enabled=True),
        )
        mock_cfg.is_configured.return_value = is_configured
        mock_config.load.return_value = mock_cfg

        mocker.patch("src.__main__.AudioRecorder")
        mocker.patch("src.__main__.TextTyper")
        mocker.patch("src.__main__.HistoryStore")
        mocker.patch("src.__main__.FloatingRecordingWindow")
        mocker.patch("src.__main__.TrayIcon")
        mocker.patch("src.__main__.HotkeyManager")

        from src.__main__ import Application
        app = Application()
        return app

    def test_on_recording_stopped_cancelled_skips_processing(self, qtbot, mocker):
        app = self._make_application(qtbot, mocker)
        app._cancelled = True
        app.audio_recorder.stop = mocker.MagicMock()
        app.audio_recorder.cleanup = mocker.MagicMock()
        app.tray.set_recording = mocker.MagicMock()

        app._on_recording_stopped()

        assert app._cancelled is False  # flag reset
        app.audio_recorder.cleanup.assert_called_once()
        app.window.set_done.assert_called_once()

    def test_on_recording_stopped_save_valueerror_shows_error(self, qtbot, mocker):
        app = self._make_application(qtbot, mocker)
        app._cancelled = False
        app.audio_recorder.stop = mocker.MagicMock()
        app.audio_recorder.save = mocker.MagicMock(side_effect=ValueError("no audio"))
        app.tray.set_recording = mocker.MagicMock()

        app._on_recording_stopped()

        app.window.set_error.assert_called_once()
        app.tray.show_message.assert_called_once()

    def test_on_processing_done_with_auto_paste(self, qtbot, mocker):
        app = self._make_application(qtbot, mocker)
        mock_toast = mocker.patch("src.__main__.Toast")
        app.config.output.auto_paste = True
        app._saved_hwnd = 12345
        app.typer.output_text = mocker.MagicMock(return_value=True)
        app.audio_recorder.cleanup = mocker.MagicMock()

        app._on_processing_done("Hello, world!")

        app.history_store.add.assert_called_once_with("Hello, world!")
        app.typer.output_text.assert_called_once_with("Hello, world!", 12345)
        app.tray.show_message.assert_not_called()
        mock_toast.assert_not_called()
        app.audio_recorder.cleanup.assert_called_once()

    def test_on_processing_done_auto_paste_failure_shows_copied_toast(self, qtbot, mocker):
        app = self._make_application(qtbot, mocker)
        mock_toast = mocker.patch("src.__main__.Toast")
        app.config.output.auto_paste = True
        app._saved_hwnd = 12345
        app.typer.output_text = mocker.MagicMock(return_value=False)
        app.audio_recorder.cleanup = mocker.MagicMock()

        app._on_processing_done("Hello, world!")

        app.history_store.add.assert_called_once_with("Hello, world!")
        app.typer.output_text.assert_called_once_with("Hello, world!", 12345)
        app.tray.show_message.assert_not_called()
        mock_toast.assert_called_once()
        mock_toast.return_value.show.assert_called_once()
        app.audio_recorder.cleanup.assert_called_once()

    def test_on_processing_done_without_auto_paste(self, qtbot, mocker):
        app = self._make_application(qtbot, mocker)
        app.config.output.auto_paste = False
        app._saved_hwnd = 12345
        mock_copy = mocker.patch("pyperclip.copy")
        app.audio_recorder.cleanup = mocker.MagicMock()

        app._on_processing_done("Hello, world!")

        app.history_store.add.assert_called_once_with("Hello, world!")
        mock_copy.assert_called_once_with("Hello, world!")
        app.audio_recorder.cleanup.assert_called_once()

    def test_on_processing_done_empty_text_not_added_to_history(self, qtbot, mocker):
        app = self._make_application(qtbot, mocker)
        app.audio_recorder.cleanup = mocker.MagicMock()

        app._on_processing_done("")

        app.history_store.add.assert_not_called()
        app.audio_recorder.cleanup.assert_called_once()

    def test_on_processing_error(self, qtbot, mocker):
        app = self._make_application(qtbot, mocker)
        app.audio_recorder.cleanup = mocker.MagicMock()

        app._on_processing_error("API failed")

        app.window.set_error.assert_called_once()
        app.tray.show_message.assert_called_once()
        app.audio_recorder.cleanup.assert_called_once()

    def test_show_settings_lazy_loads_dialog(self, qtbot, mocker):
        app = self._make_application(qtbot, mocker)
        mock_dialog_cls = mocker.patch("src.__main__.SettingsDialog")
        mock_dialog = mocker.MagicMock()
        mock_dialog_cls.return_value = mock_dialog

        app._settings_dialog = None
        mocker.patch.object(mock_dialog, "exec")
        app._show_settings()

        mock_dialog_cls.assert_called_once()
        mock_dialog.exec.assert_called_once()

    def test_show_settings_reuses_existing_dialog(self, qtbot, mocker):
        app = self._make_application(qtbot, mocker)
        app._settings_dialog = mocker.MagicMock()
        mocker.patch.object(app._settings_dialog, "exec")

        app._show_settings()

        app._settings_dialog.exec.assert_called_once()

    def test_show_history_lazy_loads_dialog(self, qtbot, mocker):
        app = self._make_application(qtbot, mocker)
        mock_dialog_cls = mocker.patch("src.__main__.HistoryDialog")
        mock_dialog = mocker.MagicMock()
        mock_dialog_cls.return_value = mock_dialog

        app._history_dialog = None
        app._show_history()

        mock_dialog_cls.assert_called_once_with(app.history_store, app.window)
        mock_dialog.paste_requested.connect.assert_called_once()
        mock_dialog.exec.assert_called_once()

    def test_show_history_reloads_existing_dialog(self, qtbot, mocker):
        app = self._make_application(qtbot, mocker)
        app._history_dialog = mocker.MagicMock()

        app._show_history()

        app._history_dialog.reload.assert_called_once()
        app._history_dialog.exec.assert_called_once()

    def test_paste_history_text_with_auto_paste(self, qtbot, mocker):
        app = self._make_application(qtbot, mocker)
        mock_toast = mocker.patch("src.__main__.Toast")
        app.config.output.auto_paste = True
        app.typer.output_text = mocker.MagicMock(return_value=True)
        mocker.patch("src.__main__.get_foreground_window", return_value=456)

        app._paste_history_text("from history")

        app.typer.output_text.assert_called_once_with("from history", 456)
        app.tray.show_message.assert_not_called()
        mock_toast.assert_not_called()

    def test_paste_history_text_auto_paste_failure_shows_copied_toast(self, qtbot, mocker):
        app = self._make_application(qtbot, mocker)
        mock_toast = mocker.patch("src.__main__.Toast")
        app.config.output.auto_paste = True
        app.typer.output_text = mocker.MagicMock(return_value=False)
        mocker.patch("src.__main__.get_foreground_window", return_value=456)

        app._paste_history_text("from history")

        app.typer.output_text.assert_called_once_with("from history", 456)
        app.tray.show_message.assert_not_called()
        mock_toast.assert_called_once()
        mock_toast.return_value.show.assert_called_once()

    def test_paste_history_text_without_auto_paste(self, qtbot, mocker):
        app = self._make_application(qtbot, mocker)
        app.config.output.auto_paste = False
        mock_copy = mocker.patch("pyperclip.copy")

        app._paste_history_text("from history")

        mock_copy.assert_called_once_with("from history")

    def test_on_settings_saved_respects_toggle(self, qtbot, mocker):
        mocker.patch("src.__main__.Toast")
        app = self._make_application(qtbot, mocker)
        app.hotkey_manager.stop = mocker.MagicMock()
        app.hotkey_manager.start = mocker.MagicMock()
        app.config.hotkey.toggle_enabled = True

        app._on_settings_saved()

        app.hotkey_manager.stop.assert_called_once()
        app.hotkey_manager.start.assert_called_once()

    def test_on_settings_saved_disables_when_toggle_off(self, qtbot, mocker):
        mocker.patch("src.__main__.Toast")
        app = self._make_application(qtbot, mocker)
        app.hotkey_manager.stop = mocker.MagicMock()
        app.hotkey_manager.start = mocker.MagicMock()
        app.config.hotkey.toggle_enabled = False

        app._on_settings_saved()

        app.hotkey_manager.stop.assert_called_once()
        app.hotkey_manager.start.assert_not_called()

    def test_quit_guard_prevents_double_quit(self, qtbot, mocker):
        app = self._make_application(qtbot, mocker)
        app._quitting = True
        app.app.quit = mocker.MagicMock()

        app._quit()

        app.app.quit.assert_not_called()

    def test_toggle_recording_start(self, qtbot, mocker):
        app = self._make_application(qtbot, mocker)
        app.window.is_recording.return_value = False
        app.window.start_recording.reset_mock()
        app._toggle_recording()
        app.window.start_recording.assert_called_once()

    def test_toggle_recording_stop(self, qtbot, mocker):
        app = self._make_application(qtbot, mocker)
        app.window.is_recording.return_value = True
        app.window.stop_recording.reset_mock()
        app._toggle_recording()
        app.window.stop_recording.assert_called_once()

    def test_cancel_recording_while_recording(self, qtbot, mocker):
        app = self._make_application(qtbot, mocker)
        app.window.is_recording.return_value = True
        app.window.stop_recording.reset_mock()
        app._cancel_recording()
        assert app._cancelled is True
        app.window.stop_recording.assert_called_once()

    def test_cancel_recording_when_not_recording(self, qtbot, mocker):
        app = self._make_application(qtbot, mocker)
        app.window.is_recording.return_value = False
        app.audio_recorder.cleanup = mocker.MagicMock()
        app._cancel_recording()
        assert app._cancelled is True
        app.audio_recorder.cleanup.assert_called_once()

    def test_shows_settings_when_not_configured(self, qtbot, mocker):
        """When no API key is set, settings dialog is shown on startup."""
        mock_dialog = mocker.MagicMock()
        mocker.patch("src.__main__.SettingsDialog", return_value=mock_dialog)

        self._make_application(qtbot, mocker, is_configured=False)

        mock_dialog.exec.assert_called_once()

    def test_skips_settings_when_configured(self, qtbot, mocker):
        """When API key is set, settings dialog is NOT shown on startup."""
        mock_dialog_cls = mocker.patch("src.__main__.SettingsDialog")

        self._make_application(qtbot, mocker, is_configured=True)

        mock_dialog_cls.assert_not_called()

    def test_quick_set_auto_paste_saves_config(self, qtbot, mocker):
        app = self._make_application(qtbot, mocker)
        app.config.save = mocker.MagicMock()

        app._set_auto_paste(False)

        assert app.config.output.auto_paste is False
        app.config.save.assert_called_once()
        app.tray.apply_config.assert_called()

    def test_quick_set_polish_enabled_saves_config(self, qtbot, mocker):
        app = self._make_application(qtbot, mocker)
        app.config.save = mocker.MagicMock()

        app._set_polish_enabled(False)

        assert app.config.polish.enabled is False
        app.config.save.assert_called_once()

    def test_quick_set_paste_mode_saves_config(self, qtbot, mocker):
        app = self._make_application(qtbot, mocker)
        app.config.save = mocker.MagicMock()

        app._set_paste_mode("clipboard")

        assert app.config.output.paste_mode == "clipboard"
        app.config.save.assert_called_once()

    def test_quick_set_asr_language_saves_config(self, qtbot, mocker):
        app = self._make_application(qtbot, mocker)
        app.config.save = mocker.MagicMock()

        app._set_asr_language("en")

        assert app.config.asr.language == "en"
        app.config.save.assert_called_once()
