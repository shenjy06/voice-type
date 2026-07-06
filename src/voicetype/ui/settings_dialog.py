"""Settings dialog — configure API, models, hotkey, etc."""

import logging
import threading

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QLineEdit,
    QComboBox, QFormLayout, QGroupBox, QSpinBox, QCheckBox,
    QDialogButtonBox, QTabWidget, QWidget, QPushButton, QProgressBar,
    QHBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView,
    QCompleter,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QIcon, QCursor
from voicetype.api_client import fetch_models
from voicetype.audio import MicrophoneMonitor, get_default_input_device_name
from voicetype.config import AppConfig, DEFAULT_BASE_URL, GlossaryEntry
from voicetype.constants import PASTE_MODES, ASR_LANGUAGES, DENOISE_STRENGTHS
from voicetype.network import check_network_available
from voicetype.ui.hotkey_recorder import HotkeyRecorder
from voicetype.ui.main_window import Toast

logger = logging.getLogger(__name__)
from voicetype.ui.icon_utils import make_circle_icon
from voicetype.i18n import t

_SETTINGS_ICON = None


def _get_settings_icon() -> QIcon:
    """Lazily create settings icon (requires QApplication to exist first)."""
    global _SETTINGS_ICON
    if _SETTINGS_ICON is None:
        _SETTINGS_ICON = make_circle_icon("⚙", (99, 102, 241), font_size=14, font_family="Segoe UI")
    return _SETTINGS_ICON


