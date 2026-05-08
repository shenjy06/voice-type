"""Tests for SQLite local history storage."""

import sqlite3

from src.history import HistoryStore


class TestHistoryStore:
    def test_add_saves_newest_first(self, tmp_path):
        store = HistoryStore(path=tmp_path / "history.sqlite3", limit=20)

        store.add("first")
        second = store.add("second")

        entries = store.load()
        assert entries[0].created_at == second.created_at
        assert entries[0].text == "second"
        assert entries[1].text == "first"

    def test_add_ignores_blank_text(self, tmp_path):
        store = HistoryStore(path=tmp_path / "history.sqlite3")

        assert store.add("   ") is None
        assert store.load() == []

    def test_limit_is_enforced(self, tmp_path):
        store = HistoryStore(path=tmp_path / "history.sqlite3", limit=2)

        store.add("one")
        store.add("two")
        store.add("three")

        assert [entry.text for entry in store.load()] == ["three", "two"]

    def test_table_has_only_time_and_text_columns(self, tmp_path):
        path = tmp_path / "history.sqlite3"
        store = HistoryStore(path=path)
        store.add("hello")

        with sqlite3.connect(path) as conn:
            columns = conn.execute("PRAGMA table_info(history)").fetchall()

        assert [column[1] for column in columns] == ["created_at", "text"]

    def test_clear_removes_entries(self, tmp_path):
        path = tmp_path / "history.sqlite3"
        store = HistoryStore(path=path)
        store.add("hello")

        store.clear()

        assert store.load() == []
        with sqlite3.connect(path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM history").fetchone()[0]
        assert count == 0
