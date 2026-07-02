"""Network connectivity check with multiple probe endpoints.

Probes are issued **in parallel** and the first success wins, so the worst
case is a single probe's timeout (not the sum of all of them). Each probe
only fetches response headers — `urlopen` returns once headers are received
and the body is never read — keeping the check lightweight.
"""

import logging
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

# Probe endpoints ordered by preference. The checker issues all of them in
# parallel and returns True on the first success. This provides resilience
# for users in different regions (e.g., China, US, EU).
PROBE_URLS = [
    "https://www.baidu.com",
    "https://www.google.com/generate_204",
    "https://one.one.one.one",
]

# Default per-probe timeout. Because probes run concurrently, this is also
# the overall worst-case wait when fully offline (previously 3 × 3s = 9s
# when probed sequentially).
DEFAULT_TIMEOUT_MS = 2000

# Shared executor — threads are bounded to len(PROBE_URLS) and reused across
# saves instead of being created + destroyed on every call.
_executor = ThreadPoolExecutor(max_workers=len(PROBE_URLS))


def _probe(url: str, timeout: float) -> bool:
    """Return True if the URL responds with any HTTP status within timeout.

    Uses HEAD where possible (lighter than GET — no body transfer) for the
    generic endpoints; ``generate_204`` already returns an empty body so the
    method doesn't matter for it.
    """
    try:
        request = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(request, timeout=timeout):
            return True
    except (OSError, urllib.error.URLError):
        return False


def check_network_available(timeout_ms: int = DEFAULT_TIMEOUT_MS) -> bool:
    """Return True if any HTTP probe succeeds within the timeout.

    Probes run in parallel and the function returns as soon as the FIRST one
    succeeds — it does NOT wait for the others. This matters for users behind
    region-level firewalls (e.g. China, where baidu responds in ~50ms but
    google/cloudflare time out for the full window): a naive
    ``ThreadPoolExecutor`` context manager would block on ``shutdown(wait=True)``
    until every probe finished, defeating the early return.

    Returns False only when every probe has failed (or timed out), which takes
    at most ``timeout_ms`` since the probes are concurrent.
    """
    timeout = timeout_ms / 1000.0
    start = time.monotonic()
    futures = [_executor.submit(_probe, url, timeout) for url in PROBE_URLS]
    try:
        for future in as_completed(futures):
            if future.result():
                logger.debug(
                    "Network check passed in %.0f ms",
                    (time.monotonic() - start) * 1000,
                )
                return True
        logger.warning(
            "Network check failed — all %d probes timed out (%.0f ms)",
            len(PROBE_URLS),
            (time.monotonic() - start) * 1000,
        )
        return False
    finally:
        # Best-effort: cancel any probe that hasn't started yet. Note that
        # Future.cancel() only succeeds for PENDING futures — a probe already
        # executing its blocking urlopen() will run to its timeout regardless;
        # those threads are daemon-style and cleaned up at process exit.
        for future in futures:
            future.cancel()
