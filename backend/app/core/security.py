"""Password hashing and session tokens.

Passwords are hashed with scrypt (standard library, memory-hard, per-password random salt)
and stored as `scrypt$n$r$p$salt$hash`. The plain password is never stored or logged.

The session token is a compact HMAC-SHA256-signed payload ({sub, iat, exp}) - the same job
a JWT access token does. Every route resolves the user through `get_current_user`
(app/api/deps.py), so swapping the token format later touches only this file.

The token carries only the user id. Role is always re-read from the database,
so a client cannot elevate itself by editing local storage.
"""
import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid

from app.core.config import get_settings
from app.core.errors import NotAuthenticated

TOKEN_VERSION = "v1"
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 1
PASSWORD_MIN_LENGTH = 8


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = _unb64(digest)
        actual = hashlib.scrypt(password.encode(), salt=_unb64(salt), n=int(n), r=int(r), p=int(p), dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# Compared against when the account does not exist, so a wrong username costs the same time as a wrong password.
_DUMMY_HASH: str | None = None


def burn_password_check(password: str) -> None:
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password(secrets.token_urlsafe(16))
    verify_password(password, _DUMMY_HASH)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _sign(payload_b64: str) -> str:
    key = get_settings().signing_key.encode()
    return _b64(hmac.new(key, f"{TOKEN_VERSION}.{payload_b64}".encode(), hashlib.sha256).digest())


def password_version(password_hash: str | None) -> str:
    """Short fingerprint of the stored hash. It is put in the token, so changing or resetting a
    password invalidates every token issued before it."""
    return hashlib.sha256((password_hash or "").encode()).hexdigest()[:12]


def issue_token(user_id: uuid.UUID, password_hash: str | None = None) -> tuple[str, int]:
    settings = get_settings()
    now = int(time.time())
    exp = now + settings.session_ttl_hours * 3600
    payload = _b64(json.dumps({"sub": str(user_id), "iat": now, "exp": exp, "pv": password_version(password_hash)},
                              separators=(",", ":")).encode())
    return f"{TOKEN_VERSION}.{payload}.{_sign(payload)}", exp


def verify_token(token: str) -> tuple[uuid.UUID, str | None]:
    """Returns (user id, password version the token was issued for)."""
    try:
        version, payload, signature = token.split(".")
    except ValueError:
        raise NotAuthenticated("Your session is invalid. Please sign in again.")
    if version != TOKEN_VERSION or not hmac.compare_digest(signature, _sign(payload)):
        raise NotAuthenticated("Your session is invalid. Please sign in again.")
    data = json.loads(_unb64(payload))
    if data.get("exp", 0) < time.time():
        raise NotAuthenticated("Your session has expired. Please sign in again.", code="SESSION_EXPIRED")
    return uuid.UUID(data["sub"]), data.get("pv")
