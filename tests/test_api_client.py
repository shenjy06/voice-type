"""Tests for voicetype.api_client — fetch_models."""

from unittest.mock import MagicMock, patch

from voicetype.api_client import ApiClient, fetch_models


class TestFetchModels:
    def test_returns_sorted_model_ids(self):
        """fetch_models returns a sorted list of model ID strings."""
        mock_client = MagicMock()
        mock_client.models.list.return_value = MagicMock(data=[
            MagicMock(id="whisper-1"),
            MagicMock(id="FunAudioLLM/SenseVoiceSmall"),
            MagicMock(id="gpt-4o"),
        ])
        with patch("voicetype.api_client.OpenAI", return_value=mock_client):
            result = fetch_models("sk-test", "https://api.example.com/v1")

        assert result == [
            "FunAudioLLM/SenseVoiceSmall",
            "gpt-4o",
            "whisper-1",
        ]

    def test_empty_list_when_no_models(self):
        """fetch_models returns an empty list when the provider lists none."""
        mock_client = MagicMock()
        mock_client.models.list.return_value = MagicMock(data=[])
        with patch("voicetype.api_client.OpenAI", return_value=mock_client):
            result = fetch_models("sk-test", "https://api.example.com/v1")

        assert result == []

    def test_passes_credentials_to_client(self):
        """fetch_models builds the OpenAI client with the given key/url."""
        mock_client = MagicMock()
        mock_client.models.list.return_value = MagicMock(data=[])
        with patch("voicetype.api_client.OpenAI", return_value=mock_client) as mock_ctor:
            fetch_models("sk-test", "https://api.example.com/v1", timeout=15)

        mock_ctor.assert_called_once_with(
            api_key="sk-test",
            base_url="https://api.example.com/v1",
            timeout=15,
        )

    def test_propagates_errors(self):
        """fetch_models lets SDK errors propagate to the caller."""
        mock_client = MagicMock()
        mock_client.models.list.side_effect = RuntimeError("auth failed")
        with patch("voicetype.api_client.OpenAI", return_value=mock_client):
            import pytest
            with pytest.raises(RuntimeError, match="auth failed"):
                fetch_models("sk-test", "https://api.example.com/v1")


class TestApiClient:
    def test_client_property_returns_underlying_client(self):
        """ApiClient.client exposes the wrapped OpenAI instance."""
        mock_openai = MagicMock()
        with patch("voicetype.api_client.OpenAI", return_value=mock_openai):
            client = ApiClient(api_key="sk", base_url="https://api.example.com/v1", timeout=42)

        assert client.client is mock_openai
