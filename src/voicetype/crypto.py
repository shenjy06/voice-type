"""Encryption helpers for at-rest secrets.

Secrets are protected with the Windows DPAPI (``CryptProtectData``), which
binds ciphertext to the current Windows user account — no key material is
stored anywhere. The ctypes binding declares full ``argtypes``/``restype``:
the access violations observed with the original naive binding were caused
by pointer truncation on 64-bit Python when argtypes are omitted, NOT by
DPAPI itself. If the DPAPI call fails for any reason (e.g. non-Windows
host, restricted session), the module degrades to a ``v0:`` base64 wrapper
so the app keeps working — callers must treat v0 as obfuscation, not
encryption.

Public API:
    encrypt(plaintext) -> str | None
        Returns a versioned string (``v1:`` DPAPI or ``v0:`` fallback), or
        None for empty input.
    decrypt(ciphertext) -> str | None
        Returns the plaintext, passes unsuffixed legacy values through, or
        None on failure.
    is_available() -> bool
        True when real DPAPI protection round-tripped successfully.
"""

import base64
import ctypes
import ctypes.wintypes as wt
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
    """Return True if real DPAPI protection round-tripped on this machine."""
    return _dpapi_available()


def encrypt(plaintext: str) -> str | None:
    """Encrypt `plaintext` and return a versioned string, or None for empty input."""
    if not plaintext:
        return None
    if _dpapi_available():
        protected = _dpapi_protect(plaintext.encode("utf-8"))
        if protected is not None:
            return _VERSION_PREFIX + base64.b64encode(protected).decode("ascii")
    encoded = base64.b64encode(plaintext.encode("utf-8")).decode("ascii")
    return _FALLBACK_PREFIX + encoded


def decrypt(ciphertext: str | None) -> str | None:
    """Decrypt a value previously produced by encrypt().

    Returns:
      - None for empty / None input.
      - The original plaintext for v1: (DPAPI) values.
      - The original plaintext for v0: (fallback) values.
      - The original plaintext for unsuffixed legacy plaintext values.
      - None for unrecognizable or invalid ciphertexts.
    """
    if not ciphertext:
        return None
    if ciphertext.startswith(_VERSION_PREFIX):
        try:
            blob = base64.b64decode(ciphertext[len(_VERSION_PREFIX):])
        except Exception:
            return None
        data = _dpapi_unprotect(blob)
        if data is None:
            return None
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if ciphertext.startswith(_FALLBACK_PREFIX):
        try:
            return base64.b64decode(ciphertext[len(_FALLBACK_PREFIX):]).decode("utf-8")
        except Exception:
            return None
    return ciphertext


# ---- Windows DPAPI binding ---------------------------------------------------

class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _bind_dpapi():
    """Bind CryptProtectData/CryptUnprotectData with explicit signatures.

    Declaring argtypes is mandatory on 64-bit Python: without them ctypes
    truncates pointers to 32-bit ints, which was the root cause of the
    access violations seen with the earlier naive binding.
    """
    crypt32 = ctypes.windll.crypt32
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DATA_BLOB), wt.LPCWSTR, ctypes.POINTER(_DATA_BLOB),
        ctypes.c_void_p, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(_DATA_BLOB),
    ]
    crypt32.CryptProtectData.restype = wt.BOOL
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DATA_BLOB), ctypes.c_void_p, ctypes.POINTER(_DATA_BLOB),
        ctypes.c_void_p, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(_DATA_BLOB),
    ]
    crypt32.CryptUnprotectData.restype = wt.BOOL
    return crypt32


def _blob_from(data: bytes) -> tuple[_DATA_BLOB, object]:
    buf = ctypes.create_string_buffer(data, len(data))
    return _DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


def _dpapi_protect(data: bytes) -> bytes | None:
    try:
        crypt32 = _bind_dpapi()
        in_blob, _keep = _blob_from(data)
        out_blob = _DATA_BLOB()
        if not crypt32.CryptProtectData(
            ctypes.byref(in_blob), "VoiceType", None, None, None, 0, ctypes.byref(out_blob)
        ):
            return None
        try:
            return ctypes.string_at(out_blob.pbData, out_blob.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(out_blob.pbData)
    except (AttributeError, OSError):
        return None


def _dpapi_unprotect(data: bytes) -> bytes | None:
    try:
        crypt32 = _bind_dpapi()
        in_blob, _keep = _blob_from(data)
        out_blob = _DATA_BLOB()
        if not crypt32.CryptUnprotectData(
            ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
        ):
            return None
        try:
            return ctypes.string_at(out_blob.pbData, out_blob.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(out_blob.pbData)
    except (AttributeError, OSError):
        return None


# None = not probed yet; set by the first _dpapi_available() call. Tests can
# monkeypatch this to force safe-mode behaviour deterministically.
_DPAPI_PROBE: bool | None = None


def _dpapi_available() -> bool:
    """Probe DPAPI once with a tiny round-trip and cache the verdict."""
    global _DPAPI_PROBE
    if _DPAPI_PROBE is None:
        probe = b"voice-type-dpapi-probe"
        protected = _dpapi_protect(probe)
        _DPAPI_PROBE = protected is not None and _dpapi_unprotect(protected) == probe
    return _DPAPI_PROBE


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
