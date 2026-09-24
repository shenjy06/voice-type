"""Tests for SQLite local history storage."""

import sqlite3

from datetime import datetime, timedelta

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

    def test_table_columns(self, tmp_path):
        path = tmp_path / "history.sqlite3"
        store = HistoryStore(path=path)
        store.add("hello")

        with sqlite3.connect(path) as conn:
            columns = conn.execute("PRAGMA table_info(history)").fetchall()

        assert [column[1] for column in columns] == [
            "created_at",
            "text",
            "audio_path",
            "duration_ms",
            "processing_ms",
        ]

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


class TestHistoryArchiveAndStats:
    def test_add_stores_archive_metadata(self, tmp_path):
        store = HistoryStore(path=tmp_path / "history.sqlite3")
        store.add("hello", audio_path="/x/1.wav", duration_ms=1200, processing_ms=300)
        entry = store.load()[0]
        assert entry.audio_path == "/x/1.wav"
        assert entry.duration_ms == 1200
        assert entry.processing_ms == 300
        store.shutdown()

    def test_add_without_metadata_keeps_nulls(self, tmp_path):
        store = HistoryStore(path=tmp_path / "history.sqlite3")
        store.add("plain")
        entry = store.load()[0]
        assert entry.audio_path is None
        assert entry.duration_ms is None
        assert entry.processing_ms is None
        store.shutdown()

    def test_old_database_migrates_to_new_columns(self, tmp_path):
        """A pre-archive DB (created_at/text only) gains the new columns on
        open; old rows read back as None."""
        path = tmp_path / "history.sqlite3"
        with sqlite3.connect(path) as conn:
            conn.execute("CREATE TABLE history (created_at TEXT, text TEXT)")
            conn.execute("INSERT INTO history (created_at, text) VALUES ('t', 'old')")

        store = HistoryStore(path=path)
        entry = store.load()[0]
        assert entry.text == "old"
        assert entry.audio_path is None

        columns = {row[1] for row in sqlite3.connect(path).execute("PRAGMA table_info(history)")}
        assert {"audio_path", "duration_ms", "processing_ms"} <= columns
        store.shutdown()

    def test_stats_aggregates_buckets(self, tmp_path):
        store = HistoryStore(path=tmp_path / "history.sqlite3")
        store.add("今天测试" * 4, duration_ms=1000)   # 16 chars, today
        store.add("old text", duration_ms=2000)
        entries = store.load()
        entries[1].created_at = (datetime.now() - timedelta(days=3)).isoformat()
        with sqlite3.connect(store.path) as conn:
            conn.execute(
                "UPDATE history SET created_at = ? WHERE rowid = 2",
                (entries[1].created_at,),
            )

        stats = store.stats()
        assert stats["total"] == 2
        assert stats["total_chars"] == 16 + len("old text")
        assert stats["total_duration_ms"] == 3000
        assert stats["today_count"] == 1
        assert stats["week_count"] == 2
        assert stats["est_minutes_saved"] == round((16 + len("old text")) / 40, 1)
        store.shutdown()

    def test_stats_empty_history(self, tmp_path):
        store = HistoryStore(path=tmp_path / "history.sqlite3")
        stats = store.stats()
        assert stats["total"] == 0
        assert stats["total_chars"] == 0
        assert stats["est_minutes_saved"] == 0.0
        store.shutdown()

    def test_meta_after_clear_round_trip(self, tmp_path):
        store = HistoryStore(path=tmp_path / "history.sqlite3")
        store.add("a", audio_path="/a.wav", duration_ms=5, processing_ms=6)
        store.clear()
        assert store.load() == []
        store.shutdown()
