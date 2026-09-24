"""SQLite-backed local history storage for recognized text."""

import logging
import queue
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from voicetype.config import CONFIG_DIR

logger = logging.getLogger(__name__)

HISTORY_DB_FILE = CONFIG_DIR / "history.sqlite3"
DEFAULT_HISTORY_LIMIT = 20

# Rough typing-speed estimate used for the "minutes saved" stat: ~40 words
# per minute at ~5 characters per word ≈ 200 characters per minute.
_CHARS_PER_MINUTE = 200


@dataclass
class HistoryEntry:
    created_at: str
    text: str
    # Audio-archive metadata (None when archiving is off / pre-migration rows).
    audio_path: str | None = None
    duration_ms: int | None = None
    processing_ms: int | None = None


class HistoryStore:
    """Persist recognized text to a local SQLite database.

    All SQLite operations run on a single dedicated background thread via a
    queue, so the connection is always accessed from one thread. This avoids
    ``check_same_thread=False`` (which was a workaround for cross-thread
    access) and uses WAL mode for better concurrent read performance.

    Public methods (``add``, ``load``, ``clear``, ``stats``) enqueue work on
    the DB thread and then block on a ``threading.Event`` until that thread
    has finished the operation — callers get ordering and durability
    guarantees, while all SQLite access stays single-threaded. After
    ``shutdown()`` the methods degrade to safe no-ops instead of blocking
    forever.
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
        #   ("add", entry, event)          — insert a new entry
        #   ("load", event)                — reload the cache
        #   ("clear", event)               — delete all rows
        #   ("stats", event, result_box)   — aggregate stats into result_box
        #   ("stop",)                      — shut down the thread
        # Events are set on completion so callers get durability guarantees.
        self._queue: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._db_loop, daemon=True)
        self._thread.start()

    # ---- public API ----------------------------------------------------------

    def add(
        self,
        text: str,
        audio_path: str | None = None,
        duration_ms: int | None = None,
        processing_ms: int | None = None,
    ) -> HistoryEntry | None:
        clean_text = text.strip()
        if not clean_text:
            return None
        entry = HistoryEntry(
            created_at=datetime.now().isoformat(timespec="seconds"),
            text=clean_text,
            audio_path=audio_path,
            duration_ms=duration_ms,
            processing_ms=processing_ms,
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

    def stats(self) -> dict:
        """Aggregate usage statistics over the whole history table.

        Returns a dict with keys: total, total_chars, total_duration_ms,
        today_count, today_chars, week_count, week_chars, est_minutes_saved.
        Degrades to zeroed stats after shutdown or on DB failure.
        """
        empty = {
            "total": 0,
            "total_chars": 0,
            "total_duration_ms": 0,
            "today_count": 0,
            "today_chars": 0,
            "week_count": 0,
            "week_chars": 0,
            "est_minutes_saved": 0.0,
        }
        if self._stopped or not self.path.exists():
            return empty
        done = threading.Event()
        result_box: dict = {}
        self._queue.put(("stats", done, result_box))
        done.wait()
        return result_box.get("stats", empty)

    @staticmethod
    def prune_archive(archive_dir: Path, retention_days: int) -> int:
        """Delete expired archived WAV files; return the deleted count.

        ``archive_dir`` is swept for WAV files older than ``retention_days``
        days (by mtime). History entries whose ``audio_path`` no longer
        exists on disk are NOT rewritten — the dialog checks file existence
        when deciding whether to show the play button. Runs synchronously on
        the caller's thread; invoke from a background thread, not the UI.
        """
        if not archive_dir.exists():
            return 0
        # A misconfigured retention (0/negative) must never wipe the archive.
        if retention_days < 1:
            logger.warning("Ignoring invalid archive retention: %s days", retention_days)
            return 0
        cutoff = time.time() - retention_days * 86400
        deleted = 0
        for f in archive_dir.glob("*.wav"):
            try:
                if f.stat().st_mtime < cutoff:
                    f.unlink()
                    deleted += 1
            except OSError:
                pass
        if deleted:
            logger.info("Pruned %d expired archived audio files", deleted)
        return deleted

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
                    elif action == "stats":
                        _, done, result_box = cmd
                        self._do_stats(conn, done, result_box)
                    else:
                        logger.warning("Unknown history DB command: %r", action)
                except Exception:
                    logger.exception("History DB operation failed: %s", action)
        finally:
            conn.close()

    def _do_add(self, conn: sqlite3.Connection, entry: HistoryEntry, done: threading.Event) -> None:
        try:
            conn.execute(
                """
                INSERT INTO history (created_at, text, audio_path, duration_ms, processing_ms)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    entry.created_at,
                    entry.text,
                    entry.audio_path,
                    entry.duration_ms,
                    entry.processing_ms,
                ),
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
                """
                SELECT created_at, text, audio_path, duration_ms, processing_ms
                FROM history ORDER BY rowid DESC LIMIT ?
                """,
                (self.limit,),
            ).fetchall()
            self._cached_entries = [
                HistoryEntry(
                    created_at=row[0],
                    text=row[1],
                    audio_path=row[2],
                    duration_ms=row[3],
                    processing_ms=row[4],
                )
                for row in rows
            ]
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

    def _do_stats(
        self, conn: sqlite3.Connection, done: threading.Event, result_box: dict
    ) -> None:
        try:
            today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = today_start - timedelta(days=7)
            today_iso = today_start.isoformat()
            week_iso = week_start.isoformat()
            total, total_chars, total_duration = conn.execute(
                """
                SELECT COUNT(*), COALESCE(SUM(LENGTH(text)), 0),
                       COALESCE(SUM(duration_ms), 0)
                FROM history
                """
            ).fetchone()
            today_count, today_chars = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(LENGTH(text)), 0) FROM history WHERE created_at >= ?",
                (today_iso,),
            ).fetchone()
            week_count, week_chars = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(LENGTH(text)), 0) FROM history WHERE created_at >= ?",
                (week_iso,),
            ).fetchone()
            result_box["stats"] = {
                "total": total,
                "total_chars": total_chars,
                "total_duration_ms": total_duration,
                "today_count": today_count,
                "today_chars": today_chars,
                "week_count": week_count,
                "week_chars": week_chars,
                "est_minutes_saved": round(total_chars / _CHARS_PER_MINUTE, 1),
            }
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
        # Migrate pre-archive databases: add the audio metadata columns to
        # tables created before they existed. Old rows keep NULLs, which
        # load() surfaces as None.
        existing = {row[1] for row in conn.execute("PRAGMA table_info(history)")}
        for column, ddl in (
            ("audio_path", "ALTER TABLE history ADD COLUMN audio_path TEXT"),
            ("duration_ms", "ALTER TABLE history ADD COLUMN duration_ms INTEGER"),
            ("processing_ms", "ALTER TABLE history ADD COLUMN processing_ms INTEGER"),
        ):
            if column not in existing:
                conn.execute(ddl)
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
