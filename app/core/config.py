"""Application configuration — loaded from environment variables."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Central config, auto-loaded from .env or Railway env vars."""

    # --- App ---
    app_name: str = "ModellenWerk Workforce Intelligence API"
    app_version: str = "0.1.0"
    environment: str = "development"
    log_level: str = "INFO"
    port: int = 8000

    # --- Database (Neon Postgres + pgvector) ---
    database_url: str  # postgresql://user:pass@ep-xxx.eu-west-1.aws.neon.tech/neondb?sslmode=require

    # --- AI Providers ---
    anthropic_api_key: str
    voyage_api_key: str

    # --- Security ---
    api_secret_key: str = "dev-secret-change-me"
    architect_api_key: str = "mw-dev-key"

    # --- Embedding ---
    embedding_model: str = "voyage-3"
    embedding_dimensions: int = 1024
    chunk_size: int = 512
    chunk_overlap: int = 50

    # --- Claude ---
    claude_model: str = "claude-sonnet-4-20250514"
    claude_max_tokens: int = 4096

    # --- Monitoring ---
    sentry_dsn: str = ""

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
