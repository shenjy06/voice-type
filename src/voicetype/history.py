"""SQLite-backed local history storage for recognized text."""

import logging
import queue
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

    All SQLite operations run on a single dedicated background thread via a
    queue, so the connection is always accessed from one thread. This avoids
    ``check_same_thread=False`` (which was a workaround for cross-thread
    access) and uses WAL mode for better concurrent read performance.

    Public methods (``add``, ``load``, ``clear``) enqueue work on the DB
    thread and then block on a ``threading.Event`` until that thread has
    finished the operation — callers get ordering and durability guarantees,
    while all SQLite access stays single-threaded. After ``shutdown()`` the
    methods degrade to safe no-ops instead of blocking forever.
    """

    def __init__(self, path: Path = HISTORY_DB_FILE, limit: int = DEFAULT_HISTORY_LIMIT):
        self.path = path
        self.limit = limit
        self.path.parent.mkdir(parents=True, exist_ok=True)

        # In-memory cache + dirty flag — avoids re-querying SQLite when
        # nothing has changed since the last load. Writes happen only on the
        # DB thread; readers always see a fully-built list because _do_load
        # rebinds the attribute atomically instead of mutating it in place.
        self._dirty = True
        self._cached_entries: list[HistoryEntry] = []
        self._stopped = False

        # Command queue for the dedicated DB thread. Each item is a tuple:
        #   ("add", text, event)   — insert a new entry; event is set on completion
        #   ("load", event)        — reload the cache; event is set on completion
        #   ("clear", event)       — delete all rows; event is set on completion
        #   ("stop",)              — shut down the thread
        self._queue: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._db_loop, daemon=True)
        self._thread.start()

    # ---- public API ----------------------------------------------------------

    def add(self, text: str) -> HistoryEntry | None:
        clean_text = text.strip()
        if not clean_text:
            return None
        entry = HistoryEntry(
            created_at=datetime.now().isoformat(timespec="seconds"),
            text=clean_text,
        )
        if self._stopped:
            return entry
        done = threading.Event()
        self._queue.put(("add", entry, done))
        done.wait()
        return entry

    def load(self) -> list[HistoryEntry]:
        if not self.path.exists():
            return []
        if not self._dirty:
            logger.debug("Loading history from cache (%d entries)", len(self._cached_entries))
            # Return a copy so callers can't mutate the shared cache.
            return list(self._cached_entries)
        if self._stopped:
            return list(self._cached_entries)
        done = threading.Event()
        self._queue.put(("load", done))
        done.wait()
        return list(self._cached_entries)

    def clear(self) -> None:
        if self._stopped:
            return
        done = threading.Event()
        self._queue.put(("clear", done))
        done.wait()
        logger.info("History cleared")

    def shutdown(self) -> None:
        """Signal the DB thread to exit and join it (call at application quit)."""
        if self._stopped:
            return
        self._stopped = True
        self._queue.put(("stop",))
        self._thread.join(timeout=2.0)

    # ---- DB thread -----------------------------------------------------------

    def _db_loop(self) -> None:
        """Run SQLite operations on a dedicated thread, draining the command queue."""
        conn = sqlite3.connect(self.path)
        conn.execute("PRAGMA journal_mode=WAL")
        self._init_db(conn)

        try:
            while True:
                cmd = self._queue.get()
                action = cmd[0]
                if action == "stop":
                    break
                # One failed command must NOT kill this thread — the finally
                # blocks in _do_* still release the waiting caller, and the
                # thread stays alive for subsequent operations. Without this
                # guard a single sqlite3.Error (locked DB, full disk) would
                # wedge every later add/load/clear on done.wait() forever.
                try:
                    if action == "add":
                        _, entry, done = cmd
                        self._do_add(conn, entry, done)
                    elif action == "load":
                        _, done = cmd
                        self._do_load(conn, done)
                    elif action == "clear":
                        _, done = cmd
                        self._do_clear(conn, done)
                    else:
                        logger.warning("Unknown history DB command: %r", action)
                except Exception:
                    logger.exception("History DB operation failed: %s", action)
        finally:
            conn.close()

    def _do_add(self, conn: sqlite3.Connection, entry: HistoryEntry, done: threading.Event) -> None:
        try:
            conn.execute(
                "INSERT INTO history (created_at, text) VALUES (?, ?)",
                (entry.created_at, entry.text),
            )
            conn.commit()
            count = conn.execute("SELECT COUNT(*) FROM history").fetchone()[0]
            if count > self.limit * 2:
                self._trim(conn)
            self._dirty = True
        finally:
            done.set()

    def _do_load(self, conn: sqlite3.Connection, done: threading.Event) -> None:
        try:
            rows = conn.execute(
                "SELECT created_at, text FROM history ORDER BY rowid DESC LIMIT ?",
                (self.limit,),
            ).fetchall()
            self._cached_entries = [HistoryEntry(created_at=row[0], text=row[1]) for row in rows]
            self._dirty = False
            logger.debug("History loaded from DB: %d entries", len(self._cached_entries))
        finally:
            done.set()

    def _do_clear(self, conn: sqlite3.Connection, done: threading.Event) -> None:
        try:
            conn.execute("DELETE FROM history")
            conn.commit()
            self._dirty = True
        finally:
            done.set()

    # ---- schema --------------------------------------------------------------

    def _init_db(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS history (
                created_at TEXT NOT NULL,
                text TEXT NOT NULL
            )
            """
        )
        conn.commit()

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
        conn.commit()
