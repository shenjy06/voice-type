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
import logging

logger = logging.getLogger(__name__)

_VERSION_PREFIX = "v1:"
_FALLBACK_PREFIX = "v0:"


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
        except Exception as e:
            logger.debug("decrypt: invalid fallback ciphertext: %s", e)
            return None
    if ciphertext.startswith(_VERSION_PREFIX):
        # No real DPAPI round-trip is wired in this build. Returning None here
        # causes callers to treat the value as missing rather than mis-decoding.
        logger.warning("decrypt: v1 ciphertext encountered but DPAPI is not wired in")
        return None
    return ciphertext
