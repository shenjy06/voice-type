"""Background processing worker — runs save + ASR + LLM polishing off the UI thread."""

import os

from PySide6.QtCore import QObject, Signal

from voicetype.asr import Transcriber
from voicetype.config import AppConfig
from voicetype.glossary import apply_glossary
from voicetype.polisher import TextPolisher


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

    The audio ``recorder`` is saved (OGG/Vorbis encoding) on this background
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
    ):
        super().__init__()
        self.config = config
        self.recorder = recorder
        # Cursor context captured at recording start, used for context-aware
        # polishing. Empty strings fall back to standalone polishing.
        self.context_before = context_before
        self.context_after = context_after

    def run(self):
        try:
            self.started.emit()
            # Encode the captured frames to a temp OGG file on this thread so
            # the (potentially slow) Vorbis encoding never blocks the UI.
            audio_path = str(self.recorder.save())
            transcriber = get_transcriber(self.config)
            transcript = transcriber.transcribe(audio_path)
            # Delete audio file immediately after STT to limit sensitive data on disk.
            try:
                os.remove(audio_path)
            except OSError:
                pass
            if not transcript:
                self.finished.emit("")
                return
            transcript = apply_glossary(transcript, self.config.glossary)
            if not self.config.polish.enabled:
                self.finished.emit(transcript)
                return
            polisher = get_polisher(self.config)
            refined = polisher.polish(
                transcript,
                context_before=self.context_before,
                context_after=self.context_after,
            )
            self.finished.emit(refined)
        except Exception as e:
            self.error.emit(str(e))
