"""Settings dialog — configure API, models, hotkey, etc."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QLineEdit,
    QComboBox, QFormLayout, QGroupBox, QSpinBox, QCheckBox,
    QDialogButtonBox, QTabWidget, QWidget,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from src.config import AppConfig
from src.network import check_network_available
from src.ui.main_window import Toast
from src.ui.icon_utils import make_circle_icon

_SETTINGS_ICON = None


def _get_settings_icon() -> QIcon:
    """Lazily create settings icon (requires QApplication to exist first)."""
    global _SETTINGS_ICON
    if _SETTINGS_ICON is None:
        _SETTINGS_ICON = make_circle_icon("⚙", (99, 102, 241), font_size=14, font_family="Segoe UI")
    return _SETTINGS_ICON


class SettingsDialog(QDialog):

    settings_saved = Signal()

    POLISH_MODELS = [
        "gpt-4o", "gpt-4o-mini", "gpt-4-turbo",
        "claude-sonnet-4-5-20250514", "deepseek-chat",
        "qwen-plus", "qwen-max",
    ]

    ASR_MODELS = [
        "FunAudioLLM/SenseVoiceSmall",
        "whisper-1",
    ]

    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Settings")
        self.setWindowIcon(_get_settings_icon())
        self.setModal(True)
        self.setMinimumWidth(480)
        self.setWindowFlags(Qt.Dialog)
        self._init_ui()
        self._load_config()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        tabs = QTabWidget()

        # === Tab 1: STT (Speech-to-Text) ===
        stt_tab = QWidget()
        stt_layout = QVBoxLayout(stt_tab)
        stt_layout.setSpacing(12)

        stt_api_group = QGroupBox("STT API")
        stt_api_layout = QFormLayout()

        self.stt_api_key_input = QLineEdit()
        self.stt_api_key_input.setEchoMode(QLineEdit.Password)
        self.stt_api_key_input.setPlaceholderText("sk-...")
        stt_api_layout.addRow("API Key:", self.stt_api_key_input)

        self.stt_base_url_input = QLineEdit()
        self.stt_base_url_input.setPlaceholderText("https://api.openai.com/v1")
        stt_api_layout.addRow("Base URL:", self.stt_base_url_input)

        self.stt_model_combo = QComboBox()
        self.stt_model_combo.setEditable(True)
        for m in self.ASR_MODELS:
            self.stt_model_combo.addItem(m)
        stt_api_layout.addRow("Model:", self.stt_model_combo)

        self.stt_lang_combo = QComboBox()
        for lang in ["auto", "zh", "en", "ja", "ko", "fr", "de", "es"]:
            self.stt_lang_combo.addItem(lang)
        stt_api_layout.addRow("Language:", self.stt_lang_combo)

        stt_api_group.setLayout(stt_api_layout)
        stt_layout.addWidget(stt_api_group)

        stt_misc_group = QGroupBox("Recording")
        stt_misc_layout = QFormLayout()

        self.sample_rate_spin = QSpinBox()
        self.sample_rate_spin.setRange(8000, 48000)
        self.sample_rate_spin.setSingleStep(8000)
        stt_misc_layout.addRow("Sample Rate:", self.sample_rate_spin)

        stt_misc_group.setLayout(stt_misc_layout)
        stt_layout.addWidget(stt_misc_group)
        stt_layout.addStretch()
        tabs.addTab(stt_tab, "STT")

        # === Tab 2: Polish ===
        polish_tab = QWidget()
        polish_layout = QVBoxLayout(polish_tab)
        polish_layout.setSpacing(12)

        polish_api_group = QGroupBox("Polish API")
        polish_api_layout = QFormLayout()

        self.polish_api_key_input = QLineEdit()
        self.polish_api_key_input.setEchoMode(QLineEdit.Password)
        self.polish_api_key_input.setPlaceholderText("sk-...")
        polish_api_layout.addRow("API Key:", self.polish_api_key_input)

        self.polish_base_url_input = QLineEdit()
        self.polish_base_url_input.setPlaceholderText("https://api.openai.com/v1")
        polish_api_layout.addRow("Base URL:", self.polish_base_url_input)

        self.polish_model_combo = QComboBox()
        self.polish_model_combo.setEditable(True)
        for m in self.POLISH_MODELS:
            self.polish_model_combo.addItem(m)
        polish_api_layout.addRow("Model:", self.polish_model_combo)

        polish_api_group.setLayout(polish_api_layout)
        polish_layout.addWidget(polish_api_group)

        polish_layout.addStretch()
        tabs.addTab(polish_tab, "Polish")

        layout.addWidget(tabs)

        # === Output Settings (always visible below tabs) ===
        output_group = QGroupBox("Output")
        output_layout = QFormLayout()

        self.paste_delay_spin = QSpinBox()
        self.paste_delay_spin.setRange(0, 2000)
        self.paste_delay_spin.setSuffix(" ms")
        output_layout.addRow("Paste Delay:", self.paste_delay_spin)

        self.auto_paste_check = QCheckBox("Auto-paste to cursor position")
        output_layout.addRow("", self.auto_paste_check)

        output_group.setLayout(output_layout)
        layout.addWidget(output_group)

        # === Hotkey Settings ===
        hotkey_group = QGroupBox("Hotkeys")
        hotkey_layout = QVBoxLayout()

        self.hotkey_toggle_check = QCheckBox("Enable Left Alt toggle (tap to start/stop recording)")
        self.hotkey_toggle_check.setChecked(True)
        hotkey_layout.addWidget(self.hotkey_toggle_check)

        hint_label = QLabel(
            "Quickly tap Left Alt to toggle recording.\n"
            "Holding Alt + another key (e.g. Alt+Tab) will not trigger it."
        )
        hint_label.setWordWrap(True)
        hint_label.setStyleSheet("color: #9ca3af; font-size: 12px;")
        hotkey_layout.addWidget(hint_label)

        cancel_label = QLabel(
            "<b>Alt+C</b> — Cancel recording and discard audio."
        )
        cancel_label.setWordWrap(True)
        cancel_label.setStyleSheet("color: #9ca3af; font-size: 12px;")
        hotkey_layout.addWidget(cancel_label)

        hotkey_group.setLayout(hotkey_layout)
        layout.addWidget(hotkey_group)

        # === Buttons ===
        button_box = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self._save_and_close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _load_config(self):
        # STT tab
        self.stt_api_key_input.setText(self.config.asr.api_key)
        self.stt_base_url_input.setText(self.config.asr.base_url)
        idx = self.stt_model_combo.findText(self.config.asr.model)
        if idx >= 0:
            self.stt_model_combo.setCurrentIndex(idx)
        else:
            self.stt_model_combo.setEditText(self.config.asr.model)
        idx = self.stt_lang_combo.findText(self.config.asr.language)
        if idx >= 0:
            self.stt_lang_combo.setCurrentIndex(idx)
        self.sample_rate_spin.setValue(self.config.recording.sample_rate)

        # Polish tab
        self.polish_api_key_input.setText(self.config.polish.api_key)
        self.polish_base_url_input.setText(self.config.polish.base_url)
        idx = self.polish_model_combo.findText(self.config.polish.model)
        if idx >= 0:
            self.polish_model_combo.setCurrentIndex(idx)
        else:
            self.polish_model_combo.setEditText(self.config.polish.model)

        # Output
        self.paste_delay_spin.setValue(self.config.output.paste_delay_ms)
        self.auto_paste_check.setChecked(self.config.output.auto_paste)

        # Hotkeys
        self.hotkey_toggle_check.setChecked(self.config.hotkey.toggle_enabled)

    def _save_and_close(self):
        if not check_network_available():
            self._toast = Toast("Network unavailable, settings not saved", parent=self)
            self._toast.show()
            return

        api_key = self.stt_api_key_input.text().strip()
        polish_key = self.polish_api_key_input.text().strip()
        if not api_key and not polish_key:
            self._toast = Toast("At least one API Key is required", parent=self)
            self._toast.show()
            return

        # STT
        self.config.asr.api_key = api_key
        self.config.asr.base_url = self.stt_base_url_input.text().strip() or "https://api.openai.com/v1"
        self.config.asr.model = self.stt_model_combo.currentText()
        self.config.asr.language = self.stt_lang_combo.currentText()
        self.config.recording.sample_rate = self.sample_rate_spin.value()

        # Polish
        self.config.polish.api_key = self.polish_api_key_input.text().strip()
        self.config.polish.base_url = self.polish_base_url_input.text().strip() or "https://api.openai.com/v1"
        self.config.polish.model = self.polish_model_combo.currentText()

        # Output
        self.config.output.paste_delay_ms = self.paste_delay_spin.value()
        self.config.output.auto_paste = self.auto_paste_check.isChecked()

        # Hotkeys
        self.config.hotkey.toggle_enabled = self.hotkey_toggle_check.isChecked()

        self.config.save()
        self.settings_saved.emit()
        self.accept()
