"""Background processing worker — runs ASR + LLM polishing off the UI thread."""

import os

from PySide6.QtCore import QObject, Signal

from voicetype.asr import Transcriber
from voicetype.config import AppConfig
from voicetype.glossary import apply_glossary
from voicetype.polisher import TextPolisher


class ProcessingWorker(QObject):
    """Runs transcribe -> glossary -> polish pipeline and emits signals.

    Signals:
        started()    — emitted before any work begins
        finished(str)— emitted with the refined text (empty string for no transcript)
        error(str)   — emitted on any failure, with a string error message
    """

    started = Signal()
    finished = Signal(str)  # refined text
    error = Signal(str)

    def __init__(self, config: AppConfig, audio_path: str):
        super().__init__()
        self.config = config
        self.audio_path = audio_path

    def run(self):
        try:
            self.started.emit()
            transcriber = Transcriber(self.config)
            transcript = transcriber.transcribe(self.audio_path)
            # Delete audio file immediately after STT to limit sensitive data on disk.
            try:
                os.remove(self.audio_path)
            except OSError:
                pass
            if not transcript:
                self.finished.emit("")
                return
            transcript = apply_glossary(transcript, self.config.glossary)
            if not self.config.polish.enabled:
                self.finished.emit(transcript)
                return
            polisher = TextPolisher(self.config)
            refined = polisher.polish(transcript)
            self.finished.emit(refined)
        except BaseException as e:
            self.error.emit(str(e))
