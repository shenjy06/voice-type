"""ProcessingController — owns the QThread that runs ProcessingWorker.

Encapsulates starting a processing cycle and routing done/error results to
the supplied callbacks, replacing the inline orchestration that previously
lived in src/__main__.py.
"""

import logging

from PySide6.QtCore import QThread

from voicetype.config import AppConfig
from voicetype.processing import ProcessingWorker

logger = logging.getLogger(__name__)


class ProcessingController:
    """Runs ProcessingWorker in a QThread and routes results to callbacks."""

    def __init__(
        self,
        config: AppConfig,
        on_done,
        on_error,
    ):
        self._config = config
        self._on_done = on_done
        self._on_error = on_error
        self._thread: QThread | None = None
        self._worker: ProcessingWorker | None = None

    # ---- public API ---------------------------------------------------------

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def start(self, audio_path: str) -> None:
        """Start a new processing cycle for the given audio file."""
        if self.is_running():
            logger.warning("Processing already in progress; ignoring start()")
            return

        thread = QThread()
        worker = ProcessingWorker(self._config, audio_path)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(self._on_done)
        worker.error.connect(self._on_error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        self._thread = thread
        self._worker = worker
        thread.start()

    def shutdown(self) -> None:
        """Stop the thread if running; called at application quit."""
        try:
            if self._thread and self._thread.isRunning():
                self._thread.quit()
                if not self._thread.wait(1000):
                    logger.warning("Processing thread did not stop gracefully; terminating")
                    self._thread.terminate()
                    self._thread.wait(500)
        except RuntimeError:
            pass
        finally:
            self._thread = None
            self._worker = None
