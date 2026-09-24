"""Background processing worker — runs save + ASR + LLM polishing off the UI thread."""

import logging
import os
import time
import wave

from PySide6.QtCore import QObject, Signal

from voicetype.asr import Transcriber
from voicetype.audio import get_archive_dir
from voicetype.config import AppConfig
from voicetype.glossary import apply_glossary
from voicetype.i18n import t
from voicetype.polisher import TextPolisher
from voicetype.voice_commands import match_voice_command

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
        command_detected(str) — emitted instead of ``finished`` when the
            transcript exactly matches a voice command; carries the action
            (newline/enter/undo/tab/discard). The UI performs the action.
    """

    started = Signal()
    progress = Signal(str)  # stage text, e.g. "转写中..." / "润色中..."
    finished = Signal(str)  # refined text
    error = Signal(str)
    command_detected = Signal(str)  # voice-command action

    def __init__(
        self,
        config: AppConfig,
        recorder=None,
        context_before: str = "",
        context_after: str = "",
        audio_path: str | None = None,
        streaming_transcriber=None,
        skip_polish: bool = False,
    ):
        super().__init__()
        self.config = config
        self.recorder = recorder
        # Cursor context captured at recording start, used for context-aware
        # polishing. Empty strings fall back to standalone polishing.
        self.context_before = context_before
        self.context_after = context_after
        # Raw mode (double-tap gesture): emit the transcript as-is for this
        # cycle, skipping the polish stage even when it is enabled.
        self._skip_polish = skip_polish
        # When set, the worker reuses this existing audio file (retained from
        # a previous failed run) instead of calling recorder.save(). Used by
        # retry; in that case ``recorder`` is not touched.
        self._reused_audio_path = audio_path
        # When set, the worker is in streaming mode — audio was piped to
        # this transcriber during recording; finalize() collects the text.
        self._streaming_transcriber = streaming_transcriber
        # Audio duration for history metadata (from the recorder in normal
        # mode, probed from the WAV header in retry mode, None for streaming).
        self._duration_ms: int | None = None
        # Populated on success when audio archiving is enabled:
        # {"audio_path", "duration_ms", "processing_ms"} — consumed by the
        # controller to attach archive metadata to the history entry.
        self.archive_info: dict | None = None

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
            self._duration_ms = _probe_wav_duration_ms(audio_path)
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
            self._duration_ms = self.recorder.last_duration_ms
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
        """Apply glossary, match voice commands, optionally polish, emit result.

        ``audio_path``, when set, is the temp WAV file that should be deleted
        on success. It is NOT deleted on the error path (the caller retains the
        file for retry), but this method only runs on the success path — errors
        are handled in the per-mode ``_run_*`` methods. Archived files (in the
        audio-archive dir) are never deleted.
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
        # Voice commands run after glossary (so corrections apply) and before
        # polishing (a command phrase must not be rewritten by the LLM).
        if self.config.commands.enabled:
            action = match_voice_command(transcript, self.config.commands.items)
            if action is not None:
                logger.info(
                    "Voice command %r — skipping polish/paste (pipeline %.1fs)",
                    action,
                    time.monotonic() - pipeline_start,
                )
                self._cleanup_audio(audio_path)
                self.command_detected.emit(action)
                return
        if not self.config.polish.enabled or self._skip_polish:
            logger.info(
                "Polishing %s — emitting transcript directly (pipeline %.1fs)",
                "skipped (raw mode)" if self._skip_polish and self.config.polish.enabled else "disabled",
                time.monotonic() - pipeline_start,
            )
            self._capture_archive_info(audio_path, pipeline_start)
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
        self._capture_archive_info(audio_path, pipeline_start)
        self._cleanup_audio(audio_path)
        self.finished.emit(refined)

    def _capture_archive_info(self, audio_path: str | None, pipeline_start: float) -> None:
        """Record archive metadata for the controller to attach to history.

        Only files that live in the audio-archive dir (i.e. saved while
        ``archive_audio`` was on) qualify — temp files are deleted on success
        and would dangle in the history entry.
        """
        if not audio_path or not self.config.recording.archive_audio:
            return
        if not self._is_archived(audio_path):
            return
        self.archive_info = {
            "audio_path": audio_path,
            "duration_ms": self._duration_ms,
            "processing_ms": int((time.monotonic() - pipeline_start) * 1000),
        }

    @staticmethod
    def _is_archived(audio_path: str) -> bool:
        """Return True when ``audio_path`` lives in the audio-archive dir."""
        try:
            return os.path.dirname(os.path.abspath(audio_path)) == os.path.abspath(
                str(get_archive_dir())
            )
        except OSError:
            return False

    @staticmethod
    def _cleanup_audio(audio_path: str | None) -> None:
        """Delete the temp audio file once the pipeline has succeeded.

        Called only on success paths (empty transcript, polish disabled, or
        full success) — never on the exception path, where the file is kept
        for retry. Archived recordings are kept for history replay.
        """
        if audio_path is None:
            return
        if ProcessingWorker._is_archived(audio_path):
            return
        try:
            os.remove(audio_path)
        except OSError:
            pass


def _probe_wav_duration_ms(audio_path: str) -> int | None:
    """Read the duration of a WAV file from its header (stdlib only).

    Used in retry mode, where the recorder (and its last_duration_ms) is no
    longer available. Returns None on any failure — duration is metadata,
    never worth failing the pipeline over.
    """
    try:
        with wave.open(audio_path, "rb") as wf:
            rate = wf.getframerate()
            if rate <= 0:
                return None
            return int(wf.getnframes() / rate * 1000)
    except Exception:
        return None