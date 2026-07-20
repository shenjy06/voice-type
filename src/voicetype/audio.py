"""Audio recording — start/stop/save WAV via sounddevice."""

import logging
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

from voicetype.denoise import denoise

logger = logging.getLogger(__name__)

# Use a leading dot prefix on POSIX and the Windows hidden attribute on Windows
# to discourage other users on a shared box from browsing recordings.
TEMP_AUDIO_DIR_NAME = ".voice_type"
# Delete temp audio files older than this on startup (1 hour)
STALE_AUDIO_MAX_AGE_SECONDS = 3600


def _tighten_dir_permissions(directory: Path) -> None:
    """Best-effort restriction of `directory` to the current user.

    On Windows, %TEMP% is already per-user via the user profile layout, so
    this is mostly a defensive no-op; on POSIX we'd use chmod 0o700.
    """
    try:
        if sys.platform == "win32":
            # Mark the directory as hidden so casual browsing ignores it.
            import ctypes
            FILE_ATTRIBUTE_HIDDEN = 0x02
            FILE_ATTRIBUTE_NOT_INDEXED = 0x2000
            attrs = ctypes.windll.kernel32.GetFileAttributesW(str(directory))
            if attrs != ctypes.wintypes.INVALID_HANDLE_VALUE:
                new_attrs = attrs | FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_NOT_INDEXED
                ctypes.windll.kernel32.SetFileAttributesW(str(directory), new_attrs)
        else:
            directory.chmod(0o700)
    except Exception:
        pass


def _calculate_input_level(indata) -> float:
    """Return a normalized level for float audio input."""
    rms = float(np.sqrt(np.mean(np.square(indata), dtype=np.float64)))
    return min(1.0, rms * 12.0)


def cleanup_stale_audio() -> None:
    """Delete old temporary audio files from previous sessions.

    Call this at application startup to clean up files left behind
    by crashes or abnormal exits.
    """
    tmpdir = Path(tempfile.gettempdir()) / TEMP_AUDIO_DIR_NAME
    if not tmpdir.exists():
        return

    _tighten_dir_permissions(tmpdir)
    now = time.time()
    deleted = 0
    for f in tmpdir.glob("recording_*.wav"):
        try:
            age = now - f.stat().st_mtime
            if age > STALE_AUDIO_MAX_AGE_SECONDS:
                f.unlink()
                deleted += 1
        except OSError:
            pass


def get_default_input_device_name() -> str:
    """Return the current default input device name, or an empty string."""
    try:
        device = sd.query_devices(kind="input")
    except Exception:
        return ""
    if isinstance(device, dict):
        return str(device.get("name", ""))
    return str(device)


def list_input_devices() -> list[tuple[int, str]]:
    """Return a list of ``(device_index, device_name)`` for all input-capable audio devices.

    The first entry is always ``(-1, "…")`` representing the system default.
    Returns an empty list on failure.
    """
    try:
        devices = sd.query_devices()
    except Exception:
        return []
    # sd.default.device can raise or be a bare ``-1`` when no default input
    # is configured — resolve defensively so enumeration still works.
    try:
        default_index = int(sd.default.device[0])
    except Exception:
        default_index = -1
    result: list[tuple[int, str]] = []
    default_name = get_default_input_device_name()
    if default_name:
        result.append((-1, f"{default_name} ({_t('settings.mic_device_default')})"))
    for i, dev in enumerate(devices):
        if isinstance(dev, dict):
            if dev.get("max_input_channels", 0) > 0:
                name = str(dev.get("name", f"Device {i}"))
                # Skip adding the default device again under its real index.
                if i == default_index:
                    continue
                result.append((i, name))
        elif hasattr(dev, "max_input_channels") and dev.max_input_channels > 0:
            name = getattr(dev, "name", f"Device {i}")
            if i == default_index:
                continue
            result.append((i, name))
    return result


def _t(key: str) -> str:
    """Lazy translate helper — avoids import-time i18n dependency."""
    try:
        from voicetype.i18n import t
        return t(key)
    except Exception:
        return key


class MicrophoneMonitor:
    """Lightweight microphone level monitor for settings diagnostics."""

    def __init__(self, sample_rate: int = 16000, device: int | None = None):
        self.sample_rate = sample_rate
        self._device = device
        self._stream: sd.InputStream | None = None
        self._input_level = 0.0
        self._error = ""

    @property
    def input_level(self) -> float:
        return self._input_level

    @property
    def error(self) -> str:
        return self._error

    @property
    def is_running(self) -> bool:
        return self._stream is not None

    def start(self) -> bool:
        if self._stream:
            return True
        self._error = ""
        self._input_level = 0.0
        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype=np.float32,
                device=self._device,
                callback=self._callback,
            )
            self._stream.start()
        except Exception as e:
            self._stream = None
            self._error = str(e)
            return False
        return True

    def stop(self) -> None:
        if not self._stream:
            return
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:
            pass
        finally:
            self._stream = None
            self._input_level = 0.0

    def _callback(self, indata, frames, time_info, status):
        self._input_level = _calculate_input_level(indata)


