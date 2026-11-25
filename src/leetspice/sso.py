"""Single sign-on through Authentik forward auth.

Caddy asks the Authentik outpost about every request and, when it is allowed, copies the outpost's
identity headers onto the request it proxies here. This module turns those headers into a LeetSpice
account (created on first request, keyed by Authentik's stable user id) and derives the role from
the Authentik groups on every request.

Trust: the identity headers are only believed when the request also carries the shared secret that
Caddy adds (`X-Leetspice-Proxy-Secret`). Caddy overwrites that header on every request it proxies,
so a client cannot supply it, and a request that reaches the app any other way has no valid secret.
"""

import hmac
import logging
from dataclasses import dataclass

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import SSO_PASSWORD_MARKER
from .config import Settings
from .models import User

LOGGER = logging.getLogger("leetspice.sso")

PROXY_SECRET_HEADER = "x-leetspice-proxy-secret"
# Only these headers are read; they are exactly the ones Caddy's `copy_headers` lists, so Caddy
# strips any client-supplied copy of them before adding the outpost's values.
UID_HEADER = "x-authentik-uid"
EMAIL_HEADER = "x-authentik-email"
NAME_HEADER = "x-authentik-name"
USERNAME_HEADER = "x-authentik-username"
GROUPS_HEADER = "x-authentik-groups"
# Authentik joins the group names with "|".
GROUPS_SEPARATOR = "|"


class SsoError(Exception):
    """The request must be refused; `status_code` and `message` go to the client."""

    def __init__(self, message: str, status_code: int = 403) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class Identity:
    uid: str
    email: str
    username: str
    name: str
    groups: frozenset[str]


def check_proxy_secret(request: Request, settings: Settings) -> None:
    supplied = request.headers.get(PROXY_SECRET_HEADER, "")
    if not supplied or not hmac.compare_digest(
        supplied.encode(), settings.sso_proxy_secret.encode()
    ):
        raise SsoError("This application is only reachable through the sign-in proxy.")


def read_identity(request: Request, settings: Settings) -> Identity:
    check_proxy_secret(request, settings)
    uid = request.headers.get(UID_HEADER, "").strip()
    email = request.headers.get(EMAIL_HEADER, "").strip().lower()
    if not uid or len(uid) > 255:
        raise SsoError("Missing sign-in identity.")
    if email.count("@") != 1 or email.startswith("@") or email.endswith("@") or len(email) > 320:
        raise SsoError("Your account has no usable email address. Ask an administrator.")
    username = request.headers.get(USERNAME_HEADER, "").strip()[:150]
    name = request.headers.get(NAME_HEADER, "").strip()
    groups = frozenset(
        g.strip()
        for g in request.headers.get(GROUPS_HEADER, "").split(GROUPS_SEPARATOR)
        if g.strip()
    )
    return Identity(uid=uid, email=email, username=username, name=name, groups=groups)


def _display_name(identity: Identity) -> str:
    local = identity.email.split("@")[0]
    return (identity.name or identity.username or local).strip()[:80] or local[:80]


def _apply(user: User, identity: Identity, settings: Settings) -> None:
    """Copy identity and role onto the user; only touches attributes that actually differ."""
    values = {
        "authentik_uid": identity.uid,
        "authentik_username": identity.username or None,
        "email": identity.email,
        "display_name": _display_name(identity),
        "is_admin": settings.sso_admin_group in identity.groups,
        "is_tester": settings.sso_tester_group in identity.groups,
    }
    for attribute, value in values.items():
        if getattr(user, attribute) != value:
            setattr(user, attribute, value)


def _find_or_create(db: Session, identity: Identity, settings: Settings) -> User:
    user = db.scalar(select(User).where(User.authentik_uid == identity.uid))
    if user is None:
        # First sign-in of this Authentik user: link an existing account only by an exact
        # (case-insensitive) email match that has no Authentik user yet.
        by_email = db.scalar(select(User).where(func.lower(User.email) == identity.email))
        if by_email is not None:
            if by_email.authentik_uid is not None:
                raise SsoError(
                    "Another account already uses your email address. Ask an administrator.",
                    status_code=409,
                )
            user = by_email
        else:
            user = User(email=identity.email, display_name="", password_hash=SSO_PASSWORD_MARKER)
            db.add(user)
    else:
        other = db.scalar(
            select(User.id).where(func.lower(User.email) == identity.email, User.id != user.id)
        )
        if other is not None:
            raise SsoError(
                "Another account already uses your email address. Ask an administrator.",
                status_code=409,
            )
    _apply(user, identity, settings)
    return user


def sync_user(db: Session, identity: Identity, settings: Settings) -> int:
    """Return the id of the LeetSpice user for this identity, creating or updating it."""
    for attempt in (1, 2):
        try:
            user = _find_or_create(db, identity, settings)
            if db.new or db.dirty:
                db.commit()
            return user.id
        except IntegrityError:
            # Two workers created the same new user at once; the retry finds the winner's row.
            db.rollback()
            if attempt == 2:
                LOGGER.exception("could not store the account for Authentik uid %s", identity.uid)
                raise SsoError("Could not store your account.", status_code=500) from None
    raise AssertionError("unreachable")
