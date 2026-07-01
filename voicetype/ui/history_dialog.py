"""History dialog for recent recognized text."""

import pyperclip
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)
from PySide6.QtGui import QIcon

from voicetype.history import HistoryEntry, HistoryStore
from voicetype.ui.icon_utils import make_circle_icon
from voicetype.i18n import t

_HISTORY_ICON = None


def _get_history_icon() -> QIcon:
    """Lazily create history icon (requires QApplication to exist first)."""
    global _HISTORY_ICON
    if _HISTORY_ICON is None:
        _HISTORY_ICON = make_circle_icon("H", (16, 185, 129), font_size=14)
    return _HISTORY_ICON


class HistoryDialog(QDialog):
    paste_requested = Signal(str)

    # After a copy, we briefly restore the original button text after this delay.
    _COPY_FEEDBACK_MS = 1200

    def __init__(self, history_store: HistoryStore, parent=None):
        super().__init__(parent)
        self.history_store = history_store
        self._entries: list[HistoryEntry] = []
        self.setWindowTitle(t("history.title"))
        self.setWindowIcon(_get_history_icon())
        self.setModal(True)
        self.setMinimumSize(640, 420)
        self._copy_feedback_timer = QTimer(self)
        self._copy_feedback_timer.setSingleShot(True)
        self._copy_feedback_timer.timeout.connect(self._restore_copy_label)
        self._init_ui()
        self.reload()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        body = QHBoxLayout()
        body.setSpacing(8)

        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self._show_entry)
        body.addWidget(self.list_widget, 1)

        preview_layout = QVBoxLayout()
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        preview_layout.addWidget(self.preview, 1)

        actions = QHBoxLayout()
        self.copy_btn = QPushButton(t("history.copy"))
        self.copy_btn.setToolTip(t("history.copy"))
        self.paste_btn = QPushButton(t("history.paste"))
        self.clear_btn = QPushButton(t("history.clear"))
        self.copy_btn.clicked.connect(self._copy_current)
        self.paste_btn.clicked.connect(self._paste_current)
        self.clear_btn.clicked.connect(self._clear_history)
        actions.addWidget(self.copy_btn)
        actions.addWidget(self.paste_btn)
        actions.addStretch()
        actions.addWidget(self.clear_btn)
        preview_layout.addLayout(actions)
        body.addLayout(preview_layout, 2)

        layout.addLayout(body, 1)

        self.empty_label = QLabel(t("history.empty"))
        self.empty_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.empty_label)

        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def reload(self):
        self._entries = self.history_store.load()
        self.list_widget.clear()
        for entry in self._entries:
            self.list_widget.addItem(QListWidgetItem(self._label_for(entry)))

        has_entries = bool(self._entries)
        self.list_widget.setVisible(has_entries)
        self.preview.setVisible(has_entries)
        self.copy_btn.setEnabled(has_entries)
        self.paste_btn.setEnabled(has_entries)
        self.clear_btn.setEnabled(has_entries)
        self.empty_label.setVisible(not has_entries)

        if has_entries:
            self.list_widget.setCurrentRow(0)
        else:
            self.preview.clear()

    def _label_for(self, entry: HistoryEntry) -> str:
        first_line = entry.text.splitlines()[0].strip()
        if len(first_line) > 48:
            first_line = first_line[:45] + "..."
        if entry.created_at:
            return f"{entry.created_at}  {first_line}"
        return first_line

    def _current_entry(self) -> HistoryEntry | None:
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self._entries):
            return None
        return self._entries[row]

    def _show_entry(self, row: int):
        entry = self._current_entry()
        self.preview.setPlainText(entry.text if entry else "")

    def _copy_current(self):
        entry = self._current_entry()
        if entry:
            try:
                pyperclip.copy(entry.text)
            except Exception:
                return
            # Briefly change the button text to confirm the copy to the user.
            self.copy_btn.setText(t("history.copied"))
            self._copy_feedback_timer.start(self._COPY_FEEDBACK_MS)

    def _paste_current(self):
        entry = self._current_entry()
        if entry:
            self.paste_requested.emit(entry.text)

    def _clear_history(self):
        self.history_store.clear()
        self.reload()

    def _restore_copy_label(self):
        self.copy_btn.setText(t("history.copy"))

    def retranslate(self):
        self.setWindowTitle(t("history.title"))
        self.copy_btn.setText(t("history.copy"))
        self.paste_btn.setText(t("history.paste"))
        self.clear_btn.setText(t("history.clear"))
        self.empty_label.setText(t("history.empty"))
