"""Password hashing, signed sessions, and CSRF helpers."""

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import HTTPException, Request, Response, status

from .config import Settings

password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def sign_session(payload: dict[str, Any], settings: Settings) -> str:
    body = _encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signature = hmac.new(settings.secret_key.encode(), body.encode(), hashlib.sha256).digest()
    return f"{body}.{_encode(signature)}"


def read_session(request: Request, settings: Settings) -> dict[str, Any]:
    value = request.cookies.get(settings.session_cookie)
    if not value:
        return {}
    try:
        body, supplied_signature = value.split(".", 1)
        expected = hmac.new(settings.secret_key.encode(), body.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _decode(supplied_signature)):
            return {}
        payload = json.loads(_decode(body))
        if not isinstance(payload, dict) or int(payload.get("expires", 0)) < int(time.time()):
            return {}
        return payload
    except (ValueError, TypeError, json.JSONDecodeError):
        return {}


def new_session(user_id: int | None, settings: Settings) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "csrf": secrets.token_urlsafe(32),
        "expires": int(time.time()) + settings.session_max_age,
    }


def set_session_cookie(response: Response, payload: dict[str, Any], settings: Settings) -> None:
    response.set_cookie(
        settings.session_cookie,
        sign_session(payload, settings),
        max_age=settings.session_max_age,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(settings.session_cookie, path="/", httponly=True, samesite="lax")


def require_csrf(request: Request, submitted_token: str) -> None:
    expected = request.state.session.get("csrf", "")
    if not expected or not hmac.compare_digest(expected, submitted_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")
