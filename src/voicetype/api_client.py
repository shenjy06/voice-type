"""Base API client for OpenAI-compatible services."""

import logging

from openai import OpenAI

logger = logging.getLogger(__name__)


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


def fetch_models(api_key: str, base_url: str, timeout: float = 10) -> list[str]:
    """Fetch available model IDs from an OpenAI-compatible ``/models`` endpoint.

    Returns a sorted list of model ID strings. Raises whatever the SDK raises
    on failure (auth error, network error, etc.) so the caller can surface a
    meaningful message.
    """
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
    response = client.models.list()
    return sorted(m.id for m in response.data)


def warmup_connection(client, *, label: str = "") -> None:
    """Pre-establish TLS via a lightweight ``models.list()`` call.

    The first API call in a session pays a TLS handshake cost (~200-500ms).
    Calling this at startup opens and pools a connection in the SDK's httpx
    client so the first real request skips the handshake.

    ``client`` is an OpenAI-compatible SDK client instance.
    ``label``, if given, is included in the debug log (e.g. "ASR", "Polish").
    Best-effort: any failure is swallowed.
    """
    try:
        client.models.list(timeout=5)
        if label:
            logger.debug("%s connection warmed up", label)
    except Exception:
        pass
