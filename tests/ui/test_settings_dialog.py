"""Tests for voice_type.ui.settings_dialog — SettingsDialog."""

from PySide6.QtWidgets import QDialogButtonBox, QDialog
from voicetype.config import (
    AppConfig,
    AsrConfig,
    PolishApiConfig,
    RecordingConfig,
    HotkeyConfig,
    OutputConfig,
    GlossaryEntry,
)
from voicetype.ui.settings_dialog import SettingsDialog


class TestSettingsDialogCreation:
    def test_dialog_creates(self, qtbot):
        dlg = SettingsDialog(AppConfig())
        qtbot.addWidget(dlg)
        assert dlg.windowTitle() == "Settings"

    def test_stt_model_combo_populated(self, qtbot):
        dlg = SettingsDialog(AppConfig())
        qtbot.addWidget(dlg)
        assert dlg.stt_model_combo.count() >= 2  # SenseVoiceSmall, whisper-1

    def test_polish_model_combo_populated(self, qtbot):
        dlg = SettingsDialog(AppConfig())
        qtbot.addWidget(dlg)
        assert dlg.polish_model_combo.count() >= 7

    def test_language_combo_populated(self, qtbot):
        dlg = SettingsDialog(AppConfig())
        qtbot.addWidget(dlg)
        langs = [dlg.stt_lang_combo.itemData(i) for i in range(dlg.stt_lang_combo.count())]
        assert "auto" in langs
        assert "zh" in langs
        assert "en" in langs

    def test_paste_mode_combo_populated(self, qtbot):
        dlg = SettingsDialog(AppConfig())
        qtbot.addWidget(dlg)
        modes = [dlg.paste_mode_combo.itemData(i) for i in range(dlg.paste_mode_combo.count())]
        assert modes == ["auto", "ctrl_v", "ctrl_shift_v", "clipboard"]

    def test_microphone_controls_exist(self, qtbot, mocker):
        mocker.patch("voicetype.ui.settings_dialog.get_default_input_device_name", return_value="Mic")
        dlg = SettingsDialog(AppConfig())
        qtbot.addWidget(dlg)
        # The device name is resolved on a background thread and applied via
        # signal; wait for the label to update before asserting.
        qtbot.waitUntil(lambda: dlg.mic_device_label.text() == "Mic", timeout=2000)
        assert dlg.mic_level_bar.value() == 0
        assert dlg.mic_test_btn.text() == "Test Microphone"

    def test_glossary_controls_exist(self, qtbot):
        dlg = SettingsDialog(AppConfig())
        qtbot.addWidget(dlg)
        assert dlg.glossary_table.columnCount() == 2
        assert dlg.glossary_add_btn.text() == "Add Term"


class TestSettingsDialogLoadConfig:
    def test_load_config_populates_fields(self, qtbot):
        cfg = AppConfig(
            asr=AsrConfig(api_key="sk-stt", base_url="https://stt.api", model="whisper-1", language="en"),
            polish=PolishApiConfig(api_key="sk-polish", base_url="https://polish.api", model="gpt-4o-mini"),
        )
        dlg = SettingsDialog(cfg)
        qtbot.addWidget(dlg)
        assert dlg.stt_api_key_input.text() == "sk-stt"
        assert dlg.stt_base_url_input.text() == "https://stt.api"
        assert dlg.polish_api_key_input.text() == "sk-polish"
        assert dlg.polish_base_url_input.text() == "https://polish.api"
        assert dlg.polish_enabled_check.isChecked() is True

    def test_load_config_with_custom_model_not_in_list(self, qtbot):
        """Custom model sets the edit text."""
        cfg = AppConfig(asr=AsrConfig(model="custom-unknown-model"))
        dlg = SettingsDialog(cfg)
        qtbot.addWidget(dlg)
        assert dlg.stt_model_combo.currentText() == "custom-unknown-model"

    def test_load_config_populates_paste_mode(self, qtbot):
        cfg = AppConfig(output=OutputConfig(paste_mode="ctrl_shift_v"))
        dlg = SettingsDialog(cfg)
        qtbot.addWidget(dlg)
        assert dlg.paste_mode_combo.currentData() == "ctrl_shift_v"

    def test_load_config_populates_glossary(self, qtbot):
        cfg = AppConfig(glossary=[GlossaryEntry(source="派森", replacement="Python")])
        dlg = SettingsDialog(cfg)
        qtbot.addWidget(dlg)
        assert dlg.glossary_table.rowCount() == 1
        assert dlg.glossary_table.item(0, 0).text() == "派森"
        assert dlg.glossary_table.item(0, 1).text() == "Python"


