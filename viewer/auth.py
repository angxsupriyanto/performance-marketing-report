"""Password check, signed session cookie and login rate limit for the viewer.

One shared password for the internal team (no per-person accounts). The password itself is never stored: only a
scrypt hash, in a Docker secret file. Sessions are stateless HMAC-signed tokens, so restarting the container
does not log anyone out, and rotating the session secret logs everyone out.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 15, 8, 1
SESSION_SECONDS = 12 * 3600
MAX_FAILURES = 5
WINDOW_SECONDS = 5 * 60
MIN_PASSWORD_CHARS = 12


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=32, maxmem=128 * n * r * 2)


def hash_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_CHARS:
        raise ValueError(f"password minimal {MIN_PASSWORD_CHARS} karakter")
    salt = secrets.token_bytes(16)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(_scrypt(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P))}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.strip().split("$")
        if scheme != "scrypt":
            return False
        expected = _unb64(digest)
        actual = _scrypt(password, _unb64(salt), int(n), int(r), int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def new_session(secret: bytes, now: float | None = None) -> tuple[str, str]:
    """Returns (cookie value, csrf token). The csrf token is derived from the session, not stored."""
    expires = int((now if now is not None else time.time()) + SESSION_SECONDS)
    nonce = _b64(secrets.token_bytes(16))
    body = f"{expires}.{nonce}"
    signature = _b64(hmac.new(secret, body.encode(), hashlib.sha256).digest())
    return f"{body}.{signature}", csrf_for(secret, f"{body}.{signature}")


def csrf_for(secret: bytes, cookie: str) -> str:
    return _b64(hmac.new(secret, b"csrf:" + cookie.encode(), hashlib.sha256).digest())


def read_session(secret: bytes, cookie: str | None, now: float | None = None) -> str | None:
    """Returns the csrf token of a valid, unexpired session, otherwise None."""
    if not cookie:
        return None
    try:
        expires, nonce, signature = cookie.split(".")
        expected = _b64(hmac.new(secret, f"{expires}.{nonce}".encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature.encode(), expected.encode()):
            return None
        if int(expires) < (now if now is not None else time.time()):
            return None
    except ValueError:
        return None
    return csrf_for(secret, cookie)


class LoginLimiter:
    """Locks an address for WINDOW_SECONDS after MAX_FAILURES wrong passwords within WINDOW_SECONDS."""

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.failures: dict[str, list[float]] = {}
        self.locked_until: dict[str, float] = {}
        self.lock = threading.Lock()

    def retry_after(self, who: str) -> int:
        with self.lock:
            until = self.locked_until.get(who, 0)
            now = self.clock()
            if until > now:
                return int(until - now) + 1
            self.locked_until.pop(who, None)
            return 0

    def failed(self, who: str) -> None:
        with self.lock:
            now = self.clock()
            recent = [t for t in self.failures.get(who, []) if now - t < WINDOW_SECONDS] + [now]
            self.failures[who] = recent
            if len(recent) >= MAX_FAILURES:
                self.locked_until[who] = now + WINDOW_SECONDS
                self.failures.pop(who, None)
            if len(self.failures) > 5000:  # bound memory under a flood of distinct addresses
                self.failures = {k: v for k, v in self.failures.items() if now - v[-1] < WINDOW_SECONDS}

    def succeeded(self, who: str) -> None:
        with self.lock:
            self.failures.pop(who, None)
