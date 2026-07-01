"""Speech-to-text via OpenAI-compatible API."""

from voicetype.api_client import ApiClient
from voicetype.config import AppConfig

# Prompt hint for auto-detect mode to improve Chinese-English mixed recognition.
# Whisper uses the prompt parameter as context to bias language detection.
_AUTO_DETECT_PROMPT = "以下是普通话和English混合的句子。"


class Transcriber:
    def __init__(self, config: AppConfig):
        self.config = config
        self._client = ApiClient(
            api_key=config.asr.api_key,
            base_url=config.asr.base_url,
            timeout=30,
        ).client

    def transcribe(self, audio_path: str) -> str:
        """Transcribe audio file to text."""
        kwargs = {
            "model": self.config.asr.model,
        }
        lang = self.config.asr.language
        if lang and lang != "auto":
            kwargs["language"] = lang
        else:
            kwargs["prompt"] = _AUTO_DETECT_PROMPT
        with open(audio_path, "rb") as f:
            response = self._client.audio.transcriptions.create(file=f, **kwargs)
        text = response.text.strip()
        return text
