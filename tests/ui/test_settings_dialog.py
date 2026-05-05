"""Tests for voice_type.ui.settings_dialog — SettingsDialog."""

from PySide6.QtWidgets import QDialogButtonBox, QDialog
from voice_type.config import AppConfig, AsrConfig, PolishApiConfig, RecordingConfig
from voice_type.ui.settings_dialog import SettingsDialog


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

    def test_load_config_with_custom_model_not_in_list(self, qtbot):
        """Custom model sets the edit text."""
        cfg = AppConfig(asr=AsrConfig(model="custom-unknown-model"))
        dlg = SettingsDialog(cfg)
        qtbot.addWidget(dlg)
        assert dlg.stt_model_combo.currentText() == "custom-unknown-model"

    def test_load_hotkey_row_empty_mods(self, qtbot):
        cfg = AppConfig(recording=RecordingConfig(
            start_hotkey_modifiers=[],
            start_hotkey_key="x",
        ))
        dlg = SettingsDialog(cfg)
        qtbot.addWidget(dlg)
        assert dlg.start_mod1.currentText() == "none"
        assert dlg.start_mod2.currentText() == "none"
        assert dlg.start_key.text() == "x"


class TestSettingsDialogSave:
    def test_save_hotkey_row_both_none(self, qtbot):
        dlg = SettingsDialog(AppConfig())
        qtbot.addWidget(dlg)
        dlg.start_mod1.setCurrentText("none")
        dlg.start_mod2.setCurrentText("none")
        result = dlg._save_hotkey_row(dlg.start_mod1, dlg.start_mod2, dlg.start_key)
        assert result == []

    def test_save_hotkey_row_one_modifier(self, qtbot):
        dlg = SettingsDialog(AppConfig())
        qtbot.addWidget(dlg)
        dlg.start_mod1.setCurrentText("alt")
        dlg.start_mod2.setCurrentText("none")
        result = dlg._save_hotkey_row(dlg.start_mod1, dlg.start_mod2, dlg.start_key)
        assert result == ["alt"]

    def test_save_hotkey_row_two_modifiers(self, qtbot):
        dlg = SettingsDialog(AppConfig())
        qtbot.addWidget(dlg)
        dlg.stop_mod1.setCurrentText("ctrl")
        dlg.stop_mod2.setCurrentText("shift")
        result = dlg._save_hotkey_row(dlg.stop_mod1, dlg.stop_mod2, dlg.stop_key)
        assert result == ["ctrl", "shift"]

    def test_save_and_close_with_network_available(self, qtbot, mocker):
        """When network is available, config is saved and dialog accepted."""
        mocker.patch("voice_type.ui.settings_dialog.check_network_available", return_value=True)
        mock_toast = mocker.patch("voice_type.ui.settings_dialog.Toast")

        cfg = AppConfig(asr=AsrConfig(api_key="sk-test"))
        dlg = SettingsDialog(cfg)
        qtbot.addWidget(dlg)

        with qtbot.waitSignal(dlg.settings_saved):
            dlg._save_and_close()

        mock_toast.assert_not_called()

    def test_save_and_close_with_network_unavailable(self, qtbot, mocker):
        """When network is unavailable, toast is shown and config is NOT saved."""
        mocker.patch("voice_type.ui.settings_dialog.check_network_available", return_value=False)
        mock_toast = mocker.patch("voice_type.ui.settings_dialog.Toast")

        cfg = AppConfig()
        dlg = SettingsDialog(cfg)
        qtbot.addWidget(dlg)

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
        mocker.patch("voice_type.ui.settings_dialog.check_network_available", return_value=True)

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
        mocker.patch("voice_type.ui.settings_dialog.check_network_available", return_value=True)

        cfg = AppConfig()
        dlg = SettingsDialog(cfg)
        qtbot.addWidget(dlg)

        dlg.stt_api_key_input.setText("  sk-test  ")
        dlg.polish_api_key_input.setText("  sk-polish  ")

        dlg._save_and_close()

        assert cfg.asr.api_key == "sk-test"
        assert cfg.polish.api_key == "sk-polish"

    def test_save_and_close_accepts_dialog(self, qtbot, mocker):
        """_save_and_close calls accept() to close the dialog."""
        mocker.patch("voice_type.ui.settings_dialog.check_network_available", return_value=True)

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
