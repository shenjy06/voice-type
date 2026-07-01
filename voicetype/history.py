"""SQLite-backed local history storage for recognized text."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from voicetype.config import CONFIG_DIR

HISTORY_DB_FILE = CONFIG_DIR / "history.sqlite3"
DEFAULT_HISTORY_LIMIT = 20


@dataclass
class HistoryEntry:
    created_at: str
    text: str


class HistoryStore:
    def __init__(self, path: Path = HISTORY_DB_FILE, limit: int = DEFAULT_HISTORY_LIMIT):
        self.path = path
        self.limit = limit

    def add(self, text: str) -> HistoryEntry | None:
        clean_text = text.strip()
        if not clean_text:
            return None

        entry = HistoryEntry(
            created_at=datetime.now().isoformat(timespec="seconds"),
            text=clean_text,
        )
        with self._connect() as conn:
            self._init_db(conn)
            conn.execute(
                "INSERT INTO history (created_at, text) VALUES (?, ?)",
                (entry.created_at, entry.text),
            )
            self._trim(conn)
        return entry

    def load(self) -> list[HistoryEntry]:
        if not self.path.exists():
            return []

        with self._connect() as conn:
            self._init_db(conn)
            rows = conn.execute(
                "SELECT created_at, text FROM history ORDER BY rowid DESC LIMIT ?",
                (self.limit,),
            ).fetchall()
        return [HistoryEntry(created_at=row[0], text=row[1]) for row in rows]

    def clear(self) -> None:
        with self._connect() as conn:
            self._init_db(conn)
            conn.execute("DELETE FROM history")

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self.path)

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
