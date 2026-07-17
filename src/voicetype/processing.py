"""Background processing worker — runs save + ASR + LLM polishing off the UI thread."""

import logging
import os
import time

from PySide6.QtCore import QObject, Signal

from voicetype.asr import Transcriber
from voicetype.config import AppConfig
from voicetype.glossary import apply_glossary
from voicetype.i18n import t
from voicetype.polisher import TextPolisher

logger = logging.getLogger(__name__)


# --- Cached API clients --------------------------------------------------
# Transcriber/TextPolisher each wrap an OpenAI httpx client with its own
# connection pool. Constructing them fresh on every processing cycle pays a
# TLS handshake every time, so we cache one instance per distinct API config
# fingerprint. When the user changes keys/base_url/model, the fingerprint
# changes and the cached client is rebuilt — see ``invalidate_clients``.


class _ClientCache:
    """Thread-safe cache of API clients keyed by config fingerprint.

    Each cache slot holds exactly one client (the most recently used
    fingerprint). This avoids the module-level mutable dicts that were
    not thread-safe and provides a clean invalidation interface.
    """

    def __init__(self):
        self._transcriber: tuple[tuple, Transcriber] | None = None
        self._polisher: tuple[tuple, TextPolisher] | None = None

    def get_transcriber(self, config: AppConfig) -> Transcriber:
        fp = (config.asr.api_key, config.asr.base_url, config.asr.model)
        cached = self._transcriber
        if cached is not None and cached[0] == fp:
            return cached[1]
        transcriber = Transcriber(config)
        self._transcriber = (fp, transcriber)
        return transcriber

    def get_polisher(self, config: AppConfig) -> TextPolisher:
        fp = (config.polish.api_key, config.polish.base_url, config.polish.model)
        cached = self._polisher
        if cached is not None and cached[0] == fp:
            return cached[1]
        polisher = TextPolisher(config)
        self._polisher = (fp, polisher)
        return polisher

    def invalidate(self) -> None:
        self._transcriber = None
        self._polisher = None


_client_cache = _ClientCache()


def get_transcriber(config: AppConfig) -> Transcriber:
    """Return a cached Transcriber, rebuilding it when the ASR config changes."""
    return _client_cache.get_transcriber(config)


def get_polisher(config: AppConfig) -> TextPolisher:
    """Return a cached TextPolisher, rebuilding it when the polish config changes."""
    return _client_cache.get_polisher(config)


def invalidate_clients() -> None:
    """Drop cached clients (e.g. after settings change)."""
    _client_cache.invalidate()


