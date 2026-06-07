from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Spotify OAuth
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    spotify_redirect_uri: str = "http://127.0.0.1:8000/api/music/spotify/callback"

    # Google OAuth for YouTube Music
    google_client_id: str = ""
    google_client_secret: str = ""
    ytmusic_redirect_uri: str = "http://127.0.0.1:8000/api/music/ytmusic/callback"

    # Security — required; no defaults so startup fails loudly if missing
    token_encryption_key: str
    secret_key: str

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@postgres:5432/musicsync"

    # Redis / Celery
    redis_url: str = "redis://redis:6379/0"
    celery_concurrency: int = 4

    # Sync
    track_match_threshold: int = 85  # rapidfuzz WRatio minimum (0–100)

    # Frontend URL — used for post-OAuth redirects
    frontend_url: str = "http://localhost"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
