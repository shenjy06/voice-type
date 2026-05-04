"""Audio recording — start/stop/save OGG via sounddevice."""

import logging
import tempfile
from pathlib import Path
from threading import Thread
import numpy as np
import sounddevice as sd
import soundfile as sf

logger = logging.getLogger(__name__)


class AudioRecorder:
    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self._recording = False
        self._frames: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._temp_file: Path | None = None

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def audio_path(self) -> Path | None:
        return self._temp_file

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
        self._temp_file = Path(tempfile.mktemp(suffix=".ogg", prefix="voice_"))
        sf.write(str(self._temp_file), data, self.sample_rate, format="OGG", subtype="VORBIS")
        logger.info("Audio saved to %s (%.1f seconds)", self._temp_file, len(data) / self.sample_rate)
        return self._temp_file

    def _callback(self, indata, frames, time_info, status):
        if status:
            logger.debug("Stream status: %s", status)
        if self._recording:
            self._frames.append(indata.copy())

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
