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


@lru_cache
def get_settings() -> Settings:
    return Settings()
