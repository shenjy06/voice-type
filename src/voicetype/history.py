"""SQLite-backed local history storage for recognized text."""

import logging
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from voicetype.config import CONFIG_DIR

logger = logging.getLogger(__name__)

HISTORY_DB_FILE = CONFIG_DIR / "history.sqlite3"
DEFAULT_HISTORY_LIMIT = 20


@dataclass
class HistoryEntry:
    created_at: str
    text: str


class HistoryStore:
    """Persist recognized text to a local SQLite database.

    A single connection is opened once and reused across calls (the schema is
    initialized once at construction) instead of reconnecting on every add /
    load / clear. All access is serialized with a lock so the store is safe
    even though SQLite's default connection is bound to a single thread.
    """

    def __init__(self, path: Path = HISTORY_DB_FILE, limit: int = DEFAULT_HISTORY_LIMIT):
        self.path = path
        self.limit = limit
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False because add() runs on the UI thread while a
        # background paste thread could theoretically touch history; the lock
        # serializes all access regardless.
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._init_db(self._conn)
        # In-memory cache + dirty flag — avoids re-querying SQLite when
        # nothing has changed since the last load.
        self._dirty = True
        self._cached_entries: list[HistoryEntry] = []

    def add(self, text: str) -> HistoryEntry | None:
        clean_text = text.strip()
        if not clean_text:
            return None

        entry = HistoryEntry(
            created_at=datetime.now().isoformat(timespec="seconds"),
            text=clean_text,
        )
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO history (created_at, text) VALUES (?, ?)",
                (entry.created_at, entry.text),
            )
            # Only trim when table exceeds limit significantly, to avoid
            # a full scan + sort on every insert.
            count = self._conn.execute("SELECT COUNT(*) FROM history").fetchone()[0]
            if count > self.limit * 2:
                self._trim(self._conn)
        self._dirty = True
        return entry

    def load(self) -> list[HistoryEntry]:
        if not self.path.exists():
            return []

        with self._lock:
            if not self._dirty:
                logger.debug("Loading history from cache (%d entries)", len(self._cached_entries))
                return self._cached_entries
            rows = self._conn.execute(
                "SELECT created_at, text FROM history ORDER BY rowid DESC LIMIT ?",
                (self.limit,),
            ).fetchall()
            self._cached_entries = [HistoryEntry(created_at=row[0], text=row[1]) for row in rows]
            self._dirty = False
            logger.debug("History loaded from DB: %d entries", len(self._cached_entries))
            return self._cached_entries

    def clear(self) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM history")
        self._dirty = True
        logger.info("History cleared")

    def _init_db(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS history (
                created_at TEXT NOT NULL,
                text TEXT NOT NULL
            )
            """
        )

    def _trim(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            DELETE FROM history
            WHERE rowid NOT IN (
                SELECT rowid FROM history ORDER BY rowid DESC LIMIT ?
            )
            """,
            (self.limit,),
        )
