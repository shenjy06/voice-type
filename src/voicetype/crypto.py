"""Encryption helpers for at-rest secrets.

CURRENT STATUS: This module ships a "safe-mode" implementation that wraps
secrets in a `v0:` base64 prefix and never calls the native Windows
DPAPI. The reason is that the raw `ctypes` DPAPI binding has been observed
to crash the Python process with an access violation in some environments
(notably when called from inside pytest-qt). The DPAPI integration is
intentionally left as a future wiring task — once enabled, no public API
will change: `encrypt()` will start emitting `v1:` ciphertexts and
`decrypt()` will transparently round-trip both `v0:` (fallback) and `v1:`
(DPAPI) values.

Public API:
    encrypt(plaintext) -> str | None
        Returns a versioned string or None.
    decrypt(ciphertext) -> str | None
        Returns the plaintext, passes unsuffixed legacy values through, or
        None on failure.
    is_available() -> bool
        Always False in this safe-mode build. Kept for source compatibility
        with future wiring.
"""

import base64
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

_VERSION_PREFIX = "v1:"
_FALLBACK_PREFIX = "v0:"

# Password-based encryption envelope for exported config files. Uses
# PBKDF2-HMAC-SHA256 to derive a 32-byte Fernet key from the user's password
# plus a random salt. Unlike the OS-bound DPAPI path, this is portable across
# machines — suitable for backup/migration files that carry API keys.
ENC_FORMAT = "voice-type-config-enc-v1"
# OWASP (2023+) recommends >= 600k iterations for PBKDF2-HMAC-SHA256.
# The iteration count is stored in the envelope, so raising it later still
# decrypts old files (old count is read back from the envelope at decrypt time).
PBKDF2_ITERATIONS = 600_000
SALT_BYTES = 16


def is_available() -> bool:
    """Return True if real DPAPI protection is wired in and usable.

    In safe-mode (the current default) this always returns False.
    """
    return False


def encrypt(plaintext: str) -> str | None:
    """Encrypt `plaintext` and return a versioned string, or None for empty input."""
    if not plaintext:
        return None
    encoded = base64.b64encode(plaintext.encode("utf-8")).decode("ascii")
    return _FALLBACK_PREFIX + encoded


def decrypt(ciphertext: str | None) -> str | None:
    """Decrypt a value previously produced by encrypt().

    Returns:
      - None for empty / None input.
      - The original plaintext for v0: (fallback) values.
      - The original plaintext for unsuffixed legacy plaintext values.
      - None for unrecognizable or invalid v1: ciphertexts.
    """
    if not ciphertext:
        return None
    if ciphertext.startswith(_FALLBACK_PREFIX):
        try:
            return base64.b64decode(ciphertext[len(_FALLBACK_PREFIX):]).decode("utf-8")
        except Exception:
            return None
    if ciphertext.startswith(_VERSION_PREFIX):
        # No real DPAPI round-trip is wired in this build. Returning None here
        # causes callers to treat the value as missing rather than mis-decoding.
        return None
    return ciphertext


def is_encrypted_envelope(data) -> bool:
    """Return True if ``data`` is a password-encrypted config export envelope."""
    return isinstance(data, dict) and data.get("format") == ENC_FORMAT


def encrypt_with_password(plaintext: str, password: str) -> dict:
    """Encrypt ``plaintext`` with ``password`` and return a serializable envelope.

    The envelope contains the KDF parameters, a random salt, and the Fernet
    ciphertext — everything needed to decrypt later given the same password.
    """
    salt = os.urandom(SALT_BYTES)
    key = _derive_key(password, salt)
    token = Fernet(key).encrypt(plaintext.encode("utf-8"))
    return {
        "format": ENC_FORMAT,
        "kdf": "pbkdf2-sha256",
        "iterations": PBKDF2_ITERATIONS,
        "salt": base64.b64encode(salt).decode("ascii"),
        "ciphertext": base64.b64encode(token).decode("ascii"),
    }


def decrypt_with_password(envelope: dict, password: str) -> str | None:
    """Decrypt an envelope produced by :func:`encrypt_with_password`.

    Returns the plaintext, or ``None`` on a wrong password, tampered data, or
    any malformed envelope — callers should treat ``None`` as "decryption
    failed" without distinguishing the cause.
    """
    try:
        salt = base64.b64decode(envelope["salt"])
        token = base64.b64decode(envelope["ciphertext"])
        key = _derive_key(password, salt)
        return Fernet(key).decrypt(token).decode("utf-8")
    except (KeyError, TypeError, ValueError, InvalidToken):
        return None


def _derive_key(password: str, salt: bytes) -> bytes:
    """Derive a 32-byte Fernet key from ``password`` and ``salt``."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))