class ProcessingWorker(QObject):
    """Runs save -> transcribe -> glossary -> polish and emits signals.

    The audio ``recorder`` is saved (WAV/PCM encoding) on this background
    thread so the encoding cost never blocks the UI thread. The recorder holds
    the captured frames between ``stop()`` and this save; recording cannot
    restart during PROCESSING, so the frames are safe to read here.

    API clients (Transcriber/TextPolisher) are cached across cycles via
    ``get_transcriber``/``get_polisher`` so connection pools are reused.

    This worker supports three mutually exclusive modes, selected by which
    constructor arguments are provided:

    * **Normal mode** — ``recorder`` is provided; the worker calls
      ``recorder.save()`` to encode audio before transcribing.
    * **Retry mode** — ``audio_path`` is provided; the worker reuses an
      existing audio file from a previous failed cycle.
    * **Streaming mode** — ``streaming_transcriber`` is provided; the worker
      calls ``finalize()`` on it to collect the real-time transcript (no file
      is saved).

    Only one of these arguments should be set per instance; the first
    matching mode (in priority order: streaming > retry > normal) is used.

    Signals:
        started()    — emitted before any work begins
        finished(str)— emitted with the refined text (empty string for no transcript)
        error(str)   — emitted on any failure (incl. save failure), with a message
    """

    started = Signal()
    progress = Signal(str)  # stage text, e.g. "转写中..." / "润色中..."
    finished = Signal(str)  # refined text
    error = Signal(str)

    def __init__(
        self,
        config: AppConfig,
        recorder=None,
        context_before: str = "",
        context_after: str = "",
        audio_path: str | None = None,
        streaming_transcriber=None,
    ):
        super().__init__()
        self.config = config
        self.recorder = recorder
        # Cursor context captured at recording start, used for context-aware
        # polishing. Empty strings fall back to standalone polishing.
        self.context_before = context_before
        self.context_after = context_after
        # When set, the worker reuses this existing audio file (retained from
        # a previous failed run) instead of calling recorder.save(). Used by
        # retry; in that case ``recorder`` is not touched.
        self._reused_audio_path = audio_path
        # When set, the worker is in streaming mode — audio was piped to
        # this transcriber during recording; finalize() collects the text.
        self._streaming_transcriber = streaming_transcriber

    def run(self):
        """Dispatch to the appropriate processing path based on constructor args.

        Streaming mode has the highest priority, then retry, then normal.
        """
        if self._streaming_transcriber is not None:
            self._run_streaming()
        elif self._reused_audio_path is not None:
            self._run_retry()
        else:
            self._run_normal()

    # ---- per-mode implementations -------------------------------------------

    def _run_streaming(self) -> None:
        """Streaming mode: finalize the real-time transcriber to collect text.

        No file is saved — audio was piped to the ASR client during recording.
        """
        pipeline_start = time.monotonic()
        try:
            self.started.emit()
            self.progress.emit(t("status.transcribing"))
            transcript = self._streaming_transcriber.finalize()
            logger.info(
                "Streaming transcript finalized in %.1fs: %d chars",
                time.monotonic() - pipeline_start,
                len(transcript),
            )
            self._finish(transcript, pipeline_start)
        except Exception as e:
            logger.error("Streaming processing failed: %s", e, exc_info=True)
            self.error.emit(str(e))

    def _run_retry(self) -> None:
        """Retry mode: reuse the audio file retained from a previous failed run.

        Skips recorder.save() — the file already exists on disk.
        """
        pipeline_start = time.monotonic()
        audio_path = self._reused_audio_path
        try:
            self.started.emit()
            self.progress.emit(t("status.transcribing"))
            logger.debug("Retrying with retained audio: %s", os.path.basename(audio_path))
            transcriber = get_transcriber(self.config)
            transcript = transcriber.transcribe(audio_path)
            self._finish(transcript, pipeline_start, audio_path=audio_path)
        except Exception as e:
            logger.error("Retry processing failed: %s", e, exc_info=True)
            # Retain audio_path on failure so the caller can retry again.
            self.error.emit(str(e))

    def _run_normal(self) -> None:
        """Normal mode: encode captured frames to WAV, then transcribe.

        The encode runs on this background thread so it never blocks the UI.
        """
        pipeline_start = time.monotonic()
        audio_path = None
        try:
            self.started.emit()
            # Encode the captured frames to a temp WAV file on this thread
            # so the (potentially slow) encoding never blocks the UI.
            save_start = time.monotonic()
            self.progress.emit(t("status.saving"))
            audio_path = str(self.recorder.save())
            self.recorder = None  # release reference; buffer freed in save()
            logger.debug("Processing pipeline started: %s", os.path.basename(audio_path))
            logger.info("Audio saved in %.0fms", (time.monotonic() - save_start) * 1000)
            self.progress.emit(t("status.transcribing"))
            transcriber = get_transcriber(self.config)
            transcript = transcriber.transcribe(audio_path)
            self._finish(transcript, pipeline_start, audio_path=audio_path)
        except Exception as e:
            logger.error("Processing pipeline failed: %s", e, exc_info=True)
            self.error.emit(str(e))

    # ---- shared pipeline tail ------------------------------------------------

    def _finish(self, transcript: str, pipeline_start: float, *, audio_path: str | None = None) -> None:
        """Apply glossary, optionally polish, and emit finished.

        ``audio_path``, when set, is the temp WAV file that should be deleted
        on success. It is NOT deleted on the error path (the caller retains the
        file for retry), but this method only runs on the success path — errors
        are handled in the per-mode ``_run_*`` methods.
        """
        if not transcript:
            logger.info(
                "Transcription returned empty — pipeline finished in %.1fs",
                time.monotonic() - pipeline_start,
            )
            self._cleanup_audio(audio_path)
            self.finished.emit("")
            return
        transcript = apply_glossary(transcript, self.config.glossary)
        if not self.config.polish.enabled:
            logger.info(
                "Polishing disabled — emitting transcript directly (pipeline %.1fs)",
                time.monotonic() - pipeline_start,
            )
            self._cleanup_audio(audio_path)
            self.finished.emit(transcript)
            return
        polisher = get_polisher(self.config)
        self.progress.emit(t("status.polishing"))
        refined = polisher.polish(
            transcript,
            context_before=self.context_before,
            context_after=self.context_after,
        )
        logger.info("Processing pipeline finished in %.1fs", time.monotonic() - pipeline_start)
        self._cleanup_audio(audio_path)
        self.finished.emit(refined)

    @staticmethod
    def _cleanup_audio(audio_path: str | None) -> None:
        """Delete the temp audio file once the pipeline has succeeded.

        Called only on success paths (empty transcript, polish disabled, or
        full success) — never on the exception path, where the file is kept
        for retry.
        """
        if audio_path is None:
            return
        try:
            os.remove(audio_path)
        except OSError:
            pass