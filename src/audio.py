"""Audio recording — start/stop/save OGG via sounddevice."""

import logging
import tempfile
import uuid
from pathlib import Path
import numpy as np
import sounddevice as sd
import soundfile as sf

logger = logging.getLogger(__name__)

TEMP_AUDIO_DIR_NAME = "voice_type"


def _calculate_input_level(indata) -> float:
    """Return a normalized level for float audio input."""
    rms = float(np.sqrt(np.mean(np.square(indata), dtype=np.float64)))
    return min(1.0, rms * 12.0)


def get_default_input_device_name() -> str:
    """Return the current default input device name, or an empty string."""
    try:
        device = sd.query_devices(kind="input")
    except Exception as e:
        logger.warning("Failed to query input device: %s", e)
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
            logger.warning("Failed to start microphone monitor: %s", e)
            return False
        return True

    def stop(self) -> None:
        if not self._stream:
            return
        try:
            self._stream.stop()
            self._stream.close()
        except Exception as e:
            logger.warning("Failed to stop microphone monitor: %s", e)
        finally:
            self._stream = None
            self._input_level = 0.0

    def _callback(self, indata, frames, time_info, status):
        if status:
            logger.debug("Monitor stream status: %s", status)
        self._input_level = _calculate_input_level(indata)


class AudioRecorder:
    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self._recording = False
        self._frames: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._temp_file: Path | None = None
        self._input_level = 0.0

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def audio_path(self) -> Path | None:
        return self._temp_file

    @property
    def input_level(self) -> float:
        """Return the latest normalized microphone level in the range 0.0-1.0."""
        return self._input_level

    def start(self) -> None:
        if self._recording:
            return
        self._frames = []
        self._recording = True
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype=np.float32,
            callback=self._callback,
        )
        self._stream.start()
        logger.info("Recording started")

    def stop(self) -> None:
        if not self._recording:
            return
        self._recording = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        logger.info("Recording stopped")

    def save(self) -> Path:
        if not self._frames:
            raise ValueError("No audio data recorded")
        data = np.concatenate(self._frames)
        tmpdir = Path(tempfile.gettempdir()) / TEMP_AUDIO_DIR_NAME
        tmpdir.mkdir(parents=True, exist_ok=True)
        self._temp_file = tmpdir / f"recording_{uuid.uuid4().hex}.ogg"
        sf.write(str(self._temp_file), data, self.sample_rate, format="OGG", subtype="VORBIS")
        logger.info("Audio saved to %s (%.1f seconds)", self._temp_file, len(data) / self.sample_rate)
        return self._temp_file

    def _callback(self, indata, frames, time_info, status):
        if status:
            logger.debug("Stream status: %s", status)
        if self._recording:
            self._frames.append(indata.copy())
            self._input_level = _calculate_input_level(indata)
        else:
            self._input_level = 0.0

    def cleanup(self) -> None:
        if self._temp_file and self._temp_file.exists():
            try:
                self._temp_file.unlink()
            except OSError:
                pass

    def cancel(self) -> None:
        """Stop recording and delete audio file without processing."""
        if self._recording:
            self.stop()
        if self._temp_file and self._temp_file.exists():
            try:
                self._temp_file.unlink()
                logger.info("Cancelled: deleted audio %s", self._temp_file)
            except OSError as e:
                logger.warning("Failed to delete audio on cancel: %s", e)
        self._temp_file = None
