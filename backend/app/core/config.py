from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str = "sqlite+aiosqlite:///data/db.sqlite"
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_API_KEY: str | None = None
    LLM_API_BASE: str | None = None
    IMAGE_GEN_MODEL: str = "gemini-2.5-flash-image-preview"
    IMAGE_GEN_API_KEY: str | None = None
    IMAGE_GEN_API_BASE: str = "https://api.whatai.cc/v1/chat/completions"
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]
    PLUGINS_DIR: str = "plugins"
    TEMPLATES_DIR: str = "templates/worlds"
    SECRET_STORE_DIR: str = "data/secrets"
    PLUGIN_BLOCK_STRICT_CONFLICTS: bool = False
    MAX_LOG_SESSIONS: int = 200
    LOG_TTL_MINUTES: int = 30


settings = Settings()
