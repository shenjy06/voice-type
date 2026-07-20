"""Tests for SQLite local history storage."""

import sqlite3

from voicetype.history import HistoryStore


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


    def test_db_error_does_not_kill_worker_thread(self, tmp_path):
        """A failed SQLite operation must not wedge the store.

        Regression: an exception inside a _do_* handler escaped _db_loop and
        killed the daemon thread, so every later add/load/clear blocked
        forever on done.wait(). After the fix the thread logs the failure and
        keeps serving subsequent commands.
        """
        path = tmp_path / "history.sqlite3"
        store = HistoryStore(path=path)
        store.add("ok")

        # Break the schema out from under the DB thread.
        with sqlite3.connect(path) as conn:
            conn.execute("DROP TABLE history")

        # This insert fails inside the DB thread — the call must still return
        # (the entry object is handed back optimistically) and must not hang.
        entry = store.add("boom")
        assert entry is not None

        # The worker survived: later commands still complete.
        store.clear()
        assert isinstance(store.load(), list)
        store.shutdown()

    def test_calls_after_shutdown_do_not_hang(self, tmp_path):
        """Public methods degrade to safe no-ops once the DB thread is gone."""
        store = HistoryStore(path=tmp_path / "history.sqlite3")
        store.add("x")
        store.shutdown()
        store.shutdown()  # idempotent

        entry = store.add("y")
        assert entry is not None  # returned but not persisted
        store.clear()
        assert isinstance(store.load(), list)

    def test_load_returns_independent_copy(self, tmp_path):
        """Mutating the returned list must not corrupt the shared cache."""
        store = HistoryStore(path=tmp_path / "history.sqlite3")
        store.add("one")
        first = store.load()
        first.append("corrupted")
        assert [e.text for e in store.load()] == ["one"]
        store.shutdown()
