"""Tests for voice_type.asr — Transcriber."""

from unittest.mock import MagicMock, patch
from voicetype.asr import Transcriber
from tests.conftest import make_config


def _mock_api_client(mocker, mock_client):
    """Patch ApiClient to return a mock client wrapper."""
    mock_api = MagicMock()
    mock_api.client = mock_client
    return mocker.patch("voicetype.asr.ApiClient", return_value=mock_api)


class TestTranscriber:
    def test_transcribe_language_auto(self, mocker):
        """When language='auto', no 'language' kwarg is sent to the API."""
        mock_resp = MagicMock()
        mock_resp.text = "hello world"
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = mock_resp
        mocker.patch("builtins.open", mocker.mock_open(read_data=b"audio"))
        _mock_api_client(mocker, mock_client)
        cfg = make_config(asr={"language": "auto", "model": "whisper-1", "api_key": "sk", "base_url": "https://api"})
        transcriber = Transcriber(cfg)
        result = transcriber.transcribe("/path/to/audio.wav")

        call_kwargs = mock_client.audio.transcriptions.create.call_args[1]
        assert "language" not in call_kwargs
        assert call_kwargs["model"] == "whisper-1"
        assert result == "hello world"

    def test_transcribe_language_zh(self, mocker):
        """When language='zh', language='zh' is sent to the API."""
        mock_resp = MagicMock()
        mock_resp.text = "你好"
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = mock_resp
        mocker.patch("builtins.open", mocker.mock_open(read_data=b"audio"))
        _mock_api_client(mocker, mock_client)
        cfg = make_config(asr={"language": "zh", "model": "whisper-1", "api_key": "sk", "base_url": "https://api"})
        transcriber = Transcriber(cfg)
        transcriber.transcribe("/path/to/audio.wav")

        call_kwargs = mock_client.audio.transcriptions.create.call_args[1]
        assert call_kwargs["language"] == "zh"

    def test_transcribe_language_various(self, mocker):
        """Various non-auto language codes are passed through."""
        for lang in ["en", "ja", "ko", "fr", "de", "es"]:
            mock_resp = MagicMock()
            mock_resp.text = f"test {lang}"
            mock_client = MagicMock()
            mock_client.audio.transcriptions.create.return_value = mock_resp
            mocker.patch("builtins.open", mocker.mock_open(read_data=b"audio"))
            _mock_api_client(mocker, mock_client)
            cfg = make_config(asr={"language": lang, "model": "whisper-1", "api_key": "sk", "base_url": "https://api"})
            transcriber = Transcriber(cfg)
            transcriber.transcribe("/path/to/audio.wav")

            call_kwargs = mock_client.audio.transcriptions.create.call_args[1]
            assert call_kwargs["language"] == lang

    def test_transcribe_strips_response(self, mocker):
        """Response text is stripped of leading/trailing whitespace."""
        mock_resp = MagicMock()
        mock_resp.text = "  hello world  \n"
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = mock_resp
        mocker.patch("builtins.open", mocker.mock_open(read_data=b"audio"))
        _mock_api_client(mocker, mock_client)
        cfg = make_config(asr={"api_key": "sk", "base_url": "https://api"})
        transcriber = Transcriber(cfg)
        result = transcriber.transcribe("/path/to/audio.wav")

        assert result == "hello world"

    def test_transcribe_opens_file_in_binary_mode(self, mocker):
        """The audio file is opened in binary read mode."""
        mock_resp = MagicMock()
        mock_resp.text = "text"
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = mock_resp
        mock_open_func = mocker.patch("builtins.open", mocker.mock_open(read_data=b"audio"))
        _mock_api_client(mocker, mock_client)
        cfg = make_config(asr={"api_key": "sk", "base_url": "https://api"})
        transcriber = Transcriber(cfg)
        transcriber.transcribe("/path/to/audio.wav")

        mock_open_func.assert_called_once_with("/path/to/audio.wav", "rb")

    def test_transcribe_api_error_propagates(self, mocker):
        """API exceptions bubble up to the caller."""
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.side_effect = Exception("API rate limit exceeded")
        mocker.patch("builtins.open", mocker.mock_open(read_data=b"audio"))
        _mock_api_client(mocker, mock_client)
        cfg = make_config(asr={"api_key": "sk", "base_url": "https://api"})
        transcriber = Transcriber(cfg)

        try:
            transcriber.transcribe("/path/to/audio.wav")
        except Exception as e:
            assert "API rate limit" in str(e)

    def test_transcriber_uses_config_api_key_and_base_url(self, mocker):
        """Transcriber creates ApiClient with config.asr.api_key and base_url."""
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = MagicMock(text="x")
        mock_api = MagicMock()
        mock_api.client = mock_client
        mock_api_cls = mocker.patch("voicetype.asr.ApiClient", return_value=mock_api)

        cfg = make_config(asr={"api_key": "my-key", "base_url": "https://my-api.com/v1"})
        Transcriber(cfg)

        mock_api_cls.assert_called_once_with(api_key="my-key", base_url="https://my-api.com/v1", timeout=30)