class TestSettingsDialogHotkeyToggle:
    def test_hotkey_toggle_checked_by_default(self, qtbot):
        dlg = SettingsDialog(AppConfig())
        qtbot.addWidget(dlg)
        assert dlg.hotkey_toggle_check.isChecked() is True

    def test_hotkey_toggle_loads_from_config(self, qtbot):
        cfg = AppConfig(hotkey=HotkeyConfig(toggle_enabled=False))
        dlg = SettingsDialog(cfg)
        qtbot.addWidget(dlg)
        assert dlg.hotkey_toggle_check.isChecked() is False

    def test_hotkey_toggle_saves_to_config(self, qtbot, mocker):
        mocker.patch("voicetype.ui.settings_dialog.check_network_available", return_value=True)
        cfg = AppConfig(asr=AsrConfig(api_key="sk-test"))
        dlg = SettingsDialog(cfg)
        qtbot.addWidget(dlg)
        dlg.hotkey_toggle_check.setChecked(False)
        dlg._save_and_close()
        assert cfg.hotkey.toggle_enabled is False

    def test_hotkey_recorder_exists(self, qtbot):
        dlg = SettingsDialog(AppConfig())
        qtbot.addWidget(dlg)
        assert dlg.hotkey_recorder is not None

    def test_hotkey_loads_from_config(self, qtbot):
        cfg = AppConfig(hotkey=HotkeyConfig(toggle_hotkey="f9"))
        dlg = SettingsDialog(cfg)
        qtbot.addWidget(dlg)
        assert dlg.hotkey_recorder.hotkey() == "f9"

    def test_hotkey_saves_to_config(self, qtbot, mocker):
        mocker.patch("voicetype.ui.settings_dialog.check_network_available", return_value=True)
        cfg = AppConfig(asr=AsrConfig(api_key="sk-test"))
        dlg = SettingsDialog(cfg)
        qtbot.addWidget(dlg)
        dlg.hotkey_recorder.set_hotkey("f5")
        dlg._save_and_close()
        assert cfg.hotkey.toggle_hotkey == "f5"


