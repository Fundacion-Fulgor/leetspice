"""Application configuration loaded from environment variables."""

from functools import lru_cache

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

    # Optional single sign-on via Authentik (OpenID Connect). Enabled only when
    # issuer, client id and client secret are all set.
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_scopes: str = "openid email profile"
    # When set, User.is_admin is synced from the "groups" claim on every OIDC login.
    oidc_admin_group: str = ""
    oidc_button_label: str = "Sign in with Fundación Fulgor"
    # Optional override for the callback URL; defaults to one built from the request.
    oidc_redirect_url: str = ""

    @property
    def oidc_enabled(self) -> bool:
        return bool(self.oidc_issuer and self.oidc_client_id and self.oidc_client_secret)


@lru_cache
def get_settings() -> Settings:
    return Settings()
