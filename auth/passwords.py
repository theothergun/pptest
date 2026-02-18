from __future__ import annotations

import base64
import hashlib
import hmac
import os


_ALGO = "pbkdf2_sha256"
_DEFAULT_ITERATIONS = 210_000


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(raw: str) -> bytes:
    pad = "=" * ((4 - (len(raw) % 4)) % 4)
    return base64.urlsafe_b64decode((raw + pad).encode("ascii"))


def is_password_hash(value: str) -> bool:
    value = str(value or "")
    return value.startswith(f"{_ALGO}$")


def hash_password(password: str, *, iterations: int = _DEFAULT_ITERATIONS) -> str:
    password = str(password or "")
    if not password:
        raise ValueError("password must not be empty")

    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
    return f"{_ALGO}${int(iterations)}${_b64e(salt)}${_b64e(digest)}"


def verify_password(password: str, stored_value: str) -> bool:
    password = str(password or "")
    stored_value = str(stored_value or "")
    if not stored_value:
        return False

    if not is_password_hash(stored_value):
        # Backward compatibility for legacy plain-text values.
        return hmac.compare_digest(password, stored_value)

    try:
        algo, iter_raw, salt_raw, digest_raw = stored_value.split("$", 3)
        if algo != _ALGO:
            return False
        iterations = int(iter_raw)
        salt = _b64d(salt_raw)
        expected = _b64d(digest_raw)
    except Exception:
        return False

    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)