class TestSettingsDialogMicrophoneTest:
    def test_start_microphone_monitor(self, qtbot, mocker):
        monitor = mocker.MagicMock()
        monitor.start.return_value = True
        monitor.is_running = True
        monitor.input_level = 0.0  # prevent timer callback from crashing
        mock_monitor_cls = mocker.patch(
            "voicetype.ui.settings_dialog.MicrophoneMonitor",
            return_value=monitor,
        )
        mocker.patch("voicetype.ui.settings_dialog.get_default_input_device_name", return_value="Mic")

        dlg = SettingsDialog(AppConfig())
        qtbot.addWidget(dlg)
        dlg.sample_rate_spin.setValue(16000)
        dlg._start_microphone_monitor()

        mock_monitor_cls.assert_called_once_with(16000)
        monitor.start.assert_called_once()
        assert dlg._mic_timer.isActive()
        assert dlg.mic_test_btn.text() == "Stop Test"
        assert dlg.mic_status_label.text() == "Listening..."

    def test_start_microphone_monitor_failure(self, qtbot, mocker):
        monitor = mocker.MagicMock()
        monitor.start.return_value = False
        monitor.error = "permission denied"
        mocker.patch("voicetype.ui.settings_dialog.MicrophoneMonitor", return_value=monitor)
        mocker.patch("voicetype.ui.settings_dialog.get_default_input_device_name", return_value="Mic")

        dlg = SettingsDialog(AppConfig())
        qtbot.addWidget(dlg)
        dlg._start_microphone_monitor()

        assert not dlg._mic_timer.isActive()
        assert dlg.mic_level_bar.value() == 0
        assert "permission denied" in dlg.mic_status_label.text()
        assert dlg.mic_test_btn.text() == "Test Microphone"

    def test_refresh_microphone_level_detects_input(self, qtbot, mocker):
        monitor = mocker.MagicMock()
        monitor.is_running = True
        monitor.input_level = 0.5
        mocker.patch("voicetype.ui.settings_dialog.get_default_input_device_name", return_value="Mic")

        dlg = SettingsDialog(AppConfig())
        qtbot.addWidget(dlg)
        dlg._mic_monitor = monitor
        dlg._refresh_microphone_level()

        assert dlg.mic_level_bar.value() == 50
        assert dlg.mic_status_label.text() == "Microphone input detected."

    def test_refresh_microphone_level_reports_silence(self, qtbot, mocker):
        monitor = mocker.MagicMock()
        monitor.is_running = True
        monitor.input_level = 0.0
        mocker.patch("voicetype.ui.settings_dialog.get_default_input_device_name", return_value="Mic")

        dlg = SettingsDialog(AppConfig())
        qtbot.addWidget(dlg)
        dlg._mic_monitor = monitor
        dlg._refresh_microphone_level()

        assert dlg.mic_level_bar.value() == 0
        assert "No input detected" in dlg.mic_status_label.text()

    def test_reject_stops_microphone_monitor(self, qtbot, mocker):
        monitor = mocker.MagicMock()
        monitor.is_running = True
        mocker.patch("voicetype.ui.settings_dialog.get_default_input_device_name", return_value="Mic")

        dlg = SettingsDialog(AppConfig())
        qtbot.addWidget(dlg)
        dlg._mic_monitor = monitor
        dlg.reject()

        monitor.stop.assert_called_once()


class TestSettingsDialogDenoise:
    def test_denoise_controls_exist(self, qtbot):
        dlg = SettingsDialog(AppConfig())
        qtbot.addWidget(dlg)
        assert dlg.denoise_check.isChecked() is False  # off by default
        assert dlg.denoise_strength_combo.count() == 3  # low/medium/high
        assert dlg.denoise_strength_combo.currentData() == "medium"

    def test_strength_combo_disabled_when_denoise_off(self, qtbot):
        dlg = SettingsDialog(AppConfig())
        qtbot.addWidget(dlg)
        assert dlg.denoise_check.isChecked() is False
        assert dlg.denoise_strength_combo.isEnabled() is False

    def test_strength_combo_enabled_when_denoise_on(self, qtbot):
        dlg = SettingsDialog(AppConfig())
        qtbot.addWidget(dlg)
        dlg.denoise_check.setChecked(True)
        assert dlg.denoise_strength_combo.isEnabled() is True

    def test_denoise_loads_from_config(self, qtbot):
        cfg = AppConfig(recording=RecordingConfig(denoise_enabled=True, denoise_strength="high"))
        dlg = SettingsDialog(cfg)
        qtbot.addWidget(dlg)
        assert dlg.denoise_check.isChecked() is True
        assert dlg.denoise_strength_combo.currentData() == "high"
        assert dlg.denoise_strength_combo.isEnabled() is True

    def test_denoise_saves_to_config(self, qtbot, mocker):
        mocker.patch("voicetype.ui.settings_dialog.check_network_available", return_value=True)
        cfg = AppConfig(asr=AsrConfig(api_key="sk-test"))
        dlg = SettingsDialog(cfg)
        qtbot.addWidget(dlg)
        dlg.denoise_check.setChecked(True)
        idx = dlg.denoise_strength_combo.findData("low")
        dlg.denoise_strength_combo.setCurrentIndex(idx)
        dlg._save_and_close()
        assert cfg.recording.denoise_enabled is True
        assert cfg.recording.denoise_strength == "low"


