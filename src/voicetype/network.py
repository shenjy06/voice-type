"""Network connectivity check with multiple probe endpoints.

Probes are issued **in parallel** and the first success wins, so the worst
case is a single probe's timeout (not the sum of all of them). Each probe
only fetches response headers — `urlopen` returns once headers are received
and the body is never read — keeping the check lightweight.
"""

import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

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
    executor = ThreadPoolExecutor(max_workers=len(PROBE_URLS))
    futures = [executor.submit(_probe, url, timeout) for url in PROBE_URLS]
    try:
        for future in as_completed(futures):
            if future.result():
                return True
        return False
    finally:
        # Cancel any probes still running (e.g. the slow/blocked ones after a
        # fast success) and shut down WITHOUT waiting for them.
        for future in futures:
            future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
