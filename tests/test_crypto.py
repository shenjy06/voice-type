"""Tests for voicetype.crypto — at-rest encryption helpers.

The crypto module ships in safe-mode and wraps secrets in a base64-prefixed
string. These tests verify the fallback round-trip plus the contract for
legacy unsuffixed and missing values.
"""

import base64

from voicetype import crypto


class TestCryptoHelpers:
    def test_encrypt_returns_versioned_string(self):
        out = crypto.encrypt("hello")
        assert out is not None
        assert out.startswith("v0:")

    def test_encrypt_empty_string_returns_none(self):
        assert crypto.encrypt("") is None

    def test_decrypt_with_empty_or_none_returns_none(self):
        assert crypto.decrypt("") is None
        assert crypto.decrypt(None) is None

    def test_decrypt_passes_through_unsuffixed_values(self):
        """Legacy plaintext values in config files should pass through unchanged."""
        assert crypto.decrypt("plaintext-legacy-value") == "plaintext-legacy-value"

    def test_decrypt_invalid_v1_returns_none(self):
        # v1: prefix is reserved for DPAPI which is not wired in this build.
        assert crypto.decrypt("v1:garbage") is None

    def test_encrypt_decrypt_round_trip(self):
        secret = "sk-secret-key-12345"
        out = crypto.encrypt(secret)
        assert out is not None
        # Even though it's a fallback, the value should differ from the secret
        assert out != secret
        # ... and round-trip back to the original.
        assert crypto.decrypt(out) == secret

    def test_is_available_is_false_in_safemode(self):
        assert crypto.is_available() is False

    def test_fallback_format_uses_base64(self):
        secret = "with spaces and unicode 中文"
        out = crypto.encrypt(secret)
        assert out.startswith("v0:")
        encoded = out[len("v0:"):]
        assert base64.b64decode(encoded).decode("utf-8") == secret


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