class TestSettingsDialogSave:
    def test_save_and_close_with_network_available(self, qtbot, mocker):
        """When network is available, config is saved and dialog accepted."""
        mocker.patch("voicetype.ui.settings_dialog.check_network_available", return_value=True)
        mock_toast = mocker.patch("voicetype.ui.settings_dialog.Toast")

        cfg = AppConfig(asr=AsrConfig(api_key="sk-test"))
        dlg = SettingsDialog(cfg)
        qtbot.addWidget(dlg)

        with qtbot.waitSignal(dlg.settings_saved):
            dlg._save_and_close()

        mock_toast.assert_not_called()

    def test_save_and_close_with_network_unavailable(self, qtbot, mocker):
        """When network is unavailable, toast is shown and config is NOT saved."""
        mocker.patch("voicetype.ui.settings_dialog.check_network_available", return_value=False)
        mock_toast = mocker.patch("voicetype.ui.settings_dialog.Toast")

        cfg = AppConfig()
        dlg = SettingsDialog(cfg)
        qtbot.addWidget(dlg)
        # Simulate the user typing a new API key, which marks the API state as changed.
        dlg.stt_api_key_input.setText("sk-new-key")

        # Should NOT emit settings_saved. The network check runs on a
        # background thread and reports back via _network_check_done; wait for
        # that signal so the toast assertion runs after the result lands.
        emitted = []
        dlg.settings_saved.connect(lambda: emitted.append(True))

        with qtbot.waitSignal(dlg._network_check_done, timeout=2000):
            dlg._save_and_close()

        assert emitted == []
        mock_toast.assert_called_once()
        toast_call_args = mock_toast.call_args
        assert "Network unavailable" in toast_call_args[0][0]

    def test_save_and_close_empty_base_url_defaults(self, qtbot, mocker):
        """Empty base_url is saved as empty string (openai client uses its own default)."""
        mocker.patch("voicetype.ui.settings_dialog.check_network_available", return_value=True)

        cfg = AppConfig(asr=AsrConfig(api_key="sk-test"))
        cfg.asr.base_url = "https://old.url"
        cfg.polish.base_url = "https://old.url"
        dlg = SettingsDialog(cfg)
        qtbot.addWidget(dlg)

        # Clear the base url inputs (this marks the API state as changed ->
        # async network-check path).
        dlg.stt_base_url_input.clear()
        dlg.polish_base_url_input.clear()

        with qtbot.waitSignal(dlg.settings_saved, timeout=2000):
            dlg._save_and_close()

        assert cfg.asr.base_url == ""
        assert cfg.polish.base_url == ""

    def test_save_strips_whitespace_from_api_key(self, qtbot, mocker):
        """API key inputs are stripped."""
        mocker.patch("voicetype.ui.settings_dialog.check_network_available", return_value=True)

        cfg = AppConfig()
        dlg = SettingsDialog(cfg)
        qtbot.addWidget(dlg)

        dlg.stt_api_key_input.setText("  sk-test  ")
        dlg.polish_api_key_input.setText("  sk-polish  ")

        with qtbot.waitSignal(dlg.settings_saved, timeout=2000):
            dlg._save_and_close()

        assert cfg.asr.api_key == "sk-test"
        assert cfg.polish.api_key == "sk-polish"

    def test_save_paste_mode(self, qtbot, mocker):
        mocker.patch("voicetype.ui.settings_dialog.check_network_available", return_value=True)

        cfg = AppConfig(asr=AsrConfig(api_key="sk-test"))
        dlg = SettingsDialog(cfg)
        qtbot.addWidget(dlg)
        dlg.paste_mode_combo.setCurrentIndex(dlg.paste_mode_combo.findData("clipboard"))

        dlg._save_and_close()

        assert cfg.output.paste_mode == "clipboard"

    def test_save_polish_enabled(self, qtbot, mocker):
        mocker.patch("voicetype.ui.settings_dialog.check_network_available", return_value=True)

        cfg = AppConfig(asr=AsrConfig(api_key="sk-test"))
        dlg = SettingsDialog(cfg)
        qtbot.addWidget(dlg)
        dlg.polish_enabled_check.setChecked(False)

        dlg._save_and_close()

        assert cfg.polish.enabled is False

    def test_save_glossary_entries(self, qtbot, mocker):
        mocker.patch("voicetype.ui.settings_dialog.check_network_available", return_value=True)

        cfg = AppConfig(asr=AsrConfig(api_key="sk-test"))
        dlg = SettingsDialog(cfg)
        qtbot.addWidget(dlg)
        dlg._add_glossary_row(" 派森 ", " Python ")
        dlg._add_glossary_row("", "ignored")

        dlg._save_and_close()

        assert cfg.glossary == [GlossaryEntry(source="派森", replacement="Python")]

    def test_save_and_close_accepts_dialog(self, qtbot, mocker):
        """_save_and_close calls accept() to close the dialog."""
        mocker.patch("voicetype.ui.settings_dialog.check_network_available", return_value=True)

        cfg = AppConfig(asr=AsrConfig(api_key="sk-test"))
        dlg = SettingsDialog(cfg)
        qtbot.addWidget(dlg)

        # accept() closes the dialog
        dlg._save_and_close()
        assert dlg.result() == QDialog.Accepted or dlg.isVisible() is False


