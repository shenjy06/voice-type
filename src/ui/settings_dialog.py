"""Settings dialog — configure API, models, hotkey, etc."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QLineEdit,
    QComboBox, QFormLayout, QGroupBox, QSpinBox, QCheckBox,
    QDialogButtonBox, QTabWidget, QWidget, QPushButton, QProgressBar,
    QHBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QIcon
from src.audio import MicrophoneMonitor, get_default_input_device_name
from src.config import AppConfig, DEFAULT_BASE_URL, GlossaryEntry
from src.network import check_network_available
from src.ui.main_window import Toast
from src.ui.icon_utils import make_circle_icon
from src.i18n import t

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

    POLISH_STYLES = [
        ("settings.polish_style_default", "default"),
        ("settings.polish_style_formal", "formal"),
        ("settings.polish_style_casual", "casual"),
        ("settings.polish_style_concise", "concise"),
    ]

    ASR_MODELS = [
        "FunAudioLLM/SenseVoiceSmall",
        "whisper-1",
    ]

    PASTE_MODES = [
        ("settings.paste_mode_auto", "auto"),
        ("settings.paste_mode_ctrl_v", "ctrl_v"),
        ("settings.paste_mode_ctrl_shift_v", "ctrl_shift_v"),
        ("settings.paste_mode_clipboard", "clipboard"),
    ]

    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle(t("settings.title"))
        self.setWindowIcon(_get_settings_icon())
        self.setModal(True)
        self.setMinimumWidth(480)
        self.setWindowFlags(Qt.Dialog)
        self._mic_monitor = None
        self._mic_timer = QTimer(self)
        self._mic_timer.setInterval(100)
        self._mic_timer.timeout.connect(self._refresh_microphone_level)
        self._init_ui()
        self._load_config()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        self._tabs = QTabWidget()

        # === Tab 0: General ===
        general_tab = QWidget()
        general_layout = QVBoxLayout(general_tab)
        general_layout.setSpacing(12)

        lang_group = QGroupBox(t("settings.general"))
        lang_layout = QFormLayout()

        self.language_combo = QComboBox()
        self.language_combo.addItem(t("settings.ui_language_auto"), "auto")
        self.language_combo.addItem("English", "en")
        self.language_combo.addItem("中文", "zh")
        lang_layout.addRow(t("settings.ui_language"), self.language_combo)

        self.auto_start_check = QCheckBox(t("settings.auto_start"))
        lang_layout.addRow("", self.auto_start_check)

        lang_group.setLayout(lang_layout)
        general_layout.addWidget(lang_group)
        general_layout.addStretch()
        self._tabs.addTab(general_tab, t("settings.general"))

        # === Tab 1: STT (Speech-to-Text) ===
        stt_tab = QWidget()
        stt_layout = QVBoxLayout(stt_tab)
        stt_layout.setSpacing(12)

        stt_api_group = QGroupBox(t("settings.stt_api"))
        stt_api_layout = QFormLayout()

        self.stt_api_key_input = QLineEdit()
        self.stt_api_key_input.setEchoMode(QLineEdit.Password)
        self.stt_api_key_input.setPlaceholderText("sk-...")
        stt_api_layout.addRow(t("settings.api_key"), self.stt_api_key_input)

        self.stt_base_url_input = QLineEdit()
        self.stt_base_url_input.setPlaceholderText(DEFAULT_BASE_URL)
        stt_api_layout.addRow(t("settings.base_url"), self.stt_base_url_input)

        self.stt_model_combo = QComboBox()
        self.stt_model_combo.setEditable(True)
        for m in self.ASR_MODELS:
            self.stt_model_combo.addItem(m)
        stt_api_layout.addRow(t("settings.model"), self.stt_model_combo)

        self.stt_lang_combo = QComboBox()
        self.stt_lang_combo.addItem(t("settings.lang_auto"), "auto")
        for code in ["zh", "en", "ja", "ko", "fr", "de", "es"]:
            self.stt_lang_combo.addItem(code, code)
        stt_api_layout.addRow(t("settings.language"), self.stt_lang_combo)

        stt_api_group.setLayout(stt_api_layout)
        stt_layout.addWidget(stt_api_group)

        stt_misc_group = QGroupBox(t("settings.recording_group"))
        stt_misc_layout = QFormLayout()

        self.sample_rate_spin = QSpinBox()
        self.sample_rate_spin.setRange(8000, 48000)
        self.sample_rate_spin.setSingleStep(8000)
        stt_misc_layout.addRow(t("settings.sample_rate"), self.sample_rate_spin)

        self.mic_device_label = QLabel()
        self.mic_device_label.setWordWrap(True)
        stt_misc_layout.addRow(t("settings.mic_device"), self.mic_device_label)

        self.mic_level_bar = QProgressBar()
        self.mic_level_bar.setRange(0, 100)
        self.mic_level_bar.setValue(0)
        self.mic_level_bar.setTextVisible(False)
        self.mic_level_bar.setFixedHeight(10)
        self.mic_level_bar.setStyleSheet(
            "QProgressBar { background: #1f2937; border: 1px solid #4b5563; border-radius: 5px; }"
            "QProgressBar::chunk { background: #22c55e; border-radius: 4px; }"
        )
        stt_misc_layout.addRow(t("settings.mic_level"), self.mic_level_bar)

        self.mic_status_label = QLabel(t("settings.mic_status_idle"))
        self.mic_status_label.setWordWrap(True)
        self.mic_status_label.setStyleSheet("color: #9ca3af; font-size: 12px;")
        stt_misc_layout.addRow("", self.mic_status_label)

        self.mic_test_btn = QPushButton(t("settings.mic_test_start"))
        self.mic_test_btn.clicked.connect(self._toggle_microphone_monitor)
        stt_misc_layout.addRow("", self.mic_test_btn)

        stt_misc_group.setLayout(stt_misc_layout)
        stt_layout.addWidget(stt_misc_group)
        stt_layout.addStretch()
        self._tabs.addTab(stt_tab, t("settings.stt_tab"))

        # === Tab 2: Polish ===
        polish_tab = QWidget()
        polish_layout = QVBoxLayout(polish_tab)
        polish_layout.setSpacing(12)

        polish_api_group = QGroupBox(t("settings.polish_api"))
        polish_api_layout = QFormLayout()

        self.polish_api_key_input = QLineEdit()
        self.polish_api_key_input.setEchoMode(QLineEdit.Password)
        self.polish_api_key_input.setPlaceholderText("sk-...")
        polish_api_layout.addRow(t("settings.api_key"), self.polish_api_key_input)

        self.polish_base_url_input = QLineEdit()
        self.polish_base_url_input.setPlaceholderText(DEFAULT_BASE_URL)
        polish_api_layout.addRow(t("settings.base_url"), self.polish_base_url_input)

        self.polish_model_combo = QComboBox()
        self.polish_model_combo.setEditable(True)
        for m in self.POLISH_MODELS:
            self.polish_model_combo.addItem(m)
        polish_api_layout.addRow(t("settings.model"), self.polish_model_combo)

        self.polish_enabled_check = QCheckBox(t("settings.polish_enabled"))
        polish_api_layout.addRow("", self.polish_enabled_check)

        self.polish_style_combo = QComboBox()
        for label_key, value in self.POLISH_STYLES:
            self.polish_style_combo.addItem(t(label_key), value)
        polish_api_layout.addRow(t("settings.polish_style"), self.polish_style_combo)

        polish_api_group.setLayout(polish_api_layout)
        polish_layout.addWidget(polish_api_group)

        polish_layout.addStretch()
        self._tabs.addTab(polish_tab, t("settings.polish_tab"))

        # === Tab 3: Glossary ===
        glossary_tab = QWidget()
        glossary_layout = QVBoxLayout(glossary_tab)
        glossary_layout.setSpacing(12)

        glossary_group = QGroupBox(t("settings.glossary_group"))
        glossary_group_layout = QVBoxLayout()

        self.glossary_table = QTableWidget(0, 2)
        self.glossary_table.setHorizontalHeaderLabels([
            t("settings.glossary_source"),
            t("settings.glossary_replacement"),
        ])
        self.glossary_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.glossary_table.verticalHeader().setVisible(False)
        self.glossary_table.setSelectionBehavior(QTableWidget.SelectRows)
        glossary_group_layout.addWidget(self.glossary_table)

        glossary_buttons = QHBoxLayout()
        self.glossary_add_btn = QPushButton(t("settings.glossary_add"))
        self.glossary_remove_btn = QPushButton(t("settings.glossary_remove"))
        self.glossary_add_btn.clicked.connect(lambda: self._add_glossary_row())
        self.glossary_remove_btn.clicked.connect(self._remove_selected_glossary_rows)
        glossary_buttons.addWidget(self.glossary_add_btn)
        glossary_buttons.addWidget(self.glossary_remove_btn)
        glossary_buttons.addStretch()
        glossary_group_layout.addLayout(glossary_buttons)

        glossary_group.setLayout(glossary_group_layout)
        glossary_layout.addWidget(glossary_group)
        self._tabs.addTab(glossary_tab, t("settings.glossary_tab"))

        layout.addWidget(self._tabs)

        # === Output Settings (always visible below tabs) ===
        output_group = QGroupBox(t("settings.output"))
        output_layout = QFormLayout()

        self.paste_delay_spin = QSpinBox()
        self.paste_delay_spin.setRange(0, 2000)
        self.paste_delay_spin.setSuffix(" ms")
        output_layout.addRow(t("settings.paste_delay"), self.paste_delay_spin)

        self.paste_mode_combo = QComboBox()
        for label_key, value in self.PASTE_MODES:
            self.paste_mode_combo.addItem(t(label_key), value)
        output_layout.addRow(t("settings.paste_mode"), self.paste_mode_combo)

        self.auto_paste_check = QCheckBox(t("settings.auto_paste"))
        output_layout.addRow("", self.auto_paste_check)

        output_group.setLayout(output_layout)
        layout.addWidget(output_group)

        # === Hotkey Settings ===
        hotkey_group = QGroupBox(t("settings.hotkeys"))
        hotkey_layout = QVBoxLayout()

        self.hotkey_toggle_check = QCheckBox(t("settings.hotkey_toggle"))
        self.hotkey_toggle_check.setChecked(True)
        hotkey_layout.addWidget(self.hotkey_toggle_check)

        self._hint_label = QLabel(t("settings.hotkey_hint"))
        self._hint_label.setWordWrap(True)
        self._hint_label.setStyleSheet("color: #9ca3af; font-size: 12px;")
        hotkey_layout.addWidget(self._hint_label)

        self._cancel_label = QLabel(t("settings.hotkey_cancel"))
        self._cancel_label.setWordWrap(True)
        self._cancel_label.setStyleSheet("color: #9ca3af; font-size: 12px;")
        hotkey_layout.addWidget(self._cancel_label)

        hotkey_group.setLayout(hotkey_layout)
        layout.addWidget(hotkey_group)

        # === Buttons ===
        button_box = QDialogButtonBox()
        self._save_btn = QPushButton(t("settings.save"))
        self._save_btn.setDefault(True)
        self._cancel_btn = QPushButton(t("settings.cancel"))
        button_box.addButton(self._save_btn, QDialogButtonBox.AcceptRole)
        button_box.addButton(self._cancel_btn, QDialogButtonBox.RejectRole)
        self._save_btn.clicked.connect(self._save_and_close)
        self._cancel_btn.clicked.connect(self.reject)
        layout.addWidget(button_box)

    def _load_config(self):
        # General tab — language
        idx = self.language_combo.findData(self.config.language)
        if idx >= 0:
            self.language_combo.setCurrentIndex(idx)
        self.auto_start_check.setChecked(self.config.window.auto_start)

        # STT tab
        self.stt_api_key_input.setText(self.config.asr.api_key)
        self.stt_base_url_input.setText(self.config.asr.base_url)
        idx = self.stt_model_combo.findText(self.config.asr.model)
        if idx >= 0:
            self.stt_model_combo.setCurrentIndex(idx)
        else:
            self.stt_model_combo.setEditText(self.config.asr.model)
        idx = self.stt_lang_combo.findData(self.config.asr.language)
        if idx < 0:
            idx = self.stt_lang_combo.findData("auto")
        self.stt_lang_combo.setCurrentIndex(idx)
        self.sample_rate_spin.setValue(self.config.recording.sample_rate)

        # Polish tab
        self.polish_api_key_input.setText(self.config.polish.api_key)
        self.polish_base_url_input.setText(self.config.polish.base_url)
        self.polish_enabled_check.setChecked(self.config.polish.enabled)
        idx = self.polish_style_combo.findData(self.config.polish.style)
        if idx < 0:
            idx = self.polish_style_combo.findData("default")
        self.polish_style_combo.setCurrentIndex(idx)
        idx = self.polish_model_combo.findText(self.config.polish.model)
        if idx >= 0:
            self.polish_model_combo.setCurrentIndex(idx)
        else:
            self.polish_model_combo.setEditText(self.config.polish.model)

        # Output
        self.paste_delay_spin.setValue(self.config.output.paste_delay_ms)
        idx = self.paste_mode_combo.findData(self.config.output.paste_mode)
        if idx < 0:
            idx = self.paste_mode_combo.findData("auto")
        self.paste_mode_combo.setCurrentIndex(idx)
        self.auto_paste_check.setChecked(self.config.output.auto_paste)

        # Glossary
        self.glossary_table.setRowCount(0)
        for entry in self.config.glossary:
            self._add_glossary_row(entry.source, entry.replacement)

        # Hotkeys
        self.hotkey_toggle_check.setChecked(self.config.hotkey.toggle_enabled)
        self._update_microphone_device_label()

    def _save_and_close(self):
        if not check_network_available():
            self._toast = Toast(t("settings.network_error"), parent=self)
            self._toast.show()
            return

        api_key = self.stt_api_key_input.text().strip()
        polish_key = self.polish_api_key_input.text().strip()
        if not api_key and not polish_key:
            self._toast = Toast(t("settings.api_key_required"), parent=self)
            self._toast.show()
            return

        # General — language
        self.config.language = self.language_combo.currentData()
        self.config.window.auto_start = self.auto_start_check.isChecked()

        # STT
        self.config.asr.api_key = api_key
        self.config.asr.base_url = self.stt_base_url_input.text().strip() or DEFAULT_BASE_URL
        self.config.asr.model = self.stt_model_combo.currentText()
        self.config.asr.language = self.stt_lang_combo.currentData()
        self.config.recording.sample_rate = self.sample_rate_spin.value()

        # Polish
        self.config.polish.api_key = self.polish_api_key_input.text().strip()
        self.config.polish.base_url = self.polish_base_url_input.text().strip() or DEFAULT_BASE_URL
        self.config.polish.model = self.polish_model_combo.currentText()
        self.config.polish.enabled = self.polish_enabled_check.isChecked()
        self.config.polish.style = self.polish_style_combo.currentData()

        # Output
        self.config.output.paste_delay_ms = self.paste_delay_spin.value()
        self.config.output.paste_mode = self.paste_mode_combo.currentData()
        self.config.output.auto_paste = self.auto_paste_check.isChecked()

        # Glossary
        self.config.glossary = self._collect_glossary_entries()

        # Hotkeys
        self.config.hotkey.toggle_enabled = self.hotkey_toggle_check.isChecked()

        self.config.save()
        self.settings_saved.emit()
        self.accept()

    def _add_glossary_row(self, source: str = "", replacement: str = ""):
        row = self.glossary_table.rowCount()
        self.glossary_table.insertRow(row)
        self.glossary_table.setItem(row, 0, QTableWidgetItem(source))
        self.glossary_table.setItem(row, 1, QTableWidgetItem(replacement))

    def _remove_selected_glossary_rows(self):
        rows = sorted(
            {index.row() for index in self.glossary_table.selectedIndexes()},
            reverse=True,
        )
        for row in rows:
            self.glossary_table.removeRow(row)

    def _collect_glossary_entries(self) -> list[GlossaryEntry]:
        entries = []
        for row in range(self.glossary_table.rowCount()):
            source_item = self.glossary_table.item(row, 0)
            replacement_item = self.glossary_table.item(row, 1)
            source = source_item.text().strip() if source_item else ""
            replacement = replacement_item.text().strip() if replacement_item else ""
            if source and replacement:
                entries.append(GlossaryEntry(source=source, replacement=replacement))
        return entries

    def _update_microphone_device_label(self):
        device_name = get_default_input_device_name()
        self.mic_device_label.setText(device_name or t("settings.mic_device_none"))

    def _toggle_microphone_monitor(self):
        if self._mic_monitor and self._mic_monitor.is_running:
            self._stop_microphone_monitor()
        else:
            self._start_microphone_monitor()

    def _start_microphone_monitor(self):
        self._stop_microphone_monitor()
        self._update_microphone_device_label()
        self._mic_monitor = MicrophoneMonitor(self.sample_rate_spin.value())
        if not self._mic_monitor.start():
            self.mic_level_bar.setValue(0)
            detail = self._mic_monitor.error or t("settings.mic_status_error")
            self.mic_status_label.setText(f"{t('settings.mic_status_error')}: {detail}")
            self.mic_test_btn.setText(t("settings.mic_test_start"))
            return
        self.mic_status_label.setText(t("settings.mic_status_listening"))
        self.mic_test_btn.setText(t("settings.mic_test_stop"))
        self._mic_timer.start()

    def _stop_microphone_monitor(self):
        self._mic_timer.stop()
        if self._mic_monitor:
            self._mic_monitor.stop()
        self.mic_level_bar.setValue(0)
        self.mic_status_label.setText(t("settings.mic_status_idle"))
        self.mic_test_btn.setText(t("settings.mic_test_start"))

    def _refresh_microphone_level(self):
        if not self._mic_monitor or not self._mic_monitor.is_running:
            return
        level = self._mic_monitor.input_level
        self.mic_level_bar.setValue(int(level * 100))
        if level < 0.02:
            self.mic_status_label.setText(t("settings.mic_status_silent"))
        else:
            self.mic_status_label.setText(t("settings.mic_status_ok"))

    def closeEvent(self, event):
        self._stop_microphone_monitor()
        super().closeEvent(event)

    def reject(self):
        self._stop_microphone_monitor()
        super().reject()

    def accept(self):
        self._stop_microphone_monitor()
        super().accept()
