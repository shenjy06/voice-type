"""Tests for voice_type.polisher — TextPolisher."""

from unittest.mock import MagicMock, patch
from src.polisher import TextPolisher, SYSTEM_PROMPT
from tests.conftest import make_config


def _mock_api_client(mocker, mock_client):
    """Patch ApiClient to return a mock client wrapper."""
    mock_api = MagicMock()
    mock_api.client = mock_client
    return mocker.patch("src.polisher.ApiClient", return_value=mock_api)


class TestTextPolisher:
    def test_polish_returns_refined_text(self, mocker):
        """Normal polish returns the refined text, stripped."""
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = "  Hello, world!  \n"
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_resp
        _mock_api_client(mocker, mock_client)
        cfg = make_config(polish={"api_key": "sk", "base_url": "https://api", "model": "gpt-4o"})
        polisher = TextPolisher(cfg)
        result = polisher.polish("hello world")

        assert result == "Hello, world!"

    def test_polish_uses_system_prompt(self, mocker):
        """SYSTEM_PROMPT is included in the messages."""
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = "ok"
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_resp
        _mock_api_client(mocker, mock_client)
        cfg = make_config(polish={"api_key": "sk", "base_url": "https://api", "model": "gpt-4o"})
        polisher = TextPolisher(cfg)
        polisher.polish("test input")

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        messages = call_kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == SYSTEM_PROMPT

    def test_polish_uses_user_text(self, mocker):
        """User text is passed as the user message."""
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = "refined"
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_resp
        _mock_api_client(mocker, mock_client)
        cfg = make_config(polish={"api_key": "sk", "base_url": "https://api", "model": "gpt-4o"})
        polisher = TextPolisher(cfg)
        polisher.polish("my raw text")

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        messages = call_kwargs["messages"]
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "my raw text"

    def test_polish_temperature_fixed(self, mocker):
        """Temperature is fixed at 0.3."""
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = "ok"
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_resp
        _mock_api_client(mocker, mock_client)
        cfg = make_config(polish={"api_key": "sk", "base_url": "https://api", "model": "gpt-4o"})
        polisher = TextPolisher(cfg)
        polisher.polish("text")

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["temperature"] == 0.3

    def test_polish_uses_config_model(self, mocker):
        """Uses config.polish.model for the API call."""
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = "ok"
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_resp
        _mock_api_client(mocker, mock_client)
        cfg = make_config(polish={"api_key": "sk", "base_url": "https://api", "model": "qwen-plus"})
        polisher = TextPolisher(cfg)
        polisher.polish("text")

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "qwen-plus"

    def test_polish_api_error_propagates(self, mocker):
        """API exceptions bubble up to the caller."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("Rate limited")
        _mock_api_client(mocker, mock_client)
        cfg = make_config(polish={"api_key": "sk", "base_url": "https://api", "model": "gpt-4o"})
        polisher = TextPolisher(cfg)

        try:
            polisher.polish("text")
        except Exception as e:
            assert "Rate limited" in str(e)

    def test_polisher_client_timeout_60(self, mocker):
        """ApiClient is created with timeout=60."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock()
        mock_api = MagicMock()
        mock_api.client = mock_client
        mock_api_cls = mocker.patch("src.polisher.ApiClient", return_value=mock_api)

        cfg = make_config(polish={"api_key": "sk", "base_url": "https://api"})
        TextPolisher(cfg)

        mock_api_cls.assert_called_once_with(api_key="sk", base_url="https://api", timeout=60)

    def test_polish_uses_first_choice(self, mocker):
        """Uses choices[0] from the response."""
        mock_resp = MagicMock()
        mock_resp.choices = [
            MagicMock(message=MagicMock(content="first choice")),
            MagicMock(message=MagicMock(content="second choice")),
        ]
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_resp
        _mock_api_client(mocker, mock_client)
        cfg = make_config(polish={"api_key": "sk", "base_url": "https://api", "model": "gpt-4o"})
        polisher = TextPolisher(cfg)
        result = polisher.polish("text")

        assert result == "first choice"