class TestSettingsDialogCancel:
    def test_cancel_rejects_dialog(self, qtbot):
        dlg = SettingsDialog(AppConfig())
        qtbot.addWidget(dlg)
        dlg.reject()
        assert dlg.result() == QDialog.Rejected


class TestSettingsDialogWrapHeights:
    """Word-wrapped form-field labels must not clip their wrapped text.

    Regression: QFormLayout sizes field rows by sizeHint, not by
    heightForWidth, so word-wrapped QLabels placed as form fields
    (denoise_hint_label, mic_status_label, mic_device_label) were
    compressed to one line in English — where the field column narrows
    because the form labels are longer — clipping both lines of wrapped
    text. SettingsDialog._adjust_wrap_heights forces each label's
    minimum height to its heightForWidth so the layout allocates the
    full wrapped height.
    """

    def test_wrap_labels_get_full_wrapped_height_in_english(self, qtbot):
        from voicetype import i18n
        saved_lang = i18n._current_lang
        try:
            i18n.init_language("en")
            dlg = SettingsDialog(AppConfig())
            qtbot.addWidget(dlg)
            dlg.show()
            dlg._tabs.setCurrentIndex(0)  # General tab (recording settings)
            # _adjust_wrap_heights is deferred via QTimer.singleShot(0, ...);
            # the mic device name is fetched on a background thread and
            # delivered via a queued signal. Wait for both to settle.
            qtbot.wait(200)
            for lbl in dlg._wrap_labels:
                if lbl.width() <= 0 or not lbl.text():
                    continue
                hfw = lbl.heightForWidth(lbl.width())
                if hfw <= 0:
                    continue
                # _adjust_wrap_heights must have set minimumHeight to the
                # full wrapped height so the layout can't compress the label.
                assert lbl.minimumHeight() >= hfw, (
                    f"minimumHeight {lbl.minimumHeight()} < heightForWidth {hfw} "
                    f"for '{lbl.text()[:30]}'"
                )
        finally:
            dlg.close()
            i18n.init_language(saved_lang)

    def test_wrap_labels_not_clipped_in_chinese(self, qtbot):
        """In Chinese the field column is wider and text fits on one line,
        but the fix must still not leave the label shorter than its text."""
        from voicetype import i18n
        saved_lang = i18n._current_lang
        try:
            i18n.init_language("zh")
            dlg = SettingsDialog(AppConfig())
            qtbot.addWidget(dlg)
            dlg.show()
            dlg._tabs.setCurrentIndex(0)  # General tab
            qtbot.wait(200)
            for lbl in dlg._wrap_labels:
                if lbl.width() <= 0 or not lbl.text():
                    continue
                hfw = lbl.heightForWidth(lbl.width())
                if hfw <= 0:
                    continue
                assert lbl.minimumHeight() >= hfw, (
                    f"minimumHeight {lbl.minimumHeight()} < heightForWidth {hfw} "
                    f"for '{lbl.text()[:30]}'"
                )
        finally:
            dlg.close()
            i18n.init_language(saved_lang)


