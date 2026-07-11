"""Background processing worker — runs save + ASR + LLM polishing off the UI thread."""

import logging
import os
import time

from PySide6.QtCore import QObject, Signal

from voicetype.asr import Transcriber
from voicetype.config import AppConfig
from voicetype.glossary import apply_glossary
from voicetype.polisher import TextPolisher

logger = logging.getLogger(__name__)


# --- Cached API clients --------------------------------------------------
# Transcriber/TextPolisher each wrap an OpenAI httpx client with its own
# connection pool. Constructing them fresh on every processing cycle pays a
# TLS handshake every time, so we cache one instance per distinct API config
# fingerprint. When the user changes keys/base_url/model, the fingerprint
# changes and the cached client is rebuilt — see ``invalidate_clients``.
_transcriber_cache: dict = {}  # fingerprint -> Transcriber
_polisher_cache: dict = {}     # fingerprint -> TextPolisher


def _asr_fingerprint(config: AppConfig) -> tuple:
    return (
        config.asr.api_key,
        config.asr.base_url,
        config.asr.model,
    )


def _polish_fingerprint(config: AppConfig) -> tuple:
    return (
        config.polish.api_key,
        config.polish.base_url,
        config.polish.model,
    )


def get_transcriber(config: AppConfig) -> Transcriber:
    """Return a cached Transcriber, rebuilding it when the ASR config changes."""
    fp = _asr_fingerprint(config)
    cached = _transcriber_cache.get(fp)
    if cached is None:
        cached = Transcriber(config)
        _transcriber_cache.clear()
        _transcriber_cache[fp] = cached
    return cached


def get_polisher(config: AppConfig) -> TextPolisher:
    """Return a cached TextPolisher, rebuilding it when the polish config changes."""
    fp = _polish_fingerprint(config)
    cached = _polisher_cache.get(fp)
    if cached is None:
        cached = TextPolisher(config)
        _polisher_cache.clear()
        _polisher_cache[fp] = cached
    return cached


def invalidate_clients() -> None:
    """Drop cached clients (e.g. after settings change)."""
    _transcriber_cache.clear()
    _polisher_cache.clear()


class ProcessingWorker(QObject):
    """Runs save -> transcribe -> glossary -> polish and emits signals.

    The audio ``recorder`` is saved (WAV/PCM encoding) on this background
    thread so the encoding cost never blocks the UI thread. The recorder holds
    the captured frames between ``stop()`` and this save; recording cannot
    restart during PROCESSING, so the frames are safe to read here.

    API clients (Transcriber/TextPolisher) are cached across cycles via
    ``get_transcriber``/``get_polisher`` so connection pools are reused.

    Signals:
        started()    — emitted before any work begins
        finished(str)— emitted with the refined text (empty string for no transcript)
        error(str)   — emitted on any failure (incl. save failure), with a message
    """

    started = Signal()
    finished = Signal(str)  # refined text
    error = Signal(str)

    def __init__(
        self,
        config: AppConfig,
        recorder,
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
        # Mutually exclusive with the other two modes.
        self._streaming_transcriber = streaming_transcriber

    def run(self):
        audio_path = None
        pipeline_start = time.monotonic()
        try:
            self.started.emit()
            if self._streaming_transcriber is not None:
                # Streaming mode: audio was piped to the ASR client during
                # recording; finalize to collect the accumulated transcript.
                # No file is saved in this mode.
                transcript = self._streaming_transcriber.finalize()
                logger.info("Streaming transcript finalized in %.1fs: %d chars",
                            time.monotonic() - pipeline_start, len(transcript))
            elif self._reused_audio_path is not None:
                # Retry: reuse the audio file retained from a previous failed
                # run instead of re-encoding from the recorder.
                audio_path = self._reused_audio_path
                logger.debug("Retrying with retained audio: %s", os.path.basename(audio_path))
                transcriber = get_transcriber(self.config)
                transcript = transcriber.transcribe(audio_path)
            else:
                # Encode the captured frames to a temp WAV file on this thread
                # so the (potentially slow) encoding never blocks the UI.
                save_start = time.monotonic()
                audio_path = str(self.recorder.save())
                self.recorder = None  # release reference; buffer freed in save()
                logger.debug("Processing pipeline started: %s", os.path.basename(audio_path))
                logger.info("Audio saved in %.0fms", (time.monotonic() - save_start) * 1000)
                transcriber = get_transcriber(self.config)
                transcript = transcriber.transcribe(audio_path)

            if not transcript:
                logger.info("Transcription returned empty — pipeline finished in %.1fs",
                            time.monotonic() - pipeline_start)
                self._cleanup_audio(audio_path)
                self.finished.emit("")
                return
            transcript = apply_glossary(transcript, self.config.glossary)
            if not self.config.polish.enabled:
                logger.info("Polishing disabled — emitting transcript directly (pipeline %.1fs)",
                            time.monotonic() - pipeline_start)
                self._cleanup_audio(audio_path)
                self.finished.emit(transcript)
                return
            polisher = get_polisher(self.config)
            refined = polisher.polish(
                transcript,
                context_before=self.context_before,
                context_after=self.context_after,
            )
            logger.info("Processing pipeline finished in %.1fs", time.monotonic() - pipeline_start)
            self._cleanup_audio(audio_path)
            self.finished.emit(refined)
        except Exception as e:
            logger.error("Processing pipeline failed: %s", e, exc_info=True)
            # Retain audio_path on failure so the caller can retry without
            # re-recording. The file is NOT deleted here — the caller owns
            # cleanup via the retry-state lifecycle (abandon on new recording
            # / quit; delete on retry success).
            self.error.emit(str(e))

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
