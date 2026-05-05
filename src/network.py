"""Network connectivity check with multiple probe endpoints."""

import logging
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

# Probe endpoints ordered by preference. The checker tries each in sequence
# and returns True on the first success. This provides resilience for users
# in different regions (e.g., China, US, EU).
PROBE_URLS = [
    "https://www.baidu.com",
    "https://www.google.com/generate_204",
    "https://one.one.one.one",
]


def check_network_available(timeout_ms: int = 3000) -> bool:
    """Return True if any HTTP probe succeeds within timeout.

    Tries multiple endpoints in order to handle regional connectivity
    differences (e.g., baidu.com for China, google.com for rest of world).
    """
    timeout = timeout_ms / 1000.0
    for url in PROBE_URLS:
        try:
            urllib.request.urlopen(url, timeout=timeout)
            return True
        except (OSError, urllib.error.URLError) as e:
            logger.debug("Probe failed: %s (%s)", url, e)
    return False
