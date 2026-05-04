"""Speech-to-text via OpenAI-compatible API."""

import logging
from openai import OpenAI
from voice_type.config import AppConfig

logger = logging.getLogger(__name__)


class Transcriber:
    def __init__(self, config: AppConfig):
        self.config = config
        self._client = OpenAI(
            api_key=config.asr.api_key,
            base_url=config.asr.base_url,
        )

    def transcribe(self, audio_path: str) -> str:
        """Transcribe audio file to text."""
        logger.info("Transcribing audio: %s", audio_path)
        kwargs = {
            "model": self.config.asr.model,
        }
        if self.config.asr.language and self.config.asr.language != "auto":
            kwargs["language"] = self.config.asr.language
        with open(audio_path, "rb") as f:
            response = self._client.audio.transcriptions.create(file=f, **kwargs)
        text = response.text.strip()
        logger.info("Transcription complete: %d chars", len(text))
        return text
