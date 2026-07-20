"""Tests for voicetype.crypto — at-rest encryption helpers.

Secrets are protected with Windows DPAPI (``v1:`` prefix) when available,
degrading to a base64 wrapper (``v0:`` prefix) otherwise. These tests cover
both paths; safe-mode behaviour is forced by monkeypatching the cached
DPAPI probe (``crypto._DPAPI_PROBE``).
"""

import base64

import pytest

from voicetype import crypto


@pytest.fixture
def safe_mode(monkeypatch):
    """Force the safe-mode (v0: base64) path regardless of DPAPI availability."""
    monkeypatch.setattr(crypto, "_DPAPI_PROBE", False)


@pytest.fixture
def dpapi_mode(monkeypatch):
    """Force the DPAPI path; skipped when DPAPI is genuinely unavailable."""
    monkeypatch.setattr(crypto, "_DPAPI_PROBE", None)
    if not crypto._dpapi_available():
        pytest.skip("DPAPI not available on this machine")


class TestCryptoHelpers:
    def test_encrypt_returns_versioned_string(self):
        out = crypto.encrypt("hello")
        assert out is not None
        assert out.startswith(("v0:", "v1:"))

    def test_encrypt_empty_string_returns_none(self):
        assert crypto.encrypt("") is None

    def test_decrypt_with_empty_or_none_returns_none(self):
        assert crypto.decrypt("") is None
        assert crypto.decrypt(None) is None

    def test_decrypt_passes_through_unsuffixed_values(self):
        """Legacy plaintext values in config files should pass through unchanged."""
        assert crypto.decrypt("plaintext-legacy-value") == "plaintext-legacy-value"

    def test_decrypt_invalid_v1_returns_none(self):
        # Not valid base64 → rejected before ever reaching DPAPI.
        assert crypto.decrypt("v1:!!!not-base64!!!") is None

    def test_encrypt_decrypt_round_trip(self):
        secret = "sk-secret-key-12345"
        out = crypto.encrypt(secret)
        assert out is not None
        # The stored value must differ from the secret...
        assert out != secret
        # ... and round-trip back to the original.
        assert crypto.decrypt(out) == secret

    def test_is_available_matches_probe(self, monkeypatch):
        monkeypatch.setattr(crypto, "_DPAPI_PROBE", False)
        assert crypto.is_available() is False
        monkeypatch.setattr(crypto, "_DPAPI_PROBE", True)
        assert crypto.is_available() is True


class TestSafeMode:
    """v0: base64 fallback path, forced by disabling the DPAPI probe."""

    def test_fallback_format_uses_base64(self, safe_mode):
        secret = "with spaces and unicode 中文"
        out = crypto.encrypt(secret)
        assert out.startswith("v0:")
        encoded = out[len("v0:"):]
        assert base64.b64decode(encoded).decode("utf-8") == secret

    def test_fallback_round_trip(self, safe_mode):
        secret = "sk-fallback-secret"
        out = crypto.encrypt(secret)
        assert crypto.decrypt(out) == secret

    def test_v1_ciphertext_still_decrypted_in_safe_mode(self, safe_mode, monkeypatch):
        """v1: values must decrypt even when the probe is forced off — DPAPI
        unprotect does not depend on the encrypt-side probe."""
        # Produce a real v1 ciphertext first (requires DPAPI), then decrypt
        # with the probe forced to False by the safe_mode fixture.
        monkeypatch.setattr(crypto, "_DPAPI_PROBE", None)
        if not crypto._dpapi_available():
            pytest.skip("DPAPI not available on this machine")
        out = crypto.encrypt("secret-in-v1")
        assert out.startswith("v1:")
        monkeypatch.setattr(crypto, "_DPAPI_PROBE", False)
        assert crypto.decrypt(out) == "secret-in-v1"


class TestDpapiMode:
    """v1: DPAPI path — only runs where DPAPI genuinely works."""

    def test_encrypt_uses_v1_prefix(self, dpapi_mode):
        out = crypto.encrypt("hello")
        assert out.startswith("v1:")

    def test_v1_round_trip(self, dpapi_mode):
        secret = "sk-dpapi-secret-中文"
        out = crypto.encrypt(secret)
        assert crypto.decrypt(out) == secret

    def test_v1_ciphertext_is_not_plaintext_base64(self, dpapi_mode):
        secret = "sk-dpapi-secret"
        out = crypto.encrypt(secret)
        blob = base64.b64decode(out[len("v1:"):])
        assert secret.encode("utf-8") not in blob

    def test_corrupt_v1_returns_none(self, dpapi_mode):
        garbage = base64.b64encode(b"not-a-dpapi-blob").decode("ascii")
        assert crypto.decrypt(f"v1:{garbage}") is None


class TestPasswordEncryption:
    """Password-based (Fernet) encryption for exported config files."""

    def test_encrypt_decrypt_round_trip(self):
        secret = "sk-secret-key-12345"
        envelope = crypto.encrypt_with_password(secret, "p@ssword")
        assert crypto.is_encrypted_envelope(envelope)
        assert envelope["kdf"] == "pbkdf2-sha256"
        assert crypto.decrypt_with_password(envelope, "p@ssword") == secret

    def test_wrong_password_returns_none(self):
        envelope = crypto.encrypt_with_password("secret", "right")
        assert crypto.decrypt_with_password(envelope, "wrong") is None

    def test_empty_password_round_trip(self):
        envelope = crypto.encrypt_with_password("secret", "")
        assert crypto.decrypt_with_password(envelope, "") == "secret"

    def test_tampered_ciphertext_returns_none(self):
        envelope = crypto.encrypt_with_password("secret", "pw")
        envelope = dict(envelope)
        envelope["ciphertext"] = base64.b64encode(b"garbage").decode("ascii")
        assert crypto.decrypt_with_password(envelope, "pw") is None

    def test_is_encrypted_envelope_rejects_plaintext(self):
        assert not crypto.is_encrypted_envelope({"polish": {}})
        assert not crypto.is_encrypted_envelope("not a dict")
        assert crypto.is_encrypted_envelope({"format": crypto.ENC_FORMAT})

    def test_pbkdf2_iterations_meets_owasp_minimum(self):
        # OWASP (2023+) recommends >= 600k iterations for PBKDF2-HMAC-SHA256.
        assert crypto.PBKDF2_ITERATIONS >= 600_000
