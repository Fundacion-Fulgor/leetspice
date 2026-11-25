"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    database_url: str = "sqlite:///./leetspice.db"
    secret_key: str = "local-development-key-change-me"
    session_cookie: str = "leetspice_session"
    session_max_age: int = 60 * 60 * 24 * 14
    secure_cookies: bool = False
    seed_demo: bool = True
    challenges_path: str = "challenges"

    # Database connection pool tuning for production scalability
    db_pool_size: int = 20
    db_max_overflow: int = 10
    db_pool_recycle: int = 1800
    db_pool_timeout: int = 30

    # Rate limiting configuration (per IP)
    rate_limit_default: str = "120/minute"
    rate_limit_auth: str = "10/minute"
    rate_limit_submission: str = "20/minute"

    # Single sign-on through Authentik forward auth (Caddy). When enabled, accounts and roles come
    # only from the headers Caddy copies from the Authentik outpost's response, and the local
    # sign-up / password login is switched off. Requests must carry the shared proxy secret.
    sso_enabled: bool = False
    sso_proxy_secret: str = ""
    # Members of these Authentik groups become LeetSpice admins / testers (on every request).
    sso_admin_group: str = "leetspice-admin"
    sso_tester_group: str = "leetspice-tester"
    # Where "Log out" goes: Caddy proxies this path to the Authentik outpost.
    sso_logout_url: str = "/outpost.goauthentik.io/sign_out"

    @model_validator(mode="after")
    def _sso_needs_a_proxy_secret(self) -> "Settings":
        if self.sso_enabled and len(self.sso_proxy_secret) < 16:
            raise ValueError("SSO_ENABLED requires SSO_PROXY_SECRET (at least 16 characters)")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
