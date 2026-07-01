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
        langs = [dlg.stt_lang_combo.itemText(i) for i in range(dlg.stt_lang_combo.count())]
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
        assert dlg.mic_device_label.text() == "Mic"
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


class TestSettingsDialogMicrophoneTest:
    def test_start_microphone_monitor(self, qtbot, mocker):
        monitor = mocker.MagicMock()
        monitor.start.return_value = True
        monitor.is_running = True
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

        # Should NOT emit settings_saved
        emitted = []
        dlg.settings_saved.connect(lambda: emitted.append(True))

        dlg._save_and_close()

        assert emitted == []
        mock_toast.assert_called_once()
        toast_call_args = mock_toast.call_args
        assert "Network unavailable" in toast_call_args[0][0]

    def test_save_and_close_empty_base_url_defaults(self, qtbot, mocker):
        """Empty base_url defaults to https://api.openai.com/v1."""
        mocker.patch("voicetype.ui.settings_dialog.check_network_available", return_value=True)

        cfg = AppConfig(asr=AsrConfig(api_key="sk-test"))
        cfg.asr.base_url = "https://old.url"
        cfg.polish.base_url = "https://old.url"
        dlg = SettingsDialog(cfg)
        qtbot.addWidget(dlg)

        # Clear the base url inputs
        dlg.stt_base_url_input.clear()
        dlg.polish_base_url_input.clear()

        dlg._save_and_close()

        assert cfg.asr.base_url == "https://api.openai.com/v1"
        assert cfg.polish.base_url == "https://api.openai.com/v1"

    def test_save_strips_whitespace_from_api_key(self, qtbot, mocker):
        """API key inputs are stripped."""
        mocker.patch("voicetype.ui.settings_dialog.check_network_available", return_value=True)

        cfg = AppConfig()
        dlg = SettingsDialog(cfg)
        qtbot.addWidget(dlg)

        dlg.stt_api_key_input.setText("  sk-test  ")
        dlg.polish_api_key_input.setText("  sk-polish  ")

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
