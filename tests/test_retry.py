"""Tests for voicetype.retry — bounded retry with backoff."""

import pytest

from voicetype.retry import retry_call, _is_retriable


class _Fake:
    """A small hierarchy of fake exceptions matching openai's shape."""

    class APIConnectionError(Exception):
        pass

    class APITimeoutError(Exception):
        pass

    class RateLimitError(Exception):
        pass

    class APIStatusError(Exception):
        def __init__(self, status_code=None):
            self.status_code = status_code

    class InternalServerError(Exception):
        pass


@pytest.fixture
def fake_openai(monkeypatch):
    """Inject a fake `openai` module so retry's lazy import finds it."""
    import sys
    import types

    mod = types.ModuleType("openai")
    mod.APIConnectionError = _Fake.APIConnectionError
    mod.APITimeoutError = _Fake.APITimeoutError
    mod.RateLimitError = _Fake.RateLimitError
    mod.APIStatusError = _Fake.APIStatusError
    mod.InternalServerError = _Fake.InternalServerError
    monkeypatch.setitem(sys.modules, "openai", mod)
    return mod


class TestIsRetriable:
    def test_connection_error_is_retriable(self, fake_openai):
        assert _is_retriable(_Fake.APIConnectionError()) is True

    def test_timeout_is_retriable(self, fake_openai):
        assert _is_retriable(_Fake.APITimeoutError()) is True

    def test_rate_limit_is_retriable(self, fake_openai):
        assert _is_retriable(_Fake.RateLimitError()) is True

    def test_5xx_is_retriable(self, fake_openai):
        assert _is_retriable(_Fake.APIStatusError(503)) is True
        assert _is_retriable(_Fake.APIStatusError(500)) is True

    def test_4xx_is_not_retriable(self, fake_openai):
        assert _is_retriable(_Fake.APIStatusError(401)) is False
        assert _is_retriable(_Fake.APIStatusError(404)) is False

    def test_generic_exception_not_retriable(self, fake_openai):
        assert _is_retriable(ValueError("bad")) is False


class TestRetryCall:
    def test_success_first_try(self, fake_openai):
        calls = []

        def func():
            calls.append(1)
            return "ok"

        assert retry_call(func, sleep=lambda _: None) == "ok"
        assert len(calls) == 1

    def test_retries_then_succeeds(self, fake_openai):
        calls = []

        def func():
            calls.append(1)
            if len(calls) < 3:
                raise _Fake.APIConnectionError("drop")
            return "ok"

        sleeps = []
        assert retry_call(func, sleep=sleeps.append) == "ok"
        assert len(calls) == 3
        # Exponential backoff: 0.5, 1.0
        assert sleeps == [0.5, 1.0]

    def test_non_retriable_propagates_immediately(self, fake_openai):
        calls = []

        def func():
            calls.append(1)
            raise ValueError("permanent")

        with pytest.raises(ValueError):
            retry_call(func, sleep=lambda _: None)
        assert len(calls) == 1  # no retries

    def test_exhausts_attempts_then_raises(self, fake_openai):
        calls = []

        def func():
            calls.append(1)
            raise _Fake.RateLimitError("slow down")

        sleeps = []
        with pytest.raises(_Fake.RateLimitError):
            retry_call(func, max_attempts=3, sleep=sleeps.append)
        assert len(calls) == 3
        assert sleeps == [0.5, 1.0]

    def test_backoff_capped_at_max_delay(self, fake_openai):
        calls = []

        def func():
            calls.append(1)
            raise _Fake.APIConnectionError("drop")

        sleeps = []
        with pytest.raises(_Fake.APIConnectionError):
            retry_call(
                func, max_attempts=5, base_delay=1.0, max_delay=2.5, sleep=sleeps.append
            )
        # Delays: 1.0, 2.0, capped 4.0->2.5, capped 8.0->2.5
        assert sleeps == [1.0, 2.0, 2.5, 2.5]

    def test_passes_args_and_kwargs(self, fake_openai):
        recorded = {}

        def func(a, b, c=0):
            recorded["args"] = (a, b, c)
            return "ok"

        retry_call(func, 1, 2, c=3, sleep=lambda _: None)
        assert recorded["args"] == (1, 2, 3)