class SettingsDialog(QDialog):

    settings_saved = Signal()
    # Emitted (on the UI thread) when the background network check finishes;
    # carries True if the network is reachable.
    _network_check_done = Signal(bool)
    # Emitted (on the UI thread) with the resolved default input device name.
    _device_name_ready = Signal(str)
    # Emitted (on the UI thread) with (section, model_ids) when a background
    # model-list fetch succeeds. section is "asr" or "polish".
    _models_fetched = Signal(str, list)
    # Emitted (on the UI thread) with (section, error_message) when a
    # background model-list fetch fails.
    _models_error = Signal(str, str)

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
        self._wrap_adjust_pending = False
        # Refresh buttons by section ("asr"/"polish") — populated in _init_ui.
        # Must exist before _init_ui() runs because _make_model_row writes to it.
        self._refresh_buttons: dict[str, QPushButton] = {}
        self._model_before_fetch: dict[str, str] = {}
        self._model_items_before_fetch: dict[str, list] = {}
        self._init_ui()
        self._load_config()
        # Word-wrapped labels placed as QFormLayout fields — their height must
        # be enforced because QFormLayout sizes field rows by sizeHint, not by
        # heightForWidth, so wrapped text gets clipped (see _adjust_wrap_heights).
        self._wrap_labels = [
            self.mic_device_label,
            self.mic_status_label,
            self.denoise_hint_label,
        ]
        self._tabs.currentChanged.connect(lambda _: self._schedule_adjust_wrap_heights())
        # Snapshot original API-related fields to detect changes on save
        self._initial_api_state = self._snapshot_api_state()
        # Route the background network-check result back to the UI thread.
        self._network_check_done.connect(self._on_network_check_done)
        # Route the background device-name query back to the UI thread.
        self._device_name_ready.connect(self._set_microphone_device_label)
        # Route background model-list fetch results back to the UI thread.
        self._models_fetched.connect(self._on_models_fetched)
        self._models_error.connect(self._on_models_error)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        def _make_model_row(combo: QComboBox, section: str) -> QWidget:
            """Wrap a model combo with a 'fetch models' refresh button.

            The combo stays editable so the user can still type a model name
            that the provider doesn't list (some providers hide certain
            models from the /models endpoint). A completer on the combo lets
            the user filter the provider's model list by typing a keyword —
            essential when a provider returns dozens of models (e.g.
            SiliconFlow lists 50+).
            """
            # Attach a completer that filters by substring (not just prefix)
            # so the user can type any fragment of the model id. The completer
            # shares the combo's own model, so it stays in sync after
            # fetch_models() repopulates the list.
            completer = QCompleter(combo)
            completer.setModel(combo.model())
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            completer.setFilterMode(Qt.MatchContains)
            combo.setCompleter(completer)

            container = QWidget()
            row = QHBoxLayout(container)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
            row.addWidget(combo, 1)
            btn = QPushButton("🔄")
            btn.setFixedWidth(32)
            btn.setToolTip(t("settings.refresh_models"))
            btn.setCursor(QCursor(Qt.PointingHandCursor))
            btn.clicked.connect(lambda checked=False, s=section: self._fetch_models(s))
            row.addWidget(btn)
            self._refresh_buttons[section] = btn
            return container

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
        stt_api_layout.addRow(t("settings.model"), _make_model_row(self.stt_model_combo, "asr"))

        self.stt_lang_combo = QComboBox()
        for code in ASR_LANGUAGES:
            label = t("settings.lang_auto") if code == "auto" else code
            self.stt_lang_combo.addItem(label, code)
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

        self.denoise_check = QCheckBox(t("settings.denoise_enabled"))
        self.denoise_check.toggled.connect(self._on_denoise_toggled)
        stt_misc_layout.addRow("", self.denoise_check)

        self.denoise_strength_combo = QComboBox()
        for label_key, value in DENOISE_STRENGTHS:
            self.denoise_strength_combo.addItem(t(label_key), value)
        stt_misc_layout.addRow(t("settings.denoise_strength"), self.denoise_strength_combo)

        self.denoise_hint_label = QLabel(t("settings.denoise_hint"))
        self.denoise_hint_label.setWordWrap(True)
        self.denoise_hint_label.setStyleSheet("color: #9ca3af; font-size: 12px;")
        stt_misc_layout.addRow("", self.denoise_hint_label)

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
        polish_api_layout.addRow(t("settings.model"), _make_model_row(self.polish_model_combo, "polish"))

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
        for label_key, value in PASTE_MODES:
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

        hotkey_form = QFormLayout()
        self.hotkey_recorder = HotkeyRecorder()
        self.hotkey_recorder.hotkey_captured.connect(self._on_hotkey_captured)
        hotkey_form.addRow(t("settings.hotkey_toggle_key"), self.hotkey_recorder)
        hotkey_layout.addLayout(hotkey_form)

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

        self.denoise_check.setChecked(self.config.recording.denoise_enabled)
        idx = self.denoise_strength_combo.findData(self.config.recording.denoise_strength)
        if idx < 0:
            idx = self.denoise_strength_combo.findData("medium")
        self.denoise_strength_combo.setCurrentIndex(idx)
        self._on_denoise_toggled(self.denoise_check.isChecked())

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
        self.hotkey_recorder.set_hotkey(self.config.hotkey.toggle_hotkey)
        self._update_microphone_device_label()

    def _snapshot_api_state(self) -> dict:
        """Capture current API-related fields so we can detect changes on save."""
        return {
            "stt_api_key": self.stt_api_key_input.text(),
            "stt_base_url": self.stt_base_url_input.text(),
            "polish_api_key": self.polish_api_key_input.text(),
            "polish_base_url": self.polish_base_url_input.text(),
        }

    def _api_state_changed(self) -> bool:
        """Return True if any API-related field differs from the snapshot."""
        current = self._snapshot_api_state()
        return current != self._initial_api_state

    def _save_and_close(self):
        # Validate keys synchronously first — no network needed for that.
        api_key = self.stt_api_key_input.text().strip()
        polish_key = self.polish_api_key_input.text().strip()
        if not api_key and not polish_key:
            logger.warning("Save rejected: no API key provided")
            self._toast = Toast(t("settings.api_key_required"), parent=self)
            self._toast.show()
            return

        # Only require network access if an API-related field actually changed.
        if not self._api_state_changed():
            logger.debug("API state unchanged — saving without network check")
            self._apply_save()
            return

        # Run the (blocking, up to ~2s offline) network check on a background
        # thread so the dialog stays responsive. Disable the save button and
        # show a checking state until the result lands back on the UI thread.
        logger.info("API state changed — checking network availability")
        self._set_checking_network(True)

        def _check():
            ok = check_network_available()
            self._network_check_done.emit(ok)

        threading.Thread(target=_check, daemon=True).start()

    def _on_network_check_done(self, ok: bool):
        self._set_checking_network(False)
        if not ok:
            logger.warning("Save rejected: network unavailable")
            self._toast = Toast(t("settings.network_error"), parent=self)
            self._toast.show()
            return
        self._apply_save()

    def _set_checking_network(self, checking: bool):
        """Toggle the save button into/out of the network-checking state."""
        self._save_btn.setEnabled(not checking)
        self._save_btn.setText(
            t("settings.network_checking") if checking else t("settings.save")
        )

    # ---- model list fetching -----------------------------------------------

    def _fetch_models(self, section: str) -> None:
        """Fetch available models from the provider on a background thread.

        ``section`` is "asr" or "polish". Reads the current api_key /
        base_url from the inputs so the user can fill them in and fetch
        without saving first.
        """
        if section == "asr":
            api_key = self.stt_api_key_input.text().strip()
            base_url = self.stt_base_url_input.text().strip() or DEFAULT_BASE_URL
            combo = self.stt_model_combo
        else:
            api_key = self.polish_api_key_input.text().strip()
            base_url = self.polish_base_url_input.text().strip() or DEFAULT_BASE_URL
            combo = self.polish_model_combo

        if not api_key:
            self._on_models_error(section, t("settings.api_key_required"))
            return

        # Snapshot the current selection so it survives repopulating the combo,
        # and save the current items so they can be restored on error.
        self._model_before_fetch[section] = combo.currentText().strip()
        self._model_items_before_fetch[section] = [
            combo.itemText(i) for i in range(combo.count())
        ]
        combo.clear()
        combo.addItem(t("settings.loading_models"))
        combo.setEnabled(False)
        self._set_refreshing(section, True)

        def _work():
            try:
                models = fetch_models(api_key, base_url)
                self._models_fetched.emit(section, models)
            except Exception as e:
                self._models_error.emit(section, str(e))

        threading.Thread(target=_work, daemon=True).start()

    def _set_refreshing(self, section: str, refreshing: bool) -> None:
        """Toggle a section's refresh button into/out of the loading state."""
        btn = self._refresh_buttons.get(section)
        if btn is None:
            return
        btn.setEnabled(not refreshing)
        btn.setText("⏳" if refreshing else "🔄")

    def _restore_combo_on_fetch_failure(self, section: str) -> None:
        """Put back every item the combo held before the fetch started."""
        combo = self.stt_model_combo if section == "asr" else self.polish_model_combo
        saved = self._model_items_before_fetch.pop(section, None)
        previous = self._model_before_fetch.get(section, "")
        combo.setEnabled(True)
        if saved is None:
            # The combo was never cleared (e.g. API-key check failed early);
            # just re-enable it and leave the existing items intact.
            return
        combo.clear()
        combo.addItems(saved)
        if previous:
            idx = combo.findText(previous)
            if idx >= 0:
                combo.setCurrentIndex(idx)

    def _on_models_fetched(self, section: str, model_ids: list) -> None:
        """Apply a fetched model list to the section's combo (UI thread)."""
        combo = self.stt_model_combo if section == "asr" else self.polish_model_combo
        previous = self._model_before_fetch.pop(section, "")
        self._set_refreshing(section, False)
        combo.setEnabled(True)

        if not model_ids:
            self._restore_combo_on_fetch_failure(section)
            self._toast = Toast(
                t("settings.models_fetch_failed").format(error=t("settings.models_loaded").format(count=0)),
                parent=self,
            )
            self._toast.show()
            logger.info("Fetched 0 models for section %s", section)
            return

        # Clean up saved snapshot — we're replacing the combo contents.
        self._model_items_before_fetch.pop(section, None)

        # Rebuild the combo from the provider's list. Keep the user's prior
        # selection (even if the provider no longer lists it) so a refresh
        # never silently changes the configured model.
        combo.clear()
        if previous and previous not in model_ids:
            combo.addItem(previous)
        combo.addItems(model_ids)
        if previous:
            idx = combo.findText(previous)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        self._toast = Toast(
            t("settings.models_loaded").format(count=len(model_ids)), parent=self
        )
        self._toast.show()
        logger.info("Fetched %d models for section %s", len(model_ids), section)

    def _on_models_error(self, section: str, error: str) -> None:
        """Surface a fetch failure as a non-blocking toast (UI thread)."""
        self._model_before_fetch.pop(section, None)
        self._restore_combo_on_fetch_failure(section)
        self._set_refreshing(section, False)
        self._toast = Toast(
            t("settings.models_fetch_failed").format(error=error), parent=self
        )
        self._toast.show()
        logger.warning("Model fetch failed for section %s: %s", section, error)

    def _apply_save(self):
        """Write all fields into config, persist, and close the dialog."""
        api_key = self.stt_api_key_input.text().strip()

        # General — language
        self.config.language = self.language_combo.currentData()
        self.config.window.auto_start = self.auto_start_check.isChecked()

        # STT
        self.config.asr.api_key = api_key
        self.config.asr.base_url = self.stt_base_url_input.text().strip()
        self.config.asr.model = self.stt_model_combo.currentText()
        self.config.asr.language = self.stt_lang_combo.currentData()
        self.config.recording.sample_rate = self.sample_rate_spin.value()
        self.config.recording.denoise_enabled = self.denoise_check.isChecked()
        self.config.recording.denoise_strength = self.denoise_strength_combo.currentData()

        # Polish
        self.config.polish.api_key = self.polish_api_key_input.text().strip()
        self.config.polish.base_url = self.polish_base_url_input.text().strip()
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
        self.config.hotkey.toggle_hotkey = self.hotkey_recorder.hotkey()

        self.config.save()
        self.settings_saved.emit()
        self.accept()

    def _add_glossary_row(self, source: str = "", replacement: str = ""):
        row = self.glossary_table.rowCount()
        self.glossary_table.insertRow(row)
        # Store stripped values so users don't see trailing whitespace reload later
        self.glossary_table.setItem(row, 0, QTableWidgetItem(source.strip()))
        self.glossary_table.setItem(row, 1, QTableWidgetItem(replacement.strip()))

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

    def _on_hotkey_captured(self, hotkey: str):
        """Update the recorder display when a key is captured."""
        self.hotkey_recorder.set_hotkey(hotkey)
        self.hotkey_recorder.stop_recording()

    def _on_denoise_toggled(self, enabled: bool):
        """Enable/disable the strength selector to match the checkbox."""
        self.denoise_strength_combo.setEnabled(enabled)
        self.denoise_hint_label.setEnabled(enabled)

    def _update_microphone_device_label(self):
        # sd.query_devices(kind="input") enumerates PortAudio devices, which
        # can take 50-200ms on systems with many audio endpoints. Run it on a
        # background thread and apply the result via signal so dialog open is
        # not blocked. Defer the thread start to the next event-loop tick so
        # the signal is delivered cleanly after construction completes.
        def _query():
            self._device_name_ready.emit(get_default_input_device_name())

        QTimer.singleShot(0, lambda: threading.Thread(target=_query, daemon=True).start())

    def _set_microphone_device_label(self, device_name: str):
        self.mic_device_label.setText(device_name or t("settings.mic_device_none"))
        self._schedule_adjust_wrap_heights()

    def _set_mic_status(self, text: str):
        """Update the mic status label and re-check its wrapped height."""
        self.mic_status_label.setText(text)
        self._schedule_adjust_wrap_heights()

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
            self._set_mic_status(f"{t('settings.mic_status_error')}: {detail}")
            self.mic_test_btn.setText(t("settings.mic_test_start"))
            return
        self._set_mic_status(t("settings.mic_status_listening"))
        self.mic_test_btn.setText(t("settings.mic_test_stop"))
        self._mic_timer.start()

    def _stop_microphone_monitor(self):
        self._mic_timer.stop()
        if self._mic_monitor:
            self._mic_monitor.stop()
        self.mic_level_bar.setValue(0)
        self._set_mic_status(t("settings.mic_status_idle"))
        self.mic_test_btn.setText(t("settings.mic_test_start"))

    def _refresh_microphone_level(self):
        if not self._mic_monitor or not self._mic_monitor.is_running:
            return
        level = self._mic_monitor.input_level
        self.mic_level_bar.setValue(int(level * 100))
        if level < 0.02:
            self._set_mic_status(t("settings.mic_status_silent"))
        else:
            self._set_mic_status(t("settings.mic_status_ok"))

    def _schedule_adjust_wrap_heights(self):
        """Coalesce multiple wrap-height adjustments into one deferred call."""
        if self._wrap_adjust_pending:
            return
        self._wrap_adjust_pending = True
        QTimer.singleShot(0, self._adjust_wrap_heights)

    def _adjust_wrap_heights(self):
        """Force word-wrapped form-field labels to fit their wrapped text.

        QFormLayout determines field-row heights from each widget's sizeHint,
        not from heightForWidth, so a word-wrapped QLabel placed as a form
        field is compressed to a single line whenever its text wraps. In
        English the form labels are longer, the field column narrows, and the
        hint text wraps — producing two clipped lines. Setting each label's
        minimum height to its heightForWidth value forces the layout to
        allocate the full wrapped height.
        """
        self._wrap_adjust_pending = False
        for lbl in self._wrap_labels:
            if lbl.width() <= 0:
                continue
            # Reset first so the label can shrink back down when the dialog
            # widens and the text no longer wraps.
            lbl.setMinimumHeight(0)
            hfw = lbl.heightForWidth(lbl.width())
            if hfw > 0:
                lbl.setMinimumHeight(hfw)

    def showEvent(self, event):
        super().showEvent(event)
        # The layout hasn't resolved field widths until after the first show,
        # so defer the height adjustment to the next event-loop iteration.
        self._schedule_adjust_wrap_heights()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._schedule_adjust_wrap_heights()

    def closeEvent(self, event):
        self._stop_microphone_monitor()
        self.hotkey_recorder.stop_recording()
        super().closeEvent(event)

    def reject(self):
        self._stop_microphone_monitor()
        self.hotkey_recorder.stop_recording()
        super().reject()

    def accept(self):
        self._stop_microphone_monitor()
        self.hotkey_recorder.stop_recording()
        super().accept()