class AudioRecorder:
    """Captures and saves mono audio via sounddevice InputStream.

    Audio is recorded as float32 via a callback on sounddevice's internal
    thread.  The callback only holds ``self._lock`` for the minimum span
    needed to append frames and update the level / VAD state — CPU work
    (level computation, frame copy, PCM conversion) happens outside the
    lock.  Optional features (denoise, VAD, streaming) are gated by
    constructor flags; all are ``False`` by default for backward
    compatibility.

    Public hooks (callbacks invoked on the audio thread, receivers must
    marshal to their own thread):
        ``on_silence``       — no arguments; VAD silence threshold reached
        ``on_audio_chunk``   — ``bytes`` of 16-bit PCM; streaming mode only
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        denoise_enabled: bool = False,
        denoise_strength: str = "medium",
        vad_enabled: bool = False,
        vad_silence_duration_ms: int = 1500,
        vad_threshold: float = 0.02,
        streaming_enabled: bool = False,
        device: int | None = None,
    ):
        self.sample_rate = sample_rate
        self.denoise_enabled = denoise_enabled
        self.denoise_strength = denoise_strength
        self.vad_enabled = vad_enabled
        self.vad_silence_duration_ms = vad_silence_duration_ms
        self.vad_threshold = vad_threshold
        self.streaming_enabled = streaming_enabled
        self.device = device
        self._recording = False
        self._frames: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._temp_file: Path | None = None
        self._input_level = 0.0
        self._lock = threading.Lock()
        self._temp_dir = Path(tempfile.gettempdir()) / TEMP_AUDIO_DIR_NAME
        self._temp_dir.mkdir(parents=True, exist_ok=True)
        _tighten_dir_permissions(self._temp_dir)
        # VAD state — all touched only under self._lock. ``on_silence`` is the
        # cross-thread hook invoked (outside the lock) when silence has
        # persisted past ``vad_silence_duration_ms`` after the first speech.
        self.on_silence = None
        self._vad_speech_detected = False
        self._vad_silence_start: float | None = None
        self._vad_triggered = False
        # Streaming ASR hook — invoked on the audio thread with 16-bit PCM
        # bytes when set. See StreamingTranscriber.
        self.on_audio_chunk = None

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def audio_path(self) -> Path | None:
        return self._temp_file

    @property
    def input_level(self) -> float:
        """Return the latest normalized microphone level in the range 0.0-1.0."""
        with self._lock:
            return self._input_level

    def start(self) -> bool:
        if self._recording:
            return True
        with self._lock:
            self._frames = []
            self._input_level = 0.0
            # Reset VAD so each recording starts fresh — speech not yet
            # detected, no silence timer running, trigger latch cleared.
            self._vad_speech_detected = False
            self._vad_silence_start = None
            self._vad_triggered = False
        # Initialise before the try-block: if sd.InputStream(...) itself raises
        # (e.g. no input device / permission denied), `stream` would otherwise
        # be unbound in the handler and the cleanup check would raise
        # UnboundLocalError, masking the original failure.
        stream = None
        try:
            stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype=np.float32,
                device=self.device,
                callback=self._callback,
            )
            stream.start()
        except Exception as e:
            logger.error("Failed to start recording: %s", e, exc_info=True)
            if stream is not None:
                try:
                    stream.close()
                except Exception:
                    pass
            with self._lock:
                self._recording = False
            return False

        with self._lock:
            self._stream = stream
            self._recording = True
        logger.info("Recording started (sample_rate=%d)", self.sample_rate)
        return True

    def stop(self) -> None:
        if not self._recording:
            return
        with self._lock:
            self._recording = False
            stream = self._stream
            self._stream = None
        if stream:
            try:
                stream.stop()
                stream.close()
            except Exception as e:
                logger.warning("Error stopping audio stream: %s", e)
        logger.info("Recording stopped")

    def save(self) -> Path:
        with self._lock:
            frames = self._frames
            self._frames = []  # release buffer immediately after handing off
        if not frames:
            raise ValueError("No audio data recorded")

        try:
            data = np.concatenate(frames)
        except ValueError as e:
            raise ValueError("Invalid audio data") from e

        # Optional noise suppression — runs on the processing worker
        # thread, so the ~tens-of-ms spectral-gate cost never blocks the
        # UI. ``denoise`` is best-effort and returns the original audio
        # on any failure, so it can never break the save pipeline.
        if self.denoise_enabled:
            data = denoise(data, self.sample_rate, strength=self.denoise_strength)

        duration_ms = len(data) / self.sample_rate * 1000
        # WAV/PCM_16 instead of OGG/Vorbis: libsndfile 1.2.2's Vorbis
        # encoder crashes natively once the clip exceeds ~32 s (bundled)
        # / ~60 s (dev). WAV skips the encoder entirely — PCM is just a
        # raw byte copy, so it cannot crash regardless of duration. The
        # larger file (~1 MB per 33 s vs ~185 KB for OGG) is well within
        # ASR providers' upload limits.
        temp_file = self._temp_dir / f"recording_{uuid.uuid4().hex}.wav"
        try:
            sf.write(str(temp_file), data, self.sample_rate, format="WAV", subtype="PCM_16")
        except Exception as e:
            logger.error("Failed to save audio: %s", e, exc_info=True)
            raise ValueError(f"Failed to save audio: {e}") from e

        with self._lock:
            self._temp_file = temp_file
        logger.info(
            "Audio saved: %s (%.1f s, %d frames, denoise=%s)",
            temp_file.name,
            duration_ms / 1000,
            len(frames),
            self.denoise_strength if self.denoise_enabled else "off",
        )
        return self._temp_file

    def _callback(self, indata, frames, time_info, status):
        # Do the (CPU) level computation, the array copy, AND the timestamp
        # OUTSIDE the lock — they don't touch shared mutable state. Only the
        # list append and the level write need the lock, so we hold it for the
        # minimum span. ``time.monotonic()`` is a system call; calling it
        # under the lock would block the audio thread.
        level = _calculate_input_level(indata)
        frame = indata.copy()
        now = time.monotonic()
        trigger = False
        stream_chunk = False
        with self._lock:
            if self._recording:
                # In streaming mode the frames buffer is not needed — audio
                # is piped to the ASR client in real time and never saved.
                if not self.streaming_enabled:
                    self._frames.append(frame)
                self._input_level = level
                if self._update_vad(level, now):
                    trigger = True
                if self.streaming_enabled:
                    stream_chunk = True
            else:
                self._input_level = 0.0
        # Fire the silence callback OUTSIDE the lock — the receiver (a Qt
        # signal emit) is thread-safe and never touches this lock, but
        # invoking it under the lock would block the audio thread behind
        # whatever the UI thread is doing.
        if trigger and self.on_silence is not None:
            try:
                self.on_silence()
            except Exception:
                logger.warning("VAD silence callback raised", exc_info=True)
        # Stream PCM to the realtime ASR client. ``on_audio_chunk`` is a
        # non-blocking queue put, so the audio callback thread never stalls
        # on network I/O.
        if stream_chunk and self.on_audio_chunk is not None:
            try:
                self.on_audio_chunk(self._to_pcm16(frame))
            except Exception:
                logger.warning("on_audio_chunk callback raised", exc_info=True)

    @staticmethod
    def _to_pcm16(frame: np.ndarray) -> bytes:
        """Convert float32 audio [-1, 1] to 16-bit signed little-endian PCM.

        DashScope's realtime ASR expects raw PCM frames (mono, 16-bit, at the
        configured sample rate) — not a container format like WAV.
        """
        pcm = np.ascontiguousarray(frame * 32767, dtype=np.int16)
        return pcm.tobytes()

    def _update_vad(self, level: float, now: float) -> bool:
        """Advance the VAD state machine; return True to trigger auto-stop.

        Called under self._lock on the audio thread. ``now`` is the current
        ``time.monotonic()`` value, captured OUTSIDE the lock so the system
        call never blocks the critical section.

        Silence is only counted after the first speech has been detected
        (``level >= vad_threshold``), so a pause before the user starts
        talking does not trigger an early stop. Once triggered, the latch
        (``_vad_triggered``) prevents repeat fires until the next ``start()``
        resets it.
        """
        if not self.vad_enabled or self.on_silence is None or self._vad_triggered:
            return False
        if level >= self.vad_threshold:
            self._vad_speech_detected = True
            self._vad_silence_start = None
        elif self._vad_speech_detected:
            if self._vad_silence_start is None:
                self._vad_silence_start = now
            elif (now - self._vad_silence_start) * 1000 >= self.vad_silence_duration_ms:
                self._vad_triggered = True
                return True
        return False

    def take_audio_path(self) -> Path | None:
        """Return _temp_file and clear the reference.

        Ownership of the file transfers to the caller — ``cleanup()`` will no
        longer delete it. Used by the retry flow so the retained audio file
        survives ``recorder.cleanup()`` and can be reprocessed.
        """
        temp_file = self._temp_file
        self._temp_file = None
        return temp_file

    def cleanup(self) -> None:
        temp_file = self._temp_file
        self._temp_file = None
        if temp_file and temp_file.exists():
            try:
                temp_file.unlink()
                logger.debug("Cleaned up audio file: %s", temp_file.name)
            except OSError as e:
                logger.warning("Failed to clean up audio file %s: %s", temp_file.name, e)
