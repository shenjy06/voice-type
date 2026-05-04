"""Network connectivity check."""

import urllib.request


def check_network_available(timeout_ms: int = 3000) -> bool:
    """Return True if a lightweight HTTP probe succeeds within timeout."""
    try:
        urllib.request.urlopen(
            "https://www.baidu.com", timeout=timeout_ms / 1000.0
        )
        return True
    except (OSError, urllib.error.URLError):
        return False
