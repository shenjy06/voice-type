"""Audio recording — start/stop/save OGG via sounddevice."""

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
    for f in tmpdir.glob("recording_*.ogg"):
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


class MicrophoneMonitor:
    """Lightweight microphone level monitor for settings diagnostics."""

    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
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
    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self._recording = False
        self._frames: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._temp_file: Path | None = None
        self._input_level = 0.0
        self._lock = threading.Lock()
        self._temp_dir = Path(tempfile.gettempdir()) / TEMP_AUDIO_DIR_NAME
        self._temp_dir.mkdir(parents=True, exist_ok=True)
        _tighten_dir_permissions(self._temp_dir)

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

        duration_ms = len(data) / self.sample_rate * 1000
        temp_file = self._temp_dir / f"recording_{uuid.uuid4().hex}.ogg"
        try:
            sf.write(str(temp_file), data, self.sample_rate, format="OGG", subtype="VORBIS")
        except Exception as e:
            logger.error("Failed to save audio: %s", e, exc_info=True)
            raise ValueError(f"Failed to save audio: {e}") from e

        with self._lock:
            self._temp_file = temp_file
        logger.info(
            "Audio saved: %s (%.1f s, %d frames)",
            temp_file.name,
            duration_ms / 1000,
            len(frames),
        )
        return self._temp_file

    def _callback(self, indata, frames, time_info, status):
        # Do the (CPU) level computation and the array copy OUTSIDE the lock —
        # they don't touch shared mutable state. Only the list append and the
        # level write need the lock, so we hold it for the minimum span.
        level = _calculate_input_level(indata)
        frame = indata.copy()
        with self._lock:
            if self._recording:
                self._frames.append(frame)
                self._input_level = level
            else:
                self._input_level = 0.0

    def cleanup(self) -> None:
        temp_file = self._temp_file
        self._temp_file = None
        if temp_file and temp_file.exists():
            try:
                temp_file.unlink()
                logger.debug("Cleaned up audio file: %s", temp_file.name)
            except OSError as e:
                logger.warning("Failed to clean up audio file %s: %s", temp_file.name, e)

    def cancel(self) -> None:
        """Stop recording and delete audio file without processing."""
        if self._recording:
            self.stop()
        temp_file = self._temp_file
        self._temp_file = None
        if temp_file and temp_file.exists():
            try:
                temp_file.unlink()
                logger.info("Recording cancelled, deleted: %s", temp_file.name)
            except OSError as e:
                logger.warning("Failed to delete cancelled audio %s: %s", temp_file.name, e)
