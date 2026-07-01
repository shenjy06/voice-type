"""ProcessingController — owns the QThread that runs ProcessingWorker.

Encapsulates starting a processing cycle and routing done/error results to
the supplied callbacks, replacing the inline orchestration that previously
lived in src/__main__.py.
"""

from PySide6.QtCore import QThread, QTimer, QObject, Signal

from voicetype.config import AppConfig
from voicetype.processing import ProcessingWorker

# Hard upper bound on a processing cycle. The ASR (30 s) and polish (60 s)
# timeouts should fire first, but if the worker thread dies without emitting a
# signal (e.g. a native crash) this guard ensures the UI is not stuck in
# "润色中…" forever.
_PROCESSING_TIMEOUT_MS = 120_000


class ProcessingController(QObject):
    """Runs ProcessingWorker in a QThread and routes results to callbacks."""

    # Internal signals used to marshal worker results back to the controller's
    # own thread (the UI thread). This is required because the worker lives in
    # a background QThread and the callbacks operate on Qt widgets.
    _done = Signal(str)
    _error = Signal(str)

    def __init__(
        self,
        config: AppConfig,
        on_done,
        on_error,
        parent=None,
    ):
        # Guard against non-QObject parents (e.g. mocked QApplication in tests).
        if parent is not None and not isinstance(parent, QObject):
            parent = None
        super().__init__(parent)
        self._config = config
        self._on_done = on_done
        self._on_error = on_error
        self._thread: QThread | None = None
        self._worker: ProcessingWorker | None = None
        self._timeout_timer: QTimer | None = None
        self._completed = False

        self._done.connect(self._on_worker_done)
        self._error.connect(self._on_worker_error)

    # ---- public API ---------------------------------------------------------

    def is_running(self) -> bool:
        """Return True only if a live thread is still executing."""
        if self._thread is None:
            return False
        try:
            return self._thread.isRunning()
        except RuntimeError:
            # The underlying C++ QThread was already deleted by deleteLater.
            self._thread = None
            self._worker = None
            return False

    def start(
        self,
        recorder,
        context_before: str = "",
        context_after: str = "",
    ) -> None:
        """Start a new processing cycle for the given recorder.

        The worker saves the recorder's captured audio (encoding it to OGG on
        the background thread) before transcribing. ``context_before`` /
        ``context_after`` carry optional cursor context captured at recording
        start, enabling context-aware polishing.
        """
        if self.is_running():
            return

        self._completed = False

        thread = QThread()
        worker = ProcessingWorker(
            self._config, recorder, context_before, context_after
        )
        worker.moveToThread(thread)

        # Worker signals: route results to the UI thread, then quit the thread.
        thread.started.connect(worker.run)
        worker.finished.connect(self._done)
        worker.error.connect(self._error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)

        # Cleanly delete the QObject wrappers once the thread exits.  This is
        # required for QObjects that were moved to the worker thread; without
        # deleteLater their C++ destructors can run on the wrong thread and
        # crash the process during polish completion.
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_thread_finished)

        # Watchdog: if the worker thread finishes without emitting
        # finished/error, surface an error so the UI is unstuck.
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(self._on_timeout)
        timer.start(_PROCESSING_TIMEOUT_MS)

        self._thread = thread
        self._worker = worker
        self._timeout_timer = timer
        thread.start()

    def _on_worker_done(self, refined_text: str) -> None:
        if self._completed:
            return
        self._completed = True
        self._stop_timeout()
        self._on_done(refined_text)

    def _on_worker_error(self, error_msg: str) -> None:
        if self._completed:
            return
        self._completed = True
        self._stop_timeout()
        self._on_error(error_msg)

    def _on_thread_finished(self) -> None:
        """Clear references when the QThread exits.

        Connected to ``thread.finished`` instead of ``deleteLater`` so we
        can safely drop our references *before* the C++ object is destroyed
        by the event loop.  This prevents the next ``is_running()`` call
        from touching a deleted QThread (RuntimeError: Internal C++ object
        already deleted).
        """
        self._thread = None
        self._worker = None

    def _on_timeout(self) -> None:
        if self._completed:
            return
        self._completed = True
        self._cleanup_thread()
        self._on_error("Processing timed out")

    def _stop_timeout(self) -> None:
        if self._timeout_timer is not None:
            self._timeout_timer.stop()
            self._timeout_timer.deleteLater()
            self._timeout_timer = None

    def _cleanup_thread(self) -> None:
        """Force-stop a runaway thread."""
        try:
            if self._thread and self._thread.isRunning():
                self._thread.quit()
                if not self._thread.wait(2000):
                    self._thread.terminate()
                    self._thread.wait(1000)
        except RuntimeError:
            pass
        finally:
            self._thread = None
            self._worker = None

    def shutdown(self) -> None:
        """Stop the thread if running; called at application quit."""
        self._stop_timeout()
        self._cleanup_thread()