class TestSettingsDialogModelFetch:
    """Model-list fetching from the provider's /models endpoint."""

    def test_refresh_buttons_created(self, qtbot):
        """Each editable model combo gets a paired refresh button."""
        dlg = SettingsDialog(AppConfig())
        qtbot.addWidget(dlg)
        assert "asr" in dlg._refresh_buttons
        assert "polish" in dlg._refresh_buttons
        assert dlg._refresh_buttons["asr"].isEnabled()
        assert dlg._refresh_buttons["polish"].isEnabled()

    def test_fetch_models_requires_api_key(self, qtbot, mocker):
        """Fetching without an API key surfaces an error (no thread started)."""
        dlg = SettingsDialog(AppConfig(asr=AsrConfig(api_key="")))
        qtbot.addWidget(dlg)
        mocker.patch("voicetype.ui.settings_dialog.Toast")
        spy = mocker.spy(dlg, "_on_models_error")
        mocker.patch("voicetype.ui.settings_dialog.threading.Thread")
        dlg._fetch_models("asr")
        spy.assert_called_once()
        assert spy.call_args[0][0] == "asr"

    def test_fetch_models_starts_background_thread(self, qtbot, mocker):
        """With a key present, a daemon thread is started to fetch models."""
        cfg = AppConfig(asr=AsrConfig(api_key="sk-test", base_url="https://api/v1"))
        dlg = SettingsDialog(cfg)
        qtbot.addWidget(dlg)
        mock_thread = mocker.patch("voicetype.ui.settings_dialog.threading.Thread")
        mocker.patch("voicetype.ui.settings_dialog.fetch_models", return_value=["m1", "m2"])
        dlg._fetch_models("asr")
        assert mock_thread.called
        assert mock_thread.call_args.kwargs.get("daemon") is True

    def test_on_models_fetched_populates_combo(self, qtbot):
        """A successful fetch replaces the combo contents with the model list."""
        dlg = SettingsDialog(AppConfig())
        qtbot.addWidget(dlg)
        dlg._on_models_fetched("asr", ["whisper-1", "gpt-4o"])
        items = [dlg.stt_model_combo.itemText(i)
                 for i in range(dlg.stt_model_combo.count())]
        assert "whisper-1" in items
        assert "gpt-4o" in items

    def test_on_models_fetched_keeps_previous_selection(self, qtbot):
        """The model selected before the fetch stays selected afterwards."""
        dlg = SettingsDialog(AppConfig())
        qtbot.addWidget(dlg)
        dlg._model_before_fetch["polish"] = "gpt-4o"
        dlg._on_models_fetched("polish", ["deepseek-chat", "gpt-4o", "qwen-plus"])
        assert dlg.polish_model_combo.currentText() == "gpt-4o"

    def test_on_models_fetched_preserves_unlisted_model(self, qtbot):
        """A previously-selected model no longer listed is kept as an option."""
        dlg = SettingsDialog(AppConfig())
        qtbot.addWidget(dlg)
        dlg._model_before_fetch["asr"] = "my-custom-model"
        dlg._on_models_fetched("asr", ["whisper-1", "gpt-4o"])
        items = [dlg.stt_model_combo.itemText(i)
                 for i in range(dlg.stt_model_combo.count())]
        assert "my-custom-model" in items
        assert dlg.stt_model_combo.currentText() == "my-custom-model"

    def test_on_models_fetched_replaces_not_appends(self, qtbot):
        """Fetch replaces rather than appends — no duplicate items."""
        dlg = SettingsDialog(AppConfig())
        qtbot.addWidget(dlg)
        dlg._on_models_fetched("asr", ["a", "b"])
        dlg._on_models_fetched("asr", ["c", "d"])
        items = [dlg.stt_model_combo.itemText(i)
                 for i in range(dlg.stt_model_combo.count())]
        assert items == ["c", "d"]

    def test_on_models_fetched_empty_list_is_noop(self, qtbot):
        """An empty model list doesn't clear the existing combo."""
        dlg = SettingsDialog(AppConfig())
        qtbot.addWidget(dlg)
        original = dlg.stt_model_combo.count()
        dlg._on_models_fetched("asr", [])
        assert dlg.stt_model_combo.count() == original

    def test_on_models_error_restores_button_and_clears_state(self, qtbot, mocker):
        """A fetch failure re-enables the button and clears the pending state."""
        dlg = SettingsDialog(AppConfig())
        qtbot.addWidget(dlg)
        mocker.patch("voicetype.ui.settings_dialog.Toast")
        dlg._model_before_fetch["asr"] = "pending"
        dlg._refresh_buttons["asr"].setEnabled(False)
        dlg._refresh_buttons["asr"].setText("⏳")
        dlg._on_models_error("asr", "boom")
        assert dlg._refresh_buttons["asr"].isEnabled()
        assert dlg._refresh_buttons["asr"].text() == "🔄"
        assert "asr" not in dlg._model_before_fetch

    def test_fetch_disables_combo_and_shows_loading(self, qtbot, mocker):
        """During fetch, the combo shows the loading placeholder and is disabled."""
        cfg = AppConfig(asr=AsrConfig(api_key="sk-test", base_url="https://api/v1"))
        dlg = SettingsDialog(cfg)
        qtbot.addWidget(dlg)
        mocker.patch("voicetype.ui.settings_dialog.threading.Thread")
        mocker.patch("voicetype.ui.settings_dialog.fetch_models", return_value=["m1"])
        dlg._fetch_models("asr")
        items = [dlg.stt_model_combo.itemText(i)
                 for i in range(dlg.stt_model_combo.count())]
        from voicetype import i18n
        assert dlg.stt_model_combo.currentText() == i18n.t("settings.loading_models")
        assert not dlg.stt_model_combo.isEnabled()
        assert "m1" not in items  # old items cleared

    def test_on_models_fetched_empty_list_restores_and_toasts(self, qtbot, mocker):
        """When the provider returns no models, the combo is restored + toast."""
        dlg = SettingsDialog(AppConfig())
        qtbot.addWidget(dlg)
        mock_toast = mocker.patch("voicetype.ui.settings_dialog.Toast")
        dlg._model_before_fetch["asr"] = "selected"
        dlg._model_items_before_fetch["asr"] = ["selected", "other"]
        dlg._on_models_fetched("asr", [])
        # Combo restored with original items
        items = [dlg.stt_model_combo.itemText(i)
                 for i in range(dlg.stt_model_combo.count())]
        assert "selected" in items
        assert "other" in items
        assert dlg.stt_model_combo.currentText() == "selected"
        assert dlg.stt_model_combo.isEnabled()
        # Toast was shown
        assert mock_toast.called

    def test_restore_combo_without_saved_items_is_noop(self, qtbot):
        """When _model_items_before_fetch has no entry, the combo is untouched."""
        dlg = SettingsDialog(AppConfig())
        qtbot.addWidget(dlg)
        original_count = dlg.stt_model_combo.count()
        original_text = dlg.stt_model_combo.currentText()
        dlg._restore_combo_on_fetch_failure("asr")
        assert dlg.stt_model_combo.count() == original_count
        assert dlg.stt_model_combo.currentText() == original_text
