"""OpenID Connect (Authorization Code + PKCE) login through Authentik."""

import hmac
import logging
import secrets
import threading
import time
from typing import Annotated, Any
from urllib.parse import urlencode

import httpx
from authlib.jose import JsonWebKey, JsonWebToken
from authlib.oauth2.rfc7636 import create_s256_code_challenge
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import OIDC_PASSWORD_MARKER, new_session
from .config import Settings, get_settings
from .db import get_session
from .limiter import limiter
from .models import User
from .web import _context, templates

logger = logging.getLogger(__name__)
router = APIRouter()

SESSION_KEY = "oidc"
CACHE_TTL_SECONDS = 3600
HTTP_TIMEOUT_SECONDS = 10.0
# Only asymmetric signatures: never accept HS* (key confusion) or "none".
ID_TOKEN_ALGORITHMS = ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"]
_jwt = JsonWebToken(ID_TOKEN_ALGORITHMS)

GENERIC_ERROR = "Single sign-on failed. Please try again or use your email and password."

_cache: dict[str, tuple[float, dict[str, Any], dict[str, Any]]] = {}
_cache_lock = threading.Lock()


class OidcError(Exception):
    """Any failure during the OIDC flow; the message is for logs only."""


def _http() -> httpx.Client:
    """HTTP client for IdP calls. Tests replace this to avoid the network."""
    return httpx.Client(timeout=HTTP_TIMEOUT_SECONDS)


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _provider(settings: Settings) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (discovery document, JWKS) for the issuer, cached in-process."""
    issuer = settings.oidc_issuer
    with _cache_lock:
        cached = _cache.get(issuer)
    if cached and cached[0] > time.monotonic():
        return cached[1], cached[2]
    try:
        with _http() as client:
            url = f"{issuer.rstrip('/')}/.well-known/openid-configuration"
            discovery = client.get(url).raise_for_status().json()
            jwks = client.get(discovery["jwks_uri"]).raise_for_status().json()
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise OidcError(f"discovery failed: {type(exc).__name__}") from exc
    with _cache_lock:
        _cache[issuer] = (time.monotonic() + CACHE_TTL_SECONDS, discovery, jwks)
    return discovery, jwks


def _redirect_uri(request: Request, settings: Settings) -> str:
    return settings.oidc_redirect_url or str(request.url_for("oidc_callback"))


def _enabled_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    if not settings.oidc_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return settings


def _failure(request: Request, db: Session, detail: str) -> Response:
    logger.warning("OIDC login failed: %s", detail)
    request.state.session.pop(SESSION_KEY, None)
    return templates.TemplateResponse(
        request,
        "login.html",
        _context(request, db, error=GENERIC_ERROR),
        status_code=status.HTTP_400_BAD_REQUEST,
    )


@router.get("/auth/oidc/login")
@limiter.limit(get_settings().rate_limit_auth)
def oidc_login(request: Request) -> Response:
    settings = _enabled_settings(request)
    try:
        discovery, _ = _provider(settings)
        endpoint = discovery["authorization_endpoint"]
    except (OidcError, KeyError) as exc:
        logger.error("OIDC discovery unavailable: %s", exc)
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    request.state.session[SESSION_KEY] = {"state": state, "nonce": nonce, "verifier": verifier}
    query = urlencode(
        {
            "response_type": "code",
            "client_id": settings.oidc_client_id,
            "redirect_uri": _redirect_uri(request, settings),
            "scope": settings.oidc_scopes,
            "state": state,
            "nonce": nonce,
            "code_challenge": create_s256_code_challenge(verifier),
            "code_challenge_method": "S256",
        }
    )
    return RedirectResponse(f"{endpoint}?{query}", status_code=status.HTTP_302_FOUND)


def _exchange_code(
    settings: Settings, discovery: dict[str, Any], code: str, verifier: str, redirect_uri: str
) -> dict[str, Any]:
    try:
        with _http() as client:
            response = client.post(
                discovery["token_endpoint"],
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "code_verifier": verifier,
                },
                auth=(settings.oidc_client_id, settings.oidc_client_secret),
                headers={"Accept": "application/json"},
            )
            if response.status_code != 200:
                raise OidcError(f"token endpoint returned {response.status_code}")
            tokens = response.json()
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise OidcError(f"token exchange failed: {type(exc).__name__}") from exc
    if not isinstance(tokens, dict) or not isinstance(tokens.get("id_token"), str):
        raise OidcError("token response has no id_token")
    return tokens


def _validate_id_token(
    settings: Settings, jwks: dict[str, Any], id_token: str, nonce: str
) -> dict[str, Any]:
    """Check signature, iss, aud, exp and nonce; return the claims."""
    try:
        claims = _jwt.decode(
            id_token,
            JsonWebKey.import_key_set(jwks),
            claims_options={
                "iss": {"essential": True, "value": settings.oidc_issuer},
                "aud": {"essential": True, "value": settings.oidc_client_id},
                "exp": {"essential": True},
                "sub": {"essential": True},
            },
        )
        claims.validate()
    except Exception as exc:  # authlib raises many JoseError subclasses
        raise OidcError(f"invalid id_token: {type(exc).__name__}") from exc
    token_nonce = claims.get("nonce")
    if not isinstance(token_nonce, str) or not hmac.compare_digest(
        token_nonce.encode(), nonce.encode()
    ):
        raise OidcError("id_token nonce mismatch")
    return dict(claims)


def _userinfo(discovery: dict[str, Any], access_token: str) -> dict[str, Any]:
    endpoint = discovery.get("userinfo_endpoint")
    if not endpoint:
        return {}
    try:
        with _http() as client:
            response = client.get(endpoint, headers={"Authorization": f"Bearer {access_token}"})
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise OidcError(f"userinfo failed: {type(exc).__name__}") from exc
    return data if isinstance(data, dict) else {}


def _groups(claims: dict[str, Any]) -> list[str]:
    groups = claims.get("groups")
    if isinstance(groups, list):
        return [item for item in groups if isinstance(item, str)]
    return []


def _fill_from_userinfo(
    settings: Settings, discovery: dict[str, Any], claims: dict[str, Any], access_token: object
) -> None:
    """Fall back to the userinfo endpoint for claims missing from the ID token."""
    wanted = ["email", "name", "preferred_username"]
    if settings.oidc_admin_group:
        wanted.append("groups")
    missing = [key for key in wanted if not claims.get(key)]
    # name and preferred_username are interchangeable for the display name.
    if claims.get("name") or claims.get("preferred_username"):
        missing = [key for key in missing if key not in ("name", "preferred_username")]
    if not missing or not isinstance(access_token, str):
        return
    extra = _userinfo(discovery, access_token)
    if extra.get("sub") not in (None, claims["sub"]):
        raise OidcError("userinfo subject mismatch")
    for key in missing:
        if extra.get(key):
            claims[key] = extra[key]


def _resolve_user(db: Session, settings: Settings, claims: dict[str, Any]) -> User:
    subject = str(claims["sub"])[:255]
    raw_email = claims.get("email")
    email = raw_email.strip().lower() if isinstance(raw_email, str) else ""

    user = db.scalar(select(User).where(User.oidc_subject == subject))
    if user is None:
        if not email or "@" not in email or len(email) > 320:
            raise OidcError("no usable email claim")
        # The identity provider is first-party (Fundación Fulgor's Authentik), so
        # its email claim is trusted: an existing local account with the same
        # address and no OIDC link yet is linked to this subject.
        user = db.scalar(select(User).where(User.email == email, User.oidc_subject.is_(None)))
        if user is not None:
            user.oidc_subject = subject
        elif db.scalar(select(User.id).where(User.email == email)):
            raise OidcError("email already linked to a different subject")
        else:
            local_part = email.split("@")[0]
            name = claims.get("name") or claims.get("preferred_username") or local_part
            user = User(
                email=email,
                display_name=str(name).strip()[:80] or local_part[:80],
                password_hash=OIDC_PASSWORD_MARKER,
                oidc_subject=subject,
            )
            db.add(user)
    if settings.oidc_admin_group:
        user.is_admin = settings.oidc_admin_group in _groups(claims)
    db.commit()
    return user


@router.get("/auth/oidc/callback", response_model=None)
def oidc_callback(
    request: Request,
    db: Annotated[Session, Depends(get_session)],
    state: str = "",
    code: str = "",
    error: str = "",
) -> Response:
    settings = _enabled_settings(request)
    pending = request.state.session.pop(SESSION_KEY, None)
    if error:
        return _failure(request, db, f"identity provider returned error '{error[:60]}'")
    if (
        not isinstance(pending, dict)
        or not state
        or not hmac.compare_digest(str(pending.get("state", "")).encode(), state.encode())
    ):
        return _failure(request, db, "state mismatch or missing session")
    if not code:
        return _failure(request, db, "missing authorization code")
    try:
        discovery, jwks = _provider(settings)
        tokens = _exchange_code(
            settings, discovery, code, pending["verifier"], _redirect_uri(request, settings)
        )
        claims = _validate_id_token(settings, jwks, tokens["id_token"], pending["nonce"])
        _fill_from_userinfo(settings, discovery, claims, tokens.get("access_token"))
        user = _resolve_user(db, settings, claims)
    except OidcError as exc:
        return _failure(request, db, str(exc))
    request.state.session = new_session(user.id, settings)
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
