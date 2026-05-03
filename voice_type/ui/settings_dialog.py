"""Settings dialog — configure API, models, hotkey, etc."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QFormLayout, QGroupBox, QMessageBox,
    QSpinBox, QCheckBox, QDialogButtonBox, QTabWidget, QWidget,
)
from PySide6.QtCore import Qt, Signal, QTimer
from voice_type.config import AppConfig


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
        hotkey_layout = QFormLayout()

        # Start recording hotkey
        self.start_mod1 = QComboBox()
        self.start_mod2 = QComboBox()
        for mod in ["alt", "ctrl", "shift", "super", "none"]:
            self.start_mod1.addItem(mod)
            self.start_mod2.addItem(mod)
        self.start_key = QLineEdit()
        self.start_key.setMaxLength(1)
        self.start_key.setFixedWidth(40)
        start_row = QHBoxLayout()
        start_row.addWidget(self.start_mod1)
        start_row.addWidget(self.start_mod2)
        start_row.addWidget(QLabel("+"))
        start_row.addWidget(self.start_key)
        hotkey_layout.addRow("Start Recording:", start_row)

        # Stop recording hotkey
        self.stop_mod1 = QComboBox()
        self.stop_mod2 = QComboBox()
        for mod in ["alt", "ctrl", "shift", "super", "none"]:
            self.stop_mod1.addItem(mod)
            self.stop_mod2.addItem(mod)
        self.stop_key = QLineEdit()
        self.stop_key.setMaxLength(1)
        self.stop_key.setFixedWidth(40)
        stop_row = QHBoxLayout()
        stop_row.addWidget(self.stop_mod1)
        stop_row.addWidget(self.stop_mod2)
        stop_row.addWidget(QLabel("+"))
        stop_row.addWidget(self.stop_key)
        hotkey_layout.addRow("Stop Recording:", stop_row)

        # Cancel recording hotkey
        self.cancel_mod1 = QComboBox()
        self.cancel_mod2 = QComboBox()
        for mod in ["alt", "ctrl", "shift", "super", "none"]:
            self.cancel_mod1.addItem(mod)
            self.cancel_mod2.addItem(mod)
        self.cancel_key = QLineEdit()
        self.cancel_key.setMaxLength(1)
        self.cancel_key.setFixedWidth(40)
        cancel_row = QHBoxLayout()
        cancel_row.addWidget(self.cancel_mod1)
        cancel_row.addWidget(self.cancel_mod2)
        cancel_row.addWidget(QLabel("+"))
        cancel_row.addWidget(self.cancel_key)
        hotkey_layout.addRow("Cancel:", cancel_row)

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
        self._load_hotkey_row(self.config.recording.start_hotkey_modifiers, self.config.recording.start_hotkey_key,
                              self.start_mod1, self.start_mod2, self.start_key)
        self._load_hotkey_row(self.config.recording.stop_hotkey_modifiers, self.config.recording.stop_hotkey_key,
                              self.stop_mod1, self.stop_mod2, self.stop_key)
        self._load_hotkey_row(self.config.recording.cancel_hotkey_modifiers, self.config.recording.cancel_hotkey_key,
                              self.cancel_mod1, self.cancel_mod2, self.cancel_key)

    def _load_hotkey_row(self, mods, key, mod1_combo, mod2_combo, key_input):
        mod1_combo.setCurrentText(mods[0] if len(mods) > 0 else "none")
        mod2_combo.setCurrentText(mods[1] if len(mods) > 1 else "none")
        key_input.setText(key)

    def _save_and_close(self):
        # STT
        self.config.asr.api_key = self.stt_api_key_input.text().strip()
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
        self.config.recording.start_hotkey_modifiers = self._save_hotkey_row(self.start_mod1, self.start_mod2, self.start_key)
        self.config.recording.start_hotkey_key = self.start_key.text().lower()
        self.config.recording.stop_hotkey_modifiers = self._save_hotkey_row(self.stop_mod1, self.stop_mod2, self.stop_key)
        self.config.recording.stop_hotkey_key = self.stop_key.text().lower()
        self.config.recording.cancel_hotkey_modifiers = self._save_hotkey_row(self.cancel_mod1, self.cancel_mod2, self.cancel_key)
        self.config.recording.cancel_hotkey_key = self.cancel_key.text().lower()

        self.config.save()
        self.settings_saved.emit()
        self.accept()

    def _save_hotkey_row(self, mod1_combo, mod2_combo, key_input):
        mods = []
        m1 = mod1_combo.currentText()
        m2 = mod2_combo.currentText()
        if m1 != "none":
            mods.append(m1)
        if m2 != "none":
            mods.append(m2)
        return mods
