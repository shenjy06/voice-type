"""Base API client for OpenAI-compatible services."""

from openai import OpenAI


class ApiClient:
    """Wraps OpenAI client creation with common defaults."""

    def __init__(self, api_key: str, base_url: str, timeout: float = 60):
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
        )

    @property
    def client(self) -> OpenAI:
        return self._client
