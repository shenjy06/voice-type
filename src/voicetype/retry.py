"""Bounded retry with exponential backoff for transient API failures.

Retries the subset of OpenAI SDK errors that are worth retrying on a
dictation tool: connection/timeout failures (the request never landed) and
rate-limit (429) / server (5xx) responses. Non-retriable errors (4xx
auth/bad-request) propagate immediately so the user gets fast feedback.
"""

import logging
import time

logger = logging.getLogger(__name__)

# Defaults tuned for a dictation tool: a few quick retries, capped total wait.
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BASE_DELAY = 0.5  # seconds; doubled each attempt, capped
DEFAULT_MAX_DELAY = 4.0  # seconds


def _is_retriable(exc: BaseException) -> bool:
    """Return True for transient errors worth retrying."""
    # openai is imported lazily so this module stays importable even if the
    # SDK isn't present (e.g. in minimal test environments).
    try:
        import openai
    except Exception:
        return False

    if isinstance(exc, (openai.APIConnectionError, openai.APITimeoutError)):
        return True
    if isinstance(exc, openai.RateLimitError):
        return True
    # Server errors (5xx). APIStatusError carries .status_code for non-stream
    # calls; for streaming/other paths fall back to retrying the whole class.
    if isinstance(exc, openai.APIStatusError):
        status = getattr(exc, "status_code", None)
        if status is not None:
            return status >= 500
        return True
    # Older SDK aliases still seen in the wild.
    if isinstance(exc, getattr(openai, "InternalServerError", ())):
        return True
    return False


def retry_call(
    func,
    *args,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    sleep=time.sleep,
    **kwargs,
):
    """Call ``func(*args, **kwargs)`` with retries on transient errors.

    Non-retriable exceptions propagate immediately. Retries use exponential
    backoff (base_delay, 2×, 4×, …) capped at ``max_delay``. Returns the
    func's return value on success.
    """
    last_exc = None
    for attempt in range(1, max_attempts + 1):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            if not _is_retriable(exc) or attempt >= max_attempts:
                raise
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            logger.warning(
                "Transient API error (attempt %d/%d): %s — retrying in %.1fs",
                attempt,
                max_attempts,
                exc,
                delay,
            )
            sleep(delay)
    # Unreachable: the loop either returns or raises. Kept for safety.
    raise last_exc  # pragma: no cover
