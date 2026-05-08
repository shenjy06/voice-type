"""Tests for the history dialog."""

from src.history import HistoryStore
from src.ui.history_dialog import HistoryDialog


class TestHistoryDialog:
    def test_empty_history_shows_empty_label(self, qtbot, tmp_path):
        store = HistoryStore(path=tmp_path / "history.sqlite3")
        dlg = HistoryDialog(store)
        qtbot.addWidget(dlg)

        assert dlg.list_widget.count() == 0
        assert dlg.copy_btn.isEnabled() is False
        assert dlg.paste_btn.isEnabled() is False

    def test_window_icon_is_set(self, qtbot, tmp_path):
        store = HistoryStore(path=tmp_path / "history.sqlite3")
        dlg = HistoryDialog(store)
        qtbot.addWidget(dlg)

        assert dlg.windowIcon().isNull() is False

    def test_history_entries_populate_list_and_preview(self, qtbot, tmp_path):
        store = HistoryStore(path=tmp_path / "history.sqlite3")
        store.add("hello world")
        dlg = HistoryDialog(store)
        qtbot.addWidget(dlg)

        assert dlg.list_widget.count() == 1
        assert dlg.preview.toPlainText() == "hello world"

    def test_copy_current_copies_text(self, qtbot, tmp_path, mocker):
        store = HistoryStore(path=tmp_path / "history.sqlite3")
        store.add("copy me")
        dlg = HistoryDialog(store)
        qtbot.addWidget(dlg)
        mock_copy = mocker.patch("pyperclip.copy")

        dlg._copy_current()

        mock_copy.assert_called_once_with("copy me")

    def test_paste_current_emits_text(self, qtbot, tmp_path):
        store = HistoryStore(path=tmp_path / "history.sqlite3")
        store.add("paste me")
        dlg = HistoryDialog(store)
        qtbot.addWidget(dlg)

        with qtbot.waitSignal(dlg.paste_requested) as blocker:
            dlg._paste_current()

        assert blocker.args == ["paste me"]

    def test_clear_history_removes_entries(self, qtbot, tmp_path):
        store = HistoryStore(path=tmp_path / "history.sqlite3")
        store.add("old")
        dlg = HistoryDialog(store)
        qtbot.addWidget(dlg)

        dlg._clear_history()

        assert store.load() == []
        assert dlg.list_widget.count() == 0
